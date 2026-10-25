"""Library: the one object that owns all items, users, loans and reservations (Singleton)."""

from __future__ import annotations

from datetime import date, timedelta

from exceptions import ItemNotAvailable, LibraryException, NotFound, PermissionDenied
from models.items import LibraryItem
from models.loan import Loan
from models.reservation import Reservation
from models.users import Member, User
from services.notification_center import NotificationCenter


class Library:
    """Central service for the library. Every library rule is applied here or in the models.

    Library() always returns the same object, so every part of the app sees the
    same data.
    """

    _instance: Library | None = None

    def __new__(cls) -> Library:
        """Create the object the first time; afterwards return the same one."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Set up empty storage, but only once (Python calls __init__ on every Library())."""
        if self._initialized:
            return
        self._items: dict[str, LibraryItem] = {}
        self._users: dict[str, User] = {}
        self._loans: list[Loan] = []                # every loan, active and returned
        self._reservations: list[Reservation] = []  # active reservations only
        self._notifications: NotificationCenter = NotificationCenter()
        self._initialized: bool = True

    @classmethod
    def reset(cls) -> None:
        """Forget the current instance so the next Library() starts empty. For tests."""
        cls._instance = None

    # ---- items and users ----

    def add_item(self, actor: User, item: LibraryItem) -> None:
        """Add an item to the catalog. Librarians only."""
        self._require_librarian(actor)
        if item.item_id in self._items:
            raise ValueError(f"An item with id {item.item_id!r} already exists.")
        self._items[item.item_id] = item

    def add_user(self, user: User) -> None:
        """Register a user account."""
        if user.user_id in self._users:
            raise ValueError(f"A user with id {user.user_id!r} already exists.")
        self._users[user.user_id] = user

    def get_item(self, item_id: str) -> LibraryItem:
        """Return the item with this id, or raise NotFound."""
        item = self._items.get(item_id)
        if item is None:
            raise NotFound(f"No item with id {item_id!r}.")
        return item

    def get_user(self, user_id: str) -> User:
        """Return the user with this id, or raise NotFound."""
        user = self._users.get(user_id)
        if user is None:
            raise NotFound(f"No user with id {user_id!r}.")
        return user

    def all_items(self) -> list[LibraryItem]:
        """All items, sorted by title."""
        return sorted(self._items.values())

    # ---- issue and return ----

    def issue(self, actor: User, member_id: str, item_id: str,
              today: date | None = None) -> Loan:
        """Lend an item to a member and return the new Loan.

        Raises PermissionDenied, UnpaidFines, OverdueLoans, LimitExceeded or
        ItemNotAvailable if any rule says no. Nothing changes unless all checks pass.
        """
        today = today or date.today()
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        item = self.get_item(item_id)

        if not item.can_be_borrowed_by(member):
            reason = item.get_restriction_note() or "Not available for borrowing"
            raise PermissionDenied(f'"{item.title}" cannot be borrowed: {reason}.')
        member.check_can_borrow(today)
        if member.has_loan_of(item_id):
            raise LibraryException(f'{member.name} already has "{item.title}" on loan.')
        if not self._has_copy_for(member, item):
            raise ItemNotAvailable(self._unavailable_message(item))

        # All checks passed: now change state.
        item.checkout_copy()
        loan = Loan(member, item, today, today + timedelta(days=self._loan_days(member, item)))
        member.add_loan(loan)
        self._loans.append(loan)
        self._remove_reservation(member, item)
        return loan

    def return_item(self, actor: User, member_id: str, item_id: str,
                    today: date | None = None) -> Loan:
        """Take an item back, charge any fine, and tell the next waiting member."""
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        item = self.get_item(item_id)
        loan = next((l for l in member.loans if l.item.item_id == item_id), None)
        if loan is None:
            raise NotFound(f'{member.name} does not have "{item.title}" on loan.')

        loan.mark_returned(today)
        fine = loan.calculate_fine()
        if fine > 0:
            member.add_fine(fine)
        member.close_loan(loan)
        item.return_copy()
        self._notifications.notify(
            item_id, f'"{item.title}" is back and being held for you. Please collect it.'
        )
        return loan

    # ---- reservations ----

    def reserve(self, actor: User, member_id: str, item_id: str) -> Reservation:
        """Put a member on the waitlist for an item that has no free copy."""
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        item = self.get_item(item_id)

        if not item.can_be_borrowed_by(member):
            reason = item.get_restriction_note() or "Not available for borrowing"
            raise PermissionDenied(f'"{item.title}" cannot be reserved: {reason}.')
        if any(r.member is member for r in self.get_waitlist(item_id)):
            raise LibraryException(f'{member.name} has already reserved "{item.title}".')
        if member.has_loan_of(item_id):
            raise LibraryException(f'{member.name} already has "{item.title}" on loan.')
        if self._has_copy_for(member, item):
            raise LibraryException(f'A copy of "{item.title}" is available now. Borrow it instead.')

        reservation = Reservation(member, item)
        self._reservations.append(reservation)
        self._notifications.subscribe(item_id, member)
        return reservation

    def get_waitlist(self, item_id: str) -> list[Reservation]:
        """Reservations for an item, first in line first."""
        return sorted(r for r in self._reservations if r.item.item_id == item_id)

    # ---- search and status ----

    def search(self, query: str) -> list[LibraryItem]:
        """Items whose title, author or subject contains the query (any case), sorted by title.

        An empty query returns every item.
        """
        words = query.lower().split()
        results = []
        for item in self._items.values():
            text = f"{item.title} {item.author} {item.subject}".lower()
            if all(word in text for word in words):
                results.append(item)
        return sorted(results)

    def get_status_text(self, item_id: str) -> str:
        """Item status in words for the UI, e.g. 'All copies issued · 1 waiting'."""
        item = self.get_item(item_id)
        waiting = len(self.get_waitlist(item_id))
        parts: list[str] = []

        note = item.get_restriction_note()
        if note:
            parts.append(note)

        if item.has_unlimited_copies():
            parts.append("Available online")
        else:
            free = item.available_copies - waiting  # copies not held for the waitlist
            if free > 0:
                parts.append(f"{free} of {item.total_copies} available")
            elif item.available_copies > 0:
                parts.append("Returned copies on hold")
            else:
                parts.append("All copies issued")

        if waiting:
            parts.append(f"{waiting} waiting")
        return " · ".join(parts)

    # ---- private helpers ----

    def _get_member(self, user_id: str) -> Member:
        """Return the user as a Member, or raise if they are not one (e.g. a Librarian)."""
        user = self.get_user(user_id)
        if not isinstance(user, Member):
            raise PermissionDenied(f"{user.name} is not a borrowing member.")
        return user

    @staticmethod
    def _require_librarian(actor: User) -> None:
        if not actor.can_manage_library():
            raise PermissionDenied("Only a librarian can do this.")

    @staticmethod
    def _require_self_or_librarian(actor: User, member: Member) -> None:
        if actor is not member and not actor.can_manage_library():
            raise PermissionDenied("You can only do this for your own account.")

    @staticmethod
    def _loan_days(member: Member, item: LibraryItem) -> int:
        """The shorter of the member's loan period and the item's own limit."""
        days = member.get_loan_days()
        limit = item.get_loan_limit_days()
        if limit is not None:
            days = min(days, limit)
        return days

    def _has_copy_for(self, member: Member, item: LibraryItem) -> bool:
        """Return True if a copy can go to this member, respecting the waitlist.

        Returned copies are held for people in line: the person at position p
        (0 = first) can take one if more than p copies are free; anyone not in
        line needs a copy beyond those held.
        """
        if not item.is_available():
            return False
        if item.has_unlimited_copies():
            return True
        waiting = [r.member for r in self.get_waitlist(item.item_id)]
        if member in waiting:
            return waiting.index(member) < item.available_copies
        return item.available_copies > len(waiting)

    def _unavailable_message(self, item: LibraryItem) -> str:
        if item.available_copies > 0:
            return f'The free copies of "{item.title}" are held for members on the waitlist.'
        return f'All copies of "{item.title}" are issued. You can reserve it.'

    def _remove_reservation(self, member: Member, item: LibraryItem) -> None:
        """Drop the member's reservation for this item (if any) once they borrow it."""
        self._reservations = [
            r for r in self._reservations
            if not (r.member is member and r.item.item_id == item.item_id)
        ]
        self._notifications.unsubscribe(item.item_id, member)
