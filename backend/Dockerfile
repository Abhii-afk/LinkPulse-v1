# Image for both the FastAPI service and the analytics worker.
# The worker only changes the command, so the two never drift apart.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The dependency metadata is copied first so the dependency layer is reused
# whenever only application code changes.
COPY pyproject.toml ./
COPY app ./app
COPY workers ./workers
COPY scripts ./scripts
COPY alembic ./alembic
COPY alembic.ini ./

RUN pip install --no-cache-dir .

EXPOSE 8000

# The health check is left to the orchestrator on purpose: this image runs
# both the API, which serves HTTP, and the worker, which does not. Compose
# and the deployment provider set the probe that fits the service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
