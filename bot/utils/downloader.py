import os
import asyncio
import aiohttp
import yt_dlp
import subprocess
from typing import Optional, Tuple
import re
import tempfile
from pathlib import Path

class DownloadError(Exception):
    """Исключение для ошибок загрузки"""
    pass

async def download_and_extract_audio(url: str, temp_dir: str, progress_callback=None) -> str:
    """
    Основная функция: скачивает видео и извлекает аудио
    
    Returns:
        str: Путь к MP3 файлу
    """
    try:
        # Скачиваем видео
        video_path, title = await download_video(url, temp_dir, progress_callback)
        
        # Извлекаем аудио
        if progress_callback:
            await progress_callback("🎵 Извлечение аудио...")
            
        audio_path = await extract_audio_ffmpeg(video_path, temp_dir)
        
        # Удаляем исходное видео
        try:
            os.remove(video_path)
        except:
            pass
            
        return audio_path
        
    except Exception as e:
        raise DownloadError(f"Ошибка обработки: {str(e)}")

async def extract_audio_ffmpeg(video_path: str, temp_dir: str) -> str:
    """Извлечение аудио с помощью ffmpeg"""
    try:
        # Генерируем имя для аудио файла
        base_name = Path(video_path).stem
        audio_path = os.path.join(temp_dir, f"{base_name}.mp3")
        
        # Команда ffmpeg для извлечения аудио
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn',  # Без видео
            '-acodec', 'libmp3lame',  # MP3 кодек
            '-ab', '192k',  # Битрейт 192 kbps
            '-ar', '44100',  # Частота дискретизации
            '-y',  # Перезаписать существующий файл
            audio_path
        ]
        
        # Запускаем ffmpeg
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8') if stderr else 'Unknown ffmpeg error'
            raise DownloadError(f"FFmpeg ошибка: {error_msg}")
            
        if not os.path.exists(audio_path):
            raise DownloadError("Аудио файл не был создан")
            
        return audio_path
        
    except Exception as e:
        raise DownloadError(f"Ошибка извлечения аудио: {str(e)}")

async def download_video(url: str, temp_dir: str, progress_callback=None) -> Tuple[str, str]:
    """Скачивает видео по URL"""
    try:
        os.makedirs(temp_dir, exist_ok=True)
        
        # Проверяем тип ссылки
        if "disk.yandex" in url or "yadi.sk" in url:
            return await download_yandex_disk(url, temp_dir, progress_callback)
        elif "cloud.mail.ru/public" in url:
            return await download_mail_ru(url, temp_dir, progress_callback)
        else:
            return await download_with_ytdlp(url, temp_dir, progress_callback)
            
    except Exception as e:
        raise DownloadError(f"Ошибка при скачивании: {str(e)}")

async def download_yandex_disk(url: str, temp_dir: str, progress_callback=None) -> Tuple[str, str]:
    """Скачивание с Яндекс.Диска"""
    try:
        # Получаем прямую ссылку через API
        api_url = f"https://cloud-api.yandex.net/v1/disk/public/resources/download?public_key={url}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status == 200:
                    data = await response.json()
                    download_url = data.get('href')
                    if download_url:
                        return await download_direct_link(download_url, temp_dir, progress_callback)
                        
        # Fallback на yt-dlp
        return await download_with_ytdlp(url, temp_dir, progress_callback)
        
    except Exception as e:
        # Если API не работает, используем yt-dlp
        return await download_with_ytdlp(url, temp_dir, progress_callback)

async def download_mail_ru(url: str, temp_dir: str, progress_callback=None) -> Tuple[str, str]:
    """Скачивание с Mail.ru - используем yt-dlp напрямую"""
    return await download_with_ytdlp(url, temp_dir, progress_callback)

async def download_with_ytdlp(url: str, temp_dir: str, progress_callback=None) -> Tuple[str, str]:
    """Скачивание через yt-dlp"""
    def progress_hook(d):
        if progress_callback and d['status'] == 'downloading':
            try:
                percent = d.get('_percent_str', 'N/A')
                speed = d.get('_speed_str', 'N/A')
                asyncio.create_task(progress_callback(f"📥 Скачивание: {percent} ({speed})"))
            except Exception:
                pass
    
    # Генерируем уникальное имя файла
    timestamp = int(asyncio.get_event_loop().time())
    output_template = os.path.join(temp_dir, f'video_{timestamp}_%(title)s.%(ext)s')
    
    ydl_opts = {
        'outtmpl': output_template,
        'format': 'best[ext=mp4]/best[ext=webm]/best',  # Предпочитаем mp4
        'progress_hooks': [progress_hook],
        'no_warnings': False,
        'extractaudio': False,  # Мы будем извлекать аудио отдельно
        'embed_subs': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
        'ignoreerrors': False,
    }
    
    try:
        loop = asyncio.get_event_loop()
        
        def run_ytdl():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'video')
                filename = ydl.prepare_filename(info)
                ydl.download([url])
                return filename, title
        
        # Запускаем yt-dlp в отдельном потоке
        filename, title = await loop.run_in_executor(None, run_ytdl)
        
        if os.path.exists(filename):
            return filename, title
        else:
            raise DownloadError("Файл не был скачан")
            
    except Exception as e:
        raise DownloadError(f"Ошибка yt-dlp: {str(e)}")

async def download_direct_link(url: str, temp_dir: str, progress_callback=None) -> Tuple[str, str]:
    """Скачивание по прямой ссылке"""
    try:
        # Определяем имя файла
        filename = url.split('/')[-1].split('?')[0]
        if not filename or '.' not in filename:
            filename = 'video.mp4'
            
        # Добавляем timestamp для уникальности
        timestamp = int(asyncio.get_event_loop().time())
        name, ext = os.path.splitext(filename)
        filename = f"{name}_{timestamp}{ext}"
        
        filepath = os.path.join(temp_dir, filename)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    with open(filepath, 'wb') as f:
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback and total_size > 0:
                                percent = (downloaded / total_size) * 100
                                await progress_callback(f"📥 Скачивание: {percent:.1f}%")
                    
                    return filepath, name
                else:
                    raise DownloadError(f"HTTP {response.status}")
                    
    except Exception as e:
        raise DownloadError(f"Ошибка скачивания файла: {str(e)}")

# Дополнительная функция для обработки загруженных файлов
async def process_uploaded_file(file_path: str, temp_dir: str, progress_callback=None) -> str:
    """Обработка загруженного видео файла"""
    try:
        if progress_callback:
            await progress_callback("🎵 Извлечение аудио из загруженного файла...")
            
        return await extract_audio_ffmpeg(file_path, temp_dir)
        
    except Exception as e:
        raise DownloadError(f"Ошибка обработки файла: {str(e)}")
