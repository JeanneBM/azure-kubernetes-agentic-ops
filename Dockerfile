FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 10001
EXPOSE 8080
CMD ["uvicorn", "agentic_ops.web:app", "--host", "0.0.0.0", "--port", "8080"]
