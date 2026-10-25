"""Quick smoke tests, extended each phase.

Run from the project root:  python -m tests.smoke_test
"""

from datetime import date, datetime, timedelta

from exceptions import ItemNotAvailable, LibraryException, LimitExceeded, UnpaidFines
from models import (Book, EBook, Faculty, Librarian, LibraryItem, Loan, Magazine, Member,
                    ReferenceBook, Reservation, Student, Thesis, User)
from services.fine_policy import FacultyFinePolicy, FinePolicy, StudentFinePolicy
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
        s.add_loan(Loan(s, Book("B1", "T", "A", 2020), date.today(), date.today()))
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
    # "supervisor" is only used by Thesis; the factory ignores it for other types.
    base = {"author": "Someone", "year": 2020, "total_copies": 2, "supervisor": "Dr. Rahman"}
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


def test_research_access() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    assert not s.has_research_access()
    assert f.has_research_access()


def test_thesis_requires_supervisor() -> None:
    thesis = _sample_items()["thesis"]
    assert thesis.supervisor == "Dr. Rahman"
    for data in (
        {"type": "thesis", "item_id": "T1", "title": "T", "author": "A", "year": 2020},
        {"type": "thesis", "item_id": "T1", "title": "T", "author": "A", "year": 2020,
         "supervisor": "   "},
    ):
        try:
            ItemFactory.create(data)
            assert False, "expected ValueError for missing supervisor"
        except ValueError:
            pass


def test_eq_with_non_item_returns_not_implemented() -> None:
    book = Book("B1", "Algorithms", "Y", 2002)
    assert book.__eq__("B1") is NotImplemented
    assert book.__lt__(5) is NotImplemented
    assert book != "B1"            # Python falls back to "not equal"
    assert not (book == None)      # noqa: E711 - checking == on purpose
    try:
        _ = book < 5
        assert False, "expected TypeError"
    except TypeError:
        pass


def test_abstract_item_cannot_be_created() -> None:
    try:
        LibraryItem("X", "T", "A", 2020)
        assert False, "LibraryItem should be abstract"
    except TypeError:
        pass


# ---------- Phase 3: fine policies, Loan, Reservation ----------

def _loan(member: Member, overdue_days: int) -> Loan:
    """A 14-day loan whose due date was overdue_days ago."""
    due = date.today() - timedelta(days=overdue_days)
    return Loan(member, Book("B1", "Algorithms", "Y", 2002), due - timedelta(days=14), due)


def test_fine_policy_rates_and_caps() -> None:
    sp, fp = StudentFinePolicy(), FacultyFinePolicy()
    assert [sp.calculate_fine(d) for d in (-2, 0, 1, 3, 50, 1000)] == [0, 0, 10, 30, 500, 500]
    assert [fp.calculate_fine(d) for d in (-2, 0, 1, 3, 60, 1000)] == [0, 0, 5, 15, 300, 300]
    assert sp.describe() == "Rs 10 per day, up to Rs 500"
    assert fp.describe() == "Rs 5 per day, up to Rs 300"


def test_fine_policy_is_abstract() -> None:
    try:
        FinePolicy()
        assert False, "FinePolicy should be abstract"
    except TypeError:
        pass


def test_members_pick_their_fine_policy() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    assert isinstance(s.get_fine_policy(), StudentFinePolicy)
    assert isinstance(f.get_fine_policy(), FacultyFinePolicy)


def test_loan_overdue_and_fine_depend_on_member() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    on_time = _loan(s, overdue_days=0)
    assert not on_time.is_overdue() and on_time.calculate_fine() == 0
    # Same 4 days late, different fine: the policy decides, not Loan.
    assert _loan(s, 4).is_overdue() and _loan(s, 4).calculate_fine() == 40
    assert _loan(f, 4).calculate_fine() == 20
    assert _loan(s, 365).calculate_fine() == StudentFinePolicy.MAX_FINE


def test_fine_rates_are_configurable() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    old = StudentFinePolicy.DAILY_RATE
    try:
        StudentFinePolicy.DAILY_RATE = 20.0  # changing one setting changes every fine
        assert _loan(s, 3).calculate_fine() == 60
    finally:
        StudentFinePolicy.DAILY_RATE = old


def test_loan_return_freezes_fine() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    loan = _loan(s, overdue_days=10)
    loan.mark_returned(loan.due_date + timedelta(days=2))  # came back 2 days late
    assert loan.is_returned() and loan.days_overdue() == 2
    assert loan.calculate_fine(today=date.today() + timedelta(days=100)) == 20
    try:
        loan.mark_returned()
        assert False, "expected ValueError for double return"
    except ValueError:
        pass


def test_loan_rejects_bad_dates_and_wrong_member() -> None:
    s = Student("S1", "Ali", User.hash_password("pw"))
    other = Student("S2", "Bilal", User.hash_password("pw"))
    book = Book("B1", "T", "A", 2020)
    try:
        Loan(s, book, date.today(), date.today() - timedelta(days=1))
        assert False, "expected ValueError for due before issue"
    except ValueError:
        pass
    try:
        s.add_loan(Loan(other, book, date.today(), date.today()))
        assert False, "expected ValueError for another member's loan"
    except ValueError:
        pass


def test_reservations_sort_into_waitlist_order() -> None:
    book = Book("B1", "T", "A", 2020)
    a = Student("S1", "Ali", User.hash_password("pw"))
    b = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    c = Student("S3", "Chen", User.hash_password("pw"))
    t = datetime(2026, 10, 1, 9, 0)
    first = Reservation(b, book, t)
    second = Reservation(c, book, t + timedelta(minutes=5))
    third = Reservation(a, book, t + timedelta(hours=2))
    waitlist = sorted([third, first, second])
    assert [r.member.user_id for r in waitlist] == ["F1", "S3", "S1"]
    assert Reservation(a, book).created_at <= datetime.now()


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
