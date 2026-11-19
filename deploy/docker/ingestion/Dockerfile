FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt ingestion.py devices.py provision_sensor.py instrumentation.py security_logging.py ./
RUN pip install --no-cache-dir -r requirements.txt

ENV TRUST_LOCAL_PROXY=1

CMD ["python", "-u", "ingestion.py"]
