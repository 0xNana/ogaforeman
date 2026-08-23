FROM python:3.12-slim

ARG APP_GIT_SHA
ARG APP_BUILD_TIME
ARG APP_VERSION

LABEL org.opencontainers.image.revision=${APP_GIT_SHA} \
    org.opencontainers.image.created=${APP_BUILD_TIME} \
    org.opencontainers.image.version=${APP_VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    APP_GIT_SHA=${APP_GIT_SHA} \
    APP_BUILD_TIME=${APP_BUILD_TIME} \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

RUN pip install --no-cache-dir "uv==0.11.32"
RUN addgroup --system oga && adduser --system --ingroup oga --no-create-home oga

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts
COPY main.py ./main.py
RUN uv sync --frozen --no-dev

EXPOSE 8080

USER oga

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
