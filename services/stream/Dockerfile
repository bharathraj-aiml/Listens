FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY libs/common /libs/common
RUN pip install "/libs/common[web,storage]"
COPY services/stream/requirements.txt .
RUN pip install -r requirements.txt
COPY services/stream/app ./app
RUN useradd -r app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
