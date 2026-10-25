"""Library: the one object that owns all items, users, loans and reservations (Singleton)."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from exceptions import (ItemNotAvailable, LibraryException, NotAuthenticated, NotFound,
                        PermissionDenied)
from models.items import LibraryItem
from models.loan import Loan
from models.reservation import Reservation
from models.users import Member, User
from services.item_factory import ItemFactory
from services.notification_center import NotificationCenter
from storage.database import Database
from storage.repositories import (ItemRepository, LoanRepository, ReservationRepository,
                                  UserRepository)


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
        self._clear()
        self._initialized: bool = True

    def _clear(self) -> None:
        """Empty all in-memory data."""
        self._items: dict[str, LibraryItem] = {}
        self._users: dict[str, User] = {}
        self._loans: list[Loan] = []                # every loan, active and returned
        self._reservations: list[Reservation] = []  # active reservations only
        self._notifications: NotificationCenter = NotificationCenter()
        self._next_loan_id: int = 1

    @classmethod
    def reset(cls) -> None:
        """Forget the current instance so the next Library() starts empty. For tests."""
        cls._instance = None

    # ---- saving and loading ----

    def save_to(self, db: Database) -> None:
        """Write the whole library to the database, replacing what was saved before.

        Runs as one transaction: if anything fails, the old saved data is kept.
        """
        items, users = ItemRepository(db), UserRepository(db)
        loans = LoanRepository(db, self._users, self._items)
        reservations = ReservationRepository(db, self._users, self._items)
        with db.transaction():
            # Delete children before parents, insert parents before children,
            # so the foreign keys are never broken.
            for repo in (reservations, loans, users, items):
                repo.clear()
            for item in self._items.values():
                items.save(item)
            for user in self._users.values():
                users.save(user)
            for loan in self._loans:
                loans.save(loan)
            for reservation in self._reservations:
                reservations.save(reservation)

    def load_from(self, db: Database) -> None:
        """Replace everything in memory with what is saved in the database."""
        self._clear()
        for item in ItemRepository(db).all():
            self._items[item.item_id] = item
        for user in UserRepository(db).all():
            self._users[user.user_id] = user

        for loan in LoanRepository(db, self._users, self._items).all():
            self._loans.append(loan)
            loan.member.add_loan(loan)
            if loan.is_returned():
                loan.member.close_loan(loan)  # moves it into the member's history
        self._next_loan_id = max((l.loan_id for l in self._loans), default=0) + 1

        # Comes back in waitlist order; members not yet told go back in the line.
        for reservation in ReservationRepository(db, self._users, self._items).all():
            self._reservations.append(reservation)
            if not reservation.notified:
                self._notifications.subscribe(reservation.item.item_id, reservation.member)

    # ---- items and users ----

    def add_item(self, actor: User, item: LibraryItem) -> None:
        """Add an item to the catalog. Librarians only."""
        self._require_librarian(actor)
        if item.item_id in self._items:
            raise ValueError(f"An item with id {item.item_id!r} already exists.")
        self._items[item.item_id] = item

    def create_item(self, actor: User, data: dict[str, Any]) -> LibraryItem:
        """Build an item from plain data (e.g. a form) with ItemFactory and add it. Librarians only."""
        self._require_librarian(actor)
        item = ItemFactory.create(data)
        self.add_item(actor, item)
        return item

    def withdraw_item(self, actor: User, item_id: str) -> LibraryItem:
        """Take an item out of the catalog (soft delete). Librarians only.

        Refused while any copy is on loan. The item stays saved, so loan history
        still points to it; it is just hidden from search and the catalog.
        Its reservations are cancelled and the waiting members are told.
        """
        self._require_librarian(actor)
        item = self.get_item(item_id)
        if item.withdrawn:
            raise LibraryException(f'"{item.title}" is already withdrawn.')
        on_loan = [l for l in self._loans if l.item.item_id == item_id and not l.is_returned()]
        if on_loan:
            raise LibraryException(
                f'Cannot withdraw "{item.title}": {len(on_loan)} copy/copies still on loan.'
            )

        for reservation in self.get_waitlist(item_id):
            reservation.member.receive_notification(
                f'"{item.title}" was withdrawn from the catalog, so your reservation was cancelled.'
            )
            self._notifications.unsubscribe(item_id, reservation.member)
        self._reservations = [r for r in self._reservations if r.item.item_id != item_id]
        item.withdraw()
        return item

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

    def all_items(self, include_withdrawn: bool = False) -> list[LibraryItem]:
        """All items in the catalog, sorted by title. Withdrawn items only if asked for."""
        return sorted(i for i in self._items.values() if include_withdrawn or not i.withdrawn)

    def authenticate(self, user_id: str, password: str) -> User:
        """Return the user if the id and password match, else raise NotAuthenticated.

        The message never says which of the two was wrong.
        """
        user = self._users.get(user_id.strip())
        if user is None or not user.check_password(password):
            raise NotAuthenticated("Wrong user id or password.")
        return user

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
        self._check_can_issue(member, item, today)

        # All checks passed: now change state.
        item.checkout_copy()
        due = today + timedelta(days=self._loan_days(member, item))
        loan = Loan(self._next_loan_id, member, item, today, due)
        self._next_loan_id += 1
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
        self._notify_held_copies(item)
        return loan

    # ---- reservations ----

    def reserve(self, actor: User, member_id: str, item_id: str) -> Reservation:
        """Put a member on the waitlist for an item that has no free copy."""
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        item = self.get_item(item_id)
        self._check_can_reserve(member, item)

        reservation = Reservation(member, item)
        self._reservations.append(reservation)
        self._notifications.subscribe(item_id, member)
        return reservation

    def cancel_reservation(self, actor: User, member_id: str, item_id: str) -> None:
        """Cancel a reservation: the member's own, or anyone's if the actor is a librarian.

        If a returned copy was being held for this member, it passes to the next in line.
        """
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        item = self.get_item(item_id)
        if not any(r.member is member for r in self.get_waitlist(item_id)):
            raise NotFound(f'{member.name} has no reservation for "{item.title}".')
        self._remove_reservation(member, item)
        self._notify_held_copies(item)

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
        for item in self.all_items():  # withdrawn items are never found
            text = f"{item.title} {item.author} {item.subject}".lower()
            if all(word in text for word in words):
                results.append(item)
        return sorted(results)

    def get_status_text(self, item_id: str) -> str:
        """Item status in words for the UI, e.g. 'All copies issued · 1 waiting'."""
        item = self.get_item(item_id)
        if item.withdrawn:
            return "Withdrawn from the catalog"
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

    # ---- views for the web API ----
    # Models describe themselves with to_dict(); these add what only Library
    # knows (status text, waitlist position, what the viewer is allowed to do).

    def describe_item(self, item: LibraryItem, viewer: User,
                      today: date | None = None) -> dict[str, Any]:
        """Item data for the UI, plus status in words and (for members) allowed actions."""
        data = item.to_dict()
        data.update(
            item_type=item.get_item_type(),
            restriction_note=item.get_restriction_note(),
            status_text=self.get_status_text(item.item_id),
            waiting=len(self.get_waitlist(item.item_id)),
        )
        if isinstance(viewer, Member):
            data["actions"] = self._member_actions(viewer, item, today or date.today())
        return data

    def catalog(self, viewer: User, query: str = "") -> list[dict[str, Any]]:
        """Search results described for the viewer. Withdrawn items are left out."""
        return [self.describe_item(item, viewer) for item in self.search(query)]

    def item_details(self, viewer: User, item_id: str) -> dict[str, Any]:
        """One item described for the viewer. Withdrawn items are visible to librarians only."""
        item = self.get_item(item_id)
        if item.withdrawn and not viewer.can_manage_library():
            raise NotFound(f"No item with id {item_id!r}.")
        return self.describe_item(item, viewer)

    def get_member(self, actor: User, member_id: str) -> Member:
        """A member's account: their own, or anyone's for a librarian."""
        member = self._get_member(member_id)
        self._require_self_or_librarian(actor, member)
        return member

    def reservations_for(self, actor: User, member_id: str) -> list[dict[str, Any]]:
        """A member's reservations, oldest first, with their place in each waitlist."""
        member = self.get_member(actor, member_id)
        result = []
        for reservation in sorted(r for r in self._reservations if r.member is member):
            waitlist = self.get_waitlist(reservation.item.item_id)
            data = reservation.to_dict()
            data["position"] = waitlist.index(reservation) + 1
            data["ready"] = reservation.notified  # a copy is held for them
            result.append(data)
        return result

    def pay_fine(self, actor: User, member_id: str, amount: float) -> Member:
        """Record a fine payment for a member (their own, or anyone's for a librarian)."""
        member = self.get_member(actor, member_id)
        member.pay_fine(amount)
        return member

    def overdue_loans(self, actor: User, today: date | None = None) -> list[Loan]:
        """All loans still out past their due date, most overdue first. Librarians only."""
        self._require_librarian(actor)
        overdue = [l for l in self._loans if not l.is_returned() and l.is_overdue(today)]
        return sorted(overdue, key=lambda loan: loan.due_date)

    def stats(self, actor: User, today: date | None = None) -> dict[str, Any]:
        """Numbers for the librarian dashboard. Librarians only."""
        self._require_librarian(actor)
        items = self.all_items()
        physical = [i for i in items if not i.has_unlimited_copies()]
        members = [u for u in self._users.values() if isinstance(u, Member)]
        active = [l for l in self._loans if not l.is_returned()]
        times_borrowed = Counter(l.item.item_id for l in self._loans)
        return {
            "titles": len(items),
            "titles_by_type": dict(Counter(i.get_item_type() for i in items)),
            "copies": sum(i.total_copies for i in physical),
            "copies_on_loan": sum(i.total_copies - i.available_copies for i in physical),
            "members_by_role": dict(Counter(m.get_role() for m in members)),
            "active_loans": len(active),
            "overdue_loans": sum(1 for l in active if l.is_overdue(today)),
            "reservations": len(self._reservations),
            "unpaid_fines": sum(m.fines for m in members),
            "most_borrowed": [
                {"item_id": item_id, "title": self._items[item_id].title, "times": count}
                for item_id, count in times_borrowed.most_common(5)
            ],
        }

    # ---- private helpers ----

    def _check_can_issue(self, member: Member, item: LibraryItem, today: date) -> None:
        """Raise the right exception if this member may not borrow this item now."""
        self._require_in_catalog(item)
        if not item.can_be_borrowed_by(member):
            reason = item.get_restriction_note() or "Not available for borrowing"
            raise PermissionDenied(f'"{item.title}" cannot be borrowed: {reason}.')
        member.check_can_borrow(today)
        if member.has_loan_of(item.item_id):
            raise LibraryException(f'{member.name} already has "{item.title}" on loan.')
        if not self._has_copy_for(member, item):
            raise ItemNotAvailable(self._unavailable_message(item))

    def _check_can_reserve(self, member: Member, item: LibraryItem) -> None:
        """Raise the right exception if this member may not reserve this item now."""
        self._require_in_catalog(item)
        if not item.can_be_borrowed_by(member):
            reason = item.get_restriction_note() or "Not available for borrowing"
            raise PermissionDenied(f'"{item.title}" cannot be reserved: {reason}.')
        if any(r.member is member for r in self.get_waitlist(item.item_id)):
            raise LibraryException(f'{member.name} has already reserved "{item.title}".')
        if member.has_loan_of(item.item_id):
            raise LibraryException(f'{member.name} already has "{item.title}" on loan.')
        if self._has_copy_for(member, item):
            raise LibraryException(f'A copy of "{item.title}" is available now. Borrow it instead.')

    def _member_actions(self, member: Member, item: LibraryItem, today: date) -> dict[str, Any]:
        """What the member can do with this item, decided by the same checks issue/reserve use."""
        try:
            self._check_can_issue(member, item, today)
            borrow_problem = None
        except LibraryException as e:
            borrow_problem = e.message
        try:
            self._check_can_reserve(member, item)
            can_reserve = True
        except LibraryException:
            can_reserve = False
        waitlist = [r.member for r in self.get_waitlist(item.item_id)]
        return {
            "can_borrow": borrow_problem is None,
            "can_reserve": can_reserve,
            "reason": borrow_problem,  # why borrowing is not possible, in words
            "has_loan": member.has_loan_of(item.item_id),
            "queue_position": waitlist.index(member) + 1 if member in waitlist else None,
        }

    @staticmethod
    def _require_in_catalog(item: LibraryItem) -> None:
        if item.withdrawn:
            raise ItemNotAvailable(f'"{item.title}" has been withdrawn from the catalog.')

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

    def _notify_held_copies(self, item: LibraryItem) -> None:
        """Tell everyone a free copy is now held for, if they have not been told yet.

        The first N people in line get the N free copies. NotificationCenter's
        line holds only people not yet told, in waitlist order, so each notify()
        reaches the next of them.
        """
        waitlist = self.get_waitlist(item.item_id)
        held_for = min(item.available_copies, len(waitlist))
        for reservation in waitlist[:held_for]:
            if not reservation.notified:
                self._notifications.notify(
                    item.item_id,
                    f'"{item.title}" is back and being held for you. Please collect it.',
                )
                reservation.mark_notified()

    def _remove_reservation(self, member: Member, item: LibraryItem) -> None:
        """Drop the member's reservation for this item (if any) once they borrow it."""
        self._reservations = [
            r for r in self._reservations
            if not (r.member is member and r.item.item_id == item.item_id)
        ]
        self._notifications.unsubscribe(item.item_id, member)
