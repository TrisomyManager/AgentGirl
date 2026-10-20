FROM python:3.11-slim-bookworm AS builder
WORKDIR /build
COPY . .
RUN python -m pip wheel --no-cache-dir --wheel-dir /wheels '.[platforms]'

FROM python:3.11-slim-bookworm
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    COMPANION_LITE_MODE=true COMPANION_MONOLITHIC=true \
    COMPANION_LITE_DATABASE_URL=sqlite+aiosqlite:////data/companion_lite.db \
    COMPANION_LLM_CONFIG_PATH=/data/config/companion_llm_config.json \
    COMPANION_VOICE_CONFIG_PATH=/data/config/companion_voice_config.json \
    COMPANION_VOICE_TEMP_DIR=/data/voice COMPANION_PLUGINS_DIR=/app/plugins
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libsndfile1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 companion \
    && useradd --uid 10001 --gid companion --create-home companion \
    && mkdir -p /data/config /data/voice /app \
    && chown -R companion:companion /data /app
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir --no-index --find-links=/wheels 'companion-ai[platforms]' && rm -rf /wheels
WORKDIR /app
COPY main.py ./main.py
COPY plugins/example_echo ./plugins/example_echo
USER companion
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).read()"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
