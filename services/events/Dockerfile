FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY libs/common /libs/common
RUN pip install /libs/common
COPY services/events/requirements.txt .
RUN pip install -r requirements.txt
COPY services/events/app ./app
RUN useradd -r app && chown -R app /srv
USER app
CMD ["python", "-m", "app.main"]
