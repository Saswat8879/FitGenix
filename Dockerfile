FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip
RUN pip install -r /app/requirements.txt

COPY . /app

RUN useradd --create-home appuser
USER appuser

ENV PORT=8080
EXPOSE 8080

CMD ["gunicorn", "run:app", "--bind", "0.0.0.0:8080", "--workers", "3", "--log-file", "-"]
