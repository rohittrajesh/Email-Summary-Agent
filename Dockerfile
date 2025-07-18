FROM python:3.11-slim
WORKDIR /app

# 1) Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) Copy your package and creds
COPY src/email_summarizer /app/email_summarizer
COPY credentials.json token.json ./
# If you really need a .env in-image (not recommended for secrets):
# COPY .env ./

# 3) Module path + config
ENV PYTHONPATH=/app
ENV POLL_INTERVAL=1
ENV WORKER_COUNT=4
# (Or pass OPENAI_API_KEY and DATABASE_URL via `docker run -e`)

# 4) Launch the synchronizer
CMD ["python", "-m", "email_summarizer.service"]
