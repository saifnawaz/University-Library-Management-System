"""ItemFactory: builds the right LibraryItem subclass from plain data (Factory pattern)."""

from __future__ import annotations

from typing import Any

from models.items import Book, EBook, LibraryItem, Magazine, ReferenceBook, Thesis


class ItemFactory:
    """Turns a dict (from a form, JSON or the database) into the correct item object.

    The rest of the program never writes Book(...) or Thesis(...) itself; it calls
    ItemFactory.create(data) and gets back a LibraryItem.
    """

    # The values accepted in data["type"].
    ITEM_TYPES: tuple[str, ...] = (
        Book.TYPE_KEY, ReferenceBook.TYPE_KEY, EBook.TYPE_KEY,
        Magazine.TYPE_KEY, Thesis.TYPE_KEY,
    )

    @staticmethod
    def create(data: dict[str, Any]) -> LibraryItem:
        """Create a LibraryItem subclass based on data["type"].

        Raises ValueError if the type is unknown or a field is missing or invalid.
        """
        item_type = str(data.get("type", "")).strip().lower()
        common = ItemFactory._common_fields(data)

        match item_type:
            case "book":
                return Book(**common, isbn=str(data.get("isbn", "")))
            case "reference":
                return ReferenceBook(**common, isbn=str(data.get("isbn", "")))
            case "ebook":
                return EBook(**common, file_format=str(data.get("file_format", "PDF")))
            case "magazine":
                return Magazine(**common, issue_number=str(data.get("issue_number", "")))
            case "thesis":
                return Thesis(**common, supervisor=str(data.get("supervisor", "")))
            case _:
                allowed = ", ".join(ItemFactory.ITEM_TYPES)
                raise ValueError(f"Unknown item type {item_type!r}. Use one of: {allowed}.")

    @staticmethod
    def _common_fields(data: dict[str, Any]) -> dict[str, Any]:
        """Read and type-convert the fields every item has."""
        for field in ("item_id", "title", "author", "year"):
            if data.get(field) in (None, ""):
                raise ValueError(f"Missing required field: {field}.")

        fields: dict[str, Any] = {
            "item_id": str(data["item_id"]).strip(),
            "title": str(data["title"]),
            "author": str(data["author"]),
            "year": ItemFactory._to_int(data["year"], "year"),
            "subject": str(data.get("subject") or ""),
            "description": str(data.get("description") or ""),
        }
        # Check for None/"" explicitly: "or 1" would wrongly turn 0 into 1.
        copies = data.get("total_copies")
        fields["total_copies"] = 1 if copies in (None, "") else ItemFactory._to_int(copies, "total_copies")
        if data.get("available_copies") is not None:
            fields["available_copies"] = ItemFactory._to_int(
                data["available_copies"], "available_copies"
            )
        return fields

    @staticmethod
    def _to_int(value: Any, field: str) -> int:
        """Convert a value like '2021' to int, with a clear error message."""
        try:
            return int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field} must be a whole number, got {value!r}.") from None
