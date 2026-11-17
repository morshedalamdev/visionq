"""Database connection for the foundation operator commands."""

import os

from sqlalchemy import URL, create_engine


def database():
    url = URL.create(
        "postgresql+psycopg",
        username="visionq",
        password=os.environ["POSTGRES_PASSWORD"],
        host="db",
        database="visionq",
    )
    return create_engine(url)
