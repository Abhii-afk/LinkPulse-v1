# Process types for hosts that read a Procfile. Railway reads this when it
# builds with Nixpacks instead of the Dockerfile; with the Dockerfile the
# start command is set on the service instead.
api: uvicorn app.main:app --host 0.0.0.0 --port $PORT
worker: python -m workers.analytics_worker
