# 🔧 CONFIGURATION GUIDE

Complete guide to configuring vLLM Dashboard (FASE 2+)

---

## 📌 Configuration Precedence

The application loads configuration in this order (later overrides earlier):

1. **Built-in Defaults** - Hard-coded in `app/config.py`
2. **YAML File** - If `vllm-dashboard.yaml` exists
3. **Environment Variables** - From `.env` or shell environment

**Example Precedence:**

```
Defaults (port=5000)
  ↓ (overridden by YAML if exists)
YAML (port=8000)
  ↓ (overridden by env var if set)
ENV (SERVER_PORT=9000)
  ↓
Final Value: port=9000
```

---

## 🚀 Method 1: Environment Variables (Easiest)

### Quick Start

```bash
# Copy example file
cp .env.example .env

# Edit with your settings
nano .env

# Load and run
source .env
python3 -m uvicorn app.main:app --host 0.0.0.0 --port $SERVER_PORT
```

### All Available Variables

**Server Configuration:**
```bash
# HTTP server settings
SERVER_HOST=0.0.0.0              # Bind to all interfaces
SERVER_PORT=5000                 # Port to listen on
SERVER_LOG_LEVEL=INFO            # Logging level: DEBUG, INFO, WARNING, ERROR
```

**GPU Configuration:**
```bash
# GPU memory settings
GPU_MEMORY_UTILIZATION=0.70      # Fraction of VRAM to use (0.0-1.0)
GPU_DTYPE=float16                # Data type: float16, bfloat16, float32
GPU_MAX_MODEL_LEN=2048           # Max sequence length
# GPU_TOTAL_VRAM_MB=16384        # Auto-detected if not set (Intel Arc B580 = 16GB)
```

**Container Configuration:**
```bash
# Podman/Docker settings
CONTAINER_NAME=vllm-intel-arc    # Container name
IMAGE_NAME=docker.io/intel/vllm:0.17.0-xpu  # Image to use

# Timeout settings (NEW in FASE 2)
IMAGE_PULL_TIMEOUT=600           # Pull image timeout (seconds)
CONTAINER_START_TIMEOUT=120      # Start container timeout (seconds)  
CONTAINER_STOP_TIMEOUT=30        # Stop container timeout (seconds)
```

**Model Configuration:**
```bash
# Model loading settings
MODELS_DIR=$HOME/my_models       # Where to store downloaded models
AUTO_LOAD_DEFAULT_MODEL=false    # Load default model on startup
DEFAULT_MODEL=                   # Default model name (if AUTO_LOAD=true)
```

**Security Configuration:**
```bash
# Security settings
API_KEY=your-secret-key          # API key for protected endpoints
# (leave empty or unset to disable API key protection)
```

### Using .env with systemd

To make systemd load `.env` automatically:

Edit `vllm-dashboard.service`:
```ini
[Service]
EnvironmentFile=/path/to/.env
```

---

## 📄 Method 2: YAML File (Production Recommended)

### Quick Start

```bash
# Copy template
cp vllm-dashboard.yaml.example vllm-dashboard.yaml

# Edit with your settings
nano vllm-dashboard.yaml

# Run (will auto-load YAML)
python3 app/main.py
```

### Example Configuration

```yaml
# vllm-dashboard.yaml

server:
  host: 0.0.0.0
  port: 5000
  log_level: INFO
  reload: false

gpu:
  memory_utilization: 0.70
  dtype: float16
  max_model_len: 2048
  # total_vram_mb: 16384    # Auto-detected if not set
  # total_vram_mb: 12288    # Or set explicitly for A770 (12GB)

podman:
  container_name: vllm-intel-arc
  image_name: docker.io/intel/vllm:0.17.0-xpu
  image_pull_timeout: 600        # seconds
  container_start_timeout: 120   # seconds
  container_stop_timeout: 30     # seconds

model:
  models_dir: ~/my_models
  auto_load_default_model: false
  default_model: ""

security:
  api_key: your-secret-key
  enable_cors: true
  cors_origins: []  # Auto-detected (localhost, LAN, Tailscale)
```

### Customization Examples

**Example 1: High-VRAM Setup (A770 with 16GB)**
```yaml
gpu:
  memory_utilization: 0.85
  dtype: bfloat16
  max_model_len: 4096
  total_vram_mb: 16384
```

**Example 2: Low-VRAM Setup (A380 with 4GB)**
```yaml
gpu:
  memory_utilization: 0.80
  dtype: float8  # Requires special quantization
  max_model_len: 1024
  total_vram_mb: 4096
```

**Example 3: Development Setup**
```yaml
server:
  port: 8000
  log_level: DEBUG
  reload: true

security:
  api_key: ""  # Disable API key in development
```

**Example 4: Production Setup**
```yaml
server:
  host: 192.168.1.100
  port: 5000
  log_level: WARNING

security:
  api_key: super-secret-key-change-this

podman:
  image_pull_timeout: 900      # More time for slow networks
  container_start_timeout: 180  # More time for large models
```

---

## 🔀 Method 3: Mixed (YAML + Environment Overrides)

You can use YAML as the base configuration and override specific values with environment variables:

```bash
# Start with YAML configuration
# Create vllm-dashboard.yaml with most settings

# Then override specific values at runtime
export SERVER_PORT=8000
export API_KEY=production-key
python3 app/main.py
```

This is useful for:
- Deploying same YAML to multiple servers
- Changing port/API key per environment without editing YAML
- CI/CD pipelines

---

## 🎯 Use Cases & Recommendations

### Local Development
**Method:** Environment Variables (.env)
```bash
cp .env.example .env
nano .env      # Set API_KEY="" for easier testing
source .env
python3 -m uvicorn app.main:app --reload
```

