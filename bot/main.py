import asyncio
import logging
import os
from contextlib import suppress
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, FSInputFile, Video
from aiogram.client.default import DefaultBotProperties

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
		"Отправьте ссылку на видео (Яндекс.Диск, Mail, прямые ссылки) или загрузите видеофайл напрямую. Я извлеку аудио и пришлю файл.")


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
				# Schedule the coroutine to run in the background
				loop = asyncio.get_event_loop()
				loop.create_task(status_msg.edit_text(text))

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
		error_msg = str(e)
		if "Sign in to confirm you're not a bot" in error_msg:
			await status_msg.edit_text("❌ YouTube заблокировал доступ. Попробуйте другой источник или загрузите видео напрямую.")
		elif "Unsupported URL" in error_msg:
			await status_msg.edit_text("❌ Неподдерживаемый тип ссылки. Попробуйте прямую ссылку на видео или загрузите файл напрямую.")
		else:
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


@dp.message(F.video)
async def video_handler(message: Message, bot: Bot) -> None:
	"""Handle direct video file uploads"""
	video: Video = message.video
	status_msg = await message.answer("📥 Получил видеофайл. Скачиваю...")
	temp_dir = Path(settings.temp_dir)
	
	try:
		# Download video file from Telegram
		file_info = await bot.get_file(video.file_id)
		video_path = temp_dir / f"uploaded_{video.file_id}.mp4"
		temp_dir.mkdir(parents=True, exist_ok=True)
		
		await bot.download_file(file_info.file_path, video_path)
		
		# Check file size
		if video_path.stat().st_size > settings.max_file_size_mb * 1024 * 1024:
			await status_msg.edit_text("❌ Видеофайл слишком большой")
			video_path.unlink(missing_ok=True)
			return
		
		await status_msg.edit_text("🎵 Извлекаю аудио из загруженного видео...")
		
		progress_last = ""
		def on_progress(stage: str, percent):
			nonlocal progress_last
			text = "🎵 Обработка аудио..." if stage == "processing" else "✅ Завершаю..."
			if text != progress_last:
				progress_last = text
				# Schedule the coroutine to run in the background
				loop = asyncio.get_event_loop()
				loop.create_task(status_msg.edit_text(text))
		
		result = await run_extract_audio(
			video_path,
			temp_dir,
			ffmpeg_path=settings.ffmpeg_path,
			format="mp3",
			bitrate="192k",
			progress_cb=on_progress,
		)
		
		await status_msg.edit_text("📤 Отправляю аудиофайл...")
		audio_file = FSInputFile(result.output_path)
		await message.answer_document(audio_file, caption="Готово! 🎧")
		await status_msg.edit_text("✅ Готово. Удаляю временные файлы...")
		
	except Exception as e:
		logger.exception("Video processing failed")
		await status_msg.edit_text("❌ Ошибка обработки видео")
	finally:
		# Cleanup
		with suppress(Exception):
			if 'video_path' in locals() and video_path.exists():
				video_path.unlink()
		await asyncio.sleep(0.1)


async def main() -> None:
	if not settings.bot_token:
		raise RuntimeError("BOT_TOKEN is not set")
	bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
	await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
	asyncio.run(main())
