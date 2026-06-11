# Agent 47 — ADK web UI + scan pipelines
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Project root on sys.path so `agents`, `sdr`, `shared`, `orchestrator` import.
ENV PYTHONPATH=/app

EXPOSE 8001

# Bind 0.0.0.0 inside the container; Caddy is the only public entrypoint.
CMD ["adk", "web", "agents", "--host", "0.0.0.0", "--port", "8001"]
