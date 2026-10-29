"""User hierarchy: User -> Member -> Student / Faculty, and User -> Librarian."""

from __future__ import annotations

import hashlib
import hmac
import os
from abc import ABC, abstractmethod
from datetime import date
from typing import TYPE_CHECKING, Any

from exceptions import LibraryException, LimitExceeded, OverdueLoans, UnpaidFines
from services.fine_policy import FacultyFinePolicy, FinePolicy, StudentFinePolicy

if TYPE_CHECKING:
    # Only used for type hints; a real import would be circular (Loan uses Member).
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

    def get_role_plural(self) -> str:
        """Role name for a group of people, e.g. 'students'."""
        return self.get_role().lower() + "s"

    def can_manage_library(self) -> bool:
        """Return True if this user may add items, issue/return and manage members."""
        return False

    def to_dict(self) -> dict[str, Any]:
        """Public account data for the web API. Never includes the password hash."""
        return {
            "user_id": self._user_id,
            "name": self._name,
            "role": self.get_role(),
            "can_manage_library": self.can_manage_library(),
        }

    def __repr__(self) -> str:
        return f"{self.get_role()}(id={self._user_id!r}, name={self._name!r})"


class Member(User):
    """Abstract base for users who borrow items (Student, Faculty)."""

    # Members whose current fine is above this amount cannot borrow.
    # 0.0 means any unpaid fine blocks borrowing. Change here only.
    FINE_BLOCK_THRESHOLD: float = 0.0

    def __init__(self, user_id: str, name: str, password_hash: str) -> None:
        """Create a member with no loans, no history and no fines."""
        super().__init__(user_id, name, password_hash)
        self._loans: list[Loan] = []    # items currently borrowed
        self._history: list[Loan] = []  # loans already returned
        self._current_fine: float = 0.0  # charged and unpaid (payable now)
        self._notifications: list[str] = []  # messages from NotificationCenter

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
    def current_fine(self) -> float:
        """Fine already charged and not yet paid; payable now (use add_fine / pay_fine)."""
        return self._current_fine

    @property
    def notifications(self) -> list[str]:
        """Messages received, oldest first. Returns a copy."""
        return list(self._notifications)

    # ---- fines ----
    # Current fine: charged when a late item comes back, payable now.
    # Accruing fine: what the overdue items still out will add when they are returned.
    # Total fine: current + accruing (what the member would owe if everything came back today).

    def accruing_fine(self, today: date | None = None) -> float:
        """What overdue loans still out will add to the current fine when they are returned."""
        return sum(loan.calculate_fine(today) for loan in self._loans)

    def total_fine(self, today: date | None = None) -> float:
        """Current fine plus what overdue loans will add when returned."""
        return self._current_fine + self.accruing_fine(today)

    # ---- abstract rules each member type must define ----

    @abstractmethod
    def get_borrow_limit(self) -> int:
        """Maximum number of items this member can hold at once."""

    @abstractmethod
    def get_loan_days(self) -> int:
        """Default loan period in days for this member type."""

    @abstractmethod
    def get_fine_policy(self) -> FinePolicy:
        """Fine rules that apply to this member's late returns."""

    def has_research_access(self) -> bool:
        """Return True if this member may borrow research items such as theses."""
        return False

    # ---- borrowing rules ----

    def check_can_borrow(self, today: date | None = None) -> None:
        """Raise UnpaidFines, OverdueLoans or LimitExceeded if this member may not borrow now.

        Each exception also carries next_step: what the member can do about it.
        """
        if self._current_fine > self.FINE_BLOCK_THRESHOLD:
            raise UnpaidFines(
                f"{self.name} has a current fine of Rs {self._current_fine:g}.",
                next_step=f"Pay the current fine of Rs {self._current_fine:g} to borrow again.",
            )
        overdue = [loan for loan in self._loans if loan.is_overdue(today)]
        if overdue:
            # Checked separately from fines: the fine is only charged on return,
            # so an overdue item still out shows a current fine of 0.
            if len(overdue) == 1:
                title = overdue[0].item.title
                raise OverdueLoans(f'"{title}" is overdue.',
                                   next_step=f'Return "{title}" to borrow again.')
            raise OverdueLoans(f"{len(overdue)} items are overdue.",
                               next_step=f"Return the {len(overdue)} overdue items to borrow again.")
        if len(self._loans) >= self.get_borrow_limit():
            raise LimitExceeded(
                f"{self.name} already has {len(self._loans)} of "
                f"{self.get_borrow_limit()} allowed items.",
                next_step="Return an item to borrow another.",
            )

    def can_borrow(self, today: date | None = None) -> bool:
        """Return True if this member may borrow another item right now."""
        try:
            self.check_can_borrow(today)
            return True
        except LibraryException:
            return False

    def borrow_block_reason(self, today: date | None = None) -> str | None:
        """Why this member cannot borrow right now, in words, or None if they can."""
        try:
            self.check_can_borrow(today)
            return None
        except LibraryException as e:
            return e.message

    def borrow_next_step(self, today: date | None = None) -> str | None:
        """What the member should do to borrow again, e.g. 'Return "X" to borrow again.'"""
        try:
            self.check_can_borrow(today)
            return None
        except LibraryException as e:
            return e.next_step

    def has_loan_of(self, item_id: str) -> bool:
        """Return True if this member currently has this item on loan."""
        return any(loan.item.item_id == item_id for loan in self._loans)

    def to_dict(self) -> dict[str, Any]:
        """Account data plus the member's borrowing rules and current state."""
        data = super().to_dict()
        data.update(
            current_fine=self._current_fine,
            accruing_fine=self.accruing_fine(),
            total_fine=self.total_fine(),
            borrow_limit=self.get_borrow_limit(),
            loan_days=self.get_loan_days(),
            active_loans=len(self._loans),
            overdue_loans=sum(1 for loan in self._loans if loan.is_overdue()),
            loans_remaining=max(0, self.get_borrow_limit() - len(self._loans)),
            can_borrow=self.can_borrow(),
            borrow_block_reason=self.borrow_block_reason(),
            borrow_next_step=self.borrow_next_step(),
            fine_policy=self.get_fine_policy().describe(),
            has_research_access=self.has_research_access(),
        )
        return data

    # ---- notifications (Observer side) ----

    def receive_notification(self, message: str) -> None:
        """Called by NotificationCenter when something this member waits for happens."""
        self._notifications.append(message)

    # ---- loan and fine bookkeeping (called by Library, not by routes) ----

    def add_loan(self, loan: Loan) -> None:
        """Record a new active loan. The loan must belong to this member."""
        if loan.member is not self:
            raise ValueError("This loan belongs to a different member.")
        self._loans.append(loan)

    def close_loan(self, loan: Loan) -> None:
        """Move a loan from the active list to the history."""
        self._loans.remove(loan)
        self._history.append(loan)

    def add_fine(self, amount: float) -> None:
        """Charge a fine: it is added to the current fine."""
        if amount < 0:
            raise ValueError("Fine amount cannot be negative.")
        self._current_fine += amount

    def pay_fine(self, amount: float) -> None:
        """Pay off part or all of the current fine."""
        if amount <= 0:
            raise ValueError("Payment must be positive.")
        if amount > self._current_fine:
            raise ValueError(f"Payment is more than the current fine of Rs {self._current_fine:g}.")
        self._current_fine -= amount


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

    def get_fine_policy(self) -> FinePolicy:
        return StudentFinePolicy()


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

    def get_fine_policy(self) -> FinePolicy:
        return FacultyFinePolicy()

    def get_role_plural(self) -> str:
        return "faculty"  # "faculty" is already plural

    def has_research_access(self) -> bool:
        return True


class Librarian(User):
    """Library staff: manages items, loans, members, fine rules and reports."""

    def get_role(self) -> str:
        return "Librarian"

    def can_manage_library(self) -> bool:
        return True
