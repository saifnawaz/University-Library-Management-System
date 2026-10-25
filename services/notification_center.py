"""NotificationCenter: tells waiting members when an item comes back (Observer pattern)."""

from __future__ import annotations

from models.users import Member


class NotificationCenter:
    """Keeps, for each item, the members waiting for it, in waitlist order.

    Members 'subscribe' when they reserve. When a copy is returned, Library calls
    notify(), and the next waiting member gets a message. The returning code does
    not need to know who is waiting or how they are told.
    """

    def __init__(self) -> None:
        """Start with no subscribers."""
        self._subscribers: dict[str, list[Member]] = {}  # item_id -> waiting members

    def subscribe(self, item_id: str, member: Member) -> None:
        """Add a member to the end of the line for this item (ignored if already in it)."""
        line = self._subscribers.setdefault(item_id, [])
        if member not in line:
            line.append(member)

    def unsubscribe(self, item_id: str, member: Member) -> None:
        """Remove a member from the line for this item, if they are in it."""
        line = self._subscribers.get(item_id, [])
        if member in line:
            line.remove(member)

    def subscribers(self, item_id: str) -> list[Member]:
        """Members still waiting to be told about this item, in order. Returns a copy."""
        return list(self._subscribers.get(item_id, []))

    def notify(self, item_id: str, message: str) -> Member | None:
        """Send the message to the next member in line and return them (None if nobody waits).

        The member is then taken out of the line, so the next returned copy
        goes to the person after them.
        """
        line = self._subscribers.get(item_id, [])
        if not line:
            return None
        member = line.pop(0)
        member.receive_notification(message)
        return member
