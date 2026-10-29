"""Reservation: a member's place in the waitlist for an item."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from models.items import LibraryItem
    from models.users import Member


class Reservation:
    """A member waiting for an item. Earlier reservations come first in the waitlist."""

    def __init__(self, member: Member, item: LibraryItem,
                 created_at: datetime | None = None, notified: bool = False,
                 held_until: date | None = None) -> None:
        """Create a reservation. Pass created_at, notified and held_until when loading saved data."""
        self._member: Member = member
        self._item: LibraryItem = item
        self._created_at: datetime = created_at or datetime.now()
        self._notified: bool = notified
        self._held_until: date | None = held_until

    @property
    def member(self) -> Member:
        """Member who is waiting."""
        return self._member

    @property
    def item(self) -> LibraryItem:
        """Item being waited for."""
        return self._item

    @property
    def created_at(self) -> datetime:
        """When the reservation was made; decides the waitlist order."""
        return self._created_at

    @property
    def notified(self) -> bool:
        """True once the member has been told a copy is held for them."""
        return self._notified

    @property
    def held_until(self) -> date | None:
        """Last day the member can collect the held copy (None while no copy is held)."""
        return self._held_until

    def hold_copy(self, until: date) -> None:
        """Record that a copy is held for the member until the end of `until`."""
        self._notified = True
        self._held_until = until

    def is_hold_expired(self, today: date) -> bool:
        """True once the last collection day has passed without the member borrowing it."""
        return self._held_until is not None and today > self._held_until

    def to_dict(self) -> dict[str, Any]:
        """Reservation data for the web API."""
        return {
            "member_id": self._member.user_id,
            "member_name": self._member.name,
            "item_id": self._item.item_id,
            "item_title": self._item.title,
            "item_author": self._item.author,
            "item_type": self._item.get_item_type(),
            "item_type_key": self._item.TYPE_KEY,
            "created_at": self._created_at.isoformat(timespec="seconds"),
            "notified": self._notified,
            "held_until": self._held_until.isoformat() if self._held_until else None,
        }

    def __lt__(self, other: object) -> bool:
        """Earlier reservation is 'smaller', so sorted(reservations) gives waitlist order."""
        if not isinstance(other, Reservation):
            return NotImplemented
        # Same timestamp is very unlikely; user_id breaks the tie so order is stable.
        return (self._created_at, self._member.user_id) < (other._created_at, other._member.user_id)

    def __repr__(self) -> str:
        return (f"Reservation(member={self._member.user_id!r}, item={self._item.item_id!r}, "
                f"created_at={self._created_at.isoformat(timespec='seconds')})")
