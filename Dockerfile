FROM python:3.12-slim
WORKDIR /app
COPY selector.py /app/selector.py
CMD ["python", "/app/selector.py"]
