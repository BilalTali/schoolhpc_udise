"""
SQLAlchemy engine and session factory.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, connect_args=_connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Creates missing tables and adds columns that older databases don't have yet."""
    import backend.models.entities  # noqa: F401  (registers the models)
    import backend.models.library   # noqa: F401
    import backend.models.settings  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        raise SystemExit(
            f"Cannot open the database ({DATABASE_URL.split('@')[-1]}): {exc}\n"
            "Start MySQL in the XAMPP control panel, or set HPC_DATABASE_URL in .env."
        )
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    col_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type} NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
