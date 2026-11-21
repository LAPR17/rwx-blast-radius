FROM python:3.12-slim
WORKDIR /app
COPY selector.py map.json.gz /app/
CMD ["python", "/app/selector.py"]