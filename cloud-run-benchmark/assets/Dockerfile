FROM pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime

WORKDIR /app

RUN pip install --no-cache-dir \
    flask \
    gunicorn \
    safetensors \
    google-cloud-storage \
    accelerate \
    huggingface_hub

COPY server.py .

CMD ["python", "server.py"]
