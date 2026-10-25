"""Custom exceptions for the library system.

Every library rule that fails raises one of these, so Flask routes can
catch a single LibraryException and turn it into a JSON error.
"""


class LibraryException(Exception):
    """Base class for every library-specific error."""

    default_message: str = "A library error occurred."

    def __init__(self, message: str | None = None) -> None:
        """Use the given message, or the class's default message."""
        self.message: str = message or self.default_message
        super().__init__(self.message)


class ItemNotAvailable(LibraryException):
    """Raised when an item has no free copies or cannot be borrowed at all."""

    default_message = "This item is not available."


class LimitExceeded(LibraryException):
    """Raised when a member already has the maximum number of loans."""

    default_message = "Borrow limit reached."


class UnpaidFines(LibraryException):
    """Raised when a member has unpaid fines and tries to borrow."""

    default_message = "You have unpaid fines. Please pay them before borrowing."


class PermissionDenied(LibraryException):
    """Raised when a user tries an action their role is not allowed to do."""

    default_message = "You do not have permission to do this."
