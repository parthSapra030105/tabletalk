# One container: Django serves the API and the built UI on one port.
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.14-slim
RUN useradd -m -u 1000 app
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app backend/ backend/
COPY --from=frontend --chown=app /app/frontend/dist frontend/dist
RUN mkdir -p data/uploads && chown -R app data
USER app

ENV PORT=7860 DJANGO_DEBUG=0 PYTHONUNBUFFERED=1
EXPOSE 7860
# One process, many threads: ingest jobs run in background threads of the web process.
CMD python backend/manage.py migrate --noinput && \
    exec gunicorn --chdir backend tabletalk.wsgi -b 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300
