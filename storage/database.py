"""Database: the SQLite connection and table definitions. All SQL lives in storage/."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "library.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    item_id          TEXT PRIMARY KEY,
    type             TEXT NOT NULL,
    title            TEXT NOT NULL,
    author           TEXT NOT NULL,
    year             INTEGER NOT NULL,
    subject          TEXT NOT NULL DEFAULT '',
    description      TEXT NOT NULL DEFAULT '',
    total_copies     INTEGER,            -- NULL for e-books (unlimited)
    available_copies INTEGER,
    withdrawn        INTEGER NOT NULL DEFAULT 0, -- 1 = hidden from the catalog
    extra            TEXT NOT NULL DEFAULT '{}'  -- JSON: isbn, supervisor, ...
);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    role          TEXT NOT NULL,         -- Student, Faculty or Librarian
    name          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    fines         REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notifications (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         TEXT NOT NULL REFERENCES users(user_id),
    message         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loans (
    loan_id     INTEGER PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(user_id),
    item_id     TEXT NOT NULL REFERENCES items(item_id),
    issue_date  TEXT NOT NULL,           -- ISO dates, e.g. 2026-10-25
    due_date    TEXT NOT NULL,
    return_date TEXT
);

CREATE TABLE IF NOT EXISTS reservations (
    user_id    TEXT NOT NULL REFERENCES users(user_id),
    item_id    TEXT NOT NULL REFERENCES items(item_id),
    created_at TEXT NOT NULL,            -- ISO date-time
    notified   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, item_id)
);
"""

# Columns added after the first version: (table, column, SQL type and default).
# A database file made before they existed gets them added when it is opened.
ADDED_COLUMNS = [
    ("items", "withdrawn", "INTEGER NOT NULL DEFAULT 0"),
]


def default_db_path() -> str:
    """DB file path: LIBRARY_DB_PATH from .env, or library.db in the project folder.

    A relative path is taken relative to the project folder, not the current directory.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    value = os.getenv("LIBRARY_DB_PATH")
    if not value:
        return str(DEFAULT_DB_PATH)
    path = Path(value)
    return str(path if path.is_absolute() else PROJECT_ROOT / path)


class Database:
    """Owns one SQLite connection and creates the tables on first use."""

    def __init__(self, path: str | None = None) -> None:
        """Open (or create) the database file. path defaults to default_db_path()."""
        self._path: str = path or default_db_path()
        # isolation_level=None: each statement commits on its own,
        # unless it runs inside transaction().
        self._conn = sqlite3.connect(self._path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row  # rows can be read by column name
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """Bring an older database file up to date with ADDED_COLUMNS."""
        for table, column, definition in ADDED_COLUMNS:
            existing = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def is_empty(self) -> bool:
        """Return True if no users or items have been saved yet."""
        for table in ("users", "items"):
            if self._conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                return False
        return True

    @property
    def path(self) -> str:
        """Path of the database file."""
        return self._path

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        """Run one SQL statement with ? placeholders and return the cursor."""
        return self._conn.execute(sql, params)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group statements so they all succeed or none do.

        Usage:  with db.transaction(): ...
        """
        self._conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()
