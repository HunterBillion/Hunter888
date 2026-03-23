FROM python:3.12-slim

WORKDIR /app

# Pin exact versions for reproducible builds
RUN pip install --no-cache-dir \
    torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    fastapi==0.115.6 \
    uvicorn[standard]==0.34.0 \
    sentence-transformers==3.3.1

COPY app.py .

ENV MODEL_NAME=intfloat/multilingual-e5-large
EXPOSE 8001

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
