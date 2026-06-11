# VeraDoc API — Django REST Framework (verification runs in-process via background threads)
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py .
COPY veradoc/ ./veradoc/
COPY accounts/ ./accounts/
COPY common/ ./common/
COPY credits/ ./credits/
COPY verifications/ ./verifications/
COPY services/ ./services/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --fake-initial --noinput && exec gunicorn veradoc.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120"]
