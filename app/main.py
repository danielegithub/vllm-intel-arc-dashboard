import asyncio
import json
import urllib.request
import urllib.error
from pathlib import Path
import httpx
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.podman_cli import (
    scan_models,
    get_container_status,
    start_container,
    stop_container,
    pull_image,
    stream_logs
)
from app.gpu_mon import get_system_telemetry

app = FastAPI(
    title="Intel Arc vLLM Server & Manager (Ollama & OpenAI Compatible)",
    description="Local AI inference server for Intel Arc GPUs with OpenAI & Ollama API compatibility",
    version="1.3.0"
)

# Enable CORS for local network clients (Open WebUI, Jan, Continue, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

async def wait_for_vllm_ready(timeout_secs: int = 60) -> bool:
    """
    Polls http://localhost:8000/v1/models until vLLM API server is ready to accept requests.
    """
    start_time = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_event_loop().time() - start_time < timeout_secs:
            try:
                resp = await client.get("http://localhost:8000/v1/models")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2.0)
    return False

async def ensure_model_running(requested_model_name: str = None) -> str:
    """
    Auto-loads or auto-switches the vLLM container to the requested model.
    Like Ollama, if a client requests model 'X', it automatically boots model 'X'.
    """
    available_models = scan_models()
    if not available_models:
        raise HTTPException(
            status_code=404,
            detail="Nessun modello trovato nella cartella ~/my_models. Scarica prima un modello tramite la dashboard o download_model.sh."
        )

    model_names = [m["name"] for m in available_models]

    # Normalize requested model name
    target_model = None
    if requested_model_name and requested_model_name not in ("/workspace/model", "default", "vllm", "latest", "auto"):
        # Match exact or case-insensitive
        for m_name in model_names:
            if m_name == requested_model_name or m_name.lower() == requested_model_name.lower():
                target_model = m_name
                break

    if not target_model:
        # Fallback to current running model or first available model
        status = get_container_status()
        if status.get("running") and status.get("model_name"):
            target_model = status.get("model_name")
        else:
            target_model = model_names[0]

    status = get_container_status()
    current_running = status.get("model_name") if status.get("running") else None

    # Case 1: Target model is already running
    if current_running == target_model:
        ready = await wait_for_vllm_ready(timeout_secs=5)
        if ready:
            return target_model

    # Case 2: Different model is running or container is stopped -> Auto-switch/start
    start_res = await start_container(model_name=target_model, max_model_len=2048)
    if not start_res.get("success"):
        raise HTTPException(
            status_code=500,
            detail=f"Impossibile avviare il modello '{target_model}': {start_res.get('message')}"
        )

    ready = await wait_for_vllm_ready(timeout_secs=60)
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
    Lists available model directories in ~/my_models.
    """
    return scan_models()

@app.get("/api/status")
async def get_status():
    """
    Returns live container status and image availability.
    """
    return get_container_status()

@app.post("/api/image/pull")
async def api_pull_image():
    """
    Pulls docker.io/intel/vllm:0.17.0-xpu image directly from Podman.
    """
    res = await pull_image()
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/start")
async def api_start_model(req: StartModelRequest):
    """
    Starts vLLM Podman container with the specified model and options.
    """
    res = await start_container(
        model_name=req.model_name,
        max_model_len=req.max_model_len,
        extra_args=req.extra_args
    )
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res

@app.post("/api/stop")
async def api_stop_container():
    """
    Stops and removes the vLLM container.
    """
    res = await stop_container()
    return res

@app.post("/api/chat")
async def api_test_chat(req: ChatRequest):
    """
    Proxies a test chat completion request to http://localhost:8000/v1/chat/completions.
    Auto-starts default model if no container is running.
    """
    active_model = await ensure_model_running()

    payload = {
        "model": "/workspace/model",
        "messages": [
            {"role": "user", "content": req.prompt}
        ],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post("http://localhost:8000/v1/chat/completions", json=payload)
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
        return {"success": False, "error": "Impossibile connettersi a vLLM su http://localhost:8000/v1. Il modello è ancora in fase di caricamento in VRAM?"}
    except Exception as e:
        return {"success": False, "error": f"Errore durante l'interrogazione dell'LLM: {str(e)}"}

# =====================================================================
# OPENAI COMPATIBLE PROXY API ENDPOINTS (/v1/...)
# Available for local network clients (Open WebUI, Continue, Jan, Cursor)
# Supports AUTO-LOADING and AUTO-SWITCHING models like Ollama!
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
    
    # Auto-load or auto-switch container to requested model!
    active_model = await ensure_model_running(requested_model)

    # Override model target to point to container internal path
    body["model"] = "/workspace/model"
    is_stream = body.get("stream", False)
    vllm_target = "http://localhost:8000/v1/chat/completions"

    if is_stream:
        async def stream_generator():
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    async with client.stream("POST", vllm_target, json=body) as resp:
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
    await ensure_model_running(requested_model)

    body["model"] = "/workspace/model"
    is_stream = body.get("stream", False)
    vllm_target = "http://localhost:8000/v1/completions"

    if is_stream:
        async def stream_generator():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", vllm_target, json=body) as resp:
                    async for chunk in resp.aiter_bytes():
                        yield chunk
        return StreamingResponse(stream_generator(), media_type="text/event-stream")
    else:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(vllm_target, json=body)
            return JSONResponse(status_code=resp.status_code, content=resp.json())

# =====================================================================
# OLLAMA COMPATIBLE API ENDPOINTS (/api/tags, /api/ps, /api/show, /api/version)
# Allows Ollama-compatible clients (e.g. Open WebUI, Obsidian Ollama plugin) to connect directly
# =====================================================================

@app.get("/api/tags")
async def ollama_tags():
    """
    Ollama-compatible /api/tags endpoint listing local models.
    """
    models = scan_models()
    return {
        "models": [
            {
                "name": m["name"],
                "model": m["name"],
                "modified_at": "2026-08-13T00:00:00Z",
                "size": int(m["size_gb"] * 1024 * 1024 * 1024),
                "digest": "sha256:vllm-intel-arc",
                "details": {
                    "parent_model": "",
                    "format": "safetensors",
                    "family": "qwen2",
                    "families": ["qwen2"],
                    "parameter_size": "7B",
                    "quantization_level": "AWQ"
                }
            } for m in models
        ]
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
            telemetry = get_system_telemetry()
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
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000, reload=True, timeout_graceful_shutdown=2)
