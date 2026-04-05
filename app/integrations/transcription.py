import asyncio
from typing import Any, Protocol

from groq import Groq

from app.core.constants import GROQ_TRANSCRIPTION_FORMAT, GROQ_WHISPER_MODEL


class TranscriptionProvider(Protocol):
    async def transcribe(self, audio_bytes: bytes, filename: str) -> str: ...


class GroqWhisperTranscriber:
    def __init__(self, api_key: str) -> None:
        self._client = Groq(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        response: Any = await asyncio.to_thread(
            lambda: self._client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model=GROQ_WHISPER_MODEL,
                response_format=GROQ_TRANSCRIPTION_FORMAT,
            )
        )
        return str(response)


class StubTranscriber:
    """Deterministic stub — production fallback when GROQ_API_KEY is absent
    and used directly in integration tests to avoid real API calls.
    Pass raises= to simulate failure in unit tests."""

    def __init__(
        self,
        transcript: str = "Patient discussed anxiety and sleep difficulties.",
        raises: Exception | None = None,
    ) -> None:
        self._transcript = transcript
        self._raises = raises

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        if self._raises:
            raise self._raises
        return self._transcript
