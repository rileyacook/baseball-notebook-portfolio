"""Create safe, read-only connections to the MLB DuckDB database."""

from pathlib import Path

import duckdb


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "database" / "mlb.duckdb"


def connect_read_only(
    database_path: Path | str = DEFAULT_DATABASE_PATH,
) -> duckdb.DuckDBPyConnection:
    """Return a read-only DuckDB connection after validating the path."""
    resolved_path = Path(database_path).expanduser().resolve()

    if not resolved_path.is_file():
        raise FileNotFoundError(
            f"DuckDB database not found:\n{resolved_path}\n"
            "Run the Day 2 ingestion pipeline first."
        )

    return duckdb.connect(str(resolved_path), read_only=True, config={"memory_limit": "128MB", "threads": "1", "enable_external_access": False})
