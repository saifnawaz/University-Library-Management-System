"""Loan: one item borrowed by one member."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only for type hints; avoids a circular import with models.users.
    from models.items import LibraryItem
    from models.users import Member


class Loan:
    """Records that a member borrowed an item, when, and when it is due back.

    The due date is decided by Library.issue() and passed in here.
    """

    def __init__(
        self,
        loan_id: int,
        member: Member,
        item: LibraryItem,
        issue_date: date,
        due_date: date,
        return_date: date | None = None,
    ) -> None:
        """Create a loan. return_date stays None until the item comes back."""
        if due_date < issue_date:
            raise ValueError("Due date cannot be before the issue date.")
        if return_date is not None and return_date < issue_date:
            raise ValueError("Return date cannot be before the issue date.")
        self._loan_id: int = loan_id
        self._member: Member = member
        self._item: LibraryItem = item
        self._issue_date: date = issue_date
        self._due_date: date = due_date
        self._return_date: date | None = return_date

    # ---- properties (all read-only) ----

    @property
    def loan_id(self) -> int:
        """Unique number of this loan, given by Library."""
        return self._loan_id

    @property
    def member(self) -> Member:
        """Member who borrowed the item."""
        return self._member

    @property
    def item(self) -> LibraryItem:
        """Item that was borrowed."""
        return self._item

    @property
    def issue_date(self) -> date:
        """Day the item was issued."""
        return self._issue_date

    @property
    def due_date(self) -> date:
        """Day the item must be returned by."""
        return self._due_date

    @property
    def return_date(self) -> date | None:
        """Day the item was returned, or None if it is still out."""
        return self._return_date

    # ---- state ----

    def is_returned(self) -> bool:
        """Return True if the item has been returned."""
        return self._return_date is not None

    def mark_returned(self, on: date | None = None) -> None:
        """Record the return date (today by default). Called by Library.return_item()."""
        if self.is_returned():
            raise ValueError(f'"{self._item.title}" was already returned.')
        on = on or date.today()
        if on < self._issue_date:
            raise ValueError("Return date cannot be before the issue date.")
        self._return_date = on

    def days_overdue(self, today: date | None = None) -> int:
        """Days past the due date: up to today if still out, or up to the return date."""
        end = self._return_date or today or date.today()
        return max(0, (end - self._due_date).days)

    def is_overdue(self, today: date | None = None) -> bool:
        """Return True if the item is late (still out past due, or was returned late)."""
        return self.days_overdue(today) > 0

    def calculate_fine(self, today: date | None = None) -> float:
        """Fine for this loan. The member's fine policy decides the amount."""
        policy = self._member.get_fine_policy()
        return policy.calculate_fine(self.days_overdue(today))

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        """Loan data for the web API, including how late it is and the fine so far."""
        return {
            "loan_id": self._loan_id,
            "member_id": self._member.user_id,
            "member_name": self._member.name,
            "item_id": self._item.item_id,
            "item_title": self._item.title,
            "item_type": self._item.get_item_type(),
            "issue_date": self._issue_date.isoformat(),
            "due_date": self._due_date.isoformat(),
            "return_date": self._return_date.isoformat() if self._return_date else None,
            "returned": self.is_returned(),
            "overdue": self.is_overdue(today),
            "days_overdue": self.days_overdue(today),
            "fine": self.calculate_fine(today),
        }

    def __repr__(self) -> str:
        return (f"Loan(id={self._loan_id}, member={self._member.user_id!r}, "
                f"item={self._item.item_id!r}, "
                f"due={self._due_date.isoformat()})")
