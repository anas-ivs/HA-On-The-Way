FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
# config.yaml is the single source of truth for the version, surfaced in the web UI.
COPY config.yaml ./config.yaml
CMD ["python", "main.py"]
