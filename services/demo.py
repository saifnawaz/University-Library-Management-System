"""DemoMode: sign-in shortcuts and a data reset for the public demo deployment."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from exceptions import NotFound
from models.users import Member, User
from services.library import Library
from services.rate_limiter import RateLimiter

# (user_id, name, plain password, class), the same shape as seed.ACCOUNTS
Account = tuple[str, str, str, type]


class DemoMode:
    """Everything that exists only when DEMO_MODE is on.

    app.py creates this object (and its routes) only in demo mode, so with demo
    mode off there is no way to list demo passwords or reset the data.
    """

    ROLE_ORDER: tuple[str, ...] = ("Student", "Faculty", "Librarian")
    RESETS_PER_MINUTE: int = 2  # the reset is public, so keep it from being spammed

    def __init__(self, library: Library, accounts: Sequence[Account],
                 populate: Callable[[Library], None]) -> None:
        """accounts: the demo logins (from seed.py); populate: fills an empty library."""
        self._library: Library = library
        self._accounts: list[Account] = list(accounts)
        self._populate: Callable[[Library], None] = populate
        self._reset_limiter: RateLimiter = RateLimiter(self.RESETS_PER_MINUTE, 60)

    def accounts(self) -> list[dict[str, Any]]:
        """One demo login per role (Student, Faculty, Librarian), with a line on what it can do."""
        first_by_role: dict[str, dict[str, Any]] = {}
        for user_id, _, password, _ in self._accounts:
            try:
                user = self._library.get_user(user_id)
            except NotFound:
                continue  # not in the library right now; offer the others
            role = user.get_role()
            if role not in first_by_role:
                first_by_role[role] = {
                    "role": role,
                    "user_id": user_id,
                    "password": password,
                    "name": user.name,
                    "summary": self._summary(user),
                }
        return [first_by_role[r] for r in self.ROLE_ORDER if r in first_by_role]

    def reset(self) -> None:
        """Put the demo data back to how seed.py makes it. Raises RateLimited if done too often."""
        self._reset_limiter.check("demo-reset", "resets")
        self._library.clear()
        self._populate(self._library)

    @staticmethod
    def _summary(user: User) -> str:
        """What this account can do, in words, taken from the account's own rules."""
        if isinstance(user, Member):
            text = f"Borrows up to {user.get_borrow_limit()} items for {user.get_loan_days()} days"
            return text + (", including theses" if user.has_research_access() else "")
        return "Issues and returns items, manages members and sees reports"
