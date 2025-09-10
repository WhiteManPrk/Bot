import os
import asyncio
import subprocess
import logging
from typing import Optional, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioError(Exception):
    """Исключение для ошибок извлечения аудио"""
    pass

# Для совместимости с main.py добавляем алиас
DownloadError = AudioError

async def extract_audio_ffmpeg(
    input_path: str, 
    output_dir: str, 
    progress_callback: Optional[Callable] = None
) -> str:
    """
    Извлекает аудио из видео файла с помощью ffmpeg
    
    Args:
        input_path: Путь к входному видео файлу
        output_dir: Директория для сохранения аудио
        progress_callback: Callback для отслеживания прогресса
        
    Returns:
        str: Путь к созданному аудио файлу
        
    Raises:
        AudioError: При ошибке извлечения аудио
    """
    try:
        # Проверяем существование входного файла
        if not os.path.exists(input_path):
            raise AudioError(f"Входной файл не найден: {input_path}")
        
        # Создаем выходную директорию
        os.makedirs(output_dir, exist_ok=True)
        
        # Генерируем имя выходного файла
        input_name = Path(input_path).stem
        output_path = os.path.join(output_dir, f"{input_name}.mp3")
        
        # Удаляем существующий файл если есть
        if os.path.exists(output_path):
            os.remove(output_path)
        
        if progress_callback:
            try:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback("🎵 Извлечение аудио...", 0)
                else:
                    progress_callback("🎵 Извлечение аудио...", 0)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        
        # Команда ffmpeg для извлечения аудио
        cmd = [
            'ffmpeg',
            '-i', input_path,           # Входной файл
            '-vn',                      # Отключить видео
            '-acodec', 'libmp3lame',    # Кодек MP3
            '-b:a', '192k',             # Битрейт 192 kbps
            '-ar', '44100',             # Частота дискретизации 44.1 kHz
            '-ac', '2',                 # Стерео (2 канала)
            '-y',                       # Перезаписать существующий файл
            output_path
        ]
        
        logger.info(f"Running ffmpeg: {' '.join(cmd)}")
        
        if progress_callback:
            try:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback("🎵 Обработка аудио...", 50)
                else:
                    progress_callback("🎵 Обработка аудио...", 50)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        
        # Запускаем ffmpeg асинхронно
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        # Проверяем результат выполнения
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else 'Unknown ffmpeg error'
            logger.error(f"FFmpeg failed with return code {process.returncode}: {error_msg}")
            raise AudioError(f"Ошибка ffmpeg: {error_msg}")
        
        # Проверяем создание файла
        if not os.path.exists(output_path):
            raise AudioError("Аудио файл не был создан")
        
        # Проверяем размер файла
        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise AudioError("Созданный аудио файл пустой")
        
        if progress_callback:
            try:
                if asyncio.iscoroutinefunction(progress_callback):
                    await progress_callback("✅ Аудио готово", 100)
                else:
                    progress_callback("✅ Аудио готово", 100)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
        
        logger.info(f"Audio extraction successful: {output_path} ({file_size} bytes)")
        return output_path
        
    except AudioError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during audio extraction: {e}", exc_info=True)
        raise AudioError(f"Неожиданная ошибка: {str(e)}")

def check_ffmpeg_availability() -> bool:
    """
    Проверяет доступность ffmpeg в системе
    
    Returns:
        bool: True если ffmpeg доступен
    """
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False

# Функция инициализации для проверки зависимостей
async def init_audio_module():
    """
    Инициализирует аудио модуль и проверяет зависимости
    """
    logger.info("Initializing audio module...")
    
    if not check_ffmpeg_availability():
        logger.error("FFmpeg not found! Please install FFmpeg.")
        raise AudioError("FFmpeg не найден. Установите FFmpeg для работы с аудио.")
    
    logger.info("Audio module initialized successfully")
