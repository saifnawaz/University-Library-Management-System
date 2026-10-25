"""Item hierarchy: LibraryItem -> Book -> ReferenceBook, and EBook, Magazine, Thesis."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from exceptions import ItemNotAvailable
from models.users import Member


class LibraryItem(ABC):
    """Abstract base for everything the library holds."""

    TYPE_KEY: str = ""  # short name used by ItemFactory and in saved data, e.g. "book"

    def __init__(
        self,
        item_id: str,
        title: str,
        author: str,
        year: int,
        total_copies: int = 1,
        available_copies: int | None = None,
        subject: str = "",
        description: str = "",
        withdrawn: bool = False,
    ) -> None:
        """Create an item. available_copies defaults to total_copies (nothing issued yet)."""
        self._item_id: str = item_id
        self._title: str = ""
        self._author: str = ""
        self._year: int = 0
        self.title = title    # setters validate the values
        self.author = author
        self.year = year
        self._subject: str = subject.strip()
        self._description: str = description.strip()

        if total_copies < 1:
            raise ValueError("An item needs at least 1 copy.")
        if available_copies is None:
            available_copies = total_copies
        if not 0 <= available_copies <= total_copies:
            raise ValueError("Available copies must be between 0 and total copies.")
        self._total_copies: int = total_copies
        self._available_copies: int = available_copies
        self._withdrawn: bool = withdrawn

    # ---- properties (encapsulation) ----

    @property
    def item_id(self) -> str:
        """Unique id of the item (read-only)."""
        return self._item_id

    @property
    def title(self) -> str:
        """Title of the item."""
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("Title cannot be empty.")
        self._title = value

    @property
    def author(self) -> str:
        """Author, editor or publisher of the item."""
        return self._author

    @author.setter
    def author(self, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("Author cannot be empty.")
        self._author = value

    @property
    def year(self) -> int:
        """Publication year."""
        return self._year

    @year.setter
    def year(self, value: int) -> None:
        latest = date.today().year + 1
        if not 1000 <= value <= latest:
            raise ValueError(f"Year must be between 1000 and {latest}.")
        self._year = value

    @property
    def subject(self) -> str:
        """Subject area, e.g. 'Computer Science'."""
        return self._subject

    @property
    def description(self) -> str:
        """Short description (used later by the recommender)."""
        return self._description

    @property
    def total_copies(self) -> int:
        """Number of copies the library owns."""
        return self._total_copies

    @total_copies.setter
    def total_copies(self, value: int) -> None:
        issued = self._total_copies - self._available_copies
        if value < max(1, issued):
            raise ValueError(f"Total copies cannot be below {max(1, issued)} ({issued} issued).")
        self._available_copies += value - self._total_copies
        self._total_copies = value

    @property
    def available_copies(self) -> int:
        """Copies currently on the shelf (read-only; changes via checkout/return)."""
        return self._available_copies

    @property
    def withdrawn(self) -> bool:
        """True if the item was taken out of the catalog (kept for loan history)."""
        return self._withdrawn

    def withdraw(self) -> None:
        """Take the item out of the catalog. It stays saved so past loans still point to it."""
        if self._withdrawn:
            raise ValueError(f'"{self._title}" is already withdrawn.')
        self._withdrawn = True

    # ---- rules each item type must define (abstraction) ----

    @abstractmethod
    def can_be_borrowed_by(self, member: Member) -> bool:
        """Return True if this kind of item may be borrowed by this member.

        This is only about *who* may borrow it, not whether a copy is free.
        """

    @abstractmethod
    def get_item_type(self) -> str:
        """Human-readable type name, e.g. 'Reference Book'."""

    # ---- rules with a default that some subclasses override ----

    def get_loan_limit_days(self) -> int | None:
        """Longest loan this item allows, or None if only the member's period applies."""
        return None

    def get_restriction_note(self) -> str | None:
        """Borrowing restriction in words for the UI, or None if there is none."""
        return None

    def is_available(self) -> bool:
        """Return True if at least one copy is free."""
        return self._available_copies > 0

    def has_unlimited_copies(self) -> bool:
        """Return True if copies never run out (e-books)."""
        return False

    # ---- copy bookkeeping (called by Library, not by routes) ----

    def checkout_copy(self) -> None:
        """Take one copy off the shelf. Raises ItemNotAvailable if none are left."""
        if not self.is_available():
            raise ItemNotAvailable(f'All copies of "{self._title}" are issued.')
        self._available_copies -= 1

    def return_copy(self) -> None:
        """Put one copy back on the shelf."""
        if self._available_copies >= self._total_copies:
            raise ValueError(f'All copies of "{self._title}" are already on the shelf.')
        self._available_copies += 1

    # ---- conversion ----

    def to_dict(self) -> dict[str, Any]:
        """Return the item as a plain dict (for JSON and saving). ItemFactory can rebuild it."""
        return {
            "type": self.TYPE_KEY,
            "item_id": self._item_id,
            "title": self._title,
            "author": self._author,
            "year": self._year,
            "subject": self._subject,
            "description": self._description,
            "total_copies": self._total_copies,
            "available_copies": self._available_copies,
            "withdrawn": self._withdrawn,
        }

    # ---- operator overloading ----

    def __eq__(self, other: object) -> bool:
        """Two items are equal if they have the same item_id."""
        if not isinstance(other, LibraryItem):
            # Not "False": NotImplemented tells Python to try the other object's
            # __eq__, and if that also gives up, == falls back to False.
            return NotImplemented
        return self._item_id == other._item_id

    def __hash__(self) -> int:
        # Needed because we defined __eq__; lets items be dict keys and set members.
        return hash(self._item_id)

    def __lt__(self, other: object) -> bool:
        """Sort items alphabetically by title (then by id), so sorted(items) works."""
        if not isinstance(other, LibraryItem):
            return NotImplemented
        return (self._title.lower(), self._item_id) < (other._title.lower(), other._item_id)

    def __str__(self) -> str:
        return f'"{self._title}" by {self._author} ({self._year})'

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self._item_id!r}, title={self._title!r})"


