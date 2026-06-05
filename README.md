# 🎭 Telegram Sticker ↔ Image Bot

Converts between Telegram stickers and images/GIFs in both directions.

## Features

| Input | Output |
|-------|--------|
| Static sticker (WEBP) | PNG image |
| Animated sticker (TGS/Lottie) | GIF |
| Video sticker (WEBM) | GIF |
| PNG / JPG / WEBP image | Static sticker |
| GIF | Video sticker (WEBM/VP9) |

---

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy your **BOT_TOKEN**

### 2. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install -y ffmpeg python3-pip
# Optional: lottie2gif for animated sticker rendering
pip install lottie-python
```

**macOS (Homebrew):**
```bash
brew install ffmpeg
pip install lottie-python
```

### 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Your Bot Token

Either set an environment variable:
```bash
export BOT_TOKEN="your_token_here"
```

Or edit `bot.py` line 20:
```python
BOT_TOKEN = "your_token_here"
```

### 5. Run the Bot

```bash
python bot.py
```

---

## How Sticker Types Work

### Static Stickers (WEBP)
- Telegram stores them as 512×512 WEBP files
- Converted to PNG using Pillow
- Images → stickers are padded to 512×512 WEBP

### Animated Stickers (TGS)
- `.tgs` = gzipped Lottie JSON animation
- Converted to GIF using `lottie-python`
- Requires `lottie-python` or `lottie2gif` CLI tool
- Fallback: raw `.tgs` file is sent if conversion fails

### Video Stickers (WEBM)
- `.webm` with VP9 codec, transparent background
- Converted to GIF using `ffmpeg`
- GIF → video sticker: uses ffmpeg VP9 encoding at 512×512

---

## Deployment

### Run as a systemd service

```ini
# /etc/systemd/system/stickerbot.service
[Unit]
Description=Telegram Sticker Bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-sticker-bot
Environment=BOT_TOKEN=your_token_here
ExecStart=/usr/bin/python3 bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable stickerbot
sudo systemctl start stickerbot
```

### Docker

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install lottie-python
COPY bot.py .
CMD ["python", "bot.py"]
```

```bash
docker build -t stickerbot .
docker run -e BOT_TOKEN=your_token_here stickerbot
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Animated sticker → shows raw `.tgs` | Install `lottie-python`: `pip install lottie-python` |
| GIF conversion fails | Install `ffmpeg`: `apt install ffmpeg` |
| Sticker is too large | Bot auto-resizes to 512×512 |
| Bot doesn't respond | Check `BOT_TOKEN` is correct |
