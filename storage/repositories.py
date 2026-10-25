"""Repositories: save and load model objects. The only place (with database.py) that has SQL."""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Generic, TypeVar

from models.items import LibraryItem
from models.loan import Loan
from models.reservation import Reservation
from models.users import Faculty, Librarian, Member, Student, User
from services.item_factory import ItemFactory
from storage.database import Database

T = TypeVar("T")  # the kind of object a repository stores


class Repository(ABC, Generic[T]):
    """Saves and loads one kind of object to one table.

    Subclasses only say which table and columns they use, and how to turn an
    object into a row and back (_to_row / _from_row). The SQL itself is written
    once, here.
    """

    TABLE: str = ""
    COLUMNS: tuple[str, ...] = ()
    KEY_COLUMNS: tuple[str, ...] = ()  # primary key column(s)
    ORDER_BY: str = ""                 # order for all(), e.g. "loan_id"

    def __init__(self, db: Database) -> None:
        """Create a repository that uses this database."""
        self._db: Database = db

    @abstractmethod
    def _to_row(self, obj: T) -> dict[str, Any]:
        """Turn an object into {column: value}."""

    @abstractmethod
    def _from_row(self, row: sqlite3.Row) -> T:
        """Turn a database row back into an object."""

    def save(self, obj: T) -> None:
        """Insert the object, or replace the saved copy if it already exists."""
        row = self._to_row(obj)
        columns = ", ".join(self.COLUMNS)
        placeholders = ", ".join("?" for _ in self.COLUMNS)
        self._db.execute(
            f"INSERT OR REPLACE INTO {self.TABLE} ({columns}) VALUES ({placeholders})",
            [row[c] for c in self.COLUMNS],
        )

    def find(self, *key: Any) -> T | None:
        """Return the object with this primary key, or None."""
        row = self._db.execute(
            f"SELECT * FROM {self.TABLE} WHERE {self._key_condition()}", key
        ).fetchone()
        return self._from_row(row) if row else None

    def all(self) -> list[T]:
        """Return every saved object."""
        order = f" ORDER BY {self.ORDER_BY}" if self.ORDER_BY else ""
        rows = self._db.execute(f"SELECT * FROM {self.TABLE}{order}").fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, *key: Any) -> None:
        """Delete the object with this primary key (no error if it is not there)."""
        self._db.execute(f"DELETE FROM {self.TABLE} WHERE {self._key_condition()}", key)

    def clear(self) -> None:
        """Delete every row in this table."""
        self._db.execute(f"DELETE FROM {self.TABLE}")

    def _key_condition(self) -> str:
        """SQL condition like 'user_id = ? AND item_id = ?'."""
        return " AND ".join(f"{c} = ?" for c in self.KEY_COLUMNS)


# Table and column names above come only from these class constants, never from
# user input; values always go through ? placeholders, which prevents SQL injection.


class ItemRepository(Repository[LibraryItem]):
    """Saves items. Rebuilds them with ItemFactory, so each comes back as the right subclass."""

    TABLE = "items"
    COLUMNS = ("item_id", "type", "title", "author", "year", "subject", "description",
               "total_copies", "available_copies", "withdrawn", "extra")
    KEY_COLUMNS = ("item_id",)
    ORDER_BY = "item_id"

    def _to_row(self, obj: LibraryItem) -> dict[str, Any]:
        data = obj.to_dict()
        row = {c: data.get(c) for c in self.COLUMNS if c != "extra"}
        # Fields only some types have (isbn, supervisor, ...) go into one JSON column.
        extras = {k: v for k, v in data.items() if k not in self.COLUMNS}
        row["extra"] = json.dumps(extras)
        return row

    def _from_row(self, row: sqlite3.Row) -> LibraryItem:
        data = {c: row[c] for c in self.COLUMNS if c != "extra"}
        data.update(json.loads(row["extra"]))
        return ItemFactory.create(data)


