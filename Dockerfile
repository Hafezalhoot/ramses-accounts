FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data && chown appuser:appuser /data \
    && (getent group 1000 >/dev/null || groupadd --gid 1000 rendersecrets) \
    && usermod -aG "$(getent group 1000 | cut -d: -f1)" appuser
COPY *.py schema.sql /app/
COPY scripts/secure_backup.py /app/scripts/secure_backup.py
COPY static/ /app/static/
USER appuser
ENV RAMSES_DB_PATH=/data/ramses.sqlite3
EXPOSE 8000
CMD ["sh", "-c", "python bootstrap.py && exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
