"""Sentence-transformers embedding microservice.

Provides text embeddings and cosine similarity for the script checker.
Model: intfloat/multilingual-e5-large (best for Russian text).
"""

import os
import logging
from typing import Union

from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger("embeddings")

app = FastAPI(title="Hunter888 Embeddings Service")

MODEL_NAME = os.environ.get("MODEL_NAME", "intfloat/multilingual-e5-large")

# Lazy model loading
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        logger.info("Loading model: %s", MODEL_NAME)
        _model = SentenceTransformer(MODEL_NAME)
        logger.info("Model loaded successfully")
    return _model


class EmbedRequest(BaseModel):
    text: Union[str, None] = None
    texts: Union[list[str], None] = None


class EmbedResponse(BaseModel):
    embeddings: list[list[float]]


class SimilarityRequest(BaseModel):
    text1: str
    text2: str


class SimilarityResponse(BaseModel):
    score: float


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "loaded": _model is not None}


@app.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest):
    model = get_model()
    if req.texts:
        texts = req.texts
    elif req.text:
        texts = [req.text]
    else:
        return EmbedResponse(embeddings=[])

    # Add "query: " prefix for e5 models
    prefixed = [f"query: {t}" for t in texts]
    embeddings = model.encode(prefixed, normalize_embeddings=True)
    return EmbedResponse(embeddings=embeddings.tolist())


@app.post("/similarity", response_model=SimilarityResponse)
async def similarity(req: SimilarityRequest):
    model = get_model()
    texts = [f"query: {req.text1}", f"query: {req.text2}"]
    embeddings = model.encode(texts, normalize_embeddings=True)
    # Cosine similarity (already normalized)
    score = float(embeddings[0] @ embeddings[1])
    return SimilarityResponse(score=score)
