import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from bot.main import link_handler


class DummyMessage:
	def __init__(self):
		self.text = "https://example.com/video.mp4"
		self._answers = []
	async def answer(self, text):
		self._answers.append(text)
		return DummyStatusMessage()
	async def answer_document(self, file, caption=None):
		self._answers.append(("doc", caption))


class DummyStatusMessage:
	async def edit_text(self, text):
		return None


@pytest.mark.asyncio
async def test_link_handler_flow(tmp_path: Path, monkeypatch):
	with patch("bot.main.download_video") as m_down, patch("bot.main.run_extract_audio") as m_ext:
		class DR:
			file_path = tmp_path / "v.mp4"
			filename = "v.mp4"
			size_bytes = 1
			source = "direct"
		m_down.return_value = DR()
		DR.file_path.write_bytes(b"x")

		class ER:
			output_path = tmp_path / "v.mp3"
			format = "mp3"
			duration_sec = None
			size_bytes = 1
		m_ext.return_value = ER()
		ER.output_path.write_bytes(b"a")

		msg = DummyMessage()
		await link_handler(msg)
