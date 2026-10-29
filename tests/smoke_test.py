"""Quick smoke tests, extended each phase.

Run from the project root:  python -m tests.smoke_test
"""

import os
import re
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from exceptions import (ItemNotAvailable, LibraryException, LimitExceeded, NotFound,
                        OverdueLoans, PermissionDenied, UnpaidFines)
from models import (Book, EBook, Faculty, Librarian, LibraryItem, Loan, Magazine, Member,
                    ReferenceBook, Reservation, Student, Thesis, User)
from services.fine_policy import FacultyFinePolicy, FinePolicy, StudentFinePolicy
from services.item_factory import ItemFactory
from services.library import Library
from services.notification_center import NotificationCenter
from storage.database import PROJECT_ROOT, Database, default_db_path
from storage.repositories import ItemRepository, UserRepository


def _expect(exc_type: type[Exception], fn, *args, **kwargs) -> Exception:
    """Call fn and check it raises exc_type; return the exception."""
    try:
        fn(*args, **kwargs)
    except exc_type as e:
        return e
    raise AssertionError(f"expected {exc_type.__name__}")


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
        s.add_loan(Loan(1, s, Book("B1", "T", "A", 2020), date.today(), date.today()))
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
    return Loan(1, member, Book("B1", "Algorithms", "Y", 2002), due - timedelta(days=14), due)


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
        Loan(1, s, book, date.today(), date.today() - timedelta(days=1))
        assert False, "expected ValueError for due before issue"
    except ValueError:
        pass
    try:
        s.add_loan(Loan(1, other, book, date.today(), date.today()))
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


# ---------- Phase 4: Library + NotificationCenter ----------

def _library() -> tuple[Library, Librarian, Student, Faculty]:
    """A fresh library with one librarian, student, faculty member and a few items."""
    Library.reset()
    lib = Library()
    staff = Librarian("L1", "Sara", User.hash_password("pw"))
    s = Student("S1", "Ali", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    for u in (staff, s, f):
        lib.add_user(u)
    for data in (
        {"type": "book", "item_id": "B1", "title": "Clean Code", "author": "Robert Martin",
         "year": 2008, "subject": "Software Engineering", "total_copies": 1},
        {"type": "book", "item_id": "B2", "title": "Deep Learning", "author": "Ian Goodfellow",
         "year": 2016, "subject": "Machine Learning", "total_copies": 3},
        {"type": "reference", "item_id": "R1", "title": "Oxford Dictionary",
         "author": "Oxford", "year": 2010, "total_copies": 2},
        {"type": "ebook", "item_id": "E1", "title": "Python Basics", "author": "Ann Lee",
         "year": 2021, "subject": "Programming"},
        {"type": "magazine", "item_id": "M1", "title": "Nature", "author": "Springer",
         "year": 2026},
        {"type": "thesis", "item_id": "T1", "title": "Graph Search", "author": "Omar",
         "year": 2024, "supervisor": "Dr. Rahman"},
    ):
        lib.add_item(staff, ItemFactory.create(data))
    return lib, staff, s, f


def test_library_is_singleton() -> None:
    lib, *_ = _library()
    assert Library() is lib
    assert len(Library().all_items()) == 6  # __init__ ran again but did not wipe data


def test_issue_due_date_is_shorter_of_member_and_item() -> None:
    lib, staff, s, f = _library()
    today = date(2026, 10, 1)
    assert lib.issue(staff, "S1", "B2", today).due_date == today + timedelta(days=14)
    assert lib.issue(staff, "F1", "B2", today).due_date == today + timedelta(days=30)
    assert lib.issue(staff, "F1", "M1", today).due_date == today + timedelta(days=7)
    assert lib.get_item("B2").available_copies == 1


def test_issue_checks_permissions() -> None:
    lib, staff, s, f = _library()
    _expect(PermissionDenied, lib.issue, staff, "S1", "R1")       # reference book
    _expect(PermissionDenied, lib.issue, staff, "S1", "T1")       # thesis, student
    lib.issue(staff, "F1", "T1")                                  # thesis, faculty: ok
    _expect(PermissionDenied, lib.issue, s, "F1", "B2")           # student acting for someone else
    lib.issue(s, "S1", "B2")                                      # member for themself: ok
    _expect(PermissionDenied, lib.issue, staff, "L1", "B2")       # librarian is not a member
    _expect(PermissionDenied, lib.add_item, s, Book("X", "T", "A", 2020))
    _expect(NotFound, lib.issue, staff, "S1", "NOPE")


def test_issue_checks_borrowing_rules() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1")
    _expect(ItemNotAvailable, lib.issue, staff, "F1", "B1")       # only copy is out
    lib.issue(staff, "S1", "B2")
    lib.issue(staff, "S1", "E1")
    _expect(LimitExceeded, lib.issue, staff, "S1", "M1")          # 3 of 3 (B1, B2, E1)


def test_same_item_twice_is_blocked() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "F1", "B2")
    e = _expect(LibraryException, lib.issue, staff, "F1", "B2")
    assert "already has" in str(e)


def test_overdue_loan_blocks_borrowing_with_zero_fines() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1", today=date(2026, 1, 1))          # due 15 Jan
    later = date(2026, 1, 20)
    assert s.current_fine == 0
    e = _expect(OverdueLoans, lib.issue, staff, "S1", "B2", later)
    assert "overdue" in str(e)
    assert not s.can_borrow(later)


def test_return_charges_fine_and_frees_copy() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1", today=date(2026, 1, 1))          # due 15 Jan
    loan = lib.return_item(staff, "S1", "B1", today=date(2026, 1, 19))  # 4 days late
    assert loan.is_returned() and s.current_fine == 40
    assert s.loans == [] and s.history == [loan]
    assert lib.get_item("B1").available_copies == 1
    _expect(UnpaidFines, lib.issue, staff, "S1", "B2")
    s.pay_fine(40)
    lib.issue(staff, "S1", "B2")
    _expect(NotFound, lib.return_item, staff, "S1", "B1")          # already returned


def test_reserve_rules() -> None:
    lib, staff, s, f = _library()
    _expect(LibraryException, lib.reserve, s, "S1", "B2")          # copy available now
    _expect(PermissionDenied, lib.reserve, s, "S1", "T1")          # student can't borrow thesis
    _expect(PermissionDenied, lib.reserve, s, "S1", "R1")          # reference book
    lib.issue(staff, "F1", "B1")
    _expect(LibraryException, lib.reserve, f, "F1", "B1")          # already has it
    lib.reserve(s, "S1", "B1")
    e = _expect(LibraryException, lib.reserve, s, "S1", "B1")      # duplicate
    assert "already reserved" in str(e)


