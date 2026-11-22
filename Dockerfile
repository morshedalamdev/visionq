FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
COPY --from=ghcr.io/astral-sh/uv:0.13.8@sha256:5cc1805e2426484abca4ad46ea783bab281fdb225fd82d8ce6d66a81254bac85 /uv /usr/local/bin/uv
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock README.md LICENSE alembic.ini ./
COPY src/ ./src/
COPY migrations/ ./migrations/
RUN uv sync --locked --no-dev --no-editable --python /usr/local/bin/python
CMD ["visionq", "info"]