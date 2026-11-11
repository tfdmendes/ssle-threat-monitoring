FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ingestion.py instrumentation.py ./
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "-c", "import ingestion; ingestion.register(); ingestion.app.run(host='0.0.0.0', port=5001)"]
