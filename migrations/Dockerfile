FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY libs/common /libs/common
RUN pip install /libs/common alembic==1.13.*
COPY migrations /app
CMD ["alembic", "-c", "/app/alembic.ini", "upgrade", "head"]
