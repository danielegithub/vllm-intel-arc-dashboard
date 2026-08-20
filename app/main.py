import asyncio
import json
import urllib.request
import urllib.error
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from app.podman_cli import (
    scan_models,
    get_container_status,
    start_container,
    stop_container,
    pull_image,
    stream_logs,
    download_hf_model,
    delete_model
)
from app.gpu_mon import get_system_telemetry, detect_gpu_vram, set_gpu_vram
from app.validators import validate_model_name, validate_and_sanitize_extra_args, ValidationError
from app.security import SecurityConfig, log_denied_request
from app.logging_config import logger
from app.config import get_config

# Load environment variables
load_dotenv()

# Initialize configuration
config = get_config()
logger.info(f"Configuration loaded from: {config._config_file if config._config_file else 'defaults + environment'}")

# Global lock to serialize container operations and avoid race conditions
container_lifecycle_lock = asyncio.Lock()

# Auto-detect GPU VRAM if not set
if config.gpu.total_vram_mb is None:
    logger.info("Auto-detecting GPU VRAM...")
    detected_vram = detect_gpu_vram()
    config.gpu.total_vram_mb = detected_vram
    set_gpu_vram(detected_vram)
else:
    set_gpu_vram(config.gpu.total_vram_mb)
    logger.info(f"Using configured GPU VRAM: {config.gpu.total_vram_mb}MB")

