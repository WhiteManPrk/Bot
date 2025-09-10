import asyncio
import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
from yarl import URL

logger = logging.getLogger(__name__)


YANDEX_PUBLIC_API = "https://cloud-api.yandex.net/v1/disk/public/resources/download"


def _sanitize_filename(name: str) -> str:
	return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "file"


@dataclass
class DownloadResult:
	file_path: Path
	filename: str
	size_bytes: int
	source: str


class DownloadError(Exception):
	pass


async def _download_with_aiohttp(session: aiohttp.ClientSession, url: str, dest_path: Path, *, max_size_bytes: int) -> int:
	size = 0
	async with session.get(url, timeout=aiohttp.ClientTimeout(total=None)) as resp:
		if resp.status != 200:
			raise DownloadError(f"HTTP {resp.status} while downloading")
		cd = resp.headers.get("Content-Disposition", "")
		filename_match = re.search(r'filename="?([^";]+)"?', cd)
		if filename_match:
			# We only use this to set dest filename if dest_path points to a dir
			pass
		with dest_path.open("wb") as f:
			async for chunk in resp.content.iter_chunked(1 << 15):
				size += len(chunk)
				if size > max_size_bytes:
					raise DownloadError("File exceeds maximum allowed size")
				f.write(chunk)
	return size


async def _resolve_yandex_public_direct_url(session: aiohttp.ClientSession, public_url: str) -> tuple[str, Optional[str]]:
	params = {"public_key": public_url}
	async with session.get(YANDEX_PUBLIC_API, params=params) as resp:
		if resp.status != 200:
			raise DownloadError(f"Yandex API error {resp.status}")
		data = await resp.json()
		href = data.get("href")
		if not href:
			raise DownloadError("No href in Yandex response")
		# Try to infer filename from query params
		filename = None
		try:
			parsed = URL(public_url)
			filename = _sanitize_filename(parsed.name or "video")
		except Exception:
			filename = None
		return href, filename


def _is_probably_direct(url: str) -> bool:
	return bool(re.search(r"\.(mp4|mov|mkv|webm|avi)(\?|$)", url, re.IGNORECASE))


async def download_video(url: str, *, temp_dir: Path, max_size_mb: int, yadisk_token: Optional[str] = None) -> DownloadResult:
	"""
	Download a video from various sources. Preference order:
	1) Direct HTTP(S) links
	2) Yandex Disk public links via API
	3) Fallback: yt-dlp to download bestvideo+bestaudio merged file
	"""
	temp_dir.mkdir(parents=True, exist_ok=True)
	max_size_bytes = max_size_mb * 1024 * 1024
	filename = _sanitize_filename(URL(url).name or "video")
	fd, tmp_path = tempfile.mkstemp(prefix="video_", suffix=".bin", dir=temp_dir)
	os.close(fd)
	dest = Path(tmp_path)

	async with aiohttp.ClientSession() as session:
		try:
			if _is_probably_direct(url):
				size = await _download_with_aiohttp(session, url, dest, max_size_bytes=max_size_bytes)
				return DownloadResult(file_path=dest, filename=filename, size_bytes=size, source="direct")

			# Try Yandex Disk public link
			if "disk.yandex" in url or "yadi.sk" in url:
				try:
					direct_url, inferred = await _resolve_yandex_public_direct_url(session, url)
					name = inferred or filename
					size = await _download_with_aiohttp(session, direct_url, dest, max_size_bytes=max_size_bytes)
					return DownloadResult(file_path=dest, filename=name, size_bytes=size, source="yandex")
				except Exception as e:
					logger.warning("Yandex direct download failed, will fallback to yt-dlp: %s", e)

			# Fallback: yt-dlp for arbitrary hosts (and Mail.ru cloud, Google Drive, etc.)
		except Exception as e:
			logger.info("Direct methods failed: %s", e)

	# Use yt-dlp in a separate process to a unique file in temp_dir
	merged_path = dest.with_suffix(".mp4")
	cmd = [
		"yt-dlp",
		"-f",
		"bv*+ba/b",
		"-o",
		str(merged_path),
		"--no-playlist",
		"--no-progress",
		url,
	]
	process = await asyncio.create_subprocess_exec(
		*cmd,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)
	stdout, stderr = await process.communicate()
	if process.returncode != 0:
		logger.error("yt-dlp error: %s", stderr.decode(errors="ignore"))
		raise DownloadError("Failed to download via yt-dlp")

	if not merged_path.exists():
		raise DownloadError("yt-dlp reported success but file missing")

	size = merged_path.stat().st_size
	if size > max_size_bytes:
		try:
			merged_path.unlink(missing_ok=True)
		except Exception:
			pass
		raise DownloadError("Downloaded file exceeds maximum allowed size")

	return DownloadResult(file_path=merged_path, filename=merged_path.name, size_bytes=size, source="yt-dlp")
