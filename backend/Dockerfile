FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app

RUN useradd --create-home --uid 10001 datapilot \
    && mkdir -p /var/lib/datapilot \
    && chown datapilot /var/lib/datapilot
USER datapilot

ENV UPLOAD_ROOT=/var/lib/datapilot SAMPLE_DATA_DIR=/data
VOLUME /var/lib/datapilot
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
