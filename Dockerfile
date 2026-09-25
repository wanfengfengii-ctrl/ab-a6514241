# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /srv/app

COPY app/ app/
COPY tests/ tests/
COPY verify/ verify/

RUN useradd --system --uid 10001 appuser && chown -R appuser:appuser /srv/app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=6 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=2)"

CMD ["python", "-m", "app.server"]
