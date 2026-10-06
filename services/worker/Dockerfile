FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY libs/common /libs/common
RUN pip install "/libs/common[storage]"
COPY services/worker/requirements.txt .
RUN pip install -r requirements.txt
COPY services/worker/app ./app
RUN useradd -r app && chown -R app /srv
USER app
CMD ["python", "-m", "app.main"]
