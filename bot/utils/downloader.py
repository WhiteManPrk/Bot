import asyncio
import json
import logging
import os
import re
import ssl
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp
from yarl import URL

logger = logging.getLogger(__name__)


YANDEX_PUBLIC_API = "https://cloud-api.yandex.net/v1/disk/public/resources/download"
MAILRU_PUBLIC_API = "https://cloud.mail.ru/api/v2/public/resources/download"


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
	headers = {
		"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
		"Referer": url,
	}
	async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=None)) as resp:
		if resp.status != 200:
			raise DownloadError(f"HTTP {resp.status} while downloading")
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
		filename = None
		try:
			parsed = URL(public_url)
			filename = _sanitize_filename(parsed.name or "video")
		except Exception:
			filename = None
		return href, filename


async def _resolve_mailru_public_direct_url(session: aiohttp.ClientSession, public_url: str) -> tuple[str, Optional[str]]:
	"""Resolve Mail.ru public link to direct download URL using page scraping"""
	import re
	
	# Get the page content
	headers = {
		"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
		"Referer": public_url,
	}
	
	async with session.get(public_url, headers=headers) as resp:
		if resp.status != 200:
			raise DownloadError(f"Mail.ru page error {resp.status}")
		
		page_content = await resp.text()
		
		# Search for the dispatcher pattern
		re_pattern = r'dispatcher.*?weblink_get.*?url":"(.*?)"'
		match = re.search(re_pattern, page_content)
		
		if match:
			url = match.group(1)
			# Get XXX and YYYYYYYY from the original link
			parts = public_url.split('/')[-2:]
			# Add XXX and YYYYYYYY to the resulting URL
			direct_url = f'{url}/{parts[0]}/{parts[1]}'
			
			# Try to extract filename from page content
			filename_match = re.search(r'"name":"([^"]+)"', page_content)
			filename = filename_match.group(1) if filename_match else None
			
			return direct_url, filename
		else:
			raise DownloadError("Could not find download URL in Mail.ru page")


def _is_probably_direct(url: str) -> bool:
	return bool(re.search(r"\.(mp4|mov|mkv|webm|avi)(\?|$)", url, re.IGNORECASE))


async def download_video(url: str, *, temp_dir: Path, max_size_mb: int, yadisk_token: Optional[str] = None) -> DownloadResult:
	"""
	Download a video from various sources. Preference order:
	1) Direct HTTP(S) links
	2) Yandex Disk public links via API
	3) Mail.ru public links via API
	4) Fallback: yt-dlp to download bestvideo+bestaudio merged file
	"""
	temp_dir.mkdir(parents=True, exist_ok=True)
	max_size_bytes = max_size_mb * 1024 * 1024
	filename = _sanitize_filename(URL(url).name or "video")
	fd, tmp_path = tempfile.mkstemp(prefix="video_", suffix=".bin", dir=temp_dir)
	os.close(fd)
	dest = Path(tmp_path)

	# Create SSL context that doesn't verify certificates for problematic sites
	ssl_context = ssl.create_default_context()
	ssl_context.check_hostname = False
	ssl_context.verify_mode = ssl.CERT_NONE
	
	connector = aiohttp.TCPConnector(ssl=ssl_context)
	async with aiohttp.ClientSession(connector=connector) as session:
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
					logger.warning("Yandex direct download failed, will fallback: %s", e)

        # Try Mail.ru Cloud public link
        if "cloud.mail.ru/public" in url:
            try:
                direct_url, inferred = await _resolve_mailru_public_direct_url(session, url)
                name = inferred or filename
                size = await _download_with_aiohttp(session, direct_url, dest, max_size_bytes=max_size_bytes)
                return DownloadResult(file_path=dest, filename=name, size_bytes=size, source="mailru")
            except Exception as e:
                logger.warning("Mail.ru direct download failed, will fallback: %s", e)
                # Mail.ru requires authentication, so we'll skip yt-dlp fallback
                raise DownloadError("Mail.ru Cloud requires authentication. Please upload the video file directly to the bot instead.")

			# Fallback: yt-dlp for arbitrary hosts
		except Exception as e:
			logger.info("Direct methods failed: %s", e)

	# Use yt-dlp in a separate process to a unique file in temp_dir
	merged_path = dest.with_suffix(".mp4")
	cmd = [
		"yt-dlp",
		"-f",
		"best[height<=720]/best",
		"-o",
		str(merged_path),
		"--no-playlist",
		"--no-progress",
		"--geo-bypass",
		"--retry-sleep",
		"1",
		"--retries",
		"3",
		"--user-agent",
		"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
		"--referer",
		url,
		"--extractor-args",
		"youtube:player_client=web",
		"--cookies-from-browser",
		"chrome",
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
