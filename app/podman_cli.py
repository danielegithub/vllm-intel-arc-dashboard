import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, AsyncGenerator

from app.event_broadcaster import EventBroadcaster
from app.logging_config import logger
from app.config import get_config
from app.cache import cache, get_cache, CACHE_KEYS

# Get configuration
config = get_config()

CONTAINER_NAME = config.podman.container_name
IMAGE_NAME = config.podman.image_name
DEFAULT_MODELS_DIR = config.model.models_dir
IMAGE_PULL_TIMEOUT = config.podman.image_pull_timeout
CONTAINER_START_TIMEOUT = config.podman.container_start_timeout
CONTAINER_STOP_TIMEOUT = config.podman.container_stop_timeout

# Thread-safe event broadcaster for real-time system events (image pull progress, etc.)
log_broadcaster = EventBroadcaster()

@cache(ttl_seconds=30)
def scan_models(models_dir: str = None) -> List[Dict]:
    """
    Scans ~/my_models directory for model folders and estimates details.
    Results are cached for 30 seconds to reduce filesystem I/O.
    """
    target_dir = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
    target_dir = target_dir.expanduser().resolve()
    
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        return []

    models = []
    for entry in target_dir.iterdir():
        if entry.is_dir():
            total_size_bytes = 0
            has_config = False
            weights_count = 0
            
            for file in entry.glob("**/*"):
                if file.is_file():
                    total_size_bytes += file.stat().st_size
                    if file.name.lower() in ("config.json", "tokenizer.json"):
                        has_config = True
                    if file.suffix in (".safetensors", ".bin", ".pth", ".pt", ".onnx", ".gguf"):
                        weights_count += 1

            size_gb = round(total_size_bytes / (1024 ** 3), 2)
            models.append({
                "name": entry.name,
                "path": str(entry),
                "size_gb": size_gb,
                "has_config": has_config,
                "weights_count": weights_count
            })

    models.sort(key=lambda m: m["name"].lower())
    return models

def check_image_exists() -> bool:
    """
    Checks if the vLLM Intel Arc container image exists locally in Podman.
    """
    try:
        res = subprocess.run(
            ["podman", "image", "inspect", IMAGE_NAME],
            capture_output=True,
            text=True,
            timeout=5
        )
        return res.returncode == 0
    except Exception:
        return False

