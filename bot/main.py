import asyncio
import logging
import os
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile

from .config import get_settings
from .utils.audio import run_extract_audio, ExtractionError
from .utils.downloader import download_video, DownloadError
from .utils.logging import setup_logging


setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


dp = Dispatcher()


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
	await message.answer(
		"Отправьте ссылку на видео (Яндекс.Диск, Mail, прямые ссылки). Я извлеку аудио и пришлю файл.")


@dp.message(F.text.func(lambda t: t and t.startswith("http")))
async def link_handler(message: Message) -> None:
	url = message.text.strip()
	status_msg = await message.answer("🔎 Получаю ссылку и начинаю загрузку...")
	temp_dir = Path(settings.temp_dir)

	video_result = None
	try:
		video_result = await download_video(url, temp_dir=temp_dir, max_size_mb=settings.max_file_size_mb, yadisk_token=settings.yadisk_token)
		await status_msg.edit_text("📥 Видео загружено. Извлекаю аудио через ffmpeg...")

		progress_last = ""

		def on_progress(stage: str, percent):
			nonlocal progress_last
			text = "🎵 Обработка аудио..." if stage == "processing" else "✅ Завершаю..."
			if text != progress_last:
				progress_last = text
				asyncio.create_task(status_msg.edit_text(text))

		result = await run_extract_audio(
			video_result.file_path,
			temp_dir,
			ffmpeg_path=settings.ffmpeg_path,
			format="mp3",
			bitrate="192k",
			progress_cb=on_progress,
		)

		await status_msg.edit_text("📤 Отправляю аудиофайл пользователю...")
		audio_file = FSInputFile(result.output_path)
		await message.answer_document(audio_file, caption="Готово! 🎧")
		await status_msg.edit_text("✅ Готово. Удаляю временные файлы...")

	except DownloadError as e:
		logger.exception("Download failed")
		await status_msg.edit_text(f"❌ Ошибка загрузки: {e}")
		return
	except ExtractionError as e:
		logger.exception("Extraction failed")
		await status_msg.edit_text(f"❌ Ошибка извлечения аудио: {e}")
		return
	except Exception as e:
		logger.exception("Unexpected error")
		await status_msg.edit_text("❌ Непредвиденная ошибка. Попробуйте позже.")
		return
	finally:
		# Cleanup video and possibly audio after sending
		with suppress(Exception):
			if video_result and video_result.file_path.exists():
				video_result.file_path.unlink()
		await asyncio.sleep(0.1)


async def main() -> None:
	if not settings.bot_token:
		raise RuntimeError("BOT_TOKEN is not set")
	bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
	await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
	asyncio.run(main())
