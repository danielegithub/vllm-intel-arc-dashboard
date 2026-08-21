import os
import json
import asyncio
import subprocess
import shutil
import tempfile
import re
from datetime import datetime, timezone
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
    Scans ~/my_models directory for model folders and extracts rich metadata (config.json, weights).
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
            
            # Read config.json metadata if present
            config_file = entry / "config.json"
            model_type = "unknown"
            architecture = "unknown"
            quant_method = "FP16"
            max_pos_len = 2048
            
            if "awq" in entry.name.lower():
                quant_method = "AWQ"
            elif "gptq" in entry.name.lower():
                quant_method = "GPTQ"
            elif "gguf" in entry.name.lower():
                quant_method = "GGUF"
                
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as cf:
                        cdata = json.load(cf)
                        model_type = cdata.get("model_type", "unknown")
                        archs = cdata.get("architectures", [])
                        if archs:
                            architecture = archs[0]
                        max_pos_len = cdata.get("max_position_embeddings") or cdata.get("seq_length") or 2048
                        if "quantization_config" in cdata:
                            quant_method = cdata["quantization_config"].get("quant_method", quant_method).upper()
                except Exception:
                    pass

            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc).isoformat()

            models.append({
                "name": entry.name,
                "path": str(entry),
                "size_gb": size_gb,
                "size_bytes": total_size_bytes,
                "has_config": has_config,
                "weights_count": weights_count,
                "model_type": model_type,
                "architecture": architecture,
                "quantization": quant_method,
                "max_position_embeddings": max_pos_len,
                "modified_at": mtime
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
    Pulls docker.io/intel/vllm:0.21.0-xpu while streaming live progress output to subscribers.
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
                    "api_url": config.podman.vllm_api_base_url
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
        "api_url": config.podman.vllm_api_base_url
    }

async def start_container(model_name: str, max_model_len: int = 2048, extra_args: str = "") -> Dict:
    """
    Stops existing container and runs docker.io/intel/vllm:0.21.0-xpu using official Intel Docker parameters.
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
        # SEC-1, SEC-2, PERF-2, PERF-4 optimizations
        cmd = [
            "podman", "run", "-d", "--rm", "--replace",
            "--name", CONTAINER_NAME,
            "-p", f"127.0.0.1:{config.podman.vllm_port}:{config.podman.vllm_port}",
            "--ipc=host",
            "--group-add", "keep-groups",
            "-v", "/dev/dri/by-path:/dev/dri/by-path",
            "--device", "/dev/dri:/dev/dri",
            "-e", "VLLM_WORKER_MULTIPROC_METHOD=spawn",
            "-e", "SYCL_CACHE_PERSISTENT=1",
            "-e", "SYCL_CACHE_DIR=/cache/sycl",
            "-e", "NEO_CACHE_PERSISTENT=1",
            "-e", "NEO_CACHE_DIR=/cache/neo",
            "-v", f"{Path.home()}/.cache/vllm-arc:/cache",
            "-v", f"{model_path.resolve()}:/workspace/model:ro",
            IMAGE_NAME,
            "vllm", "serve", "/workspace/model",
            "--dtype", str(config.gpu.dtype),
            "--port", str(config.podman.vllm_port),
            "--gpu-memory-utilization", str(config.gpu.memory_utilization),
            "--max-model-len", str(max_model_len),
            "--max-num-seqs", "16",
            "--enforce-eager",
            "--served-model-name", model_name
        ]

        # Automatic Tool Calling parser configuration based on model architecture
        lower_name = model_name.lower()
        has_tool_args = extra_args and ("--enable-auto-tool-choice" in extra_args or "--tool-call-parser" in extra_args)
        if not has_tool_args:
            if "llama-3" in lower_name or "llama3" in lower_name:
                cmd.extend(["--enable-auto-tool-choice", "--tool-call-parser", "llama3_json"])
            elif "mistral" in lower_name:
                cmd.extend(["--enable-auto-tool-choice", "--tool-call-parser", "mistral"])
            elif "hermes" in lower_name:
                cmd.extend(["--enable-auto-tool-choice", "--tool-call-parser", "hermes"])

        if extra_args and extra_args.strip():
            cmd.extend(extra_args.strip().split())

        try:
            await log_broadcaster.broadcast(f"[CONTAINER START] Avvio container con modello '{model_name}'...\n")
            await log_broadcaster.broadcast(f"[CONTAINER START] Timeout: {CONTAINER_START_TIMEOUT} seconds\n")
            
            # NB: non usare PIPE + communicate() qui. Con il port publishing rootless
            # (-p 127.0.0.1:8000:8000) podman lascia in vita un processo 'rootlessport'
            # che eredita le pipe: l'EOF non arriva mai e communicate() resta appeso
            # finche' il container vive. File temporanei + wait() ritornano appena
            # 'podman run -d' esce.
            with tempfile.TemporaryFile() as f_out, tempfile.TemporaryFile() as f_err:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=f_out,
                    stderr=f_err
                )
                await proc.wait()
                f_out.seek(0)
                f_err.seek(0)
                stdout = f_out.read()
                stderr = f_err.read()

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

async def download_hf_model(repo_id: str, folder_name: str = None) -> Dict:
    """
    Downloads a model from Hugging Face directly into models_dir.
    Streams download progress output via log_broadcaster.
    """
    if not folder_name or not folder_name.strip():
        folder_name = repo_id.split("/")[-1]
    
    folder_name = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', folder_name.strip())
    dest_path = DEFAULT_MODELS_DIR / folder_name
    
    try:
        await log_broadcaster.broadcast(f"[HF DOWNLOAD] Inizio download modello: '{repo_id}' -> '{dest_path}'\n")
        
        cmd = [
            "podman", "run", "--rm",
            "-v", f"{DEFAULT_MODELS_DIR.resolve()}:/download",
            "docker.io/library/python:3.11-slim",
            "bash", "-c",
            f"pip install --no-cache-dir 'huggingface_hub[cli]' && huggingface-cli download '{repo_id}' --local-dir '/download/{folder_name}' --local-dir-use-symlinks False"
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            await log_broadcaster.broadcast(f"[HF DOWNLOAD] {decoded}")
            
        await proc.wait()
        if proc.returncode == 0:
            invalidate_models_cache()
            msg = f"Modello '{repo_id}' scaricato con successo in {folder_name}!"
            await log_broadcaster.broadcast(f"[HF DOWNLOAD SUCCESS] {msg}\n")
            logger.info(msg)
            return {"success": True, "message": msg, "folder_name": folder_name}
        else:
            msg = f"Errore durante il download del modello '{repo_id}' (exit code {proc.returncode})."
            await log_broadcaster.broadcast(f"[HF DOWNLOAD ERROR] {msg}\n")
            logger.error(msg)
            return {"success": False, "message": msg}
    except asyncio.CancelledError:
        msg = "Download modello cancellato."
        await log_broadcaster.broadcast(f"[HF DOWNLOAD CANCELLED] {msg}\n")
        return {"success": False, "message": msg}
    except Exception as e:
        msg = f"Eccezione durante il download: {str(e)}"
        await log_broadcaster.broadcast(f"[HF DOWNLOAD ERROR] {msg}\n")
        return {"success": False, "message": msg}

def delete_model(model_name: str) -> Dict:
    """
    Deletes a model directory from ~/my_models safely.
    """
    if not model_name or "/" in model_name or "\\" in model_name or model_name.startswith("."):
        return {"success": False, "message": "Nome modello non valido."}
    
    target_dir = (DEFAULT_MODELS_DIR / model_name).resolve()
    if not target_dir.exists() or not target_dir.is_dir():
        return {"success": False, "message": f"Cartella modello '{model_name}' non trovata."}
    
    status = get_container_status()
    if status.get("running") and status.get("model_name") == model_name:
        return {"success": False, "message": f"Impossibile eliminare '{model_name}': il modello è attualmente in esecuzione."}
        
    try:
        shutil.rmtree(target_dir)
        invalidate_models_cache()
        logger.info(f"Deleted model directory: {target_dir}")
        return {"success": True, "message": f"Modello '{model_name}' eliminato con successo."}
    except Exception as e:
        logger.error(f"Failed to delete model '{model_name}': {e}")
        return {"success": False, "message": f"Errore durante l'eliminazione: {str(e)}"}

async def stream_logs() -> AsyncGenerator[str, None]:
    """
    Asynchronously streams logs from podman logs -f vllm-intel-arc AND event broadcaster.
    
    Uses the EventBroadcaster to receive system events (container start, image pull, etc.)
    along with live container logs concurrently into a unified stream.
    """
    merge_queue: asyncio.Queue = asyncio.Queue()
    
    async def broadcast_task():
        """Listen for broadcast events and forward to merge_queue"""
        try:
            async for msg in log_broadcaster.subscribe():
                await merge_queue.put(msg)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"Broadcast task exception: {e}")

    async def container_task():
        """Continuously follow container logs whenever container is running"""
        while True:
            try:
                status = get_container_status()
                if not status.get("running"):
                    await asyncio.sleep(1.0)
                    continue

                cmd = ["podman", "logs", "-f", "--tail", "50", CONTAINER_NAME]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                )

                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    decoded = line.decode("utf-8", errors="replace")
                    await merge_queue.put(decoded)

                await proc.wait()
                await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                await merge_queue.put(f"[LOG STREAM] Errore lettura log: {str(e)}\n")
                await asyncio.sleep(2.0)

    task_b = asyncio.create_task(broadcast_task())
    task_c = asyncio.create_task(container_task())

    try:
        while True:
            msg = await merge_queue.get()
            yield msg
    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        task_b.cancel()
        task_c.cancel()
        try:
            await asyncio.gather(task_b, task_c, return_exceptions=True)
        except Exception:
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
