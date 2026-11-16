FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ingestion.py instrumentation.py security_logging.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV TRUST_LOCAL_PROXY=1

CMD ["python", "-u", "-c", "import ingestion; ingestion.register(); ingestion.app.run(host='127.0.0.1', port=5001)"]
