import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, AsyncGenerator

CONTAINER_NAME = "vllm-intel-arc"
IMAGE_NAME = "docker.io/intel/vllm:0.17.0-xpu"
DEFAULT_MODELS_DIR = Path.home() / "my_models"

# Global log queue for real-time system events (image pull progress, etc.)
system_log_queue = asyncio.Queue()

def scan_models(models_dir: str = None) -> List[Dict]:
    """
    Scans ~/my_models directory for model folders and estimates details.
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
    Pulls docker.io/intel/vllm:0.17.0-xpu while streaming live progress output to system_log_queue.
    """
    try:
        await system_log_queue.put(f"[PODMAN PULL] Avvio download immagine {IMAGE_NAME}...\n")
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
            await system_log_queue.put(f"[PODMAN PULL] {decoded_line}")

        await proc.wait()
        if proc.returncode == 0:
            msg = f"Immagine '{IMAGE_NAME}' scaricata ed installata con successo!"
            await system_log_queue.put(f"[PODMAN PULL SUCCESS] {msg}\n")
            return {"success": True, "message": msg}
        else:
            msg = f"Errore durante il download dell'immagine {IMAGE_NAME}."
            await system_log_queue.put(f"[PODMAN PULL ERROR] {msg}\n")
            return {"success": False, "message": msg}
    except Exception as e:
        err_msg = f"Eccezione durante il pull: {str(e)}"
        await system_log_queue.put(f"[PODMAN PULL ERROR] {err_msg}\n")
        return {"success": False, "message": err_msg}

def get_container_status() -> Dict:
    """
    Checks the status of the vllm-intel-arc Podman container.
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
    """
    model_path = DEFAULT_MODELS_DIR / model_name
    if not model_path.exists():
        return {"success": False, "message": f"Cartella modello '{model_name}' non trovata in {DEFAULT_MODELS_DIR}"}

    await stop_container()

    # Official Intel vLLM Docker launch configuration
    cmd = [
        "podman", "run", "-d", "--rm",
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
        "--dtype", "float16",
        "--port", "8000",
        "--gpu-memory-utilization", "0.70",
        "--max-model-len", str(max_model_len)
    ]

    if extra_args and extra_args.strip():
        cmd.extend(extra_args.strip().split())

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode == 0:
            cid = stdout.decode().strip()[:12]
            msg = f"Container {CONTAINER_NAME} avviato con successo ({cid})"
            await system_log_queue.put(f"[CONTAINER SUCCESS] {msg}\n")
            return {
                "success": True,
                "message": msg,
                "container_id": cid,
                "command": " ".join(cmd)
            }
        else:
            err_msg = stderr.decode().strip()
            msg = f"Impossibile avviare il container: {err_msg}"
            await system_log_queue.put(f"[CONTAINER ERROR] {msg}\n")
            return {
                "success": False,
                "message": msg,
                "command": " ".join(cmd)
            }
    except Exception as e:
        err_msg = f"Eccezione avvio container: {str(e)}"
        await system_log_queue.put(f"[CONTAINER ERROR] {err_msg}\n")
        return {"success": False, "message": err_msg}

async def stop_container() -> Dict:
    """
    Stops and removes the vllm-intel-arc container.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "podman", "stop", "-t", "5", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()

        rm_proc = await asyncio.create_subprocess_exec(
            "podman", "rm", "-f", CONTAINER_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await rm_proc.communicate()

        return {"success": True, "message": f"Container {CONTAINER_NAME} arrestato e rimosso."}
    except Exception as e:
        return {"success": False, "message": f"Errore durante l'arresto: {str(e)}"}

async def stream_logs() -> AsyncGenerator[str, None]:
    """
    Asynchronously streams logs from podman logs -f vllm-intel-arc AND system_log_queue events.
    """
    has_warned_missing = False
    
    while True:
        try:
            while not system_log_queue.empty():
                try:
                    msg = system_log_queue.get_nowait()
                    yield msg
                except asyncio.QueueEmpty:
                    break

            status = get_container_status()
            if not status.get("exists"):
                if not has_warned_missing:
                    yield "[SISTEMA] Container 'vllm-intel-arc' non ancora creato. Avvia un modello per visualizzare i log di vLLM.\n"
                    has_warned_missing = True
                await asyncio.sleep(2.0)
                continue

            has_warned_missing = False
            cmd = ["podman", "logs", "-f", "--tail", "200", CONTAINER_NAME]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT
            )
            
            try:
                while True:
                    while not system_log_queue.empty():
                        try:
                            yield system_log_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break

                    try:
                        line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
                        if not line:
                            break
                        yield line.decode("utf-8", errors="replace")
                    except asyncio.TimeoutError:
                        pass
            finally:
                if proc.returncode is None:
                    try:
                        proc.terminate()
                        await proc.wait()
                    except Exception:
                        pass
            await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            break
        except Exception as e:
            yield f"[LOG STREAM ERROR] {str(e)}\n"
            await asyncio.sleep(2.0)
