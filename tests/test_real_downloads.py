"""Test real downloads with various platforms"""
import pytest
import asyncio
from pathlib import Path
from bot.utils.downloader import download_video


@pytest.mark.asyncio
async def test_youtube_download():
    """Test YouTube download with real video"""
    temp_dir = Path('/tmp/test_real_downloads')
    temp_dir.mkdir(exist_ok=True)
    
    # Test with a short YouTube video
    url = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'  # Me at the zoo (first YouTube video)
    
    result = await download_video(url, temp_dir=temp_dir, max_size_mb=50)
    
    assert result.source == "yt-dlp"
    assert result.file_path.exists()
    assert result.size_bytes > 0
    assert result.size_bytes < 50 * 1024 * 1024  # Less than 50MB


@pytest.mark.asyncio
async def test_youtube_rick_roll():
    """Test YouTube download with Rick Roll"""
    temp_dir = Path('/tmp/test_real_downloads')
    temp_dir.mkdir(exist_ok=True)
    
    # Test with Rick Roll (should work)
    url = 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'
    
    result = await download_video(url, temp_dir=temp_dir, max_size_mb=50)
    
    assert result.source == "yt-dlp"
    assert result.file_path.exists()
    assert result.size_bytes > 0
    assert result.size_bytes < 50 * 1024 * 1024  # Less than 50MB


@pytest.mark.asyncio
async def test_mailru_failure():
    """Test Mail.ru failure (should fail gracefully)"""
    temp_dir = Path('/tmp/test_real_downloads')
    temp_dir.mkdir(exist_ok=True)
    
    # Test with Mail.ru link (should fail)
    url = 'https://cloud.mail.ru/public/ZX3m/4RR3okrbf'
    
    with pytest.raises(Exception):  # Should raise DownloadError
        await download_video(url, temp_dir=temp_dir, max_size_mb=50)
