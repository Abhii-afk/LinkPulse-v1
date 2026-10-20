# Image for both the FastAPI service and the analytics worker.
# The worker only changes the command, so the two never drift apart.
#
# The build context is the repository root, which is what Railway uses and
# what docker compose uses here, so the same file builds the same image in
# both places.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The dependency metadata is copied first so the dependency layer is reused
# whenever only application code changes.
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/workers ./workers
COPY backend/scripts ./scripts
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./

RUN pip install --no-cache-dir .

EXPOSE 8000

# The health check is left to the orchestrator on purpose: this image runs
# both the API, which serves HTTP, and the worker, which does not. Compose
# and the deployment provider set the probe that fits the service.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
