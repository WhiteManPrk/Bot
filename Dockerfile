# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install ffmpeg and system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates \
	ffmpeg \
	&& rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
	PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python deps (runtime only)
COPY pyproject.toml README.md /app/
RUN pip install --upgrade pip setuptools wheel && \
	pip install \
		"aiogram==3.7.0" \
		"aiohttp~=3.9.5" \
		"pydantic>=2.7,<2.8" \
		"python-dotenv==1.0.1" \
		"yt-dlp==2024.8.6"

# Copy source
COPY bot /app/bot

# Create temp dir default
ENV TEMP_DIR=/tmp/telegram-audio-bot \
	FFMPEG_PATH=ffmpeg

# BOT_TOKEN and others should be provided at runtime
# CMD runs the bot
CMD ["python", "-m", "bot.main"]
