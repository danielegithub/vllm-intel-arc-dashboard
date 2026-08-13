# 🔌 Client Integration Guide - vLLM Intel Arc Dashboard

**Data:** 2026-08-13  
**Versione Server:** 1.3.0  
**Status:** ✅ Ready for Network Clients

---

## 📌 IMPORTANTE - Nessun Cambio Richiesto ai Client!

**Per fare inferenza (chat/completions), i tuoi client NON richiedono modifiche di codice.**

Devi solo:
1. ✅ Conoscere l'indirizzo IP del server
2. ✅ Puntare al nostro endpoint `/v1`
3. ✅ (Facoltativo) Usare Tailscale per connessione remota

---

## 🌐 Come Connettersi

### **Opzione 1: Rete Locale LAN**

Se il PC con vLLM è nella tua stessa rete WiFi/Ethernet:

```
Server Address: http://192.168.X.X:5000/v1
```

Sostituisci `192.168.X.X` con l'IP reale del PC che esegue il dashboard.

**Come trovare l'IP del server:**
```bash
# Sul PC dove gira vLLM Intel Arc:
hostname -I
# Output: 192.168.1.100

# Oppure da smartphone/altro PC:
ping <nome-computer>.local
```

---

### **Opzione 2: Tailscale (VPN Privata - Ovunque nel Mondo)**

Se vuoi connetterti **da fuori casa** in sicurezza:

1. Installa Tailscale su **entrambi** i PC:
   - PC con vLLM: `https://tailscale.com/download/linux`
   - Tuo client: `https://tailscale.com/download`

2. Accedi con lo stesso account Tailscale

3. Usa l'IP Tailscale del server:
```
Server Address: http://100.X.X.X:5000/v1
```

L'IP Tailscale lo vedi nella dashboard Tailscale (es: `100.64.123.45`)

---

## 💬 Usa il Server da Applicazioni

### **Open WebUI (Web Interface)**

1. Apri: `http://localhost:3000` (o dove hai Open WebUI)
2. Vai a **Settings → Models → Connect to External API**
3. Scegli **OpenAI**
4. Inserisci:
   - **API Base URL:** `http://192.168.X.X:5000/v1` (o IP Tailscale)
   - **API Key:** (lascia vuoto - non richiesto)
5. Clicca **Connect**
6. I modelli disponibili appariranno automaticamente

---

### **Continue / Codeium (VS Code / JetBrains)**

**Continue in VS Code:**
1. Installa estensione Continue
2. Vai a `~/.continue/config.json`
3. Aggiungi:
```json
{
  "models": [
    {
      "title": "Qwen2.5-Coder-7B",
      "provider": "openai",
      "model": "Qwen2.5-Coder-7B-Instruct-AWQ",
      "apiBase": "http://192.168.X.X:5000/v1"
    }
  ]
}
```

**Codeium (VS Code):**
1. Extension: Codeium
2. Usa `/` command → `/settings`
3. Custom API: `http://192.168.X.X:5000/v1`

---

### **Jan.ai (Desktop App)**

1. Apri Jan.ai
2. Vai a **Settings → Models**
3. Clicca **+ Add Model**
4. Seleziona **OpenAI-Compatible**
5. Inserisci:
   - **API Base:** `http://192.168.X.X:5000/v1`
   - **Model ID:** `Qwen2.5-7B-Instruct-AWQ` (o quale stai usando)

---

### **Cursor (IDE)**

1. Apri Cursor
2. Vai a **Settings → Models**
3. Aggiungi custom provider:
   - **Type:** OpenAI Compatible
   - **Base URL:** `http://192.168.X.X:5000/v1`
   - **API Key:** (vuoto)

---

### **Da Terminale (cURL/Python)**

```bash
# Test rapido - chat
curl http://192.168.X.X:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen2.5-7B-Instruct-AWQ",
    "messages": [
      {"role": "user", "content": "Ciao! Come stai?"}
    ],
    "max_tokens": 512,
    "temperature": 0.7
  }'

# Con streaming
curl http://192.168.X.X:5000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen2.5-7B-Instruct-AWQ",
    "messages": [{"role": "user", "content": "Scrivi una poesia"}],
    "stream": true
  }' | grep -o '"content":"[^"]*"'

# Lista modelli disponibili
curl http://192.168.X.X:5000/v1/models | jq .
```

