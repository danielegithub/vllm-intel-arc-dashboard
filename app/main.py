import asyncio
import json
import urllib.request
import urllib.error
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
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

app = FastAPI(title="Intel Arc B580 vLLM Manager", version="1.1.0")

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

@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """
    Renders main dashboard interface.
    """
    return templates.TemplateResponse(request=request, name="index.html")

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
    """
    vllm_url = "http://localhost:8000/v1/chat/completions"
    
    status = get_container_status()
    if not status.get("running"):
        return {
            "success": False,
            "error": "Il container vLLM non è in esecuzione. Avvia prima un modello per chattare."
        }

    model_name = status.get("model_name") or "vllm-model"

    payload = {
        "model": "/workspace/model",
        "messages": [
            {"role": "user", "content": req.prompt}
        ],
        "max_tokens": req.max_tokens,
        "temperature": req.temperature
    }

    data_bytes = json.dumps(payload).encode("utf-8")
    request_obj = urllib.request.Request(
        vllm_url,
        data=data_bytes,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        loop = asyncio.get_running_loop()
        def _do_request():
            with urllib.request.urlopen(request_obj, timeout=60) as resp:
                return resp.read().decode("utf-8")

        response_body = await loop.run_in_executor(None, _do_request)
        resp_json = json.loads(response_body)
        
        choices = resp_json.get("choices", [])
        if choices and len(choices) > 0:
            content = choices[0].get("message", {}).get("content", "")
            return {
                "success": True,
                "model": model_name,
                "reply": content,
                "usage": resp_json.get("usage", {})
            }
        else:
            return {"success": False, "error": "Nessuna risposta generata dal modello vLLM."}

    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="replace")
        return {"success": False, "error": f"vLLM HTTP Error {e.code}: {err_msg}"}
    except urllib.error.URLError:
        return {"success": False, "error": "Impossibile connettersi a vLLM su http://localhost:8000/v1. Il modello è ancora in fase di caricamento in VRAM?"}
    except Exception as e:
        return {"success": False, "error": f"Errore durante l'interrogazione dell'LLM: {str(e)}"}

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
