import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
	output_path: Path
	format: str
	duration_sec: Optional[float]
	size_bytes: int


class ExtractionError(Exception):
	pass


async def extract_audio(
	input_video: Path,
	output_dir: Path,
	ffmpeg_path: str = "ffmpeg",
	format: str = "mp3",
	bitrate: str = "192k",
	timeout_sec: Optional[int] = None,
) -> AsyncIterator[tuple[str, Optional[float]]]:
	"""
	Run ffmpeg to extract audio. Yields progress updates as (stage, percent or None).
	Final yield is ("done", None).
	"""
	output_dir.mkdir(parents=True, exist_ok=True)
	output_path = output_dir / (input_video.stem + f".{format}")

	cmd = [
		ffmpeg_path,
		"-y",
		"-hide_banner",
		"-i",
		str(input_video),
		"-vn",
		"-acodec",
		"libmp3lame" if format == "mp3" else "aac",
		"-b:a",
		bitrate,
		str(output_path),
	]

	logger.info("Running ffmpeg: %s", " ".join(cmd))
	process = await asyncio.create_subprocess_exec(
		*cmd,
		stdout=asyncio.subprocess.PIPE,
		stderr=asyncio.subprocess.PIPE,
	)

	# Heartbeat progress while process is running
	deadline = None if timeout_sec is None else (asyncio.get_event_loop().time() + timeout_sec)
	while True:
		try:
			await asyncio.wait_for(process.wait(), timeout=0.5)
			break
		except asyncio.TimeoutError:
			if deadline is not None and asyncio.get_event_loop().time() > deadline:
				process.kill()
				raise ExtractionError("ffmpeg timed out")
			yield ("processing", None)

	stdout, stderr = await process.communicate()
	if process.returncode != 0:
		logger.error("ffmpeg failed: %s", stderr.decode(errors="ignore"))
		raise ExtractionError("ffmpeg failed to extract audio")

	if not output_path.exists():
		raise ExtractionError("ffmpeg reported success but output not found")

	yield ("done", None)


async def run_extract_audio(
	input_video: Path,
	output_dir: Path,
	ffmpeg_path: str = "ffmpeg",
	format: str = "mp3",
	bitrate: str = "192k",
	cancel_event: Optional[asyncio.Event] = None,
	progress_cb: Optional[callable] = None,
) -> ExtractionResult:
	"""Convenience wrapper that consumes progress iterator and returns final result."""
	async for stage, percent in extract_audio(
		input_video,
		output_dir,
		ffmpeg_path=ffmpeg_path,
		format=format,
		bitrate=bitrate,
	):
		if progress_cb:
			progress_cb(stage, percent)
		if cancel_event and cancel_event.is_set():
			raise ExtractionError("Extraction cancelled")

	output_path = output_dir / (input_video.stem + f".{format}")
	size = output_path.stat().st_size if output_path.exists() else 0
	return ExtractionResult(output_path=output_path, format=format, duration_sec=None, size_bytes=size)