def test_return_notifies_next_in_line_and_holds_copy() -> None:
    lib, staff, s, f = _library()
    other = Student("S2", "Bilal", User.hash_password("pw"))
    lib.add_user(other)
    lib.issue(staff, "F1", "B1")
    lib.reserve(s, "S1", "B1")
    lib.reserve(other, "S2", "B1")
    assert [r.member.user_id for r in lib.get_waitlist("B1")] == ["S1", "S2"]
    assert lib.get_status_text("B1") == "All copies issued · 2 waiting"

    lib.return_item(staff, "F1", "B1")
    assert len(s.notifications) == 1 and "held for you" in s.notifications[0]
    assert other.notifications == []                                # only the next person
    assert lib.get_status_text("B1") == "Returned copies on hold · 2 waiting"
    _expect(ItemNotAvailable, lib.issue, staff, "S2", "B1")          # held for S1, not S2

    lib.issue(staff, "S1", "B1")                                     # S1 collects it
    assert [r.member.user_id for r in lib.get_waitlist("B1")] == ["S2"]
    assert lib.get_status_text("B1") == "All copies issued · 1 waiting"


def test_notification_center_order() -> None:
    nc = NotificationCenter()
    a = Student("S1", "Ali", User.hash_password("pw"))
    b = Student("S2", "Bilal", User.hash_password("pw"))
    nc.subscribe("B1", a)
    nc.subscribe("B1", b)
    nc.subscribe("B1", a)                     # duplicate ignored
    assert nc.notify("B1", "first") is a
    assert nc.notify("B1", "second") is b
    assert nc.notify("B1", "third") is None   # nobody left
    assert a.notifications == ["first"] and b.notifications == ["second"]


def test_search_title_author_subject() -> None:
    lib, *_ = _library()
    ids = lambda q: [i.item_id for i in lib.search(q)]
    assert ids("clean") == ["B1"]                       # title
    assert ids("GOODFELLOW") == ["B2"]                  # author, any case
    assert ids("machine learning") == ["B2"]            # subject, two words
    assert ids("zzz") == []
    assert len(ids("")) == 6
    assert ids("") == [i.item_id for i in sorted(lib.all_items())]  # sorted by title


def test_status_text() -> None:
    lib, staff, s, f = _library()
    assert lib.get_status_text("B2") == "3 of 3 available"
    assert lib.get_status_text("R1") == "Read in library only · 2 of 2 available"
    assert lib.get_status_text("T1") == "Faculty borrowing only · 1 of 1 available"
    assert lib.get_status_text("E1") == "Always available"
    lib.issue(staff, "F1", "B1")
    assert lib.get_status_text("B1") == "All copies issued"


def test_withdraw_item_is_a_soft_delete() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1")
    _expect(PermissionDenied, lib.withdraw_item, s, "B2")            # not a librarian
    e = _expect(LibraryException, lib.withdraw_item, staff, "B1")    # on loan
    assert "on loan" in str(e)
    lib.return_item(staff, "S1", "B1")
    lib.withdraw_item(staff, "B1")                                   # all copies back: ok

    assert lib.get_item("B1").withdrawn                              # still exists...
    assert [l.item.item_id for l in s.history] == ["B1"]             # ...so history is kept
    assert "B1" not in [i.item_id for i in lib.search("")]           # hidden from search
    assert "B1" not in [i.item_id for i in lib.all_items()]          # hidden from catalog
    assert "B1" in [i.item_id for i in lib.all_items(include_withdrawn=True)]
    assert lib.get_status_text("B1") == "Withdrawn from the catalog"
    _expect(ItemNotAvailable, lib.issue, staff, "F1", "B1")          # cannot be borrowed
    _expect(ItemNotAvailable, lib.reserve, f, "F1", "B1")            # or reserved
    _expect(LibraryException, lib.withdraw_item, staff, "B1")        # already withdrawn


def test_withdraw_item_cancels_reservations() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "F1", "B1")
    lib.reserve(s, "S1", "B1")
    lib.return_item(staff, "F1", "B1")                                # copy held for S1
    lib.withdraw_item(staff, "B1")
    assert lib.get_waitlist("B1") == []
    assert "withdrawn from the catalog" in s.notifications[-1]


def test_cancel_reservation() -> None:
    lib, staff, s, f = _library()
    other = Student("S2", "Bilal", User.hash_password("pw"))
    lib.add_user(other)
    lib.issue(staff, "F1", "B1")
    lib.reserve(s, "S1", "B1")
    lib.reserve(other, "S2", "B1")
    _expect(PermissionDenied, lib.cancel_reservation, other, "S1", "B1")  # not theirs
    _expect(NotFound, lib.cancel_reservation, f, "F1", "B1")              # has none
    lib.cancel_reservation(s, "S1", "B1")                                 # own: ok
    assert [r.member.user_id for r in lib.get_waitlist("B1")] == ["S2"]
    lib.reserve(s, "S1", "B1")                                            # back of the line
    lib.cancel_reservation(staff, "S1", "B1")                             # librarian: ok
    assert [r.member.user_id for r in lib.get_waitlist("B1")] == ["S2"]


def test_cancel_passes_held_copy_to_next() -> None:
    lib, staff, s, f = _library()
    other = Student("S2", "Bilal", User.hash_password("pw"))
    lib.add_user(other)
    lib.issue(staff, "F1", "B1")
    lib.reserve(s, "S1", "B1")
    lib.reserve(other, "S2", "B1")
    lib.return_item(staff, "F1", "B1")                                # held for S1
    assert other.notifications == []
    lib.cancel_reservation(s, "S1", "B1")                             # S1 gives it up
    assert len(other.notifications) == 1 and "held for you" in other.notifications[0]
    lib.issue(staff, "S2", "B1")                                      # S2 can now take it


# ---------- Phase 5: Repository + SQLite ----------

def _snapshot(lib: Library) -> dict[str, Any]:
    """Everything the library knows, as plain values, so two libraries can be compared."""
    users = {}
    for uid in ("L1", "S1", "S2", "F1"):
        u = lib.get_user(uid)
        users[uid] = {"role": u.get_role(), "name": u.name, "hash": u.password_hash}
        if isinstance(u, Member):
            users[uid].update(
                current_fine=u.current_fine, notifications=u.notifications,
                loans=[(l.loan_id, l.item.item_id, l.issue_date, l.due_date) for l in u.loans],
                history=[(l.loan_id, l.item.item_id, l.return_date) for l in u.history],
            )
    items = lib.all_items()
    return {
        "items": [i.to_dict() for i in items],
        "users": users,
        "waitlists": {i.item_id: [(r.member.user_id, r.created_at, r.notified)
                                  for r in lib.get_waitlist(i.item_id)] for i in items},
        "status": {i.item_id: lib.get_status_text(i.item_id) for i in items},
    }