app = FastAPI(
    title="Intel Arc vLLM Server & Manager (Ollama & OpenAI Compatible)",
    description="Local AI inference server for Intel Arc GPUs with OpenAI & Ollama API compatibility",
    version="1.4.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

import re
origins_regex = r"^http://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|100\.\d+\.\d+\.\d+)(:\d+)?$"
# CORS: Allow local network, Tailscale, Open WebUI, and desktop AI clients
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=origins_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware: Verify API Key for protected endpoints
@app.middleware("http")
async def verify_protected_operations(request: Request, call_next):
    """Verify API Key for operations that consume server resources."""
    if SecurityConfig.require_api_key_for_endpoint(request.url.path, request.method):
        api_key = request.headers.get("X-API-Key", "")
        if not SecurityConfig.verify_api_key(api_key):
            logger.warning(f"Unauthorized access to {request.method} {request.url.path} - invalid/missing API key")
            return JSONResponse(
                {"error": "Unauthorized - API Key required"},
                status_code=401
            )
    return await call_next(request)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

class StartModelRequest(BaseModel):
    model_name: str
    max_model_len: int = 2048
    extra_args: str = ""

class ChatRequest(BaseModel):
    prompt: str
    max_tokens: int = 512
    temperature: float = 0.7

class DownloadModelRequest(BaseModel):
    repo_id: str
    folder_name: str = ""

class DeleteModelRequest(BaseModel):
    model_name: str

async def wait_for_vllm_ready(timeout_secs: int = 120, initial_delay: float = 0.5) -> bool:
    """
    Polls vLLM API server with exponential backoff until it is ready to accept requests.
    """
    start_time = asyncio.get_event_loop().time()
    delay = initial_delay
    target_url = f"{config.podman.vllm_api_base_url}/models"
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_event_loop().time() - start_time < timeout_secs:
            try:
                resp = await client.get(target_url)
                if resp.status_code == 200:
                    elapsed = round(asyncio.get_event_loop().time() - start_time, 2)
                    logger.info(f"vLLM API server is ready after {elapsed}s!")
                    return True
            except Exception:
                pass
            
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout_secs - elapsed
            sleep_time = min(delay, max(0.1, remaining))
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            delay = min(delay * 1.5, 4.0)
            
    logger.error(f"vLLM API server not ready after {timeout_secs}s")
    return False

async def ensure_model_running(requested_model_name: str = None, request: Request = None) -> str:
    """
    Auto-loads or auto-switches the vLLM container to the requested model.
    Uses container_lifecycle_lock to prevent race conditions during concurrent switches.
    """
    available_models = scan_models()
    if not available_models:
        raise HTTPException(
            status_code=404,
            detail="Nessun modello trovato nella cartella ~/my_models. Scarica prima un modello tramite la dashboard o download_model.sh."
        )

    model_names = [m["name"] for m in available_models]

    target_model = None
    if requested_model_name and requested_model_name not in ("/workspace/model", "default", "vllm", "latest", "auto"):
        for m_name in model_names:
            if m_name == requested_model_name or m_name.lower() == requested_model_name.lower():
                target_model = m_name
                break

    if not target_model:
        status = get_container_status()
        if status.get("running") and status.get("model_name"):
            target_model = status.get("model_name")
        else:
            target_model = model_names[0]

    async with container_lifecycle_lock:
        status = get_container_status()
        current_running = status.get("model_name") if status.get("running") else None

        # Case 1: Target model is already running
        if current_running == target_model:
            ready = await wait_for_vllm_ready(timeout_secs=5)
            if ready:
                return target_model

        # Case 2: Different model is running or container is stopped -> Auto-switch/start
        if config.security.require_api_key_for_autoswitch and config.security.api_key and request:
            api_key = request.headers.get("X-API-Key", "")
            if api_key != config.security.api_key:
                raise HTTPException(
                    status_code=401,
                    detail="Unauthorized: API Key required to auto-switch models"
                )

        # Calculate dynamic max_model_len per PERF-3
        target_model_meta = next((m for m in available_models if m["name"] == target_model), None)
        computed_max_len = config.gpu.max_model_len
        if target_model_meta and config.gpu.total_vram_mb:
            size_gb = target_model_meta.get("size_gb", 0)
            budget_gb = (config.gpu.total_vram_mb / 1024) * config.gpu.memory_utilization
            kv_budget_gb = max(0.5, budget_gb - size_gb)
            # Roughly 56 KiB per token (for 7B model).
            # 1 GB = 1024 * 1024 KB. 1024 * 1024 / 56 ≈ 18724 tokens per GB.
            # Let's say ~15000 tokens per GB of KV budget.
            tokens = int(kv_budget_gb * 15000)
            model_max_pos = target_model_meta.get("max_position_embeddings", 32768)
            computed_max_len = min(model_max_pos, tokens)
            # Ensure it is at least the config minimum
            computed_max_len = max(config.gpu.max_model_len, computed_max_len)

        logger.info(f"Auto-switching container to model '{target_model}' (max_model_len={computed_max_len})...")
        start_res = await start_container(model_name=target_model, max_model_len=computed_max_len)
        if not start_res.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Impossibile avviare il modello '{target_model}': {start_res.get('message')}"
            )

        ready = await wait_for_vllm_ready(timeout_secs=config.podman.container_start_timeout)
        if not ready:
            raise HTTPException(
                status_code=504,
                detail=f"Timeout durante l'avvio del modello '{target_model}'. Verifica i log nella dashboard."
            )

    return target_model

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """
    Renders main dashboard interface.
    """
    return templates.TemplateResponse(request=request, name="index.html")

# =====================================================================
# MANAGEMENT REST API ENDPOINTS
# =====================================================================

@app.get("/api/models")
async def get_models():
    """
    Lists available model directories in ~/my_models with rich metadata.
    """
    return scan_models()

@app.get("/api/status")
async def get_status():
    """
    Returns live container status and image availability.
    """
    return get_container_status()

