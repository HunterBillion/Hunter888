"""OpenAI-compatible Whisper STT server for Hunter888.

Emulates /v1/audio/transcriptions endpoint used by fedirz/faster-whisper-server.
Runs on port 8001. Uses faster-whisper (CTranslate2 backend) for Apple Silicon.

Model: Systran/faster-whisper-small (500 MB, ~400 MB RAM, good for Russian).
Change via MODEL_NAME env var if needed (e.g. "medium", "large-v3").
"""

import io
import logging
import os
import time

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logger = logging.getLogger("whisper")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

app = FastAPI(title="Hunter888 Whisper STT")

MODEL_NAME = os.environ.get("MODEL_NAME", "Systran/faster-whisper-small")
DEVICE = os.environ.get("DEVICE", "cpu")
COMPUTE_TYPE = os.environ.get("COMPUTE_TYPE", "int8")

_model = None


def get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading model: %s (device=%s, compute=%s)", MODEL_NAME, DEVICE, COMPUTE_TYPE)
        _model = WhisperModel(MODEL_NAME, device=DEVICE, compute_type=COMPUTE_TYPE)
        logger.info("Model loaded")
    return _model


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _model is not None}


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default=""),
    language: str = Form(default="ru"),
    response_format: str = Form(default="json"),
    temperature: float = Form(default=0.0),
    prompt: str = Form(default=""),
):
    """OpenAI-compatible transcription endpoint.

    Supports response_format: json, verbose_json, text, srt, vtt.
    """
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")

        whisper = get_model()
        start = time.monotonic()

        segments_gen, info = whisper.transcribe(
            io.BytesIO(audio_bytes),
            language=language if language else None,
            initial_prompt=prompt or None,
            temperature=temperature,
            vad_filter=True,
        )

        segments = []
        full_text_parts = []
        for seg in segments_gen:
            segments.append({
                "id": seg.id,
                "seek": seg.seek,
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": seg.text,
                "tokens": list(seg.tokens) if seg.tokens else [],
                "temperature": seg.temperature,
                "avg_logprob": round(seg.avg_logprob, 6),
                "compression_ratio": round(seg.compression_ratio, 6),
                "no_speech_prob": round(seg.no_speech_prob, 6),
            })
            full_text_parts.append(seg.text)

        full_text = "".join(full_text_parts).strip()
        elapsed = round(time.monotonic() - start, 3)

        logger.info(
            "Transcribed %d bytes -> %d segments, %d chars, lang=%s, %.2fs",
            len(audio_bytes), len(segments), len(full_text), info.language, elapsed
        )

        if response_format == "text":
            return JSONResponse(content=full_text, media_type="text/plain")

        if response_format == "verbose_json":
            return {
                "task": "transcribe",
                "language": info.language,
                "duration": round(info.duration, 3),
                "text": full_text,
                "segments": segments,
            }

        # default: json
        return {"text": full_text}

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription error: {e}")


@app.get("/")
async def root():
    return {"service": "hunter888-whisper", "model": MODEL_NAME, "endpoints": ["/health", "/v1/audio/transcriptions"]}
