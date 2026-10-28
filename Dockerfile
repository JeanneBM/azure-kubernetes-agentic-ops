FROM python:3.11-alpine AS builder

RUN apk upgrade --no-cache
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.11-alpine AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Build tooling and its vendored dependencies are not needed at runtime.
RUN apk upgrade --no-cache \
    && rm -rf /usr/local/lib/python3.11/site-packages/* /usr/local/bin/pip*
COPY --from=builder /install /usr/local

USER 10001
EXPOSE 8080
CMD ["uvicorn", "agentic_ops.web:app", "--host", "0.0.0.0", "--port", "8080"]
