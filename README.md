# Telegram Audio Extractor Bot

Async Telegram bot that downloads a video from a link (Yandex Disk public links, direct links, others via yt-dlp), extracts its audio using ffmpeg, and returns the audio file to the user.

## Requirements
- Docker (or local Python 3.11+ with ffmpeg and yt-dlp)

## Quick start with Docker

1. Copy `.env.example` to `.env` and set `BOT_TOKEN`.

2. Build and run via Docker Compose:
```bash
git clone <your_repo_url>
cd Bot
cp .env.example .env
# edit .env to set BOT_TOKEN
docker compose up --build -d
```

3. Logs:
```bash
docker compose logs -f
```

4. Stop:
```bash
docker compose down
```

## Manual Docker commands
```bash
docker build -t audio-extractor-bot:latest .
docker run --rm \
  --name audio-bot \
  --env-file .env \
  -e TEMP_DIR=${TEMP_DIR:-/tmp/telegram-audio-bot} \
  -e FFMPEG_PATH=${FFMPEG_PATH:-ffmpeg} \
  -v ${TEMP_DIR:-/tmp/telegram-audio-bot}:${TEMP_DIR:-/tmp/telegram-audio-bot} \
  audio-extractor-bot:latest
```

## Local development (optional)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # or use pyproject with pip
PYTHONPATH=. python -m bot.main
```

## Testing
```bash
PYTHONPATH=. pytest -q
```

## Notes
- The bot sends progress updates during download/extraction.
- Yandex public links are resolved via Cloud API; if that fails, bot falls back to yt-dlp.
- Temporary files are stored under `TEMP_DIR` and cleaned after processing.
