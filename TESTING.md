# 🧪 GUIDA AL TESTING - FASE 1 Security Implementation

Questa guida ti aiuta a verificare che tutte le protezioni di sicurezza implementate in FASE 1 funzionino correttamente.

## 📋 Prerequisiti

```bash
# 1. Installa dipendenze
pip install -r requirements.txt

# 2. Copia .env.example
cp .env.example .env

# 3. Genera una API Key forte
openssl rand -hex 32 > /tmp/api_key.txt
# Copia il valore in .env: API_KEY=<value>
```

## 🧪 Test CORS & Network Compatibility

### Test 1: Localhost Access
```bash
# Dashboard dovrebbe essere accessibile
curl -I http://localhost:5000/
# Output: 200 OK
```

### Test 2: LAN Access
```bash
# Scopri la tua IP locale
hostname -I
# Esempio: 192.168.1.100

# Test dashboard da LAN
curl -I http://192.168.1.100:5000/
# Output: 200 OK
```

### Test 3: Tailscale Access (se disponibile)
```bash
# Su macchina remota con Tailscale
curl -I http://<tailscale-ip>:5000/
# Output: 200 OK
```

### Test 4: Public Inference Endpoint (No API Key)
```bash
# Questo dovrebbe funzionare senza API Key
curl -X POST http://localhost:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-7b",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
# Output: 200 OK (o 503 se container non pronto, ma NON 401)
```

### Test 5: Protected Endpoint Requires API Key
```bash
# /api/start SENZA API Key - dovrebbe fallire
curl -X POST http://localhost:5000/api/start \
  -H "Content-Type: application/json" \
  -d '{"model_name": "qwen-7b"}'
# Output: 401 Unauthorized

# /api/start CON API Key - dovrebbe funzionare
curl -X POST http://localhost:5000/api/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -d '{"model_name": "qwen-7b"}'
# Output: 200 OK
```

## 🔐 Test Input Validation

### Test 1: Valid Model Name
```bash
# Nome valido
curl -X POST http://localhost:5000/api/start \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "Qwen2.5-7B-Instruct-AWQ"}'
# Output: 200 OK
```

### Test 2: Path Traversal Prevention
```bash
# Tentativo di traversal
curl -X POST http://localhost:5000/api/start \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "../../etc/passwd"}'
# Output: 400 Bad Request (Invalid input: Path traversal not allowed)
```

### Test 3: Shell Injection Prevention
```bash
# Tentativo di shell injection
curl -X POST http://localhost:5000/api/start \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"model_name": "model; rm -rf /"}'
# Output: 400 Bad Request (Invalid input: Contains forbidden characters)
```

### Test 4: Invalid Extra Args
```bash
# Flag vLLM non whitelisted
curl -X POST http://localhost:5000/api/start \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "qwen-7b",
    "extra_args": "--unknown-flag value"
  }'
# Output: 400 Bad Request (Invalid flag: --unknown-flag)
```

### Test 5: Valid Extra Args (Whitelisted)
```bash
# Flag vLLM valido
curl -X POST http://localhost:5000/api/start \
  -H "X-API-Key: $(grep API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{
    "model_name": "qwen-7b",
    "extra_args": "--dtype float16 --gpu-memory-utilization 0.7"
  }'
# Output: 200 OK
```

## 📊 Test Logging & EventBroadcaster

### Test 1: Structured Logging to File
```bash
# Logs dovrebbero essere in ~/.vllm-dashboard/logs/app.log
tail -f ~/.vllm-dashboard/logs/app.log

# Fai un'operazione (es. start container)
# Dovresti vedere messaggi di log strutturati
```

### Test 2: WebSocket Logs Streaming
```bash
# Connettiti al WebSocket logs endpoint
websocat ws://localhost:5000/ws/logs

# In un'altra finestra, fai un'operazione di start
# Dovresti vedere i log streamati in real-time
```

### Test 3: Thread-Safe Broadcaster
```bash
# Apri multiple WebSocket connections
for i in {1..3}; do
  websocat ws://localhost:5000/ws/logs &
done

# Fai un'operazione (es. pull image)
# Tutti i client dovrebbero ricevere lo stesso log stream
```

