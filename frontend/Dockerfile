FROM python:3.14-slim

WORKDIR /srv/app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    HABIT_API_URL=https://habit-tracker-api-142205380680.us-central1.run.app

COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt && \
    useradd --create-home --uid 10001 appuser && \
    chown -R appuser:appuser /srv/app

COPY --chown=appuser:appuser src ./src
COPY --chown=appuser:appuser server.py ./server.py

USER appuser

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080} --ws websockets-sansio --proxy-headers --forwarded-allow-ips='*'"]