@app.get("/api/config")
async def get_app_config():
    """
    Returns current application configuration (non-sensitive data only).
    """
    return config.to_dict()

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """
    Kubernetes-style health check endpoint.
    Checks status of vLLM server, Podman executable, and filesystem directory non-blockingly.
    """
    checks = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {}
    }
    
    # Check vLLM API server connectivity
    status = get_container_status()
    if status.get("running"):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.get(f"{config.podman.vllm_api_base_url}/models")
                checks["checks"]["vllm_server"] = "up" if resp.status_code == 200 else "loading"
        except Exception:
            checks["checks"]["vllm_server"] = "loading"
    else:
        checks["checks"]["vllm_server"] = "stopped"
        
    # Check Podman CLI availability asynchronously
    try:
        res = await asyncio.to_thread(
            subprocess.run, ["podman", "version"], capture_output=True, text=True, timeout=2
        )
        checks["checks"]["podman"] = "up" if res.returncode == 0 else "error"
    except Exception:
        checks["checks"]["podman"] = "error"
        
    # Check models directory access
    try:
        models_dir = config.model.models_dir
        checks["checks"]["models_directory"] = "up" if models_dir.exists() else "missing"
    except Exception:
        checks["checks"]["models_directory"] = "error"

    # Overall health determination
    is_healthy = checks["checks"].get("podman") == "up" and checks["checks"].get("models_directory") == "up"
    status_code = 200 if is_healthy else 503
    checks["status"] = "ok" if is_healthy else "unhealthy"
    
    return JSONResponse(content=checks, status_code=status_code)

@app.post("/api/image/pull")
async def api_pull_image():
    """
    Pulls configured vLLM image directly from Podman.
    """
    res = await pull_image()
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/start")
async def api_start_model(req: StartModelRequest):
    """
    Starts vLLM Podman container with the specified model and options.
    Requires X-API-Key header if configured.
    """
    try:
        validate_model_name(req.model_name)
        safe_extra_args = validate_and_sanitize_extra_args(req.extra_args)
    except ValidationError as e:
        logger.warning(f"Input validation failed: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    
    if req.max_model_len < 128 or req.max_model_len > 32768:
        raise HTTPException(
            status_code=400,
            detail="max_model_len must be between 128 and 32768"
        )
    
    logger.info(f"Starting model: {req.model_name}")
    
    async with container_lifecycle_lock:
        res = await start_container(
            model_name=req.model_name,
            max_model_len=req.max_model_len,
            extra_args=" ".join(safe_extra_args) if safe_extra_args else ""
        )
    if not res["success"]:
        logger.error(f"Failed to start model {req.model_name}: {res['message']}")
        raise HTTPException(status_code=400, detail=res["message"])
    
    logger.info(f"Model {req.model_name} started successfully")
    return res

@app.post("/api/stop")
async def api_stop_container():
    """
    Stops and removes the vLLM container.
    """
    async with container_lifecycle_lock:
        res = await stop_container()
    return res

@app.post("/api/models/download")
async def api_download_model(req: DownloadModelRequest):
    """
    Downloads a model from Hugging Face directly into ~/my_models.
    Streams download progress to logs WebSocket.
    """
    repo_id = req.repo_id.strip()
    if not repo_id:
        raise HTTPException(status_code=400, detail="Repo ID Hugging Face obbligatorio.")
    
    try:
        from app.validators import validate_repo_id
        validate_repo_id(repo_id)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    res = await download_hf_model(repo_id=repo_id, folder_name=req.folder_name)
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("message"))
    return res

@app.post("/api/models/delete")
async def api_delete_model(req: DeleteModelRequest):
    """
    Deletes a model directory from ~/my_models.
    """
    model_name = req.model_name.strip()
    if not model_name:
        raise HTTPException(status_code=400, detail="Nome modello obbligatorio.")
    
    res = delete_model(model_name)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("message"))
    return res

async def ollama_stream_parser(response_iterator, requested_model: str, is_chat: bool = True):
    """
    Parses vLLM's OpenAI-compatible SSE stream into Ollama NDJSON format.
    """
    import json
    from datetime import datetime, timezone
    
    async for chunk in response_iterator:
        text = chunk.decode("utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
                choices = data.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {}) if is_chat else choices[0]
                content = delta.get("content", "") if is_chat else delta.get("text", "")
                
                # Ollama format
                out = {
                    "model": requested_model,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "done": False
                }
                if is_chat:
                    out["message"] = {"role": "assistant", "content": content}
                else:
                    out["response"] = content
                
                yield (json.dumps(out) + "\n").encode("utf-8")
            except Exception:
                pass
                
    # Final done message
    final_out = {
        "model": requested_model,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "done": True,
        "done_reason": "stop"
    }
    if is_chat:
        final_out["message"] = {"role": "assistant", "content": ""}
    else:
        final_out["response"] = ""
    yield (json.dumps(final_out) + "\n").encode("utf-8")