## 🔍 Test Python Direct

```python
# test_phase1.py
import asyncio
from app.validators import validate_model_name, validate_and_sanitize_extra_args, ValidationError
from app.security import SecurityConfig
from app.event_broadcaster import EventBroadcaster

async def test_validators():
    print("Testing validators...")
    
    # Valid
    assert validate_model_name("Qwen2.5-7B")
    assert validate_and_sanitize_extra_args("--dtype float16")
    
    # Invalid
    try:
        validate_model_name("../../etc/passwd")
        assert False, "Should have raised"
    except ValidationError:
        pass
    
    print("✅ Validators OK")

async def test_broadcaster():
    print("Testing broadcaster...")
    
    broadcaster = EventBroadcaster()
    messages = []
    
    async def subscriber():
        async for msg in broadcaster.subscribe():
            messages.append(msg)
            if len(messages) >= 2:
                break
    
    # Start subscriber task
    sub_task = asyncio.create_task(subscriber())
    
    # Send messages
    await asyncio.sleep(0.1)
    await broadcaster.broadcast("Message 1\n")
    await broadcaster.broadcast("Message 2\n")
    
    # Wait for subscriber to finish
    await asyncio.wait_for(sub_task, timeout=2.0)
    
    assert len(messages) == 2
    print("✅ Broadcaster OK")

async def test_security():
    print("Testing security config...")
    
    assert "100.*" in SecurityConfig.DASHBOARD_ORIGINS
    assert "/api/start" in SecurityConfig.PROTECTED_ENDPOINTS
    assert "/v1/chat/completions" in SecurityConfig.PUBLIC_ENDPOINTS
    
    print("✅ Security Config OK")

async def main():
    await test_validators()
    await test_broadcaster()
    await test_security()
    print("\n✅ All FASE 1 tests passed!")

if __name__ == "__main__":
    asyncio.run(main())
```

Esegui:
```bash
python test_phase1.py
```

## ✅ Checklist di Verifica

Prima di considerare FASE 1 completa:

### Security
- [ ] CORS permette localhost, LAN, Tailscale (verifica logs)
- [ ] API Key richiesta per `/api/start`, `/api/stop`, `/api/pull`
- [ ] `/v1/chat/completions` accessibile senza API Key
- [ ] Invalid API Key ritorna 401

### Input Validation
- [ ] Valid model name aceetto
- [ ] Path traversal bloccato (400 error)
- [ ] Shell injection bloccato (400 error)
- [ ] Invalid flags bloccati (400 error)
- [ ] Whitelisted flags accettati

### Logging
- [ ] Logs scritti in file con rotation
- [ ] WebSocket logs streaming funziona
- [ ] Multiple subscribers ricevono stessi logs
- [ ] Errors loggati (non swallowed)

### Network Compatibility
- [ ] Dashboard da localhost:5000 ✅
- [ ] Dashboard da IP LAN ✅
- [ ] Dashboard da Tailscale ✅
- [ ] Open WebUI inference funziona
- [ ] Client remoti possono connettersi via Tailscale

## 🐛 Troubleshooting

**Problema:** Logs non compaiono in file
```bash
# Verifica permessi directory
ls -la ~/.vllm-dashboard/logs/
chmod 755 ~/.vllm-dashboard/logs/
```

**Problema:** WebSocket logs non streamano
```bash
# Verifica che il container sia running
podman ps
# Se no, avvia un modello prima
```

**Problema:** CORS error nel browser
```bash
# Verifica che il tuo IP sia auto-detected
python3 -c "from app.security import SecurityConfig; print(SecurityConfig.DASHBOARD_ORIGINS)"
```

**Problema:** "API Key required" su /v1/chat/completions
```bash
# Non dovrebbe accadere - verifica che il path sia corretto
# /v1/chat/completions è PUBLIC, non richiede key
```

---

**Generato:** 2026-08-13  
**Status:** ✅ FASE 1 Complete
