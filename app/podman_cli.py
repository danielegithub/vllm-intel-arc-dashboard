import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict, AsyncGenerator

CONTAINER_NAME = "vllm-intel-arc"
IMAGE_NAME = "docker.io/intel/vllm:0.17.0-xpu"
DEFAULT_MODELS_DIR = Path.home() / "my_models"

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
    Pulls the vLLM Intel Arc container image from docker.io.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "podman", "pull", IMAGE_NAME,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        output_lines = []
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            output_lines.append(line.decode("utf-8", errors="replace"))

        await proc.wait()
        if proc.returncode == 0:
            return {"success": True, "message": f"Immagine '{IMAGE_NAME}' scaricata con successo!"}
        else:
            return {"success": False, "message": f"Errore download immagine: {''.join(output_lines[-5:])}"}
    except Exception as e:
        return {"success": False, "message": f"Eccezione durante il pull: {str(e)}"}

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

async def start_container(model_name: str, max_model_len: int = 4096, extra_args: str = "") -> Dict:
    """
    Stops existing container and runs docker.io/intel/vllm:0.17.0-xpu with specified parameters.
    """
    model_path = DEFAULT_MODELS_DIR / model_name
    if not model_path.exists():
        return {"success": False, "message": f"Cartella modello '{model_name}' non trovata in {DEFAULT_MODELS_DIR}"}

    await stop_container()

    cmd = [
        "podman", "run", "-d", "--rm",
        "--name", CONTAINER_NAME,
        "--device", "/dev/dri:/dev/dri",
        "--net=host",
        "--device", "xpu",
        "-v", f"{model_path.resolve()}:/workspace/model:ro",
        IMAGE_NAME,
        "--model", "/workspace/model",
        "--max-model-len", str(max_model_len),
        "--host", "0.0.0.0",
        "--port", "8000"
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
            return {
                "success": True,
                "message": f"Container {CONTAINER_NAME} avviato con successo ({cid})",
                "container_id": cid,
                "command": " ".join(cmd)
            }
        else:
            err_msg = stderr.decode().strip()
            return {
                "success": False,
                "message": f"Impossibile avviare il container: {err_msg}",
                "command": " ".join(cmd)
            }
    except Exception as e:
        return {"success": False, "message": f"Eccezione avvio container: {str(e)}"}

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
    Asynchronously streams logs from podman logs -f vllm-intel-arc.
    """
    cmd = ["podman", "logs", "-f", "--tail", "200", CONTAINER_NAME]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")
    except asyncio.CancelledError:
        if 'proc' in locals() and proc.returncode is None:
            proc.terminate()
            await proc.wait()
    except Exception as e:
        yield f"[LOG STREAM ERROR] {str(e)}\n"
