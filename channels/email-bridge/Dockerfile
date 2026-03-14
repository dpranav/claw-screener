FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && (apt-get install -y --no-install-recommends docker.io docker-cli || apt-get install -y --no-install-recommends docker.io) && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY email_bridge.py /app/email_bridge.py

CMD ["python", "/app/email_bridge.py"]
