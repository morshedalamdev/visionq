"""PostgreSQL connection configuration for worker and migration commands."""

import os

from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url


def database():
    explicit = os.environ.get("VISIONQ_DATABASE_URL")
    if explicit is not None:
        try:
            url = make_url(explicit)
        except Exception:
            raise ValueError("Invalid VISIONQ_DATABASE_URL") from None
        if url.drivername != "postgresql+psycopg" or not url.database:
            raise ValueError(
                "VISIONQ_DATABASE_URL requires postgresql+psycopg and a database"
            )
    else:
        url = URL.create(
            "postgresql+psycopg",
            username="visionq",
            password=os.environ["POSTGRES_PASSWORD"],
            host="db",
            database="visionq",
        )

    return create_engine(url, pool_pre_ping=True)