def _busy_library() -> Library:
    """A library with active, overdue, returned and fined loans, and two waitlists."""
    lib, staff, s, f = _library()
    other = Student("S2", "Bilal", User.hash_password("pw2"))
    lib.add_user(other)
    lib.issue(staff, "S1", "B1", today=date(2026, 1, 1))       # due 15 Jan
    lib.return_item(staff, "S1", "B1", today=date(2026, 1, 20))  # 5 days late: Rs 50
    lib.issue(staff, "F1", "B1")
    lib.reserve(s, "S1", "B1")
    lib.reserve(other, "S2", "B1")
    lib.return_item(staff, "F1", "B1")                          # held for S1 (notified)
    lib.issue(staff, "F1", "T1", today=date(2026, 2, 1))        # faculty thesis, overdue
    lib.issue(staff, "S2", "E1")
    return lib


def test_restart_keeps_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        lib = _busy_library()
        before = _snapshot(lib)
        db = Database(path)
        lib.save_to(db)
        db.close()

        Library.reset()                 # simulate an app restart
        fresh = Library()
        assert fresh is not lib and fresh.all_items() == []
        db = Database(path)
        fresh.load_from(db)
        db.close()

        assert _snapshot(fresh) == before
        s, other = fresh.get_user("S1"), fresh.get_user("S2")
        assert s.check_password("pw") and other.check_password("pw2")
        assert type(fresh.get_item("T1")) is Thesis
        assert all(l.member is s for l in s.history)   # loans point at the loaded objects

        # The loaded library keeps working: new ids continue, the waitlist still holds.
        _expect(ItemNotAvailable, fresh.issue, fresh.get_user("L1"), "S2", "B1")
        _expect(OverdueLoans, fresh.issue, fresh.get_user("L1"), "F1", "B2")  # thesis still out
        loan = fresh.issue(fresh.get_user("L1"), "S2", "B2")
        assert loan.loan_id == 5
        s.pay_fine(s.current_fine)
        fresh.cancel_reservation(s, "S1", "B1")
        assert "held for you" in other.notifications[-1]   # line was restored correctly


def test_save_replaces_old_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "test.db"))
        lib, staff, s, f = _library()
        lib.issue(staff, "S1", "M1")
        lib.save_to(db)
        lib.return_item(staff, "S1", "M1")
        lib.withdraw_item(staff, "M1")
        lib.save_to(db)                                 # second save replaces the first
        Library.reset()
        fresh = Library()
        fresh.load_from(db)
        db.close()
        assert fresh.get_item("M1").withdrawn           # withdrawn flag survives a restart
        assert len(fresh.all_items()) == 5
        assert [l.item.item_id for l in fresh.get_user("S1").history] == ["M1"]


def test_old_database_gets_withdrawn_column() -> None:
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "old.db")
        conn = sqlite3.connect(path)                    # an items table from before Phase 6
        conn.execute("CREATE TABLE items (item_id TEXT PRIMARY KEY, type TEXT NOT NULL, "
                     "title TEXT NOT NULL, author TEXT NOT NULL, year INTEGER NOT NULL, "
                     "subject TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '', "
                     "total_copies INTEGER, available_copies INTEGER, "
                     "extra TEXT NOT NULL DEFAULT '{}')")
        conn.execute("INSERT INTO items VALUES ('B1','book','T','A',2020,'','',1,1,'{}')")
        conn.commit()
        conn.close()
        db = Database(path)
        item = ItemRepository(db).find("B1")
        db.close()
        assert item is not None and not item.withdrawn


def test_repository_crud() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "test.db"))
        repo = ItemRepository(db)
        book = Book("B1", "Clean Code", "Robert Martin", 2008, isbn="123")
        repo.save(book)
        found = repo.find("B1")
        assert type(found) is Book and found.to_dict() == book.to_dict()
        book.title = "Clean Code, 2nd ed."
        repo.save(book)                                 # replaces, does not duplicate
        assert [i.title for i in repo.all()] == ["Clean Code, 2nd ed."]
        assert repo.find("NOPE") is None
        repo.delete("B1")
        assert repo.all() == []
        db.close()


def test_transaction_rolls_back_on_error() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(os.path.join(tmp, "test.db"))
        users = UserRepository(db)
        try:
            with db.transaction():
                users.save(Student("S1", "Ali", User.hash_password("pw")))
                raise RuntimeError("something failed half-way")
        except RuntimeError:
            pass
        assert users.all() == []
        db.close()


def test_passwords_saved_only_as_hashes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "test.db")
        db = Database(path)
        UserRepository(db).save(Student("S1", "Ali", User.hash_password("my-secret-pw")))
        db.close()
        assert b"my-secret-pw" not in Path(path).read_bytes()


def test_db_path_from_env() -> None:
    old = os.environ.get("LIBRARY_DB_PATH")
    try:
        os.environ["LIBRARY_DB_PATH"] = "data/test.db"
        assert default_db_path() == str(PROJECT_ROOT / "data" / "test.db")
        os.environ["LIBRARY_DB_PATH"] = ""
        assert default_db_path() == str(PROJECT_ROOT / "library.db")
    finally:
        if old is None:
            os.environ.pop("LIBRARY_DB_PATH", None)
        else:
            os.environ["LIBRARY_DB_PATH"] = old


def test_no_sql_outside_storage() -> None:
    sql = re.compile(r"\b(sqlite3|SELECT\s|INSERT\s|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b")
    for path in PROJECT_ROOT.rglob("*.py"):
        rel = path.relative_to(PROJECT_ROOT)
        if rel.parts[0] in ("storage", "tests", ".venv", "venv"):
            continue
        assert not sql.search(path.read_text(encoding="utf-8")), f"SQL found in {rel}"


# ---------- Phase 6: Flask routes ----------

from collections.abc import Iterator
from contextlib import contextmanager

from app import create_app
from services.llm_client import FakeLLMClient


