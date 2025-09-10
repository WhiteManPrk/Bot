import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv


class Settings(BaseModel):
	bot_token: str = Field(..., alias="BOT_TOKEN")
	temp_dir: str = Field(default="/tmp/telegram-audio-bot", alias="TEMP_DIR")
	ffmpeg_path: str = Field(default="ffmpeg", alias="FFMPEG_PATH")
	yadisk_token: str | None = Field(default=None, alias="YADISK_TOKEN")
	max_file_size_mb: int = Field(default=2000, alias="MAX_FILE_SIZE_MB")

	class Config:
		populate_by_name = True


def get_settings() -> Settings:
	load_dotenv()
	return Settings(
		BOT_TOKEN=os.getenv("BOT_TOKEN", ""),
		TEMP_DIR=os.getenv("TEMP_DIR", "/tmp/telegram-audio-bot"),
		FFMPEG_PATH=os.getenv("FFMPEG_PATH", "ffmpeg"),
		YADISK_TOKEN=os.getenv("YADISK_TOKEN"),
		MAX_FILE_SIZE_MB=int(os.getenv("MAX_FILE_SIZE_MB", "2000")),
	)
