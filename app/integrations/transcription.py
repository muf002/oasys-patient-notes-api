import asyncio
from typing import Any, Protocol

from groq import Groq


class TranscriptionProvider(Protocol):
    async def transcribe(self, audio_bytes: bytes, filename: str) -> str: ...


class GroqWhisperTranscriber:
    def __init__(self, api_key: str) -> None:
        self._client = Groq(api_key=api_key)

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        response: Any = await asyncio.to_thread(
            lambda: self._client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model="whisper-large-v3-turbo",
                response_format="text",
            )
        )
        return str(response)


class StubTranscriber:
    """Deterministic stub — production fallback when GROQ_API_KEY is absent
    and used directly in integration tests to avoid real API calls."""

    def __init__(
        self, transcript: str = "Patient discussed anxiety and sleep difficulties."
    ) -> None:
        self._transcript = transcript

    async def transcribe(self, audio_bytes: bytes, filename: str) -> str:
        return self._transcript