@contextmanager
def _client(demo_mode: bool = False) -> Iterator[Any]:
    """A Flask test client for an app whose database holds the _library() data."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "app.db")
        lib, *_ = _library()
        lib.add_user(Student("S2", "Bilal", User.hash_password("pw")))
        db = Database(path)
        lib.save_to(db)
        db.close()
        Library.reset()
        app = create_app(db_path=path, secret_key="test-secret", demo_mode=demo_mode,
                         llm=FakeLLMClient("Fake answer from the test LLM."))
        app.config["DB_PATH"] = path
        yield app.test_client()
        Library.reset()


def _login(client: Any, user_id: str, password: str = "pw") -> Any:
    return client.post("/api/login", json={"user_id": user_id, "password": password})


def _error(response: Any) -> dict[str, str]:
    """The error part of a JSON error response, checking its shape."""
    data = response.get_json()
    assert set(data) == {"error"} and {"type", "message"} <= set(data["error"]) <= {"type", "message", "next_step"}, data
    return data["error"]


def test_route_login_logout_and_me() -> None:
    with _client() as c:
        assert c.get("/api/me").status_code == 401
        r = _login(c, "S1", "wrong")
        assert r.status_code == 401 and _error(r)["message"] == "Wrong user id or password."
        r = _login(c, "S1")
        assert r.status_code == 200 and r.get_json()["role"] == "Student"
        me = c.get("/api/me").get_json()
        assert me["user_id"] == "S1" and me["borrow_limit"] == 3
        assert "password_hash" not in me
        assert c.post("/api/logout").status_code == 200
        assert c.get("/api/me").status_code == 401


def test_route_catalog_and_item_detail() -> None:
    with _client() as c:
        assert c.get("/api/items").status_code == 401                  # must log in
        _login(c, "S1")
        items = c.get("/api/items?q=deep").get_json()
        assert [i["item_id"] for i in items] == ["B2"]
        assert items[0]["status_text"] == "3 of 3 available"
        assert items[0]["actions"]["can_borrow"] is True
        thesis = c.get("/api/items/T1").get_json()
        assert thesis["actions"]["can_borrow"] is False                 # decided in Python
        assert "Faculty borrowing only" in thesis["status_text"]       # the why, in words
        assert thesis["actions"]["reason"] is None                      # not repeated
        _login(c, "F1")
        c.post("/api/loans", json={"item_id": "B1"})
        _login(c, "S1")
        busy = c.get("/api/items/B1").get_json()                        # item-specific reason
        assert busy["actions"]["can_borrow"] is False and "issued" in busy["actions"]["reason"]
        r = c.get("/api/items/NOPE")
        assert r.status_code == 404 and _error(r)["type"] == "NotFound"


def test_route_borrow_return_and_my_loans() -> None:
    with _client() as c:
        _login(c, "S1")
        r = c.post("/api/loans", json={"item_id": "B2"})
        assert r.status_code == 201 and r.get_json()["due_date"]
        r = c.post("/api/loans", json={"item_id": "T1"})
        assert r.status_code == 403 and _error(r)["type"] == "PermissionDenied"
        r = c.post("/api/loans", json={"item_id": "B2", "member_id": "F1"})
        assert r.status_code == 403                                     # not their account
        c.post("/api/loans", json={"item_id": "E1"})
        c.post("/api/loans", json={"item_id": "M1"})
        r = c.post("/api/loans", json={"item_id": "B1"})
        assert r.status_code == 409 and _error(r)["type"] == "LimitExceeded"
        loans = c.get("/api/me/loans").get_json()
        assert len(loans["current"]) == 3 and loans["fine_policy"].startswith("Rs 10")
        assert c.post("/api/loans/return", json={"item_id": "B2"}).status_code == 200
        loans = c.get("/api/me/loans").get_json()
        assert len(loans["current"]) == 2 and len(loans["history"]) == 1


def test_route_changes_are_saved() -> None:
    with _client() as c:
        _login(c, "S1")
        c.post("/api/loans", json={"item_id": "B2"})
        path = c.application.config["DB_PATH"]
        Library.reset()                                                 # restart the app
        c2 = create_app(db_path=path, secret_key="test-secret", llm=FakeLLMClient()).test_client()
        _login(c2, "S1")
        assert [l["item_id"] for l in c2.get("/api/me/loans").get_json()["current"]] == ["B2"]


def test_route_reservations_and_notifications() -> None:
    with _client() as c:
        _login(c, "F1")
        c.post("/api/loans", json={"item_id": "B1"})
        _login(c, "S1")
        r = c.post("/api/reservations", json={"item_id": "B1"})
        assert r.status_code == 201
        r = c.post("/api/reservations", json={"item_id": "B2"})        # copy free
        assert r.status_code == 400
        assert c.get("/api/me/reservations").get_json()[0]["position"] == 1
        _login(c, "L1")
        c.post("/api/loans/return", json={"item_id": "B1", "member_id": "F1"})
        _login(c, "S1")
        assert "held for you" in c.get("/api/me/notifications").get_json()[0]
        assert c.get("/api/me/reservations").get_json()[0]["ready"] is True
        assert c.delete("/api/reservations/B1").status_code == 200
        assert c.get("/api/me/reservations").get_json() == []
        assert c.delete("/api/reservations/B1").status_code == 404


def test_route_librarian_add_withdraw_and_reports() -> None:
    with _client() as c:
        new_book = {"type": "book", "item_id": "B9", "title": "Refactoring",
                    "author": "Martin Fowler", "year": 2018, "total_copies": 2}
        _login(c, "S1")
        assert c.post("/api/items", json=new_book).status_code == 403  # students cannot
        assert c.get("/api/reports/stats").status_code == 403
        _login(c, "L1")
        r = c.post("/api/items", json=new_book)
        assert r.status_code == 201 and r.get_json()["status_text"] == "2 of 2 available"
        r = c.post("/api/items", json={**new_book, "item_id": "B10", "year": "soon"})
        assert r.status_code == 400 and _error(r)["type"] == "InvalidInput"
        assert c.post("/api/items/B9/withdraw").status_code == 200
        assert "B9" not in [i["item_id"] for i in c.get("/api/items").get_json()]
        assert c.post("/api/items/B9/withdraw").status_code == 400   # already withdrawn

        c.post("/api/loans", json={"item_id": "B1", "member_id": "S1"})
        stats = c.get("/api/reports/stats").get_json()
        assert stats["active_loans"] == 1 and stats["titles"] == 6
        assert stats["members_by_role"] == {"Student": 2, "Faculty": 1}
        assert c.get("/api/reports/overdue").get_json() == []          # nothing late yet


def test_route_overdue_report() -> None:
    with _client() as c:
        lib = Library()
        staff = lib.get_user("L1")
        lib.issue(staff, "S1", "B1", today=date.today() - timedelta(days=30))
        _login(c, "L1")
        overdue = c.get("/api/reports/overdue").get_json()
        assert [l["item_id"] for l in overdue] == ["B1"]
        assert overdue[0]["days_overdue"] == 16 and overdue[0]["fine"] == 160


def test_route_fine_payment() -> None:
    with _client() as c:
        lib = Library()
        lib.get_user("S1").add_fine(50)
        _login(c, "S1")
        r = c.post("/api/fines/pay", json={"amount": "abc"})
        assert r.status_code == 400 and "number" in _error(r)["message"]
        r = c.post("/api/fines/pay", json={"amount": 80})               # more than owed
        assert r.status_code == 400 and _error(r)["type"] == "InvalidInput"
        r = c.post("/api/fines/pay", json={"amount": 50})
        assert r.status_code == 200 and r.get_json()["current_fine"] == 0


def test_route_bad_requests_are_clean_json() -> None:
    with _client() as c:
        _login(c, "S1")
        r = c.post("/api/loans", data="not json", content_type="text/plain")
        assert r.status_code == 400 and _error(r)["type"] == "InvalidInput"
        r = c.post("/api/loans", json={})
        assert r.status_code == 400 and "item_id" in _error(r)["message"]
        r = c.get("/api/does-not-exist")
        assert r.status_code == 404 and _error(r)["type"] == "NotFound"
        r = c.put("/api/items")
        assert r.status_code == 405 and _error(r)["type"] == "MethodNotAllowed"


def test_routes_contain_no_rules() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    # (isinstance is allowed: app.py uses it only to check the shape of request JSON.)
    for forbidden in ("can_manage_library", "can_be_borrowed_by",
                      "check_can_borrow", "get_borrow_limit", "Librarian", "Student"):
        assert forbidden not in source, f"app.py should not use {forbidden!r}"


# ---------- Phase 7: seed data, page routes, UI fields from the API ----------

def test_seed_builds_a_valid_demo_library() -> None:
    import seed
    lib = seed.build_library()
    staff = lib.get_user("lib01")
    assert len(lib.all_items()) >= 15
    assert {i.TYPE_KEY for i in lib.all_items()} == set(ItemFactory.ITEM_TYPES)
    assert lib.get_user("stu01").can_borrow()
    assert "overdue" in lib.get_user("stu02").borrow_block_reason() or \
           "fine" in lib.get_user("stu02").borrow_block_reason()
    assert len(lib.overdue_loans(staff)) == 2
    assert [r.member.user_id for r in lib.get_waitlist("B002")] == ["stu01"]
    for user_id, _, password, _ in seed.ACCOUNTS:
        assert lib.authenticate(user_id, password).user_id == user_id


def test_pages_are_served() -> None:
    with _client() as c:
        for url in ("/", "/dashboard", "/catalog", "/catalog/B1", "/loans", "/reservations",
                    "/staff", "/staff/desk", "/staff/members", "/staff/reports"):
            r = c.get(url)
            assert r.status_code == 200 and b"<!doctype html>" in r.data.lower(), url
        for asset in ("/static/css/tokens.css", "/static/css/app.css", "/static/js/ui.js"):
            assert c.get(asset).status_code == 200, asset


def test_api_gives_ui_everything_it_needs() -> None:
    with _client() as c:
        _login(c, "S1")
        me = c.get("/api/me").get_json()
        assert me["loans_remaining"] == 3 and me["borrow_block_reason"] is None
        c.post("/api/loans", json={"item_id": "B1"})
        loan = c.get("/api/me/loans").get_json()["current"][0]
        assert loan["days_left"] == 14 and loan["item_type_key"] == "book"
        item = c.get("/api/items/B1").get_json()
        assert item["available_now"] is False and item["actions"]["has_loan"] is True
        assert c.get("/api/items/B2").get_json()["available_now"] is True


def test_unavailable_labels_come_from_python() -> None:
    with _client() as c:
        _login(c, "S1")
        thesis = c.get("/api/items/T1").get_json()["actions"]
        assert thesis["unavailable_label"] == "Not available to students"
        _login(c, "F1")
        assert c.get("/api/items/T1").get_json()["actions"]["unavailable_label"] is None
        c.post("/api/loans", json={"item_id": "B1"})
        _login(c, "S1")
        busy = c.get("/api/items/B1").get_json()["actions"]
        assert busy["unavailable_label"] == "Not available right now" and busy["can_reserve"]
        Library().get_user("S1").add_fine(10)
        blocked = c.get("/api/items/B2").get_json()["actions"]
        assert blocked["unavailable_label"] == "Borrowing paused"


def test_route_members_for_librarians_only() -> None:
    with _client() as c:
        _login(c, "S1")
        assert c.get("/api/members").status_code == 403
        assert c.get("/api/members/F1").status_code == 403            # someone else's account
        assert c.get("/api/members/S1/loans").status_code == 200      # their own is fine
        _login(c, "L1")
        members = c.get("/api/members").get_json()
        assert [m["user_id"] for m in members] == ["S1", "S2", "F1"]  # sorted by name
        assert c.get("/api/members/L1").status_code == 403            # librarians are not members
        assert c.get("/api/members/NOPE").status_code == 404
        c.post("/api/loans", json={"member_id": "F1", "item_id": "T1"})
        loans = c.get("/api/members/F1/loans").get_json()
        assert loans["current"][0]["member_role"] == "Faculty"


def test_stats_recent_ranking() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1", today=date.today() - timedelta(days=60))
    lib.return_item(staff, "S1", "B1", today=date.today() - timedelta(days=50))
    lib.issue(staff, "S1", "B2")
    stats = lib.stats(staff)
    assert [r["item_id"] for r in stats["most_borrowed_recent"]] == ["B2"]   # B1 was too long ago
    assert {r["item_id"] for r in stats["most_borrowed"]} == {"B1", "B2"}
    assert stats["most_borrowed_recent"][0]["type"] == "book"


def test_current_and_total_fine() -> None:
    lib, staff, s, f = _library()
    lib.issue(staff, "S1", "B1", today=date.today() - timedelta(days=30))   # 16 days late: Rs 160 accruing
    lib.issue(staff, "S1", "M1", today=date.today() - timedelta(days=20))
    lib.return_item(staff, "S1", "M1", today=date.today() - timedelta(days=10))  # 3 days late: Rs 30 charged
    assert s.current_fine == 30                 # charged, payable now
    assert s.accruing_fine() == 160             # added when B1 comes back
    assert s.total_fine() == 190
    stats = lib.stats(staff)
    assert (stats["current_fines"], stats["accruing_fines"], stats["total_fines"]) == (30, 160, 190)
    data = s.to_dict()
    assert (data["current_fine"], data["accruing_fine"], data["total_fine"]) == (30, 160, 190)


def test_next_step_after_paying_a_fine() -> None:
    with _client() as c:
        lib = Library()
        staff = lib.get_user("L1")
        lib.issue(staff, "S1", "B1", today=date.today() - timedelta(days=30))   # overdue
        lib.get_user("S1").add_fine(30)
        _login(c, "S1")
        me = c.get("/api/me").get_json()
        assert me["borrow_next_step"] == "Pay the current fine of Rs 30 to borrow again."
        paid = c.post("/api/fines/pay", json={"amount": 30}).get_json()
        assert paid["current_fine"] == 0 and paid["can_borrow"] is False
        assert paid["borrow_next_step"] == 'Return "Clean Code" to borrow again.'
        r = c.post("/api/loans", json={"item_id": "B2"})
        assert r.status_code == 409 and _error(r)["next_step"] == 'Return "Clean Code" to borrow again.'


def test_no_raw_colours_outside_tokens() -> None:
    colour = re.compile(r"#[0-9a-fA-F]{3,8}\b|rgba?\(")
    for path in (PROJECT_ROOT / "static").rglob("*"):
        if path.suffix in (".css", ".html", ".js") and path.name != "tokens.css":
            text = path.read_text(encoding="utf-8")
            assert not colour.search(text), f"raw colour in {path.relative_to(PROJECT_ROOT)}"


# ---------- Phase 8: Recommender ----------

from services.recommender import (CollaborativeStrategy, ContentBasedStrategy,
                                  PopularityStrategy, Recommendation, RecommendationStrategy,
                                  Recommender)


def _rec_library() -> tuple[Library, Librarian, Student, Student, Faculty]:
    """A library whose item texts overlap, for recommender tests."""
    Library.reset()
    lib = Library()
    staff = Librarian("L1", "Sara", User.hash_password("pw"))
    s1 = Student("S1", "Ali", User.hash_password("pw"))
    s2 = Student("S2", "Bilal", User.hash_password("pw"))
    f = Faculty("F1", "Dr. Khan", User.hash_password("pw"))
    for u in (staff, s1, s2, f):
        lib.add_user(u)
    for data in (
        {"type": "book", "item_id": "P1", "title": "Learning Python", "author": "Mark Lutz",
         "year": 2013, "subject": "Python Programming",
         "description": "Python language basics, functions and classes."},
        {"type": "book", "item_id": "P2", "title": "Fluent Python", "author": "Luciano Ramalho",
         "year": 2022, "subject": "Python Programming",
         "description": "Idiomatic Python: classes, generators and data models."},
        {"type": "book", "item_id": "G1", "title": "Garden Birds", "author": "Kate Moss",
         "year": 2015, "subject": "Ornithology", "description": "Sparrows, robins and finches.", "total_copies": 3},
        {"type": "book", "item_id": "C1", "title": "Cooking at Home", "author": "Raza Ali",
         "year": 2019, "subject": "Cookery", "description": "Simple recipes for every day.", "total_copies": 3},
        {"type": "reference", "item_id": "R1", "title": "Python Reference Manual",
         "author": "PSF", "year": 2020, "subject": "Python Programming"},
        {"type": "thesis", "item_id": "T1", "title": "Python Type Inference",
         "author": "Omar", "year": 2024, "subject": "Python Programming", "supervisor": "Dr. R"},
    ):
        lib.add_item(staff, ItemFactory.create(data))
    return lib, staff, s1, s2, f


def _ids(recs: list[Recommendation]) -> list[str]:
    return [r.item.item_id for r in recs]


def test_content_based_finds_similar_text() -> None:
    lib, staff, s1, *_ = _rec_library()
    lib.issue(staff, "S1", "P1")
    strategy = ContentBasedStrategy()
    candidates = Recommender([]).candidates(s1, lib.all_items())
    recs = strategy.recommend(s1, candidates, [])
    best = max(recs, key=lambda r: r.score)
    assert best.item.item_id == "P2"
    assert best.reason == "Because you borrowed Learning Python"
    assert "G1" not in _ids(recs)  # nothing in common: score 0, left out


def test_collaborative_people_who_borrowed_x_also_borrowed_y() -> None:
    lib, staff, s1, *_ = _rec_library()
    lib.issue(staff, "S2", "G1")
    lib.issue(staff, "S2", "C1")
    lib.issue(staff, "S1", "G1")
    loans = [l for m in (lib.get_user("S1"), lib.get_user("S2")) for l in m.loans]
    candidates = Recommender([]).candidates(s1, lib.all_items())
    recs = CollaborativeStrategy().recommend(s1, candidates, loans)
    assert _ids(recs) == ["C1"]
    assert recs[0].reason == "Members who borrowed Garden Birds also borrowed this"


def test_recommender_never_suggests_excluded_items() -> None:
    lib, staff, s1, s2, f = _rec_library()
    lib.issue(staff, "S1", "P1")
    lib.return_item(staff, "S1", "P1")      # returned loans count as "borrowed" too
    lib.issue(staff, "S1", "G1")
    lib.withdraw_item(staff, "C1")
    candidates = Recommender([]).candidates(s1, lib._items.values(), reserved_ids=["P2"])
    # P1, G1 borrowed; C1 withdrawn; R1 nobody can borrow; T1 Faculty only; P2 reserved
    assert candidates == []
    faculty_ids = {i.item_id for i in Recommender([]).candidates(f, lib._items.values())}
    assert faculty_ids == {"P1", "P2", "G1", "T1"}  # Faculty may borrow the thesis


def test_new_member_falls_back_to_most_borrowed() -> None:
    lib, staff, s1, s2, f = _rec_library()
    assert lib.recommendations_for(s1, "S1") == []  # no loans anywhere: nothing to say
    lib.issue(staff, "S2", "G1")
    lib.issue(staff, "F1", "G1")
    lib.issue(staff, "F1", "C1")
    picks = lib.recommendations_for(s1, "S1")
    assert [p["item_id"] for p in picks] == ["G1", "C1"]
    assert picks[0]["reason"] == "Popular: borrowed 2 times"
    assert picks[1]["reason"] == "Popular: borrowed once"


def test_recommender_combines_strategies_and_fills_with_fallback() -> None:
    class Fixed(RecommendationStrategy):
        """A test strategy that always scores the same items (polymorphism)."""
        def __init__(self, scores: dict[str, float], weight: float = 1.0) -> None:
            super().__init__(weight)
            self._scores = scores

        def recommend(self, member, candidates, loans):
            return [Recommendation(c, self._scores[c.item_id], f"fixed {c.item_id}")
                    for c in candidates if c.item_id in self._scores]

    lib, staff, s1, *_ = _rec_library()
    items = lib.all_items()
    # P2 is liked by both strategies, so it beats G1 and C1, which only one strategy likes
    rec = Recommender([Fixed({"G1": 4, "P2": 2}), Fixed({"C1": 9, "P2": 9}, weight=0.5)])
    assert _ids(rec.recommend(s1, items, [], limit=3)) == ["P2", "G1", "C1"]
    # The reason comes from the strategy that added most to the score
    assert rec.recommend(s1, items, [], limit=1)[0].reason == "fixed P2"

    lib.issue(staff, "S2", "P1")
    rec = Recommender([Fixed({"G1": 1})], fallback=PopularityStrategy())
    recs = rec.recommend(s1, items, lib.get_user("S2").loans, limit=2)
    assert _ids(recs) == ["G1", "P1"] and recs[1].reason.startswith("Popular")

    _expect(TypeError, RecommendationStrategy)  # abstract
    _expect(ValueError, ContentBasedStrategy, weight=0)


def test_library_recommendations_use_history() -> None:
    lib, staff, s1, s2, f = _rec_library()
    lib.issue(staff, "S1", "P1")
    picks = lib.recommendations_for(s1, "S1")
    assert picks[0]["item_id"] == "P2"
    assert picks[0]["reason"] == "Because you borrowed Learning Python"
    assert "actions" in picks[0]  # same item data as the catalog, for the same tile
    assert all(p["item_id"] not in ("P1", "R1", "T1") for p in picks)
    _expect(PermissionDenied, lib.recommendations_for, s2, "S1")  # someone else's


def test_route_recommendations() -> None:
    with _client() as c:
        assert c.get("/api/me/recommendations").status_code == 401
        _login(c, "S1")
        c.post("/api/loans", json={"item_id": "B1"})
        picks = c.get("/api/me/recommendations").get_json()
        assert isinstance(picks, list)
        for p in picks:
            assert p["reason"] and p["item_id"] not in ("B1", "R1", "T1")
        _login(c, "L1")
        assert c.get("/api/me/recommendations").status_code == 403  # not a member


def test_seed_recommendations() -> None:
    import seed
    lib = seed.build_library()
    stu01, stu03 = lib.get_user("stu01"), lib.get_user("stu03")
    picks = lib.recommendations_for(stu01, "stu01")
    assert len(picks) == 3 and "B002" not in [p["item_id"] for p in picks]  # B002: reserved
    assert any(p["reason"].startswith("Members who borrowed") for p in picks)
    assert all(p["reason"].startswith("Popular") for p in lib.recommendations_for(stu03, "stu03"))


# ---------- Demo mode ----------

def test_demo_mode_off_has_no_demo_routes() -> None:
    with _client() as c:
        assert c.get("/api/demo/accounts").status_code == 404
        assert c.post("/api/demo/reset").status_code == 404
    # Nothing on the login page gives the demo logins away
    for path in ("static/login.html", "static/js/login.js"):
        text = (PROJECT_ROOT / path).read_text(encoding="utf-8")
        assert "student123" not in text and "librarian123" not in text, path


def test_demo_flag_from_env() -> None:
    from app import env_flag
    old = os.environ.get("DEMO_MODE")
    try:
        for value, expected in (("1", True), ("true", True), ("On", True), ("0", False), ("", False)):
            os.environ["DEMO_MODE"] = value
            assert env_flag("DEMO_MODE") is expected, value
    finally:
        if old is None:
            os.environ.pop("DEMO_MODE", None)
        else:
            os.environ["DEMO_MODE"] = old


def _demo_client() -> Any:
    """A demo-mode client whose database starts with the seed data."""
    from contextlib import ExitStack
    stack = ExitStack()
    c = stack.enter_context(_client(demo_mode=True))
    c.post("/api/demo/reset")  # replace the test data with the seed data
    return stack, c


def test_demo_accounts_come_from_python() -> None:
    stack, c = _demo_client()
    with stack:
        accounts = c.get("/api/demo/accounts").get_json()
        assert [a["role"] for a in accounts] == ["Student", "Faculty", "Librarian"]
        assert [a["user_id"] for a in accounts] == ["stu01", "fac01", "lib01"]
        assert accounts[0]["summary"] == "Borrows up to 3 items for 14 days"
        assert accounts[1]["summary"].endswith("including theses")
        for a in accounts:  # every demo login really works
            r = _login(c, a["user_id"], a["password"])
            assert r.status_code == 200 and r.get_json()["role"] == a["role"]


def test_demo_reset_restores_seed_data_and_saves() -> None:
    stack, c = _demo_client()
    with stack:
        app_db = c.application.config["DB_PATH"]
        _login(c, "stu03", "student123")
        assert c.post("/api/loans", json={"item_id": "B003"}).status_code == 201
        assert c.post("/api/demo/reset").status_code == 200
        assert c.get("/api/me").status_code == 401  # reset signs everyone out of this browser
        _login(c, "stu03", "student123")
        assert c.get("/api/me/loans").get_json()["current"] == []
        # The reset was saved, not only changed in memory
        Library.reset()
        lib = Library()
        db = Database(app_db)
        lib.load_from(db)
        db.close()
        assert not lib.get_user("stu03").loans and lib.get_waitlist("B002")


def test_demo_reset_is_rate_limited() -> None:
    stack, c = _demo_client()  # one reset already used
    with stack:
        assert c.post("/api/demo/reset").status_code == 200
        r = c.post("/api/demo/reset")
        assert r.status_code == 429 and _error(r)["type"] == "RateLimited"


def test_rate_limiter_window() -> None:
    from services.rate_limiter import RateLimiter
    from exceptions import RateLimited
    now = [0.0]
    limiter = RateLimiter(2, 60, clock=lambda: now[0])
    limiter.check("a")
    limiter.check("a")
    e = _expect(RateLimited, limiter.check, "a", "questions")
    assert "2 questions" in e.message and e.next_step == "Please wait 60 seconds and try again."
    limiter.check("b")          # each key has its own count
    now[0] = 60.0
    limiter.check("a")          # the first two have left the window
    _expect(ValueError, RateLimiter, 0, 60)


# ---------- Phase 9: ChatAssistant, TopicGuard, LLM clients ----------

from exceptions import LLMError, RateLimited
from services.chat_assistant import ChatAssistant, build_assistant
from services.llm_client import GeminiClient, LLMClient
from services.rate_limiter import RateLimiter
from services.topic_guard import KeywordTopicGuard, LLMTopicGuard, TopicGuard


def _guard_aware_fake(answer: str = "Here is what the catalog shows.") -> FakeLLMClient:
    """A fake that says LIBRARY when used as the topic classifier, else gives `answer`."""
    return FakeLLMClient(lambda system, message: "LIBRARY" if "sort messages" in system else answer)


def test_keyword_topic_guard() -> None:
    guard = KeywordTopicGuard(lambda: {"goodfellow", "clean", "code"})
    for q in ("Is Clean Code available?", "When is my book due?", "How much do I owe?",
              "Can I reserve a thesis?", "hello", "Anything by Goodfellow?"):
        assert guard.is_library_question(q), q
    for q in ("What's the weather today?", "What's my GPA?", "When is the next holiday?",
              "Tell me the latest news"):
        assert not guard.is_library_question(q), q
    assert isinstance(guard, TopicGuard)
    _expect(TypeError, TopicGuard)  # abstract


def test_llm_topic_guard_asks_only_when_keywords_miss() -> None:
    fake = FakeLLMClient("OTHER")
    guard = LLMTopicGuard(fake, prefilter=KeywordTopicGuard())
    assert guard.is_library_question("Can I borrow this?") and fake.calls == []  # keywords said yes
    assert not guard.is_library_question("Who won the match?")
    assert len(fake.calls) == 1 and fake.calls[0][1] == "Who won the match?"
    assert LLMTopicGuard(FakeLLMClient("LIBRARY")).is_library_question("Got Harry Potter?")
    _expect(LLMError, LLMTopicGuard(FakeLLMClient(fail=True)).is_library_question, "Who won?")


def test_chat_refuses_off_topic_before_the_main_call() -> None:
    lib, staff, s, f = _library()
    fake = FakeLLMClient("OTHER")
    assistant = build_assistant(lib, fake)
    for q in ("What's the weather today?", "What's my GPA?"):
        reply = assistant.ask(s, q)
        assert reply.kind == "refused" and reply.answer == ChatAssistant.REFUSAL
    # Only the classifier ran; the main prompt (with library data) was never sent
    assert all("LIBRARY DATA" not in message for _, message in fake.calls)


def test_chat_context_is_only_this_members_data() -> None:
    import seed
    lib = seed.build_library()
    fake = _guard_aware_fake()
    me = lib.get_user("stu02")
    reply = build_assistant(lib, fake).ask(me, "Is Database System Concepts available?")
    assert reply == type(reply)("Here is what the catalog shows.", "answer")
    system, message = fake.calls[-1]
    assert "Never invent" in system and "Bilal" not in system  # data goes in the message only
    assert "Bilal Ahmed (Student)" in message
    assert '"Introduction to Algorithms"' in message and "OVERDUE by" in message  # own loan
    assert "Current fine (charged, payable now): Rs 30" in message                # own fine
    assert '"Database System Concepts"' in message and "Status: " in message       # search hit
    assert "RECOMMENDED FOR THIS MEMBER" in message
    for user_id, name, _, _ in seed.ACCOUNTS:
        user = lib.get_user(user_id)
        assert user.password_hash not in message and user.password_hash not in system
        if user is not me:
            assert name not in message, f"other member's name sent: {name}"
            assert user_id not in message


def test_chat_context_says_when_nothing_matches() -> None:
    lib, staff, s, f = _library()
    fake = _guard_aware_fake()
    build_assistant(lib, fake).ask(s, "Do you have Harry Potter?")
    assert "No catalog items matched the question." in fake.calls[-1][1]


def test_chat_falls_back_when_llm_fails_or_is_missing() -> None:
    lib, staff, s, f = _library()
    broken = build_assistant(lib, FakeLLMClient(fail=True))
    for q in ("Is Clean Code available?", "Got anything by Tolkien?"):  # main call / guard call fails
        reply = broken.ask(s, q)
        assert reply.kind == "unavailable" and reply.answer == ChatAssistant.FALLBACK
    no_key = build_assistant(lib, None)
    assert no_key.ask(s, "Is Clean Code available?").kind == "unavailable"
    assert no_key.ask(s, "What's my GPA?").kind == "refused"  # keyword guard still works


def test_chat_checks_input_permission_and_rate() -> None:
    lib, staff, s, f = _library()
    now = [0.0]
    assistant = ChatAssistant(lib, FakeLLMClient(), KeywordTopicGuard(),
                              RateLimiter(2, 60, clock=lambda: now[0]))
    _expect(ValueError, assistant.ask, s, "   ")
    _expect(ValueError, assistant.ask, s, "book " * 200)
    _expect(PermissionDenied, assistant.ask, staff, "Is Clean Code available?")
    assistant.ask(s, "Is Clean Code available?")
    assistant.ask(s, "What's my GPA?")                    # refused questions count too
    e = _expect(RateLimited, assistant.ask, s, "Any fines?")
    assert e.http_status == 429 and e.next_step
    assert assistant.ask(f, "Any fines?").kind == "answer"  # limits are per member
    now[0] = 61
    assert assistant.ask(s, "Any fines?").kind == "answer"


def test_chat_answer_is_plain_text() -> None:
    lib, staff, s, f = _library()
    fake = FakeLLMClient("**Clean Code** is on the shelf.")
    assert build_assistant(lib, fake).ask(s, "Is Clean Code in?").answer == "Clean Code is on the shelf."


def test_gemini_client_wraps_every_failure() -> None:
    old = os.environ.pop("GEMINI_API_KEY", None)
    try:
        assert GeminiClient.from_env() is None
    finally:
        if old is not None:
            os.environ["GEMINI_API_KEY"] = old
    _expect(ValueError, GeminiClient, "")
    client = GeminiClient("not-a-real-key")  # creating it sends nothing
    assert isinstance(client, LLMClient) and client.model == GeminiClient.DEFAULT_MODEL

    class Stub:  # stands in for the SDK's client.models, so no request leaves the machine
        def __init__(self, result: Any) -> None:
            self.models = self
            self._result = result

        def generate_content(self, **kwargs: Any) -> Any:
            if isinstance(self._result, Exception):
                raise self._result
            return self._result

    class Response:
        def __init__(self, text: str | None) -> None:
            self.text = text

    client._client = Stub(ConnectionError("no network"))
    _expect(LLMError, client.generate, "system", "hi")
    client._client = Stub(Response(None))                  # e.g. a blocked reply
    _expect(LLMError, client.generate, "system", "hi")
    client._client = Stub(Response("  Clean Code is in.  "))
    assert client.generate("system", "hi") == "Clean Code is in."


def test_route_chat() -> None:
    with _client() as c:
        assert c.post("/api/chat", json={"question": "Any fines?"}).status_code == 401
        _login(c, "S1")
        r = c.post("/api/chat", json={"question": "Is Clean Code available?"})
        assert r.status_code == 200
        assert r.get_json() == {"answer": "Fake answer from the test LLM.", "kind": "answer"}
        assert c.post("/api/chat", json={"question": "What's my GPA?"}).get_json()["kind"] == "refused"
        r = c.post("/api/chat", json={"question": ""})
        assert r.status_code == 400 and _error(r)["message"] == "Type a question first."
        for _ in range(3):
            c.post("/api/chat", json={"question": "When is my book due?"})
        r = c.post("/api/chat", json={"question": "When is my book due?"})
        assert r.status_code == 429 and _error(r)["type"] == "RateLimited"
        _login(c, "L1")
        assert c.post("/api/chat", json={"question": "Any fines?"}).status_code == 403


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
