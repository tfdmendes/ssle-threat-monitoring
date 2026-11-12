FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ./
COPY monitoring/health_exporter.py monitoring/health_targets.json ./monitoring/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "-u", "monitoring/health_exporter.py", "--host", "0.0.0.0", "--port", "8000"]
