FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LISTEN_HOST=0.0.0.0 \
    LISTEN_PORT=8787 \
    DB_PATH=/data/luzbot.db

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 luzbot \
    && useradd --system --uid 10001 --gid luzbot --home-dir /app --no-create-home luzbot \
    && mkdir /data \
    && chown luzbot:luzbot /data

WORKDIR /app
COPY luzbot/ ./luzbot/

USER luzbot:luzbot
EXPOSE 8787
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8787/healthz', timeout=2)"

CMD ["python", "-m", "luzbot"]