@app.post("/api/chat")
async def api_test_chat(request: Request):
    """
    Dual-mode chat endpoint:
    1. If called by Dashboard UI: expects {"prompt": "...", "temperature": 0.7, "max_tokens": 512, "messages": [...]}
    2. If called by Ollama/OpenAI clients: expects {"model": "...", "messages": [...], "stream": bool}
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")

    vllm_target = f"{config.podman.vllm_api_base_url}/chat/completions"

    # Check if this is an Ollama/OpenAI chat request (has 'messages' and 'model')
    if "messages" in body and "model" in body:
        requested_model = body.get("model")
        active_model = await ensure_model_running(requested_model, request)
        body["model"] = active_model
        is_stream = body.get("stream", True)
        body["stream"] = is_stream

        if is_stream:
            async def stream_generator():
                try:
                    async with httpx.AsyncClient(timeout=120.0) as client:
                        async with client.stream("POST", vllm_target, json=body) as resp:
                            if resp.status_code != 200:
                                err_text = await resp.aread()
                                yield (json.dumps({"error": err_text.decode("utf-8")}) + "\n").encode()
                                return
                            async for mapped_chunk in ollama_stream_parser(resp.aiter_bytes(), requested_model, is_chat=True):
                                yield mapped_chunk
                except Exception as e:
                    err = {"error": str(e)}
                    yield (json.dumps(err) + "\n").encode()

            return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
        else:
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(vllm_target, json=body)
                    data = resp.json()
                    content = ""
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                    
                    from datetime import datetime, timezone
                    out = {
                        "model": requested_model,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "message": {"role": "assistant", "content": content},
                        "done": True,
                        "done_reason": "stop"
                    }
                    return JSONResponse(status_code=resp.status_code, content=out)
            except httpx.ConnectError:
                raise HTTPException(status_code=503, detail="Impossibile connettersi al server vLLM. Il modello si sta ancora avviando.")
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

    # Otherwise, handle dashboard test chat format (supports multi-turn)
    messages = body.get("messages")
    if not messages:
        prompt = body.get("prompt", "")
        messages = [{"role": "user", "content": prompt}]

    max_tokens = int(body.get("max_tokens", 512))
    temperature = float(body.get("temperature", 0.7))

    active_model = await ensure_model_running(request=request)

    payload = {
        "model": active_model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(vllm_target, json=payload)
            if resp.status_code == 200:
                resp_json = resp.json()
                choices = resp_json.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    return {
                        "success": True,
                        "model": active_model,
                        "reply": content,
                        "usage": resp_json.get("usage", {})
                    }
                return {"success": False, "error": "Nessuna risposta generata dal modello vLLM."}
            else:
                return {"success": False, "error": f"vLLM HTTP Error {resp.status_code}: {resp.text}"}
    except httpx.ConnectError:
        return {"success": False, "error": "Impossibile connettersi a vLLM. Il modello è ancora in fase di caricamento in VRAM?"}
    except Exception as e:
        return {"success": False, "error": f"Errore durante l'interrogazione dell'LLM: {str(e)}"}

# =====================================================================
# OPENAI COMPATIBLE PROXY API ENDPOINTS (/v1/...)
# =====================================================================

@app.get("/v1/models")
async def openai_get_models():
    """
    OpenAI-compatible /v1/models endpoint listing available & active models.
    """
    status = get_container_status()
    models_list = scan_models()
    
    data = []
    active_name = status.get("model_name") if status.get("running") else None
    
    if active_name:
        data.append({
            "id": active_name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "intel-vllm",
            "permission": [],
            "status": "running"
        })

    for m in models_list:
        if m["name"] != active_name:
            data.append({
                "id": m["name"],
                "object": "model",
                "created": 1700000000,
                "owned_by": "intel-vllm",
                "permission": [],
                "status": "available"
            })
            
    return {"object": "list", "data": data}

@app.post("/v1/chat/completions")
async def openai_chat_completions(request: Request):
    """
    OpenAI-compatible /v1/chat/completions endpoint (supports streaming & non-streaming).
    Auto-loads or auto-switches model container dynamically!
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")

    requested_model = body.get("model")
    active_model = await ensure_model_running(requested_model, request)

    body["model"] = active_model
    is_stream = body.get("stream", False)
    vllm_target = f"{config.podman.vllm_api_base_url}/chat/completions"

    if is_stream:
        async def stream_generator():
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", vllm_target, json=body) as resp:
                        if resp.status_code != 200:
                            err_text = await resp.aread()
                            yield f"data: {json.dumps({'error': err_text.decode('utf-8')})}\n\n".encode()
                            return
                        async for chunk in resp.aiter_bytes():
                            yield chunk
            except Exception as e:
                err_payload = json.dumps({"error": str(e)}).encode()
                yield f"data: {err_payload}\n\n".encode()

        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(vllm_target, json=body)
                return JSONResponse(status_code=resp.status_code, content=resp.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Impossibile connettersi al server vLLM. Il modello si sta ancora avviando.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/completions")
async def openai_completions(request: Request):
    """
    OpenAI-compatible /v1/completions endpoint. Auto-loads model if needed.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")

    requested_model = body.get("model")
    active_model = await ensure_model_running(requested_model, request)

    body["model"] = active_model
    is_stream = body.get("stream", False)
    vllm_target = f"{config.podman.vllm_api_base_url}/completions"

    if is_stream:
        async def stream_generator():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", vllm_target, json=body) as resp:
                    if resp.status_code != 200:
                        err_text = await resp.aread()
                        yield f"data: {json.dumps({'error': err_text.decode('utf-8')})}\n\n".encode()
                        return
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(vllm_target, json=body)
            return JSONResponse(status_code=resp.status_code, content=resp.json())

@app.post("/v1/embeddings")
async def openai_embeddings(request: Request):
    """
    OpenAI-compatible /v1/embeddings endpoint. Auto-loads model if needed.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")

    requested_model = body.get("model")
    active_model = await ensure_model_running(requested_model, request)

    body["model"] = active_model
    vllm_target = f"{config.podman.vllm_api_base_url}/embeddings"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(vllm_target, json=body)
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Impossibile connettersi al server vLLM. Il modello si sta ancora avviando.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================================
# OLLAMA COMPATIBLE API ENDPOINTS (/api/tags, /api/ps, /api/show, /api/version)
# =====================================================================

@app.post("/api/generate")
async def ollama_generate(request: Request):
    """
    Ollama-compatible /api/generate endpoint.
    Supports auto-loading models and streaming/non-streaming responses.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")

    requested_model = body.get("model")
    active_model = await ensure_model_running(requested_model, request)

    prompt = body.get("prompt", "")
    is_stream = body.get("stream", True)
    vllm_payload = {
        "model": active_model,
        "prompt": prompt,
        "max_tokens": body.get("options", {}).get("num_predict", 512) if isinstance(body.get("options"), dict) else 512,
        "temperature": body.get("options", {}).get("temperature", 0.7) if isinstance(body.get("options"), dict) else 0.7,
        "stream": is_stream
    }
    vllm_target = f"{config.podman.vllm_api_base_url}/completions"

    if is_stream:
        async def stream_generator():
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", vllm_target, json=vllm_payload) as resp:
                        if resp.status_code != 200:
                            err_text = await resp.aread()
                            yield (json.dumps({"error": err_text.decode("utf-8")}) + "\n").encode()
                            return
                        async for mapped_chunk in ollama_stream_parser(resp.aiter_bytes(), requested_model, is_chat=False):
                            yield mapped_chunk
            except Exception as e:
                err = {"error": str(e)}
                yield (json.dumps(err) + "\n").encode()

        return StreamingResponse(stream_generator(), media_type="application/x-ndjson")
    else:
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(vllm_target, json=vllm_payload)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    text = choices[0].get("text", "") if choices else ""
                    return {
                        "model": requested_model or "vllm-intel-arc",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                        "response": text,
                        "done": True
                    }
                return JSONResponse(status_code=resp.status_code, content=resp.json())
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Impossibile connettersi a vLLM. Il modello si sta avviando.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/tags")
async def ollama_tags():
    """
    Ollama-compatible /api/tags endpoint listing local models with dynamic metadata.
    """
    models = scan_models()
    return {
        "models": [
            {
                "name": m["name"],
                "model": m["name"],
                "modified_at": m.get("modified_at", datetime.now(timezone.utc).isoformat()),
                "size": int(m.get("size_bytes", m["size_gb"] * 1024 * 1024 * 1024)),
                "digest": f"sha256:{m['name']}",
                "details": {
                    "parent_model": "",
                    "format": "safetensors",
                    "family": m.get("model_type", "unknown"),
                    "families": [m.get("model_type", "unknown")],
                    "parameter_size": f"{m['size_gb']}GB",
                    "quantization_level": m.get("quantization", "FP16")
                }
            } for m in models
        ]
    }

@app.post("/api/show")
async def ollama_show(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Formato JSON non valido.")
    
    model_name = body.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name required")
        
    models = scan_models()
    model = next((m for m in models if m["name"] == model_name), None)
    
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    return {
        "modelfile": f"# Modelfile for {model_name}\nFROM {model_name}\n",
        "parameters": "",
        "template": "{{ .Prompt }}",
        "details": {
            "parent_model": "",
            "format": "safetensors",
            "family": model.get("model_type", "unknown"),
            "families": [model.get("model_type", "unknown")],
            "parameter_size": f"{model.get('size_gb', 0)}GB",
            "quantization_level": model.get("quantization", "FP16")
        }
    }

@app.get("/api/ps")
async def ollama_ps():
    """
    Ollama-compatible /api/ps endpoint listing currently running model.
    """
    status = get_container_status()
    if status.get("running") and status.get("model_name"):
        return {
            "models": [
                {
                    "name": status.get("model_name"),
                    "model": status.get("model_name"),
                    "size": 5500000000,
                    "digest": "sha256:vllm-intel-arc",
                    "details": {"format": "safetensors", "family": "vllm-intel-arc"},
                    "expires_at": "2099-01-01T00:00:00Z",
                    "size_vram": 5500000000
                }
            ]
        }
    return {"models": []}

@app.get("/api/version")
async def ollama_version():
    """
    Ollama-compatible /api/version endpoint.
    """
    return {"version": "0.1.33-vllm-intel-arc"}

# =====================================================================
# WEBSOCKET TELEMETRY & LOG ENDPOINTS
# =====================================================================

@app.websocket("/ws/gpu")
async def ws_gpu_telemetry(websocket: WebSocket):
    """
    WebSocket endpoint broadcasting Intel Arc GPU and host system metrics every second.
    """
    await websocket.accept()
    try:
        while True:
            telemetry = await asyncio.to_thread(get_system_telemetry)
            await websocket.send_json(telemetry)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass

@app.websocket("/ws/logs")
async def ws_container_logs(websocket: WebSocket):
    """
    WebSocket endpoint streaming live logs from podman logs -f vllm-intel-arc.
    """
    await websocket.accept()
    try:
        async for line in stream_logs():
            await websocket.send_text(line)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.server.host, port=config.server.port, reload=config.server.reload, timeout_graceful_shutdown=2)

