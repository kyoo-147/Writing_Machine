FROM python:3.13-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN python -m pip install --no-cache-dir ".[postgres]"

EXPOSE 8787
CMD ["python", "-m", "content_machine", "dashboard", "--host", "0.0.0.0", "--port", "8787"]

