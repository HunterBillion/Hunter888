"""STT adapter for self-hosted faster-whisper.

Will be implemented in Phase 1 (Week 4).
Responsibilities:
- Accept audio chunks via WebSocket
- Stream to Whisper server for transcription
- Return transcribed text with confidence score
"""

from dataclasses import dataclass


@dataclass
class STTResult:
    text: str
    confidence: float
    language: str
    duration_ms: int


async def transcribe_audio(audio_bytes: bytes) -> STTResult:
    """Transcribe audio chunk. Stub for Phase 1, Week 4."""
    raise NotImplementedError("STT integration not yet implemented — Phase 1, Week 4")