**Python:**
```python
import requests

response = requests.post(
    "http://192.168.X.X:5000/v1/chat/completions",
    json={
        "model": "Qwen2.5-7B-Instruct-AWQ",
        "messages": [{"role": "user", "content": "Ciao"}],
        "max_tokens": 512
    },
    timeout=60
)

print(response.json()["choices"][0]["message"]["content"])
```

**Node.js:**
```javascript
const response = await fetch("http://192.168.X.X:5000/v1/chat/completions", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    model: "Qwen2.5-7B-Instruct-AWQ",
    messages: [{ role: "user", content: "Ciao" }],
    max_tokens: 512
  })
});

const data = await response.json();
console.log(data.choices[0].message.content);
```

---

## 📊 API Endpoint Disponibili

### **OpenAI Compatible** (`/v1/`)
```
GET  /v1/models              ← Lista modelli
POST /v1/chat/completions    ← Chat (streaming & non-streaming)
POST /v1/completions         ← Text completion
```

### **Ollama Compatible** (`/api/`)
```
GET  /api/tags               ← Lista modelli (formato Ollama)
GET  /api/ps                 ← Modello attualmente in esecuzione
GET  /api/version            ← Versione server
```

---

## 🔐 Operazioni Admin (Avviare/Stoppare Modelli)

Se il proprietario del server ti dà permesso di controllare quali modelli girano:

**Richiede API Key** - Chiedi al proprietario una chiave segreta tipo:
```
X-API-Key: your-secret-key-12345
```

### **Avviare un modello**
```bash
curl -X POST http://192.168.X.X:5000/api/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-secret-key-12345" \
  -d '{
    "model_name": "Qwen2.5-7B-Instruct-AWQ",
    "max_model_len": 2048
  }'
```

### **Stoppare il modello attuale**
```bash
curl -X POST http://192.168.X.X:5000/api/stop \
  -H "X-API-Key: your-secret-key-12345"
```

### **Scaricare immagine vLLM** (first-time only)
```bash
curl -X POST http://192.168.X.X:5000/api/image/pull \
  -H "X-API-Key: your-secret-key-12345"
```

---

## 🌍 Modelli Disponibili

Di default sono installati questi modelli (o simili):

| Modello | Uso | VRAM | Speed |
|---------|-----|------|-------|
| `Qwen2.5-Coder-7B-Instruct-AWQ` | 💻 Programmazione | ~6GB | ⚡⚡ |
| `Qwen2.5-7B-Instruct-AWQ` | 💬 Chat generale | ~6GB | ⚡⚡ |
| `DeepSeek-R1-Distill-Qwen-7B-AWQ` | 🧠 Ragionamento | ~6GB | ⚡ |

Vedi la lista completa:
```bash
curl http://192.168.X.X:5000/v1/models
```

---

## 🔧 Troubleshooting

### "Connection refused" o "Network unreachable"
- [ ] Il server è acceso?
- [ ] Sei nella stessa rete WiFi?
- [ ] L'IP è corretto? (Prova a pingare l'indirizzo)
- [ ] Firewall blocca la porta 5000?

### "Model not found"
- [ ] Il modello esiste? (Chiedi al proprietario)
- [ ] Scrivi il nome esatto (case-sensitive!)
- [ ] Lista i modelli disponibili: `curl http://IP:5000/v1/models`

### "timeout" / "Server taking too long"
- [ ] Il modello si sta caricando in VRAM (primo avvio)
- [ ] Attendi 1-2 minuti
- [ ] Prova a richiedere il modello di nuovo

### Connessione Tailscale non funziona
- [ ] Tailscale è attivo su entrambi i PC?
- [ ] Accessi con lo stesso account Tailscale?
- [ ] Prova: `tailscale status` nel terminale

---

## 📞 Supporto

Se hai problemi:
1. Chiedi al proprietario del server l'IP corretto
2. Verifica di essere nella stessa rete (Ping)
3. Prova prima il test CLI (cURL)
4. Controlla i log del server: `sudo journalctl -u vllm-dashboard -f`

---

## ✅ Checklist Connessione

- [ ] Ho l'IP del server
- [ ] Riesco a pingare l'IP
- [ ] Il test cURL funziona: `curl http://IP:5000/v1/models`
- [ ] Ho configurato l'app client (Open WebUI, Continue, etc.)
- [ ] Riesco a fare una richiesta di chat
- [ ] I modelli sono elencati correttamente

**Sei connesso! 🎉**

---

**Documento creato:** 2026-08-13 - vLLM Intel Arc Dashboard v1.3.0
