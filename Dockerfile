# Stage 1: build the React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Python app
FROM python:3.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

EXPOSE 5000

CMD gunicorn --worker-class gevent --workers 1 --worker-connections 1000 --bind 0.0.0.0:${PORT:-5000} --timeout 120 wsgi:app