class Book(LibraryItem):
    """A normal printed book. Any member can borrow it."""

    TYPE_KEY = "book"

    def __init__(self, item_id: str, title: str, author: str, year: int,
                 isbn: str = "", **kwargs: Any) -> None:
        """Create a book. Extra keyword arguments go to LibraryItem."""
        super().__init__(item_id, title, author, year, **kwargs)
        self._isbn: str = isbn.strip()

    @property
    def isbn(self) -> str:
        """ISBN of the book (may be empty)."""
        return self._isbn

    def can_be_borrowed_by(self, member: Member) -> bool:
        return True

    def get_item_type(self) -> str:
        return "Book"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["isbn"] = self._isbn
        return data


class ReferenceBook(Book):
    """A reference book (dictionary, encyclopedia). Read in the library only."""

    TYPE_KEY = "reference"

    def can_be_borrowed_by(self, member: Member) -> bool:
        return False

    def get_item_type(self) -> str:
        return "Reference Book"

    def get_restriction_note(self) -> str | None:
        return "Read in library only"


class EBook(LibraryItem):
    """An electronic book. Any member can borrow it, and copies never run out."""

    TYPE_KEY = "ebook"

    def __init__(self, item_id: str, title: str, author: str, year: int,
                 file_format: str = "PDF", **kwargs: Any) -> None:
        """Create an e-book. Copy counts are ignored because copies are unlimited."""
        kwargs.pop("total_copies", None)
        kwargs.pop("available_copies", None)
        super().__init__(item_id, title, author, year, **kwargs)
        self._file_format: str = file_format.strip().upper() or "PDF"

    @property
    def file_format(self) -> str:
        """File format, e.g. 'PDF' or 'EPUB'."""
        return self._file_format

    def can_be_borrowed_by(self, member: Member) -> bool:
        return True

    def get_item_type(self) -> str:
        return "E-Book"

    def is_available(self) -> bool:
        return True  # unlimited copies

    def has_unlimited_copies(self) -> bool:
        return True

    def checkout_copy(self) -> None:
        pass  # nothing to count

    def return_copy(self) -> None:
        pass  # nothing to count

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["total_copies"] = None      # None means "unlimited"
        data["available_copies"] = None
        data["file_format"] = self._file_format
        return data


class Magazine(LibraryItem):
    """A magazine issue. Any member can borrow it, but only for a short time."""

    TYPE_KEY = "magazine"
    LOAN_LIMIT_DAYS: int = 7  # shorter than any member's normal loan period

    def __init__(self, item_id: str, title: str, author: str, year: int,
                 issue_number: str = "", **kwargs: Any) -> None:
        """Create a magazine issue. 'author' is the publisher or editor."""
        super().__init__(item_id, title, author, year, **kwargs)
        self._issue_number: str = issue_number.strip()

    @property
    def issue_number(self) -> str:
        """Issue number, e.g. 'Vol. 12 No. 3'."""
        return self._issue_number

    def can_be_borrowed_by(self, member: Member) -> bool:
        return True

    def get_item_type(self) -> str:
        return "Magazine"

    def get_loan_limit_days(self) -> int | None:
        return self.LOAN_LIMIT_DAYS

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["issue_number"] = self._issue_number
        return data


class Thesis(LibraryItem):
    """A research thesis. Only members with research access (Faculty) may borrow it."""

    TYPE_KEY = "thesis"

    def __init__(self, item_id: str, title: str, author: str, year: int,
                 supervisor: str, **kwargs: Any) -> None:
        """Create a thesis. 'author' is the student who wrote it; supervisor is required."""
        super().__init__(item_id, title, author, year, **kwargs)
        self._supervisor: str = ""
        self.supervisor = supervisor  # validated by the setter

    @property
    def supervisor(self) -> str:
        """Name of the thesis supervisor."""
        return self._supervisor

    @supervisor.setter
    def supervisor(self, value: str) -> None:
        value = value.strip()
        if not value:
            raise ValueError("A thesis must have a supervisor.")
        self._supervisor = value

    def can_be_borrowed_by(self, member: Member) -> bool:
        return member.has_research_access()

    def get_item_type(self) -> str:
        return "Thesis"

    def get_restriction_note(self) -> str | None:
        return "Faculty borrowing only"

    def to_dict(self) -> dict[str, Any]:
        data = super().to_dict()
        data["supervisor"] = self._supervisor
        return data
