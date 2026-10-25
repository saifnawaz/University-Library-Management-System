"""Quick smoke tests, extended each phase.

Run from the project root:  python -m tests.smoke_test
"""

from exceptions import ItemNotAvailable, LibraryException, LimitExceeded, UnpaidFines
from models import (Book, EBook, Faculty, Librarian, LibraryItem, Magazine, Member,
                    ReferenceBook, Student, Thesis, User)
from services.item_factory import ItemFactory


# ---------- Phase 1: users ----------

def test_password_hashing() -> None:
    s = Student("S1", "Ali", User.hash_password("pw123"))
    assert s.check_password("pw123")
    assert not s.check_password("wrong")
    assert "pw123" not in s.password_hash


def test_roles_and_permissions() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    l = Librarian("L1", "Sara", User.hash_password("pw"))
    assert [u.get_role() for u in (s, f, l)] == ["Student", "Faculty", "Librarian"]
    assert [u.can_manage_library() for u in (s, f, l)] == [False, False, True]
    assert (s.get_borrow_limit(), s.get_loan_days()) == (3, 14)
    assert (f.get_borrow_limit(), f.get_loan_days()) == (10, 30)


def test_borrow_limit() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    for _ in range(3):
        s.add_loan(object())  # placeholder until Loan exists (Phase 3)
    assert not s.can_borrow()
    try:
        s.check_can_borrow()
        assert False, "expected LimitExceeded"
    except LimitExceeded:
        pass


def test_unpaid_fines_block_borrowing() -> None:
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    f.add_fine(5)
    try:
        f.check_can_borrow()
        assert False, "expected UnpaidFines"
    except UnpaidFines as e:
        assert isinstance(e, LibraryException)
    f.pay_fine(5)
    assert f.can_borrow()


def test_abstract_classes_cannot_be_created() -> None:
    for cls in (User, Member):
        try:
            cls("X", "x", "h")
            assert False, f"{cls.__name__} should be abstract"
        except TypeError:
            pass


def test_name_validation() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    try:
        s.name = "   "
        assert False, "expected ValueError"
    except ValueError:
        pass


# ---------- Phase 2: items + ItemFactory ----------

def _sample_items() -> dict[str, LibraryItem]:
    base = {"author": "Someone", "year": 2020, "total_copies": 2}
    return {
        t: ItemFactory.create({"type": t, "item_id": f"I-{t}", "title": f"{t} title", **base})
        for t in ItemFactory.ITEM_TYPES
    }


def test_factory_builds_right_classes() -> None:
    items = _sample_items()
    assert type(items["book"]) is Book
    assert type(items["reference"]) is ReferenceBook
    assert type(items["ebook"]) is EBook
    assert type(items["magazine"]) is Magazine
    assert type(items["thesis"]) is Thesis
    assert isinstance(items["reference"], Book)  # ReferenceBook is a Book


def test_factory_rejects_bad_data() -> None:
    bad_inputs = [
        {"type": "dvd", "item_id": "X", "title": "T", "author": "A", "year": 2020},
        {"type": "book", "item_id": "X", "author": "A", "year": 2020},           # no title
        {"type": "book", "item_id": "X", "title": "T", "author": "A", "year": "abc"},
        {"type": "book", "item_id": "X", "title": "T", "author": "A", "year": 2020,
         "total_copies": 0},
    ]
    for data in bad_inputs:
        try:
            ItemFactory.create(data)
            assert False, f"expected ValueError for {data}"
        except ValueError:
            pass


def test_factory_round_trip() -> None:
    for item in _sample_items().values():
        copy = ItemFactory.create(item.to_dict())
        assert type(copy) is type(item) and copy.to_dict() == item.to_dict()


def test_who_can_borrow_what() -> None:
    items = _sample_items()
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    expected = {  # type: (student, faculty)
        "book": (True, True), "reference": (False, False), "ebook": (True, True),
        "magazine": (True, True), "thesis": (False, True),
    }
    for t, (student_ok, faculty_ok) in expected.items():
        assert items[t].can_be_borrowed_by(s) == student_ok, t
        assert items[t].can_be_borrowed_by(f) == faculty_ok, t
    assert items["reference"].get_restriction_note() == "Read in library only"
    assert items["thesis"].get_restriction_note() == "Faculty borrowing only"


def test_loan_limits() -> None:
    items = _sample_items()
    assert items["magazine"].get_loan_limit_days() == Magazine.LOAN_LIMIT_DAYS
    assert items["book"].get_loan_limit_days() is None


def test_copies_and_ebook_unlimited() -> None:
    items = _sample_items()
    book, ebook = items["book"], items["ebook"]
    book.checkout_copy()
    book.checkout_copy()
    assert not book.is_available()
    try:
        book.checkout_copy()
        assert False, "expected ItemNotAvailable"
    except ItemNotAvailable:
        pass
    book.return_copy()
    assert book.available_copies == 1
    for _ in range(100):
        ebook.checkout_copy()
    assert ebook.is_available()


def test_total_copies_setter_keeps_issued_count() -> None:
    book = _sample_items()["book"]  # 2 copies
    book.checkout_copy()
    book.total_copies = 5
    assert (book.total_copies, book.available_copies) == (5, 4)
    try:
        book.total_copies = 0
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_operator_overloading() -> None:
    a = Book("B1", "zoology", "X", 2001)
    b = Book("B2", "Algorithms", "Y", 2002)
    a_again = Book("B1", "zoology", "X", 2001)
    assert a == a_again and a != b
    assert len({a, a_again, b}) == 2           # __hash__ matches __eq__
    assert sorted([a, b]) == [b, a]            # __lt__ sorts by title, ignoring case
    assert str(b) == '"Algorithms" by Y (2002)'


def test_abstract_item_cannot_be_created() -> None:
    try:
        LibraryItem("X", "T", "A", 2020)
        assert False, "LibraryItem should be abstract"
    except TypeError:
        pass


# ---------- runner ----------

def main() -> None:
    """Run every test_* function in this file and report results."""
    tests = [(name, fn) for name, fn in globals().items()
             if name.startswith("test_") and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:  # report and keep going
            failed += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
