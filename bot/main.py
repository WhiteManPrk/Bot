import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, BufferedInputFile
import aiofiles

from .utils.downloader import download_video, DownloadError
from .utils.audio import extract_audio_ffmpeg, DownloadError as AudioError
from .config import BOT_TOKEN, TEMP_DIR, MAX_FILE_SIZE

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())

@dp.message(Command("start"))
async def start_handler(message: Message):
    """Обработчик команды /start"""
    welcome_text = (
        "🎵 <b>Привет! Я бот для извлечения аудио из видео</b>\n\n"
        "📹 Отправь мне:\n"
        "• Ссылку на видео (YouTube, Yandex Disk, прямые ссылки)\n"
        "• Или загрузи видеофайл напрямую\n\n"
        "🎧 Я извлеку аудио и отправлю тебе MP3 файл\n\n"
        "ℹ️ Поддерживаемые платформы:\n"
        "✅ YouTube\n"
        "✅ Yandex Disk\n" 
        "✅ Прямые ссылки на видео\n"
        "✅ Загруженные файлы\n\n"
        "❌ Для VK, Instagram, TikTok - загружай файлы напрямую"
    )
    await message.answer(welcome_text)

@dp.message(Command("help"))
async def help_handler(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "🆘 <b>Помощь</b>\n\n"
        "<b>Как использовать:</b>\n"
        "1. Отправь ссылку на видео или загрузи файл\n"
        "2. Дождись обработки\n"
        "3. Получи MP3 файл\n\n"
        "<b>Ограничения:</b>\n"
        f"• Максимальный размер файла: {MAX_FILE_SIZE // (1024*1024)} МБ\n"
        "• Время обработки зависит от размера видео\n\n"
        "<b>Команды:</b>\n"
        "/start - Начать работу\n"
        "/help - Показать эту справку"
    )
    await message.answer(help_text)

