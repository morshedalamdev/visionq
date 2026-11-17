"""Apply VisionQ migrations to the configured PostgreSQL database."""

from alembic import context
from worker.db import database

with database().connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
