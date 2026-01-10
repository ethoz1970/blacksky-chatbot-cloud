# Blacksky Chatbot

A lightweight conversational AI chatbot for Blacksky LLC, built to run on both development machines (Mac) and resource-constrained devices (Raspberry Pi 500).

## Features

- **Company Knowledge**: Answers questions about Blacksky LLC services
- **Personality**: Dry wit, tech jokes, and poetry on demand
- **Efficient**: Runs on TinyLlama 1.1B (Q4_K_M quantized)
- **Platform-Aware**: Auto-detects Mac vs Pi and optimizes accordingly
- **Conversation Memory**: Maintains context across exchanges (with sliding window)

## Quick Start

### 1. Setup Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (Mac with Metal)
CMAKE_ARGS="-DLLAMA_METAL=on" pip install -r requirements.txt

# OR for Raspberry Pi (CPU only)
pip install -r requirements.txt
```

### 2. Download Model

```bash
python download_model.py
```

This downloads the ~700MB quantized TinyLlama model to `./models/`

### 3. Run

**CLI Mode** (for testing):
```bash
python chatbot.py
```

**Server Mode** (API):
```bash
python server.py
```

Server runs on `http://localhost:8000`

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/chat` | POST | Send message, get response |
| `/clear` | POST | Clear conversation history |
| `/stats` | GET | Get current stats |

### Example Request

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about Blacksky"}'
```

## Configuration

Edit `config.py` to adjust:

- `N_CTX`: Context window size (smaller = faster)
- `MAX_TOKENS`: Max response length
- `MAX_HISTORY_TURNS`: Conversation memory depth
- `TEMPERATURE`: Response creativity (0.0-1.0)

## Raspberry Pi Deployment

1. Install Raspberry Pi OS Lite (64-bit)
2. Clone this repo
3. Install dependencies: `pip install -r requirements.txt`
4. Run as systemd service (see below)

### Systemd Service

Create `/etc/systemd/system/blacksky-chatbot.service`:

```ini
[Unit]
Description=Blacksky Chatbot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/blacksky-chatbot
ExecStart=/home/pi/blacksky-chatbot/venv/bin/python server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl enable blacksky-chatbot
sudo systemctl start blacksky-chatbot
```

## Project Structure

```
blacksky-chatbot/
├── README.md
├── requirements.txt
├── config.py          # Platform detection & settings
├── prompts.py         # System prompts & company info
├── chatbot.py         # Core chat logic (CLI mode)
├── server.py          # FastAPI server
├── download_model.py  # Model downloader
└── models/            # Downloaded model files
```

## License

Proprietary - Blacksky LLC
# Google OAuth added