@dp.message(lambda message: message.text and (
    message.text.startswith('http://') or 
    message.text.startswith('https://')
))
async def url_handler(message: Message):
    """Обработчик URL ссылок"""
    url = message.text.strip()
    logger.info(f"Processing URL: {url}")
    
    # Отправляем начальное сообщение
    status_msg = await message.answer("🔍 Анализ ссылки...")
    
    try:
        # Создаем временную директорию для этого пользователя
        user_temp_dir = os.path.join(TEMP_DIR, f"user_{message.from_user.id}")
        os.makedirs(user_temp_dir, exist_ok=True)
        
        # Callback для отслеживания прогресса
        async def on_progress(stage: str, percent: float = 0):
            try:
                text = f"{stage}"
                if percent > 0:
                    text += f" {percent:.1f}%"
                
                await status_msg.edit_text(text)
                
            except Exception as e:
                logger.warning(f"Progress update failed: {e}")
        
        # Скачиваем видео
        await on_progress("📥 Скачивание видео...")
        video_path, title = await download_video(url, user_temp_dir, on_progress)
        
        # Извлекаем аудио
        await on_progress("🎵 Извлечение аудио...")
        audio_path = await extract_audio_ffmpeg(video_path, user_temp_dir)
        
        # Проверяем размер файла
        audio_size = os.path.getsize(audio_path)
        if audio_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Файл слишком большой ({audio_size // (1024*1024)} МБ). "
                f"Максимум: {MAX_FILE_SIZE // (1024*1024)} МБ"
            )
            return
        
        # Отправляем аудио файл
        await on_progress("📤 Отправка файла...")
        
        # Читаем файл
        async with aiofiles.open(audio_path, 'rb') as audio_file:
            audio_data = await audio_file.read()
        
        # Формируем имя файла
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{safe_title[:50]}.mp3" if safe_title else "audio.mp3"
        
        # Отправляем аудио
        audio_file = BufferedInputFile(audio_data, filename=filename)
        await message.answer_audio(
            audio=audio_file,
            title=title,
            caption=f"🎵 <b>{title}</b>\n\n📊 Размер: {audio_size // 1024} КБ"
        )
        
        # Удаляем статусное сообщение
        await status_msg.delete()
        
    except DownloadError as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(f"❌ Ошибка скачивания:\n{str(e)}")
    except AudioError as e:
        logger.error(f"Audio extraction error: {e}")
        await status_msg.edit_text(f"❌ Ошибка извлечения аудио:\n{str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        await status_msg.edit_text("❌ Произошла неожиданная ошибка")
    finally:
        # Очищаем временные файлы
        try:
            import shutil
            if os.path.exists(user_temp_dir):
                shutil.rmtree(user_temp_dir)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

@dp.message(lambda message: message.video or message.document)
async def video_handler(message: Message):
    """Обработчик видео файлов и документов"""
    logger.info(f"Processing uploaded file from user {message.from_user.id}")
    
    # Определяем тип файла
    file_obj = message.video or message.document
    
    if not file_obj:
        await message.answer("❌ Файл не найден")
        return
    
    # Проверяем размер файла
    if file_obj.file_size and file_obj.file_size > MAX_FILE_SIZE:
        await message.answer(
            f"❌ Файл слишком большой ({file_obj.file_size // (1024*1024)} МБ). "
            f"Максимум: {MAX_FILE_SIZE // (1024*1024)} МБ"
        )
        return
    
    # Отправляем начальное сообщение
    status_msg = await message.answer("📥 Загрузка файла...")
    
    try:
        # Создаем временную директорию
        user_temp_dir = os.path.join(TEMP_DIR, f"user_{message.from_user.id}")
        os.makedirs(user_temp_dir, exist_ok=True)
        
        # Callback для отслеживания прогресса
        async def on_progress(stage: str, percent: float = 0):
            try:
                text = f"{stage}"
                if percent > 0:
                    text += f" {percent:.1f}%"
                
                await status_msg.edit_text(text)
                
            except Exception as e:
                logger.warning(f"Progress update failed: {e}")
        
        # Скачиваем файл от Telegram
        await on_progress("📥 Загрузка файла...")
        file = await bot.get_file(file_obj.file_id)
        
        # Определяем расширение файла
        file_extension = ""
        if file_obj.file_name:
            file_extension = Path(file_obj.file_name).suffix
        elif file_obj.mime_type:
            if "mp4" in file_obj.mime_type:
                file_extension = ".mp4"
            elif "avi" in file_obj.mime_type:
                file_extension = ".avi"
            elif "webm" in file_obj.mime_type:
                file_extension = ".webm"
            else:
                file_extension = ".mp4"  # По умолчанию
        else:
            file_extension = ".mp4"
        
        # Сохраняем файл
        video_path = os.path.join(user_temp_dir, f"uploaded_{file_obj.file_unique_id}{file_extension}")
        await bot.download_file(file.file_path, video_path)
        
        # Извлекаем аудио
        await on_progress("🎵 Извлечение аудио...")
        audio_path = await extract_audio_ffmpeg(video_path, user_temp_dir)
        
        # Проверяем размер аудио файла
        audio_size = os.path.getsize(audio_path)
        if audio_size > MAX_FILE_SIZE:
            await status_msg.edit_text(
                f"❌ Аудио файл слишком большой ({audio_size // (1024*1024)} МБ). "
                f"Максимум: {MAX_FILE_SIZE // (1024*1024)} МБ"
            )
            return
        
        # Отправляем аудио файл
        await on_progress("📤 Отправка аудио...")
        
        # Читаем аудио файл
        async with aiofiles.open(audio_path, 'rb') as audio_file:
            audio_data = await audio_file.read()
        
        # Формируем имя файла
        original_name = file_obj.file_name or "video"
        safe_name = "".join(c for c in original_name if c.isalnum() or c in (' ', '-', '_')).strip()
        filename = f"{Path(safe_name).stem}.mp3" if safe_name else "audio.mp3"
        
        # Отправляем аудио
        audio_file = BufferedInputFile(audio_data, filename=filename)
        await message.answer_audio(
            audio=audio_file,
            title=Path(original_name).stem,
            caption=f"🎵 <b>Аудио из {original_name}</b>\n\n📊 Размер: {audio_size // 1024} КБ"
        )
        
        # Удаляем статусное сообщение
        await status_msg.delete()
        
    except AudioError as e:
        logger.error(f"Audio extraction error: {e}")
        await status_msg.edit_text(f"❌ Ошибка извлечения аудио:\n{str(e)}")
    except Exception as e:
        logger.error(f"Video processing failed: {e}", exc_info=True)
        await status_msg.edit_text("❌ Произошла ошибка при обработке видео")
    finally:
        # Очищаем временные файлы
        try:
            import shutil
            if os.path.exists(user_temp_dir):
                shutil.rmtree(user_temp_dir)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")

@dp.message()
async def unknown_handler(message: Message):
    """Обработчик неизвестных сообщений"""
    await message.answer(
        "❓ Я не понимаю это сообщение.\n\n"
        "Отправь мне:\n"
        "🔗 Ссылку на видео\n"
        "📁 Видео файл\n\n"
        "Или используй /help для получения справки"
    )

async def main():
    """Главная функция запуска бота"""
    # Создаем временную директорию
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    logger.info("Starting Telegram Audio Extractor Bot...")
    logger.info(f"Temp directory: {TEMP_DIR}")
    logger.info(f"Max file size: {MAX_FILE_SIZE // (1024*1024)} MB")
    
    try:
        # Запускаем polling
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.error(f"Bot failed: {e}", exc_info=True)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
