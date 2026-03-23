FROM python:3.12-slim

WORKDIR /app

# Pin exact versions for reproducible builds
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.34.0 \
    sentence-transformers==3.3.1 \
    gunicorn==22.0.0

COPY app.py .

ENV MODEL_NAME=intfloat/multilingual-e5-large

# FIX 28: Pre-download model at build time (avoids cold-start delay)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${MODEL_NAME}')"

EXPOSE 8001

# FIX 27: Use Gunicorn + Uvicorn workers for crash-safe process management
CMD ["gunicorn", "app:app", "-w", "2", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8001", "--timeout", "120"]
