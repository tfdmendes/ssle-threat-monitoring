FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt storage.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app
WORKDIR /data
CMD ["python", "-u", "-c", "import storage; storage.init_db(); storage.app.run(host='0.0.0.0', port=5002)"]
