"""Custom exceptions for the library system.

Every library rule that fails raises one of these, so Flask routes can
catch a single LibraryException and turn it into a JSON error. Each class
carries the HTTP status code the web API should answer with.
"""


class LibraryException(Exception):
    """Base class for every library-specific error."""

    default_message: str = "A library error occurred."
    http_status: int = 400  # Bad Request

    def __init__(self, message: str | None = None) -> None:
        """Use the given message, or the class's default message."""
        self.message: str = message or self.default_message
        super().__init__(self.message)


class ItemNotAvailable(LibraryException):
    """Raised when an item has no free copies or cannot be borrowed at all."""

    default_message = "This item is not available."
    http_status = 409  # Conflict: the request is fine, the library's state says no


class LimitExceeded(LibraryException):
    """Raised when a member already has the maximum number of loans."""

    default_message = "Borrow limit reached."
    http_status = 409


class UnpaidFines(LibraryException):
    """Raised when a member has unpaid fines and tries to borrow."""

    default_message = "You have unpaid fines. Please pay them before borrowing."
    http_status = 409


class PermissionDenied(LibraryException):
    """Raised when a user tries an action their role is not allowed to do."""

    default_message = "You do not have permission to do this."
    http_status = 403  # Forbidden


class OverdueLoans(LibraryException):
    """Raised when a member with an overdue item tries to borrow, even with no fines yet."""

    default_message = "You have overdue items. Please return them before borrowing."
    http_status = 409


class NotFound(LibraryException):
    """Raised when an item, user or loan id does not exist."""

    default_message = "Not found."
    http_status = 404


class NotAuthenticated(LibraryException):
    """Raised when nobody is logged in, or the login details are wrong."""

    default_message = "Please log in."
    http_status = 401  # Unauthorized
