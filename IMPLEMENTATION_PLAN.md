# Piano di Miglioramento — vLLM Intel Arc Dashboard

**Data analisi:** 21 agosto 2026 · **Branch:** `master` (HEAD `397ce59`)
**Metodo:** lettura del codice + **misure sulla macchina reale** (B580, container in esecuzione durante l'analisi).

Il documento è diviso in due parti:

- **[Parte A — Direzione del progetto](#parte-a--direzione-del-progetto)**: cosa serve davvero a questo progetto su una Arc B580 da 12 GB, cosa va tolto perché non produce valore, cosa manca. È la parte che conta.
- **[Parte B — Difetti del codice esistente](#parte-b--difetti-del-codice-esistente)**: bug list dettagliata (sicurezza, correttezza, qualità).

---

## Misure di riferimento (raccolte il 21/08/2026 su questa macchina)

Tutto ciò che segue si basa su questi dati, non su supposizioni.

| Misura | Valore rilevato |
|---|---|
| GPU | Intel Arc B580 `8086:e20b`, 12 GB, driver `xe` — **unica GPU, nessuna iGPU** |
| Modello in esecuzione | `Llama-3.1-8B-Instruct-AWQ` |
| Throughput misurato | **63,9 tok/s** (64 tok) · **65,9 tok/s** (251 tok), prompt 48 tok |
| VRAM occupata | **11,41 / 12,0 GB (95,1 %)** |
| Temperatura / clock | 46 °C · 1200 MHz (potenza: `None` → telemetria incompleta) |
| KV cache allocata da vLLM | **38.272 token** |
| `--max-model-len` effettivo | **2.048 token** (il modello ne supporta 131.072) |
| Tempo di init engine | **23,91 s** (+ caricamento pesi ⇒ ~40-60 s per cambio modello) |
| Prefix cache hit rate | 45-75 % (attiva e funzionante) |
| Immagine container | `intel/vllm:0.21.0-xpu` = **21,3 GB** |
| Disco | 325 GB usati su 468 GB (74 %), 120 GB liberi |
| Modelli in `~/my_models` | 7 modelli, 44 GB totali |

Warning emesso da vLLM e attualmente ignorato dal progetto:

```
WARNING [xpu.py:214] XPU Graph is disabled by environment variable,
        please set VLLM_XPU_ENABLE_XPU_GRAPH=1 to enable it.
INFO  [kv_cache_utils.py:1710] GPU KV cache size: 38,272 tokens
INFO  [kv_cache_utils.py:1711] Maximum concurrency for 2,048 tokens per request: 18.69x
```

---

# Parte A — Direzione del progetto

## A0. La conclusione in una riga

**Il motore è quello giusto, la configurazione no.** 65 tok/s su un 8B quantizzato AWQ sono un ottimo risultato per una B580 (vLLM+XPU+AWQ funziona bene: non va sostituito). Il problema è che il progetto ha investito centinaia di righe in infrastruttura generica — cache TTL, modulo security, health check "Kubernetes-style", CI su tre versioni di Python — e **zero righe** nel lavoro specifico che una GPU da 12 GB richiede: far entrare il modello nella VRAM nel modo migliore possibile. Il risultato è misurabile: la macchina sta usando il 95 % della VRAM per offrire una finestra di contesto di **2.048 token su un modello che ne supporta 131.072**.

## A1. Il difetto che conta più di tutti gli altri messi insieme

**Stai pagando 11,4 GB di VRAM per usarne il 5 %.**

vLLM ha allocato una KV cache da **38.272 token**, ma `--max-model-len` è **2.048**: ogni richiesta può usare al massimo 2.048 token, il resto della cache resta inutilizzabile. Sono ~1,5 pagine di testo di contesto su un Llama 3.1 che ne regge 131.072.

Perché succede: il calcolo dinamico del contesto esiste (`app/main.py:181-195`) ma **è raggiungibile solo dal percorso di auto-switch** (richieste OpenAI/Ollama che chiedono un modello diverso da quello attivo). Quando avvii dalla dashboard, `/api/start` prende il valore del campo `max-model-len` della UI, che parte da 2048 e resta lì. Il percorso "manuale" — cioè quello che usi tu — non calcola niente.

E c'è di peggio: **il calcolo automatico, se fosse eseguito, farebbe fallire l'avvio**. L'euristica è `tokens = kv_budget_gb * 15000` (`app/main.py:191`). Per il modello attualmente caricato:

```
budget    = 12 GB × 0,86           = 10,32 GB
kv_budget = 10,32 − 5,4 (size_gb)  =  4,92 GB
tokens    = 4,92 × 15.000          = 73.800  →  max_model_len = 73.800
```

Ma la capacità reale misurata è **38.272 token**. vLLM rifiuta l'avvio quando `max_model_len` supera la capacità della KV cache (`The model's max seq len is larger than the maximum number of tokens that can be stored in KV cache`). **L'auto-switch è rotto per gli 8B su questa macchina**, ed è probabilmente il motivo per cui di fatto giri con 2048 fisso.

L'errore dell'euristica è che il costo per token non è una costante: dipende da layer, KV-head e head-dim del modello.

```
byte_per_token = 2 (K+V) × n_layer × n_kv_head × head_dim × byte_dtype
```

| Modello (in `~/my_models`) | layer | kv-head | KiB/token | token per GB |
|---|---|---|---|---|
| Qwen2.5-7B-AWQ | 28 | 4 | 56 | 18.300 |
| Llama-3.1-8B-AWQ | 32 | 8 | **128** | **8.000** |
| Llama-3.2-3B | 28 | 8 | 112 | 9.150 |
| gemma-2-2b-it | 26 | 4 | 52 | 19.700 |

L'euristica usa 15.000 per tutti: sovrastima del **+87 %** su Llama-3.1-8B (avvio fallito) e sottostima del **−18 %** su Qwen2.5-7B (contesto regalato via).

**Cosa fare — intervento singolo a più alto valore dell'intero progetto:**

1. Estendere `scan_models` (`app/podman_cli.py:74-86`, legge già `config.json`) per esporre `num_hidden_layers`, `num_key_value_heads`, `hidden_size`, `num_attention_heads`, `torch_dtype`.
2. Una funzione `plan_model_launch(model_meta, gpu) -> LaunchPlan` che calcola pesi, byte/token reali, contesto massimo ottenibile, e ritorna `max_model_len` con un margine di sicurezza (85 % del budget KV).
3. **Usarla in entrambi i percorsi** (`/api/start` e auto-switch), non solo in uno.
4. Mostrarla nella UI **prima** di avviare: `Llama-3.1-8B-AWQ → pesi 5,0 GB · KV 4,9 GB · contesto max ≈ 32.000 token · ✅ entra in 12 GB`. Il campo "max model len" diventa uno slider con il massimo calcolato, non una casella vuota con 2048.

Beneficio immediato, senza cambiare hardware né motore: **da 2.048 a ~32.000 token di contesto utilizzabile**, cioè da "non ci sta un file sorgente" a "ci sta un progetto intero".

## A2. `--enforce-eager` hardcoded: stai disattivando l'ottimizzazione che Intel ti offre

`app/podman_cli.py:278` mette `--enforce-eager` sempre, per ogni modello, senza possibilità di disattivarlo. vLLM 0.21 XPU risponde con:

```
WARNING [xpu.py:214] XPU Graph is disabled by environment variable,
        please set VLLM_XPU_ENABLE_XPU_GRAPH=1 to enable it.
```

Gli XPU Graph sono l'equivalente Battlemage dei CUDA Graph: eliminano l'overhead di lancio kernel, che nel decode autoregressivo (un kernel per token) è proprio dove si perde tempo. È la singola manopola specifica per Arc che il progetto non tocca.

**Cosa fare:** trasformarlo in un'opzione di configurazione (`gpu.enforce_eager: true`) e **misurare l'A/B** con lo stesso prompt e `max_tokens`:

| Configurazione | tok/s | VRAM | init time | esito |
|---|---|---|---|---|
| `--enforce-eager` (attuale) | **65,9** | 11,41 GB | 23,9 s | baseline misurata |
| `VLLM_XPU_ENABLE_XPU_GRAPH=1`, no eager | da misurare | da misurare | da misurare | ⟵ **esperimento #1** |

Se il guadagno c'è, il default cambia; se causa instabilità o più VRAM, resta eager ma **documentato come scelta consapevole** invece che come riga scritta e mai più rimessa in discussione. Nota: `--enforce-eager` riduce anche l'uso di VRAM, quindi il confronto va fatto a parità di `max_model_len`.

Altre manopole B580-specifiche mai valutate, da mettere nello stesso banco di prova:

- `--kv-cache-dtype fp8` → potenzialmente **raddoppia** il contesto a parità di VRAM (da verificare che il backend XPU lo supporti: se sì, è il secondo intervento di maggior valore dopo A1).
- `--max-num-seqs 16` (`app/podman_cli.py:277`): sensato per servire 16 client, inutile per un utente singolo. Con `--max-num-seqs 4` si liberano slot e si semplifica lo scheduling. Da misurare.
- `--gpu-memory-utilization 0.86` calcolato sulla VRAM **totale**: su un desktop il compositor usa già alcune centinaia di MB. Il valore va calcolato sulla VRAM **libera** letta dalla telemetria che il progetto già possiede.
- Prefix caching: risulta attivo con hit rate 45-75 %, ottimo — ma non è esposto da nessuna parte nella UI, e sarebbe una delle metriche più utili da mostrare.

## A3. L'auto-switch è la funzionalità sbagliata per una GPU singola da 12 GB

Cambiare modello costa **~40-60 s** (init engine 23,9 s misurati + caricamento pesi + JIT SYCL). Con 12 GB ci sta **un modello alla volta**: non esiste "keep-alive multiplo" come in Ollama.

Ma l'architettura attuale fa scattare un cambio di container **a ogni richiesta HTTP** che nomina un modello diverso (`ensure_model_running`, `app/main.py:134-212`). Conseguenze concrete:

- Un client come Open WebUI, che elenca i modelli da `/v1/models` (dove il progetto pubblica **tutti e 7** i modelli su disco, `app/main.py:561-570`) e ne sonda più di uno, può innescare una **catena di riavvii da 60 s l'uno**.
- Due client con preferenze diverse mettono la GPU in thrashing permanente.
- Combinato con il bug P1-1 (riavvio di un modello che sta *già* caricando), si arriva al loop infinito.

L'auto-switch ha senso in un cluster con VRAM abbondante. Qui il modello mentale corretto è quello di un **elettrodomestico a singolo slot**: il modello caricato è una risorsa scarsa, e cambiarlo è un'azione deliberata dell'utente, non un effetto collaterale di una richiesta di chat.

**Riprogettazione proposta:**

1. **Modalità "pinned" come default** (`model.switch_policy: pinned | auto | ask`): con `pinned`, una richiesta per un modello non caricato riceve un **409 Conflict** con un corpo esplicito (`"Il modello X non è caricato. Attivo: Y. Usa la dashboard o POST /api/start per cambiare."`), invece di far ripartire silenziosamente il container.
2. **`/v1/models` pubblica per default solo il modello caricato** (più gli altri sotto un flag `list_all_models: true`). È anche più corretto semanticamente: gli altri non sono servibili in quel momento.
3. Con `auto`, coda esplicita e **una sola richiesta di switch in volo**, con risposta immediata `{"status": "switching", "eta_seconds": 55}` invece di tenere la connessione HTTP appesa per un minuto.
4. Lo switch è **un'operazione protetta da API key**, sempre — è l'azione più costosa che il sistema offre.

## A4. I modelli su disco sono gestiti male, e questo corrompe i calcoli VRAM

Dati reali della cartella `Llama-3.2-3B-Instruct`:

```
model-00001-of-00002.safetensors   4,9 GB   ← serve
model-00002-of-00002.safetensors   1,5 GB   ← serve
original/                          6,0 GB   ← duplicato inutile (consolidated .pth)
.cache/                            ...      ← blob di download HF
─────────────────────────────────────────
totale riportato dalla dashboard:  12 GB  per un modello da 6,4 GB
```

Due conseguenze:

1. **Spreco di disco**: `original/` è la copia PyTorch degli stessi pesi, che vLLM non usa mai. Su 7 modelli e 120 GB liberi non è irrilevante.
2. **Matematica VRAM sbagliata**: `scan_models` somma *tutti* i file (`app/podman_cli.py:50-57`), quindi `size_gb` = 12 invece di 6,4. Quel numero è l'input del calcolo del contesto (`app/main.py:185`): il budget KV risulta negativo e viene clampato a `max(0.5, ...)`, cioè il modello riceve il contesto minimo. **Un errore di download degrada silenziosamente la configurazione di esecuzione.**

**Cosa fare:**

1. Download con `allow_patterns` (`*.safetensors`, `*.json`, `tokenizer*`, `*.model`) escludendo `original/`, `*.pth`, `*.bin` quando esistono i safetensors. Da applicare sia all'endpoint sia agli script.
2. `scan_models` deve calcolare **`weights_gb`** (solo i file effettivamente caricati da vLLM) separatamente da `disk_gb` (totale occupato). Il primo alimenta i calcoli, il secondo la UI.
3. Pulsante "Ottimizza spazio" che elenca e rimuove i duplicati rilevati (`original/`, `.cache/` interne), con anteprima dello spazio recuperabile.
4. Modelli attualmente inutilizzabili con questo stack, da segnalare nella UI invece di lasciarli lì:
   - **`Qwen2-VL-7B-Instruct-AWQ`** (6,5 GB): modello *vision*. La chat della dashboard non ha input immagini e il supporto multimodale su XPU va verificato. Oggi occupa disco e non è usabile.
   - **`gemma-2-2b-it`**: Gemma-2 usa logit softcapping + sliding window; il supporto va verificato sul backend XPU prima di proporlo nel menu.
   - **`Llama-3.2-1B-Instruct`** (4,7 GB su disco per un modello da 2,5 GB): stesso problema di duplicati.

## A5. Cosa togliere — codice che non produce valore per questo caso d'uso

Questa è la parte che hai intuito: c'è parecchia infrastruttura da "checklist enterprise" che su un desktop mono-utente con una GPU non serve, e che costa manutenzione e bug.

| Componente | Righe | Verdetto |
|---|---|---|
| `app/cache.py` (SimpleCache, `@cache`, `@async_cache`, `CACHE_KEYS`) | 183 | **Sostituire.** Esiste per evitare qualche `podman ps`, ma la chiave ignora gli argomenti (bug P1-4) e `async_cache` non è mai usato. Il problema vero non era il numero di chiamate ma il **blocco dell'event loop**. Un singolo task di background che aggiorna uno snapshot di stato ogni 2 s e che tutti leggono risolve entrambe le cose in ~30 righe, e la cache sparisce. |
| `app/security.py` — `get_local_network_ips()`, `verify_origin()`, `DASHBOARD_ORIGINS`, `log_denied_request` | ~100 | **Cancellare.** Mai chiamati: il CORS reale è la regex in `app/main.py:62`. `"http://100.*:5000"` non è nemmeno un origin valido. Restano ~15 righe di verifica chiave, che vanno in `config.py`. |
| `app/config.py` — `ConfigLoader`, `_load_yaml`, `_load_env_vars`, `to_dict`, `to_json`, `reload_config` | 310 | **Sostituire con `pydantic-settings`** (pydantic è già una dipendenza): ~60 righe, validazione dei tipi gratis, precedenza env/file gestita dalla libreria, e spariscono di colpo P1-13 (env non lette), P1-14 (mkdir prima di expanduser) e la doppia classe `SecurityConfig`. |
| `EventBroadcaster` — `get_stats()`, `clear()`, `clear_tail_buffer()` | ~50 su 169 | **Sfoltire.** Il nucleo (queue per subscriber + tail buffer + `put_nowait`) è buono e va tenuto; i metodi di servizio non sono mai chiamati. |
| `app/validators.py` — whitelist di 22 flag vLLM | 244 | **Ripensare.** Esiste per rendere sicuro un campo di testo libero "extra flags" nella UI. Ma esporre la CLI di vLLM in una dashboard è la scelta di design discutibile: il 95 % degli utenti vuole 4 manopole (contesto, quantizzazione KV, eager on/off, num-seqs). Trasformarle in **controlli strutturati** elimina insieme il rischio di injection *e* 244 righe di validazione. Il campo libero resta come "modalità avanzata" dietro un flag di configurazione. |
| `/health` "Kubernetes-style" (`app/main.py:246-291`) | 45 | **Ridurre.** Nessuno orchestra questa app con Kubernetes. Serve però un `/health` **utile alla UI**: `{stato_container, modello, fase_caricamento, %progresso, vram}`. Stesso endpoint, contenuto diverso. |
| CI matrix Python 3.10/3.11/3.12 (`.github/workflows/tests.yml`) | — | **Ridurre a una versione** (quella del venv locale). L'app gira su una macchina specifica; testare tre interpreti costa 3× e non ha mai trovato nulla. Meglio investire il tempo CI in lint + test con podman mockato. |
| 4 script `scripts/download_*.py` + `backup_models.sh` + `restore_models.sh` + `configure_pc.sh` | ~200 | **Consolidare.** Sono workaround nati perché il download dalla dashboard non supporta i token HF (modelli gated) né la selezione dei file. Risolto A4, restano un comando solo. |
| `/api/rm-container` in `PROTECTED_ENDPOINTS` | — | Endpoint **inesistente**; il pulsante chiama `/api/stop`. Rimuovere la voce. |

Totale indicativo: **~700 righe da eliminare o sostituire**, con meno superficie di bug e nessuna perdita di funzionalità reale.

## A6. Cosa aggiungere — le funzionalità che mancano e servono davvero

In ordine di rapporto valore/costo.

### 1. Calcolatore di fit VRAM (vedi A1) — *il motivo per cui esiste una dashboard*
Prima di avviare: pesi, KV, contesto ottenibile, verdetto ✅/⚠️/❌. È l'unica cosa che una dashboard per GPU da 12 GB può offrire e che una CLI non offre.

### 2. Progress bar reale del caricamento — *infrastruttura già presente, non sfruttata*
I log del container sono **già** in streaming verso il browser (`stream_logs` → `/ws/logs`). vLLM emette righe come `Loading safetensors checkpoint shards: 45% Completed`. Basta una regex per trasformare quel flusso in una progress bar e in fasi (`download → caricamento pesi → init engine (~24 s) → warmup → pronto`). Oggi l'utente vede solo un pulsante che dice "avviato con successo" mentre in realtà mancano 40 secondi (bug P1-9).

### 3. Storico della telemetria + tokens/sec — *la dashboard mostra solo l'istante presente*
Non c'è alcun grafico: solo numeri che cambiano. Per tarare una B580 (throttling termico, power limit, effetto del contesto sulla velocità) serve una finestra scorrevole di 10-15 minuti su VRAM, temperatura, potenza, clock e **tok/s**. Un `deque` in memoria e un grafico a linee: nessuna dipendenza nuova, valore alto.

### 4. Utilizzo degli engine GPU — *metrica assente, ed è la prima che si guarda*
La telemetria riporta VRAM, temperatura, clock, potenza — ma **non l'utilizzo della GPU**. Si ricava dai delta di `drm-engine-render`/`drm-engine-compute` negli stessi file `fdinfo` già letti (`app/gpu_mon.py:172`), oppure da `xpu-smi` se installato. Senza questo dato non si distingue "GPU satura" da "collo di bottiglia altrove".

### 5. Preset per modello — *oggi si riconfigura tutto ogni volta*
Un `~/.vllm-dashboard/presets.json` con, per ciascun modello, ultimo `max_model_len`, flag, dtype KV, throughput misurato l'ultima volta. La dashboard propone il preset e mostra "ultima esecuzione: 65,9 tok/s, 32k contesto".

### 6. Banco di prova integrato — *per rispondere alle domande di A2 con i numeri*
Un pulsante "Benchmark" che esegue una generazione standard (prompt fisso, 256 token) e registra tok/s, TTFT, VRAM di picco nello storico. Serve a decidere `enforce-eager` vs XPU Graph, fp8 vs fp16 KV, `max-num-seqs`, **con dati invece che con opinioni**. Costo: ~80 righe, riusando il codice della chat già presente.

### 7. Streaming nella chat della dashboard
La chat interna usa il percorso non-streaming (`app/main.py:514-534`): l'utente guarda uno spinner per 4 secondi invece di vedere i token uscire. Il supporto streaming lato server c'è già; è una modifica solo frontend.

### 8. Tray consapevole dello stato reale
`scripts/tray_indicator.py` interroga solo `systemctl is-active`: sa se il *servizio web* gira, non se un modello è caricato. Con una chiamata a `/health` il tooltip diventa `Llama-3.1-8B · 11,4/12 GB · 46 °C`, e il menu può offrire "Ferma modello (libera 11,4 GB)" — che è l'azione che serve davvero quando vuoi giocare o usare la GPU per altro.

### 9. Igiene del disco
Immagine da 21,3 GB + modelli con duplicati + `~/.cache/vllm-arc` da 1,8 GB, su 120 GB liberi. Una sezione "Spazio" con occupazione per modello, duplicati rimovibili e dimensione della cache SYCL (con pulsante per svuotarla quando si cambia versione dell'immagine).

## A7. La domanda di posizionamento, e la mia raccomandazione

Il progetto oggi è a metà tra due cose e paga i costi di entrambe:

- **Strumento personale per la tua B580**: allora API key, CORS per Tailscale, CI multi-versione, health check k8s e modulo security sono zavorra; il valore sta tutto in A1, A2, A6.
- **Progetto open per possessori di Arc**: allora servono rilevamento hardware oltre la B580 (la tabella PCI c'è già), supporto i915 oltre a `xe`, installer senza `/home/daniele` cablato, e documentazione — ma *anche* la sicurezza va presa sul serio, non lasciata rotta come oggi (Parte B, P0-1).

**Raccomandazione:** dichiarare che è **uno strumento locale mono-utente**, e di conseguenza:

- default `host: 127.0.0.1` (l'esposizione in rete è una scelta esplicita e documentata);
- API key **facoltativa ma funzionante** — la si attiva se e quando si espone in LAN/Tailscale (oggi non funziona affatto: P0-1);
- niente autenticazione multi-utente, niente rate limiting elaborato, niente metriche Prometheus;
- tutto il tempo risparmiato va in A1 (fit VRAM), A2 (tuning B580) e A6 (progress, storico, benchmark).

Il differenziatore di questo progetto non è "un'altra web UI per LLM" — ce ne sono decine e Open WebUI le batte tutte. È **"lo strumento che sa spremere una Arc da 12 GB"**: fit calculator, tuning misurato, telemetria Xe reale. Nessun altro lo fa, ed è esattamente la parte oggi mancante.

## A8. Roadmap rivista (per valore, non per categoria)

| # | Intervento | Rif. | Costo | Valore |
|---|---|---|---|---|
| 1 | `plan_model_launch()` + fit VRAM in UI + uso in **entrambi** i percorsi di avvio | A1, P1-7, P1-8 | 1 g | **Contesto da 2k a ~32k** |
| 2 | `load_dotenv` + `SecurityConfig` unica + header `X-API-Key` nel frontend | P0-1→4 | 0,5 g | Chiude il buco di sicurezza |
| 3 | Snapshot di stato in background (uccide `cache.py` e il blocco dell'event loop) | A5, P1-3, P1-4 | 0,5 g | UI reattiva, −183 righe |
| 4 | Modalità `pinned` + `/v1/models` con solo il modello attivo + niente riavvio se sta caricando | A3, P1-1 | 0,5 g | Basta thrashing e loop |
| 5 | Progress bar reale dai log già in streaming | A6.2, P1-9 | 0,5 g | Sparisce il "successo" falso |
| 6 | Banco di prova + esperimento XPU Graph / fp8 KV / max-num-seqs | A2, A6.6 | 1 g | Tuning con numeri |
| 7 | Download con `allow_patterns` + `weights_gb` vs `disk_gb` + pulizia duplicati | A4 | 0,5 g | Disco e calcoli corretti |
| 8 | Storico telemetria + utilizzo engine + tok/s | A6.3, A6.4, P1-12 | 1 g | La dashboard diventa utile |
| 9 | `pydantic-settings` al posto di `ConfigLoader`; eliminazione codice morto | A5, P1-13→15, P2-1 | 0,5 g | −700 righe |
| 10 | Kill dei processi `podman logs`, backoff WS, fix stream SSE | P1-2, P1-5, P1-6 | 0,5 g | Niente leak |
| 11 | Controlli strutturati al posto del campo "extra flags" | A5 | 0,5 g | −244 righe, meno rischio |
| 12 | Tray con stato reale, igiene disco, preset per modello | A6.5, A6.8, A6.9 | 1 g | Rifinitura |

Le prime cinque voci (~3 giorni) cambiano il progetto da "dashboard che avvia container" a "strumento che sa configurare una B580". Il resto è consolidamento.

---

# Parte B — Difetti del codice esistente

Bug list verificata. Le priorità sono **relative alla Parte A**: un P0 di sicurezza va chiuso comunque, ma se dovessi scegliere tra "sistemare tutti i P2" e "fare A1", A1 vale di più.

## P0 — Bloccanti

### P0-1. Il file `.env` viene ignorato → l'API Key non protegge nulla
**File:** `app/main.py:17-37`, `app/security.py:107`, `app/podman_cli.py:14-18`

Ordine di esecuzione a import-time: `main.py:17` importa `podman_cli` → che a riga 18 chiama `get_config()` leggendo `os.environ`; `main.py:29` importa `security` → `API_KEY = os.getenv(...)` a livello di classe; solo a `main.py:34` viene eseguito `load_dotenv()`. **Troppo tardi.**

Verifica eseguita con un `.env` contenente `API_KEY=segreto123` e `SERVER_PORT=7777`:

```
SecurityConfig.API_KEY   = ''
config.security.api_key  = ''
config.server.port       = 5000
```

**Impatto:** `verify_api_key()` ritorna sempre `True`; `/api/start`, `/api/stop`, `/api/models/delete`, `/api/image/pull`, `/api/models/download` sono aperti a chiunque raggiunga la porta 5000, che `install.sh` e l'unit systemd espongono su `0.0.0.0`.

**Fix:** `load_dotenv()` in cima a `app/config.py`, prima di ogni lettura di `os.environ`; rimuoverlo da `main.py`; test di regressione. Risolto insieme al punto 9 della roadmap (`pydantic-settings` legge il `.env` nativamente).

### P0-2. Due classi `SecurityConfig` divergenti
`app/security.py:75` (attributi di classe da env) vs `app/config.py:73` (dataclass da YAML+env). Il middleware usa la prima, `ensure_model_running` la seconda: **la chiave impostata nello YAML non protegge nulla**. Fondere in una sola fonte, rinominare per evitare la collisione di nomi.

### P0-3. Il frontend non invia mai `X-API-Key`
`app/templates/index.html:478, 503, 681, 717, 751, 767`. Appena la protezione funzionerà, **ogni pulsante restituirà 401**. Serve un helper `apiFetch()` con chiave da `localStorage` e un campo nelle impostazioni.

### P0-4. Confronto chiave non a tempo costante
`app/security.py:148` → `provided_key == cls.API_KEY`. Usare `hmac.compare_digest`.

### P0-5. `delete_model`: fuga dalla models dir via symlink
`app/podman_cli.py:439-461`. `.resolve()` segue i link simbolici e `shutil.rmtree` cancella la destinazione reale; nessun controllo di contenimento. In più `/api/models/delete` (`app/main.py:367-379`) **non chiama `validate_model_name()`**, a differenza di `/api/start`. Fix: rifiutare i symlink, verificare `target.is_relative_to(models_dir)`, validare il nome nell'endpoint.

### P0-6. Endpoint di inferenza pubblici che avviano container
`ensure_model_running` è raggiungibile da `/api/chat`, `/api/generate`, `/v1/*`, tutti in `PUBLIC_ENDPOINTS`. L'unica barriera (`require_api_key_for_autoswitch`) si attiva solo se la chiave esiste — cioè mai, per P0-1. Risolto strutturalmente dalla modalità `pinned` (A3) + default su `127.0.0.1`.

### P0-7. `download_hf_model` costruisce una riga `bash -c` per interpolazione
`app/podman_cli.py:397-403`. Oggi mitigato dai validatori a monte, ma la validazione non è dentro la funzione. Da sostituire con `huggingface_hub.snapshot_download` in `asyncio.to_thread` (che risolve anche `HF_TOKEN` e `allow_patterns`, vedi A4).

## P1 — Bug funzionali

- **P1-1. Riavvio del modello già in caricamento.** `app/main.py:167`: se il modello richiesto è quello attivo ma vLLM sta ancora caricando (40-60 s misurati), il check a 5 s fallisce e il codice **riavvia il container**. Con client che ritentano → loop infinito. Fix: attendere `container_start_timeout` e restituire 504.
- **P1-2. Leak di processi `podman logs -f`.** `app/podman_cli.py:482-528`: il processo figlio non viene mai ucciso; il frontend riconnette ogni 2 s senza backoff (`index.html:901-906`). Fix: `proc.kill()` nel `finally` + backoff esponenziale.
- **P1-3. Chiamate bloccanti nell'event loop.** `get_container_status` (fino a 3 subprocess × 5 s), `scan_models` (stat su ogni file), `delete_model` (`rmtree` sincrono su decine di GB). Fix: `asyncio.to_thread` o snapshot in background (roadmap #3).
- **P1-4. `@cache` ignora gli argomenti.** `app/cache.py:111`: la chiave è solo modulo+nome. `scan_models(dir_diversa)` restituisce il risultato sbagliato. Inoltre `if cached_value is not None` (riga 120) non cachea mai i valori falsy (lista modelli vuota). Risolto eliminando il modulo (A5).
- **P1-5. Stream SSE d'errore malformato.** `app/main.py:603-605`: `err_payload` è `bytes` dentro una f-string → `data: b'{"error":...}'`, non parsabile. Manca anche `data: [DONE]` in chiusura.
- **P1-6. `/v1/completions` senza gestione errori.** `app/main.py:635-649`: nessun `try/except`, `resp.json()` non protetto → 500 con traceback invece di 503. Stesso schema a `:612` e `:735`.
- **P1-7 / P1-8. Calcolo `max_model_len` errato e applicato a un solo percorso.** Vedi A1: `max()` dopo `min()` annulla il limite della finestra del modello (`app/main.py:195`), l'euristica da 15.000 token/GB sbaglia dell'87 % sugli 8B, e il vincolo `128 ≤ x ≤ 32768` di `/api/start` non vale nell'auto-switch.
- **P1-9. `/api/start` dichiara successo prima del caricamento.** `start_container` ritorna appena `podman run -d` esce. Risolto dalla progress bar (A6.2).
- **P1-10. URL API non raggiungibile dai client remoti.** `/api/status` restituisce `http://127.0.0.1:8000/v1` (porta pubblicata solo su loopback): da un altro PC quell'indirizzo non funziona. Va restituito `${origin}/v1`.
- **P1-11. Compatibilità Ollama incompleta.** Mancano `total_duration`/`eval_count`/`prompt_eval_count` nel messaggio finale, il `digest` è finto (`sha256:{nome}`), `/api/ps` riporta `size` **hardcoded a 5,5 GB**, mancano `/api/embeddings`, `/api/pull`, `/api/delete`. *Domanda a monte (A5): serve davvero?* Open WebUI, Continue, Zed e aider parlano tutti OpenAI. Se nessun client in uso richiede Ollama, questo strato va **rimosso** invece che completato.
- **P1-12. Telemetria GPU incompleta.** Solo driver `xe` (su i915 riporterebbe 0 MB — nota di portabilità: **questa macchina usa `xe` e non ha iGPU**, quindi non è un problema qui); hwmon prende la prima `card*` trovata; `gpu_name` è la stringa fissa `"Intel Arc B580 (Xe Driver)"` anche se la tabella PCI riconosce A770/A750/B570; **la potenza risulta `None`** nella misura effettuata (il delta di `energy1_input` richiede due letture, ma la cache a 1 s può restituire il primo campione); manca del tutto l'utilizzo degli engine (A6.4).
- **P1-13. `.env.example` disallineato.** `DEFAULT_MAX_MODEL_LEN` (il codice legge `MAX_MODEL_LEN`), `CONTAINER_STOP_TIMEOUT`, `GPU_TELEMETRY_INTERVAL`, `LOG_DIR`: **tutte ignorate**. `IMAGE_NAME` fermo a `0.17.0-xpu`, `VLLM_HOST=localhost` contro il default `127.0.0.1`.
- **P1-14. Config: percorso YAML relativo alla CWD** (`app/config.py:141`), **`mkdir` prima di `expanduser`** (`:259-263`), nessuna validazione di `dtype`.
- **P1-15. Costanti di `podman_cli` congelate all'import** (`:20-25`): `reload_config()` non ha effetto.
- **P1-16. WebSocket senza autenticazione.** Il middleware HTTP non copre lo scope `websocket`: `/ws/logs` espone i log del container a chiunque, anche a protezione attiva.

## P2 — Qualità e manutenzione

- **P2-1. Codice morto:** `get_local_network_ips`, `verify_origin`, `DASHBOARD_ORIGINS`, `log_denied_request`, `async_cache`, `ChatRequest`, `/api/rm-container`; import inutilizzati (`urllib.request`, `urllib.error`, `BackgroundTasks`); `import re` a metà file (`main.py:61`); `json`/`datetime` re-importati localmente (`:385, :482`). Vedi A5.
- **P2-2. `require_api_key_for_endpoint` usa `startswith`** senza confine (`security.py:110`) e ignora `PATCH`.
- **P2-3. XSS nella chat:** `index.html:846` → `innerHTML = marked.parse(reply)` senza sanitizzazione. L'output del modello può eseguire JS nella pagina che governa i container (e, dopo P0-3, legge la API key da `localStorage`). Serve DOMPurify.
- **P2-4. Dipendenze da CDN esterne** (`index.html:7-12`): Tailwind CDN (esplicitamente non per produzione), `marked`, `highlight.js`, Google Fonts, senza SRI. Su uno strumento locale offline la dashboard perde stile e la chat va in errore JS. Servirli da `app/static/`.
- **P2-5. Test insufficienti e dipendenti dall'ambiente:** nessun test su `podman_cli`, sul middleware, su `EventBroadcaster`, su `ensure_model_running`. `test_api.py:10-17` asserisce `/health == "ok"`, che dipende da podman installato sul runner; `test_cache.py:133` invoca davvero podman e lspci; `from app.main import app` a import-time esegue `lspci` e crea `~/my_models`. Nessun `pytest.ini`, nessuna coverage, nessun lint.
- **P2-6. `requirements.txt` incoerente:** manca `huggingface_hub` (usato da 4 script), `pystray` **non è usato** (il tray usa PyGObject/Ayatana, dipendenza di sistema non documentata), `pillow` serve solo a `generate_icons.py`, nessun pin di versione.
- **P2-7. Percorsi personali versionati:** `/home/daniele/...` in `vllm-dashboard.service` e `vllm-dashboard-tray.desktop`. Gli installer li rigenerano correttamente: rinominare in `.template`. Nota: `install.sh:33` fa `${PROJECT_DIR// /\\ }` — l'escape degli spazi non è il quoting corretto per systemd.
- **P2-8. `install.sh`** non verifica podman, i gruppi `render`/`video`, `/dev/dri`; non genera un `.env` con `API_KEY` pur avviando il servizio su `0.0.0.0`.
- **P2-9. Nessuna gestione dello shutdown:** fermando la dashboard il container resta acceso e trattiene 11,4 GB di VRAM. Inoltre `auto_load_default_model` e `default_model` (`config.py:69-70`) sono documentati nello YAML ma **mai usati dal codice**.
- **P2-10. Osservabilità:** `setup_logging()` gira a import-time con `log_level="INFO"` fisso → `LOG_LEVEL` non ha alcun effetto; `verify_api_key` logga un WARNING a **ogni richiesta** quando non c'è chiave; `SimpleCache.get_stats()` non è esposto.
- **P2-11. Documentazione:** `download_model.sh:23` dice "B580 (16GB VRAM)" — sono **12 GB**; versione `1.4.0` hardcoded in `main.py:56` senza changelog; log e messaggi mescolano italiano e inglese.

---

## Cosa funziona bene e non va toccato

- **La scelta del motore.** 65,9 tok/s su un 8B AWQ è un buon risultato per una B580: vLLM+XPU+AWQ funziona. Ero partito col sospetto che llama.cpp/SYCL fosse più adatto; **la misura dice di no** — quello che llama.cpp darebbe (swap rapido, immagine leggera) non compensa la perdita di throughput. Il motore resta.
- La whitelist in `app/validators.py` è *implementata* correttamente (allow-list + validazione per-flag): la critica in A5 è al fatto che esista quel campo nella UI, non a come è scritta.
- Il workaround documentato in `app/podman_cli.py:300-316` (file temporanei invece di `communicate()` per il deadlock con `rootlessport`): diagnosi non banale, commento eccellente.
- `EventBroadcaster`: tail buffer + `put_nowait` che salta i subscriber lenti invece di bloccare.
- Port publishing su `127.0.0.1` (`podman_cli.py:259`), mount del modello in sola lettura (`:270`), `--ipc=host` e `--group-add keep-groups`: configurazione container corretta per rootless su Arc.
- La cache SYCL/NEO persistente montata su `/cache` (`:264-269`): evita il JIT dei kernel a ogni avvio, 1,8 GB ben spesi.
- `container_lifecycle_lock` e il backoff esponenziale di `wait_for_vllm_ready`.
- Tray + systemd + `.desktop`: l'integrazione desktop è l'istinto giusto per questo tipo di strumento.
