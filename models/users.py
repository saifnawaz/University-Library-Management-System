"""User hierarchy: User -> Member -> Student / Faculty, and User -> Librarian."""

from __future__ import annotations

import hashlib
import hmac
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from exceptions import LimitExceeded, UnpaidFines

if TYPE_CHECKING:
    # Only used for type hints; the Loan class is written in Phase 3.
    from models.loan import Loan


class User(ABC):
    """Abstract base for everyone who can log in to the system."""

    _HASH_ITERATIONS: int = 200_000

    def __init__(self, user_id: str, name: str, password_hash: str) -> None:
        """Create a user. Pass a hash made by User.hash_password(), never a plain password."""
        self._user_id: str = user_id
        self._name: str = ""
        self.name = name  # goes through the setter, so it is validated
        self._password_hash: str = password_hash

    # ---- properties (encapsulation) ----

    @property
    def user_id(self) -> str:
        """Unique id of the user (read-only)."""
        return self._user_id

    @property
    def name(self) -> str:
        """Display name of the user."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("Name cannot be empty.")
        self._name = value

    @property
    def password_hash(self) -> str:
        """Stored password hash (read-only; use set_password to change it)."""
        return self._password_hash

    # ---- password handling ----

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Return a salted PBKDF2 hash of the password, as 'salt$hash' in hex."""
        if not plain_password:
            raise ValueError("Password cannot be empty.")
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode(), salt, User._HASH_ITERATIONS
        )
        return f"{salt.hex()}${digest.hex()}"

    def set_password(self, plain_password: str) -> None:
        """Replace the user's password with a new one (stored as a hash)."""
        self._password_hash = User.hash_password(plain_password)

    def check_password(self, plain_password: str) -> bool:
        """Return True if the given password matches the stored hash."""
        try:
            salt_hex, digest_hex = self._password_hash.split("$")
        except ValueError:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode(), bytes.fromhex(salt_hex), User._HASH_ITERATIONS
        )
        return hmac.compare_digest(digest.hex(), digest_hex)

    # ---- role ----

    @abstractmethod
    def get_role(self) -> str:
        """Return the role name, e.g. 'Student'."""

    def can_manage_library(self) -> bool:
        """Return True if this user may add items, issue/return and manage members."""
        return False

    def __repr__(self) -> str:
        return f"{self.get_role()}(id={self._user_id!r}, name={self._name!r})"


class Member(User):
    """Abstract base for users who borrow items (Student, Faculty)."""

    # Members with unpaid fines above this amount cannot borrow.
    # 0.0 means any unpaid fine blocks borrowing. Change here only.
    FINE_BLOCK_THRESHOLD: float = 0.0

    def __init__(self, user_id: str, name: str, password_hash: str) -> None:
        """Create a member with no loans, no history and no fines."""
        super().__init__(user_id, name, password_hash)
        self._loans: list[Loan] = []    # items currently borrowed
        self._history: list[Loan] = []  # loans already returned
        self._fines: float = 0.0        # unpaid fine balance

    # ---- properties ----

    @property
    def loans(self) -> list[Loan]:
        """Current (not yet returned) loans. Returns a copy so callers cannot edit it."""
        return list(self._loans)

    @property
    def history(self) -> list[Loan]:
        """Past (returned) loans. Returns a copy."""
        return list(self._history)

    @property
    def fines(self) -> float:
        """Unpaid fine balance (read-only; use add_fine / pay_fine)."""
        return self._fines

    # ---- abstract rules each member type must define ----

    @abstractmethod
    def get_borrow_limit(self) -> int:
        """Maximum number of items this member can hold at once."""

    @abstractmethod
    def get_loan_days(self) -> int:
        """Default loan period in days for this member type."""

    # get_fine_policy() is added in Phase 3, once the FinePolicy classes exist.

    # ---- borrowing rules ----

    def check_can_borrow(self) -> None:
        """Raise UnpaidFines or LimitExceeded if this member may not borrow right now."""
        if self._fines > self.FINE_BLOCK_THRESHOLD:
            raise UnpaidFines(f"{self.name} has unpaid fines of {self._fines:.2f}.")
        if len(self._loans) >= self.get_borrow_limit():
            raise LimitExceeded(
                f"{self.name} already has {len(self._loans)} of "
                f"{self.get_borrow_limit()} allowed items."
            )

    def can_borrow(self) -> bool:
        """Return True if this member may borrow another item right now."""
        try:
            self.check_can_borrow()
            return True
        except (UnpaidFines, LimitExceeded):
            return False

    # ---- loan and fine bookkeeping (called by Library, not by routes) ----

    def add_loan(self, loan: Loan) -> None:
        """Record a new active loan."""
        self._loans.append(loan)

    def close_loan(self, loan: Loan) -> None:
        """Move a loan from the active list to the history."""
        self._loans.remove(loan)
        self._history.append(loan)

    def add_fine(self, amount: float) -> None:
        """Add an amount to the unpaid fine balance."""
        if amount < 0:
            raise ValueError("Fine amount cannot be negative.")
        self._fines += amount

    def pay_fine(self, amount: float) -> None:
        """Pay off part or all of the unpaid fine balance."""
        if amount <= 0:
            raise ValueError("Payment must be positive.")
        if amount > self._fines:
            raise ValueError(f"Payment is more than the balance of {self._fines:.2f}.")
        self._fines -= amount


class Student(Member):
    """A student member: 3 items at a time, 14-day loans."""

    BORROW_LIMIT: int = 3
    LOAN_DAYS: int = 14

    def get_role(self) -> str:
        return "Student"

    def get_borrow_limit(self) -> int:
        return self.BORROW_LIMIT

    def get_loan_days(self) -> int:
        return self.LOAN_DAYS


class Faculty(Member):
    """A faculty member: 10 items at a time, 30-day loans."""

    BORROW_LIMIT: int = 10
    LOAN_DAYS: int = 30

    def get_role(self) -> str:
        return "Faculty"

    def get_borrow_limit(self) -> int:
        return self.BORROW_LIMIT

    def get_loan_days(self) -> int:
        return self.LOAN_DAYS


class Librarian(User):
    """Library staff: manages items, loans, members, fine rules and reports."""

    def get_role(self) -> str:
        return "Librarian"

    def can_manage_library(self) -> bool:
        return True