class UserRepository(Repository[User]):
    """Saves users with their password hash, fine balance and notifications."""

    TABLE = "users"
    COLUMNS = ("user_id", "role", "name", "password_hash", "fines")
    KEY_COLUMNS = ("user_id",)
    ORDER_BY = "user_id"

    _ROLE_CLASSES: dict[str, type[User]] = {
        "Student": Student, "Faculty": Faculty, "Librarian": Librarian,
    }

    def _to_row(self, obj: User) -> dict[str, Any]:
        return {
            "user_id": obj.user_id,
            "role": obj.get_role(),
            "name": obj.name,
            "password_hash": obj.password_hash,  # the hash, never a plain password
            "fines": obj.fines if isinstance(obj, Member) else 0.0,
        }

    def _from_row(self, row: sqlite3.Row) -> User:
        cls = self._ROLE_CLASSES.get(row["role"])
        if cls is None:
            raise ValueError(f"Unknown role {row['role']!r} for user {row['user_id']!r}.")
        user = cls(row["user_id"], row["name"], row["password_hash"])
        if isinstance(user, Member):
            if row["fines"] > 0:
                user.add_fine(row["fines"])
            for message in self._load_notifications(user.user_id):
                user.receive_notification(message)
        return user

    def save(self, obj: User) -> None:
        """Save the user row, then replace their saved notifications."""
        super().save(obj)
        self._db.execute("DELETE FROM notifications WHERE user_id = ?", (obj.user_id,))
        if isinstance(obj, Member):
            for message in obj.notifications:
                self._db.execute(
                    "INSERT INTO notifications (user_id, message) VALUES (?, ?)",
                    (obj.user_id, message),
                )

    def delete(self, *key: Any) -> None:
        self._db.execute("DELETE FROM notifications WHERE user_id = ?", key)
        super().delete(*key)

    def clear(self) -> None:
        self._db.execute("DELETE FROM notifications")
        super().clear()

    def _load_notifications(self, user_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT message FROM notifications WHERE user_id = ? ORDER BY notification_id",
            (user_id,),
        ).fetchall()
        return [row["message"] for row in rows]


class LoanRepository(Repository[Loan]):
    """Saves loans. Needs the already-loaded users and items to rebuild them."""

    TABLE = "loans"
    COLUMNS = ("loan_id", "user_id", "item_id", "issue_date", "due_date", "return_date")
    KEY_COLUMNS = ("loan_id",)
    ORDER_BY = "loan_id"

    def __init__(self, db: Database, users: Mapping[str, User],
                 items: Mapping[str, LibraryItem]) -> None:
        """users and items map ids to the objects that loans should point to."""
        super().__init__(db)
        self._users = users
        self._items = items

    def _to_row(self, obj: Loan) -> dict[str, Any]:
        return {
            "loan_id": obj.loan_id,
            "user_id": obj.member.user_id,
            "item_id": obj.item.item_id,
            "issue_date": obj.issue_date.isoformat(),
            "due_date": obj.due_date.isoformat(),
            "return_date": obj.return_date.isoformat() if obj.return_date else None,
        }

    def _from_row(self, row: sqlite3.Row) -> Loan:
        member = self._users[row["user_id"]]
        if not isinstance(member, Member):
            raise ValueError(f"Loan {row['loan_id']} belongs to a non-member.")
        return Loan(
            row["loan_id"],
            member,
            self._items[row["item_id"]],
            date.fromisoformat(row["issue_date"]),
            date.fromisoformat(row["due_date"]),
            date.fromisoformat(row["return_date"]) if row["return_date"] else None,
        )


class ReservationRepository(Repository[Reservation]):
    """Saves reservations, including whether the member was told a copy is held."""

    TABLE = "reservations"
    COLUMNS = ("user_id", "item_id", "created_at", "notified")
    KEY_COLUMNS = ("user_id", "item_id")
    ORDER_BY = "created_at, user_id"  # waitlist order

    def __init__(self, db: Database, users: Mapping[str, User],
                 items: Mapping[str, LibraryItem]) -> None:
        """users and items map ids to the objects that reservations should point to."""
        super().__init__(db)
        self._users = users
        self._items = items

    def _to_row(self, obj: Reservation) -> dict[str, Any]:
        return {
            "user_id": obj.member.user_id,
            "item_id": obj.item.item_id,
            "created_at": obj.created_at.isoformat(),
            "notified": int(obj.notified),
        }

    def _from_row(self, row: sqlite3.Row) -> Reservation:
        member = self._users[row["user_id"]]
        if not isinstance(member, Member):
            raise ValueError(f"Reservation by non-member {row['user_id']!r}.")
        return Reservation(
            member,
            self._items[row["item_id"]],
            datetime.fromisoformat(row["created_at"]),
            bool(row["notified"]),
        )