async def pull_image() -> Dict:
    """
    Pulls docker.io/intel/vllm:0.17.0-xpu while streaming live progress output to subscribers.
    Timeout is configurable via IMAGE_PULL_TIMEOUT (default: 600 seconds / 10 minutes).
    """
    async def _pull_image_impl():
        try:
            await log_broadcaster.broadcast(f"[PODMAN PULL] Avvio download immagine {IMAGE_NAME}...\n")
            await log_broadcaster.broadcast(f"[PODMAN PULL] Timeout: {IMAGE_PULL_TIMEOUT} seconds\n")
            
            proc = await asyncio.create_subprocess_exec(
                "podman", "pull", IMAGE_NAME,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                decoded_line = line.decode("utf-8", errors="replace")
                await log_broadcaster.broadcast(f"[PODMAN PULL] {decoded_line}")

            await proc.wait()
            if proc.returncode == 0:
                msg = f"Immagine '{IMAGE_NAME}' scaricata ed installata con successo!"
                await log_broadcaster.broadcast(f"[PODMAN PULL SUCCESS] {msg}\n")
                logger.info(msg)
                return {"success": True, "message": msg}
            else:
                msg = f"Errore durante il download dell'immagine {IMAGE_NAME}."
                await log_broadcaster.broadcast(f"[PODMAN PULL ERROR] {msg}\n")
                logger.error(msg)
                return {"success": False, "message": msg}
        except asyncio.CancelledError:
            msg = "Pull immagine cancellato"
            await log_broadcaster.broadcast(f"[PODMAN PULL CANCELLED] {msg}\n")
            logger.warning(msg)
            return {"success": False, "message": msg}
        except Exception as e:
            err_msg = f"Eccezione durante il pull: {str(e)}"
            await log_broadcaster.broadcast(f"[PODMAN PULL ERROR] {err_msg}\n")
            logger.error(err_msg)
            return {"success": False, "message": err_msg}
    
    try:
        return await asyncio.wait_for(_pull_image_impl(), timeout=IMAGE_PULL_TIMEOUT)
    except asyncio.TimeoutError:
        msg = f"Pull immagine timeout after {IMAGE_PULL_TIMEOUT} seconds"
        await log_broadcaster.broadcast(f"[PODMAN PULL TIMEOUT] {msg}\n")
        logger.error(msg)
        return {"success": False, "message": msg}

@cache(ttl_seconds=5)
def get_container_status() -> Dict:
    """
    Checks the status of the vllm-intel-arc Podman container.
    Results are cached for 5 seconds to reduce subprocess calls.
    Call invalidate_container_status_cache() after operations that change state.
    """
    image_downloaded = check_image_exists()
    try:
        res = subprocess.run(
            ["podman", "ps", "-a", "--filter", f"name=^/{CONTAINER_NAME}$", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            containers = json.loads(res.stdout)
            if containers:
                c = containers[0]
                state = c.get("State", "").lower()
                status_str = c.get("Status", "")
                container_id = c.get("Id", "")[:12]
                
                model_name = "Unknown"
                inspect_res = subprocess.run(
                    ["podman", "inspect", CONTAINER_NAME],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if inspect_res.returncode == 0:
                    inspect_data = json.loads(inspect_res.stdout)
                    if inspect_data:
                        mounts = inspect_data[0].get("Mounts", [])
                        for m in mounts:
                            if m.get("Destination") == "/workspace/model":
                                host_src = m.get("Source", "")
                                model_name = Path(host_src).name
                                break

                return {
                    "exists": True,
                    "running": state == "running",
                    "state": state,
                    "status": status_str,
                    "container_id": container_id,
                    "model_name": model_name,
                    "image_downloaded": image_downloaded,
                    "api_url": "http://localhost:8000/v1"
                }
    except Exception as e:
        return {"exists": False, "running": False, "state": "error", "error": str(e), "image_downloaded": image_downloaded}

    return {
        "exists": False,
        "running": False,
        "state": "stopped",
        "status": "Container non creato",
        "container_id": None,
        "model_name": None,
        "image_downloaded": image_downloaded,
        "api_url": "http://localhost:8000/v1"
    }

async def start_container(model_name: str, max_model_len: int = 2048, extra_args: str = "") -> Dict:
    """
    Stops existing container and runs docker.io/intel/vllm:0.17.0-xpu using official Intel Docker parameters.
    Broadcasts progress events to all subscribers.
    Timeout is configurable via CONTAINER_START_TIMEOUT (default: 120 seconds / 2 minutes).
    """
    async def _start_container_impl():
        model_path = DEFAULT_MODELS_DIR / model_name
        if not model_path.exists():
            msg = f"Cartella modello '{model_name}' non trovata in {DEFAULT_MODELS_DIR}"
            logger.error(msg)
            return {"success": False, "message": msg}

        await stop_container()

        # Official Intel vLLM Docker launch configuration
        cmd = [
            "podman", "run", "-d", "--rm", "--replace",
            "--name", CONTAINER_NAME,
            "--net=host",
            "--ipc=host",
            "--privileged",
            "-v", "/dev/dri/by-path:/dev/dri/by-path",
            "--device", "/dev/dri:/dev/dri",
            "-e", "VLLM_WORKER_MULTIPROC_METHOD=spawn",
            "-v", f"{model_path.resolve()}:/workspace/model:ro",
            IMAGE_NAME,
            "vllm", "serve", "/workspace/model",
            "--dtype", str(config.gpu.dtype),
            "--port", "8000",
            "--gpu-memory-utilization", str(config.gpu.memory_utilization),
            "--max-model-len", str(max_model_len)
        ]

        if extra_args and extra_args.strip():
            cmd.extend(extra_args.strip().split())

        try:
            await log_broadcaster.broadcast(f"[CONTAINER START] Avvio container con modello '{model_name}'...\n")
            await log_broadcaster.broadcast(f"[CONTAINER START] Timeout: {CONTAINER_START_TIMEOUT} seconds\n")
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                cid = stdout.decode().strip()[:12]
                msg = f"Container {CONTAINER_NAME} avviato con successo ({cid})"
                await log_broadcaster.broadcast(f"[CONTAINER SUCCESS] {msg}\n")
                logger.info(msg)
                return {
                    "success": True,
                    "message": msg,
                    "container_id": cid,
                    "command": " ".join(cmd)
                }
            else:
                err_msg = stderr.decode().strip()
                msg = f"Impossibile avviare il container: {err_msg}"
                await log_broadcaster.broadcast(f"[CONTAINER ERROR] {msg}\n")
                logger.error(msg)
                return {
                    "success": False,
                    "message": msg,
                    "command": " ".join(cmd)
                }
        except asyncio.CancelledError:
            msg = "Avvio container cancellato"
            await log_broadcaster.broadcast(f"[CONTAINER CANCELLED] {msg}\n")
            logger.warning(msg)
            return {"success": False, "message": msg}
        except Exception as e:
            err_msg = f"Eccezione avvio container: {str(e)}"
            await log_broadcaster.broadcast(f"[CONTAINER ERROR] {err_msg}\n")
            logger.error(err_msg)
            return {"success": False, "message": err_msg}
    
    try:
        result = await asyncio.wait_for(_start_container_impl(), timeout=CONTAINER_START_TIMEOUT)
        # Invalidate status cache after state change
        invalidate_status_cache()
        return result
    except asyncio.TimeoutError:
        msg = f"Container start timeout after {CONTAINER_START_TIMEOUT} seconds"
        await log_broadcaster.broadcast(f"[CONTAINER TIMEOUT] {msg}\n")
        logger.error(msg)
        # Invalidate status cache after potential state change
        invalidate_status_cache()
        return {"success": False, "message": msg}

async def stop_container() -> Dict:
    """
    Stops and removes the vllm-intel-arc container immediately.
    Automatically invalidates status cache after operation.
    """
    try:
        rm_proc = await asyncio.create_subprocess_exec(
            "podman", "rm", "-f", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await rm_proc.communicate()
        
        # Invalidate status cache after state change
        invalidate_status_cache()
        return {"success": True, "message": f"Container {CONTAINER_NAME} arrestato e rimosso."}
    except Exception as e:
        # Invalidate status cache even on error
        invalidate_status_cache()
        return {"success": False, "message": f"Errore durante l'arresto: {str(e)}"}

async def stream_logs() -> AsyncGenerator[str, None]:
    """
    Asynchronously streams logs from podman logs -f vllm-intel-arc AND event broadcaster.
    
    Uses the EventBroadcaster to receive system events (container start, image pull, etc.)
    along with live container logs.
    """
    has_warned_missing = False
    
    # Subscribe to events
    async for msg in log_broadcaster.subscribe():
        yield msg
        
        # Also check for new container logs
        status = get_container_status()
        if status.get("exists") and status.get("running"):
            # Container is running, start streaming logs
            break
        
        # Keep yielding broadcaster messages until container starts
    
    # Once container is running, stream logs combined with broadcaster events
    task_broadcaster = None
    task_container = None
    
    try:
        # Create separate tasks for broadcaster and container logs
        async def broadcast_listener():
            """Listen for broadcast events and yield them"""
            async for msg in log_broadcaster.subscribe():
                yield msg
        
        async def container_listener():
            """Listen for container logs"""
            while True:
                status = get_container_status()
                if not status.get("exists"):
                    yield "[SISTEMA] Container 'vllm-intel-arc' non più disponibile.\n"
                    await asyncio.sleep(2.0)
                    continue
                
                cmd = ["podman", "logs", "-f", "--tail", "50", CONTAINER_NAME]
                try:
                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT
                    )
                    
                    while True:
                        try:
                            line = await asyncio.wait_for(proc.stdout.readline(), timeout=2.0)
                            if not line:
                                break
                            yield line.decode("utf-8", errors="replace")
                        except asyncio.TimeoutError:
                            pass
                except Exception as e:
                    yield f"[LOG STREAM ERROR] {str(e)}\n"
                    await asyncio.sleep(2.0)
        
        # Merge both streams
        broadcast_gen = broadcast_listener()
        container_gen = container_listener()
        
        # Use a queue to merge streams
        merge_queue: asyncio.Queue = asyncio.Queue()
        
        async def broadcast_task():
            try:
                async for msg in broadcast_gen:
                    await merge_queue.put(("broadcast", msg))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Broadcast listener error: {e}")
        
        async def container_task():
            try:
                async for msg in container_gen:
                    await merge_queue.put(("container", msg))
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Container listener error: {e}")
        
        task_broadcaster = asyncio.create_task(broadcast_task())
        task_container = asyncio.create_task(container_task())
        
        while True:
            try:
                source, msg = await asyncio.wait_for(merge_queue.get(), timeout=5.0)
                yield msg
            except asyncio.TimeoutError:
                # Check if container still exists
                status = get_container_status()
                if not status.get("exists"):
                    yield "[SISTEMA] Container 'vllm-intel-arc' arrestato.\n"
                    break
    
    except asyncio.CancelledError:
        logger.debug("Stream logs cancelled")
        raise
    except Exception as e:
        logger.error(f"Stream logs error: {e}")
        yield f"[LOG STREAM ERROR] {str(e)}\n"
    
    finally:
        # Cleanup tasks
        if task_broadcaster and not task_broadcaster.done():
            task_broadcaster.cancel()
            try:
                await task_broadcaster
            except asyncio.CancelledError:
                pass
        if task_container and not task_container.done():
            task_container.cancel()
            try:
                await task_container
            except asyncio.CancelledError:
                pass


# ============================================================================
# CACHE INVALIDATION HELPERS
# ============================================================================

def invalidate_models_cache() -> None:
    """
    Invalidate model metadata cache.
    Call after operations that modify models directory.
    """
    get_cache().invalidate(CACHE_KEYS["models"])
    logger.debug("Models cache invalidated")


def invalidate_status_cache() -> None:
    """
    Invalidate container status cache.
    Call after operations that change container state (start/stop).
    """
    get_cache().invalidate(CACHE_KEYS["status"])
    logger.debug("Container status cache invalidated")


def invalidate_all_cache() -> None:
    """
    Invalidate all caches.
    Use after major changes that affect multiple cache keys.
    """
    get_cache().invalidate(CACHE_KEYS["models"])
    get_cache().invalidate(CACHE_KEYS["status"])
    get_cache().invalidate(CACHE_KEYS["gpu_telemetry"])
    logger.debug("All caches invalidated")
