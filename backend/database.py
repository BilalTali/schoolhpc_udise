"""
SQLAlchemy Database Engine and Session Factory
"""
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import DATABASE_URL, SQLITE_URL

try:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False
    )
    # Test connection immediately
    with engine.connect() as conn:
        pass
    print("[DB] Connected successfully to MySQL database (XAMPP).")
except Exception as e:
    print(f"[DB WARN] Could not connect to MySQL ({e}). Falling back to SQLite.")
    engine = create_engine(SQLITE_URL, echo=False)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
