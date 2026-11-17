FROM python:3.11-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY src/worker/ ./src/worker/
COPY migrations/ ./migrations/
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python
CMD ["visionq", "info"]