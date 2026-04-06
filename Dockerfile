# Image officielle Playwright — inclut Chromium + dépendances système
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

WORKDIR /app

# Dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer les navigateurs Playwright (Chromium uniquement)
RUN playwright install chromium

# Code de l'app
COPY app.py .

# Port exposé (Render injecte $PORT automatiquement)
EXPOSE 5001

# Lancement via gunicorn (1 worker — Playwright est single-process sur free tier)
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT:-5001} \
    --workers 1 \
    --threads 4 \
    --timeout 60 \
    --log-level info
