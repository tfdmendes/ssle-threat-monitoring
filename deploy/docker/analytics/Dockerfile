FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt analytics.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONPATH=/app
WORKDIR /data
CMD ["flask", "--app", "analytics", "run", "--host=0.0.0.0", "--port=5003"]
