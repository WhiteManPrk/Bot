import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from bot.utils.downloader import download_video, DownloadError


@pytest.mark.asyncio
async def test_download_direct_http(tmp_path: Path, monkeypatch):
	class FakeResp:
		status = 200
		headers = {"Content-Disposition": ''}
		def __init__(self):
			self.content = self
		async def __aenter__(self):
			return self
		async def __aexit__(self, *args):
			return False
		async def iter_chunked(self, n):
			yield b"data" * 10

	def fake_get(self, url, timeout=None, params=None):
		return FakeResp()

	with patch("aiohttp.ClientSession.get", new=fake_get):
		res = await download_video("https://example.com/video.mp4", temp_dir=tmp_path, max_size_mb=10)
		assert res.source == "direct"
		assert res.file_path.exists()


@pytest.mark.asyncio
async def test_download_fallback_ytdlp(tmp_path: Path, monkeypatch):
	# Make mkstemp deterministic
	det_path = tmp_path / "video_123.bin"
	def fake_mkstemp(prefix, suffix, dir):
		fd = os.open(det_path, os.O_RDWR | os.O_CREAT)
		return fd, str(det_path)

	# Fail direct methods and Yandex
	def fake_get(*args, **kwargs):
		class Bad:
			status = 404
			async def __aenter__(self):
				return self
			async def __aexit__(self, *a):
				return False
			async def json(self):
				return {}
		return Bad()

	# Fake yt-dlp process success
	async def fake_proc(*cmd, stdout=None, stderr=None):
		class P:
			returncode = 0
			async def communicate(self):
				return b"", b""
			async def wait(self):
				return 0
			stderr = asyncio.StreamReader()
			stdout = asyncio.StreamReader()
		return P()

	with patch("tempfile.mkstemp", new=fake_mkstemp), \
		 patch("aiohttp.ClientSession.get", new=fake_get), \
		 patch("asyncio.create_subprocess_exec", new=fake_proc):
		# Create the file yt-dlp is expected to write
		merged = det_path.with_suffix(".mp4")
		merged.write_bytes(b"video")
		res = await download_video("https://host/anything", temp_dir=tmp_path, max_size_mb=10)
		assert res.source == "yt-dlp"
		assert res.file_path == merged
