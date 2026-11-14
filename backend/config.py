"""Environment-based application configuration."""

import os
from pathlib import Path


def database_path() -> Path:
    """Return the SQLite file location, creating no files here."""
    return Path(os.environ.get("CONTINUUM_DATABASE_PATH", "data/continuum.sqlite3"))
