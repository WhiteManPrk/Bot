import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.utils.audio import run_extract_audio, ExtractionError


@pytest.mark.asyncio
async def test_run_extract_audio_success(tmp_path: Path):
	video = tmp_path / "input.mp4"
	video.write_bytes(b"x" * 100)

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

	with patch("asyncio.create_subprocess_exec", new=fake_proc):
		# simulate ffmpeg output file
		out = tmp_path / "input.mp3"
		out.write_bytes(b"audio")
		res = await run_extract_audio(video, tmp_path)
		assert res.output_path.exists()
		assert res.format == "mp3"


@pytest.mark.asyncio
async def test_run_extract_audio_failure(tmp_path: Path):
	video = tmp_path / "input.mp4"
	video.write_bytes(b"x" * 100)

	async def fake_proc(*cmd, stdout=None, stderr=None):
		class P:
			returncode = 1
			async def communicate(self):
				return b"", b"error"
			async def wait(self):
				return 1
			stderr = asyncio.StreamReader()
			stdout = asyncio.StreamReader()
		return P()

	with patch("asyncio.create_subprocess_exec", new=fake_proc):
		with pytest.raises(ExtractionError):
			await run_extract_audio(video, tmp_path)