### Raspberry Pi / Low Resources
**Method:** YAML
```yaml
gpu:
  memory_utilization: 0.60  # Conservative
  dtype: float8              # Compact
  max_model_len: 512         # Limit context
```

### Multi-Container Deployment (Docker Swarm / Kubernetes)
**Method:** Environment Variables + Secrets
```bash
# Use Docker secrets for API_KEY
# Use env vars for port, host, etc
# No YAML file needed in containers
```

### Production Server
**Method:** YAML + systemd
```bash
# 1. Create vllm-dashboard.yaml with all settings
# 2. Systemd EnvironmentFile loads .env for secrets
# 3. systemctl start vllm-dashboard
```

---

## 🔍 Verification

Check current configuration:

```bash
# Method 1: Call API endpoint
curl http://localhost:5000/api/config | jq .

# Method 2: Python script
python3 << 'EOF'
from app.config import get_config
config = get_config()
print(f"Server: {config.server.host}:{config.server.port}")
print(f"GPU VRAM: {config.gpu.total_vram_mb}MB")
print(f"Container: {config.podman.container_name}")
print(f"Models: {config.model.models_dir}")
EOF

# Method 3: Check loaded config file
ls -la vllm-dashboard.yaml  # Check if YAML file exists
echo $SERVER_PORT             # Check env vars
```

---

## 🛠️ Advanced: Adding New Configuration Parameters

To add a new configuration parameter:

1. **Edit `app/config.py`:**
   ```python
   @dataclass
   class ServerConfig:
       host: str = "0.0.0.0"
       port: int = 5000
       new_param: str = "default_value"  # ADD THIS
   ```

2. **Edit `vllm-dashboard.yaml.example`:**
   ```yaml
   server:
     host: 0.0.0.0
     port: 5000
     new_param: default_value  # ADD THIS
   ```

3. **Use in code:**
   ```python
   from app.config import get_config
   config = get_config()
   print(config.server.new_param)  # "default_value"
   ```

4. **Override via environment:**
   ```bash
   export SERVER_NEW_PARAM=custom_value
   python3 app/main.py
   ```

---

## 📊 Configuration Priority Reference

Quick reference for all configuration options:

| Parameter | Default | Env Variable | YAML Path |
|-----------|---------|--------------|-----------|
| Server Host | 0.0.0.0 | SERVER_HOST | server.host |
| Server Port | 5000 | SERVER_PORT | server.port |
| Log Level | INFO | SERVER_LOG_LEVEL | server.log_level |
| GPU Memory Util | 0.70 | GPU_MEMORY_UTILIZATION | gpu.memory_utilization |
| GPU Dtype | float16 | GPU_DTYPE | gpu.dtype |
| GPU Max Model Len | 2048 | GPU_MAX_MODEL_LEN | gpu.max_model_len |
| GPU Total VRAM | Auto-detect | GPU_TOTAL_VRAM_MB | gpu.total_vram_mb |
| Container Name | vllm-intel-arc | CONTAINER_NAME | podman.container_name |
| Image Name | docker.io/intel/vllm:0.17.0-xpu | IMAGE_NAME | podman.image_name |
| Pull Timeout | 600s | IMAGE_PULL_TIMEOUT | podman.image_pull_timeout |
| Start Timeout | 120s | CONTAINER_START_TIMEOUT | podman.container_start_timeout |
| Stop Timeout | 30s | CONTAINER_STOP_TIMEOUT | podman.container_stop_timeout |
| Models Dir | ~/my_models | MODELS_DIR | model.models_dir |
| Auto Load | false | AUTO_LOAD_DEFAULT_MODEL | model.auto_load_default_model |
| Default Model | "" | DEFAULT_MODEL | model.default_model |
| API Key | "" | API_KEY | security.api_key |
| Enable CORS | true | - | security.enable_cors |
| CORS Origins | auto | - | security.cors_origins |

---

## 🚨 Troubleshooting

### Problem: Configuration not loading
```bash
# Check if YAML file exists
ls -la vllm-dashboard.yaml

# Check environment variables
env | grep -i vllm
env | grep -i server

# Enable debug logging
export SERVER_LOG_LEVEL=DEBUG
python3 app/main.py
```

### Problem: GPU VRAM not auto-detected
```bash
# Check auto-detection
python3 -c "from app.gpu_mon import detect_gpu_vram; print(detect_gpu_vram())"

# Manually set VRAM
export GPU_TOTAL_VRAM_MB=12288
python3 app/main.py

# Or in YAML
gpu:
  total_vram_mb: 12288
```

### Problem: Port already in use
```bash
# Find process using port 5000
lsof -i :5000
# or
ss -tulpn | grep 5000

# Use different port
export SERVER_PORT=8000
python3 app/main.py
```

### Problem: API_KEY not working
```bash
# Verify API_KEY is set
echo $API_KEY

# Check config loads API_KEY
curl http://localhost:5000/api/config | grep -i api

# Make sure API_KEY is not empty
export API_KEY="your-secret"
python3 app/main.py
```

---

## 📚 Related Documentation

- [FASE2_COMPLETION.md](FASE2_COMPLETION.md) - What was implemented
- [vllm-dashboard.yaml.example](vllm-dashboard.yaml.example) - Full YAML template
- [.env.example](.env.example) - Environment variables template
- [implementation_plan.md](implementation_plan.md) - Roadmap

---

**Version:** FASE 2  
**Last Updated:** 2026-08-13  
**For Questions:** See CLIENT_INTEGRATION_GUIDE.md or implementation_plan.md
