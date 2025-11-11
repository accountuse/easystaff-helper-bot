FROM mcr.microsoft.com/playwright/python:v1.55.0-jammy

WORKDIR /app

COPY requirements.txt /app/

# Prod
#COPY . /app/

RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libmariadb-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install -U pip setuptools wheel && \
    pip install -r requirements.txt debugpy

CMD ["python", "main.py"]

#docker-compose run --service-ports bot python -m debugpy --listen 0.0.0.0:5678 --wait-for-client main.py