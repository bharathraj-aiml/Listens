FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PIP_DEFAULT_TIMEOUT=100
COPY libs/common /libs/common
# Cache mount (not image layer): wheels persist across retries without bloating the final
# image - scikit-learn pulls in large numpy/scipy wheels that can outlast a single
# read-timeout window on a slow link.
RUN --mount=type=cache,target=/root/.cache/pip pip install "/libs/common[web,storage]"
COPY services/catalogue/requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
COPY services/catalogue/app ./app
RUN useradd -r app && chown -R app /srv
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
