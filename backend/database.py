"""
SQLAlchemy engine and session factory.
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.config import DATABASE_URL

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
# every request and every running upload (it keeps one connection while it saves) needs a connection: room for
# a busy school (the default 5 + 10 runs out with a few uploads and a full page of teachers)
_pool = {} if DATABASE_URL.startswith("sqlite") else {"pool_size": 20, "max_overflow": 40, "pool_timeout": 20}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=3600, connect_args=_connect_args, **_pool)
if DATABASE_URL.startswith("mysql"):
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _long_idle(dbapi_conn, _record):
        """XAMPP's MySQL drops a connection after 60 s idle ("MySQL server has gone away"); a save that waits on
        PARAKH longer than that lost its connection. Each connection of the app asks for the usual 8 hours."""
        cur = dbapi_conn.cursor()
        try:
            cur.execute("SET SESSION wait_timeout = 28800")
        finally:
            cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    """Creates missing tables and adds columns that older databases don't have yet."""
    import backend.models.entities  # noqa: F401  (registers the models)
    import backend.models.library   # noqa: F401
    import backend.models.settings  # noqa: F401
    import backend.models.register  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        raise SystemExit(
            f"Cannot open the database ({DATABASE_URL.split('@')[-1]}): {exc}\n"
            "Start MySQL in the XAMPP control panel, or set HPC_DATABASE_URL in .env."
        )
    migrate(engine)


def migrate(engine) -> None:
    """Brings tables made by older versions up to date: missing columns, and the unique rule of a column
    marked unique (create_all only adds those to new tables)."""
    import backend.models.entities  # noqa: F401
    import backend.models.library   # noqa: F401
    import backend.models.settings  # noqa: F401
    import backend.models.register  # noqa: F401
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
            unique = {tuple(i["column_names"]) for i in inspector.get_indexes(table.name) if i.get("unique")}
            unique |= {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table.name)}
            for column in table.columns:
                if column.unique and (column.name,) not in unique:
                    conn.execute(text(f"CREATE UNIQUE INDEX uq_{table.name}_{column.name} ON {table.name} ({column.name})"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
