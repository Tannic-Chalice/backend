# app/database.py

import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
# Example: postgresql://username:password@hostname:5432/dbname

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment")

# Convert psycopg2 URL to SQLAlchemy format if needed
SQLALCHEMY_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://") if "postgresql://" in DATABASE_URL else DATABASE_URL

# -------------------------------------------------------------------------
# SQLAlchemy Setup
# -------------------------------------------------------------------------
engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# -------------------------------------------------------------------------
# Parse DATABASE_URL manually for psycopg2
# -------------------------------------------------------------------------
def parse_database_url(url: str):
    parsed = urlparse(url)

    return {
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "database": parsed.path.lstrip("/"),
    }


DB_CONFIG = parse_database_url(DATABASE_URL)


# -------------------------------------------------------------------------
# psycopg2 Connection Pool
# -------------------------------------------------------------------------
try:
    connection_pool = pool.SimpleConnectionPool(1, 10, **DB_CONFIG)
except psycopg2.Error as e:
    print(f"Failed to create connection pool: {e}")
    connection_pool = None

# -------------------------------------------------------------------------
# Context-managed DB connection
# -------------------------------------------------------------------------
@contextmanager
def get_db():
    """
    Usage:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            print(cur.fetchone())
    """
    if connection_pool is None:
        raise RuntimeError("Database connection pool not initialized")
    
    conn = connection_pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        connection_pool.putconn(conn)

