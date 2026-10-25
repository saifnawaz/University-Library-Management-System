# Project Notes (viva preparation)

What each class does, which OOP idea it shows, and why it was built that way.
One section per phase, added as each phase is finished.

## Quick map: OOP concept → where to point in the code

| Concept | Where |
|---|---|
| Encapsulation | `_underscore` attributes + `@property` everywhere; e.g. `User.name` setter, `LibraryItem.total_copies` setter, read-only `Member.loans` (returns a copy) |
| Abstraction | `User`, `Member`, `LibraryItem`, `FinePolicy` are ABCs with `@abstractmethod` |
| Inheritance | `User → Member → Student/Faculty`, `User → Librarian`, `LibraryItem → Book → ReferenceBook`, `FinePolicy → StudentFinePolicy/FacultyFinePolicy` |
| Polymorphism | `item.can_be_borrowed_by(member)`, `member.get_fine_policy()`, `member.has_research_access()`, `user.can_manage_library()`, `item.get_loan_limit_days()` |
| Operator overloading | `LibraryItem.__eq__`, `__hash__`, `__lt__`, `__str__`; `Reservation.__lt__` |
| Custom exceptions | `exceptions.py`: `LibraryException` and its subclasses |
| Singleton | `Library` (`services/library.py`) |
| Factory | `ItemFactory.create()` (`services/item_factory.py`) |
| Strategy | `FinePolicy` and its subclasses (`services/fine_policy.py`) |
| Observer | `NotificationCenter` (`services/notification_center.py`) + `Member.receive_notification()` |
| Generics | `Repository(Generic[T])` (`storage/repositories.py`): one base class, used as `Repository[LibraryItem]`, `Repository[User]`, and so on |
| Repository | `ItemRepository`, `UserRepository`, `LoanRepository`, `ReservationRepository`: the only classes that talk to the database |

## Python vs C++ cheat sheet

| Python | C++ equivalent |
|---|---|
| `class Student(Member):` | `class Student : public Member` |
| `super().__init__(...)` | calling the base-class constructor |
| `@abstractmethod` | pure virtual function (`= 0`) |
| every method is overridable | every method is `virtual` |
| `_name` (one underscore) | `private`/`protected`, but only by convention; Python does not enforce it |
| `@property` | a getter that looks like a field: `user.name` instead of `user.getName()` |
| `__eq__`, `__lt__`, `__str__` | `operator==`, `operator<`, `operator<<` |
| `__new__` | the allocation step, before the constructor body runs |
| `@staticmethod` | `static` member function |
| class attribute (`BORROW_LIMIT = 3`) | `static const` member |
| `class Repository(Generic[T])` | `template <typename T> class Repository` |
| `with db.transaction():` | an RAII guard object: the setup runs on entry, the cleanup runs on exit even if an exception is thrown |

---

## Phase 1: Project setup, exceptions, user hierarchy

**Files:** `exceptions.py`, `models/users.py`

### `LibraryException` and subclasses (`exceptions.py`)
- **What it does:** One exception class per kind of rule failure: `ItemNotAvailable`, `LimitExceeded`, `UnpaidFines`, `PermissionDenied` (plus `OverdueLoans` and `NotFound`, added in Phase 4). Each subclass only changes `default_message`.
- **OOP concept:** Inheritance and custom exceptions. Because all of them inherit from `LibraryException`, Flask can catch every library error with a single `except LibraryException`.

### `User` (abstract)
- **What it does:** Parent of everyone who logs in. It holds `_user_id`, `_name` and `_password_hash`. The `name` setter rejects empty names. Passwords are stored only as a salted PBKDF2 hash (from the standard library) and checked with `check_password()`. `can_manage_library()` returns `False` by default.
- **OOP concept:** Abstraction (`get_role()` is abstract, so `User(...)` raises `TypeError`) and encapsulation (underscore attributes with `@property`).

### `Member` (abstract, inherits `User`)
- **What it does:** Adds current loans, loan history, the fine balance and notifications. It declares `get_borrow_limit()`, `get_loan_days()` and `get_fine_policy()` as abstract. It implements the borrowing check once in `check_can_borrow()`, which raises `UnpaidFines`, `OverdueLoans` or `LimitExceeded`; `can_borrow()` is the True/False version. `loans` and `history` return copies, so outside code can only change them through `add_loan()` and `close_loan()`.
- **OOP concept:** Inheritance, encapsulation, and shared logic in the parent with the details left to the subclasses.

### `Student` / `Faculty`
- **What it does:** They fill in the numbers: 3 items for 14 days, or 10 items for 30 days. `Faculty` also overrides `has_research_access()` to return `True`.
- **OOP concept:** Polymorphism. The same `member.can_borrow()` call behaves differently depending on the object's class.

### `Librarian`
- **What it does:** Inherits from `User`, not `Member`, so it has no loans or fines. It overrides `can_manage_library()` to return `True`.
- **OOP concept:** Polymorphism. Permission checks call a method instead of comparing role strings.

### Decisions
- Any unpaid fine above `Member.FINE_BLOCK_THRESHOLD` (currently 0) blocks borrowing. This is one setting.
- Bad input (an empty name, a negative payment) raises Python's built-in `ValueError`. Flask will catch it alongside `LibraryException` (Phase 6).
- Password hashing uses only the standard library (`hashlib`, `hmac`, `os.urandom`), so the models don't depend on Flask.

---

## Phase 2: Item hierarchy + ItemFactory

**Files:** `models/items.py`, `services/item_factory.py`

### `LibraryItem` (abstract)
- **What it does:** Parent of every item. It holds id, title, author, year, subject, description and copy counts. Setters validate the values: no empty title, and the year must be between 1000 and next year. `available_copies` is read-only and changes only through `checkout_copy()` and `return_copy()`. The `total_copies` setter keeps the number of issued copies the same: if 1 of 2 copies is out and the total becomes 5, then 4 are available.
- **Abstract methods:** `can_be_borrowed_by(member)` and `get_item_type()`.
- **Overridable defaults:** `get_loan_limit_days()` (None, meaning only the member's period applies), `get_restriction_note()`, `is_available()`, `has_unlimited_copies()`.
- **Operator overloading:**
  - `__eq__`: same id means same item.
  - `__lt__`: sorts by title, ignoring case, so `sorted(items)` works.
  - `__str__`: produces `"Title" by Author (Year)`.
  - `__hash__`: required because Python turns off hashing when you define `__eq__`. Without it, items could not be dict keys or go in sets. **Common viva question.**
  - `__eq__` and `__lt__` return `NotImplemented` (not `False`) for a non-item. This tells Python to try the other object's comparison; `==` then falls back to `False`, and `<` raises `TypeError`.
- **OOP concept:** Abstraction, encapsulation, operator overloading.

### `Book`
- **What it does:** Anyone can borrow it. It adds `isbn`, and calls `super().__init__()` to let the parent set up the shared fields.
- **OOP concept:** Inheritance.

### `ReferenceBook(Book)`
- **What it does:** `can_be_borrowed_by()` always returns `False`, and its note is "Read in library only".
- **OOP concept:** Two-level inheritance and method overriding.

### `EBook`
- **What it does:** Copies never run out: `is_available()` and `has_unlimited_copies()` return `True`, and `checkout_copy()` and `return_copy()` do nothing.
- **OOP concept:** Polymorphism. Code that calls `item.checkout_copy()` doesn't need to know it's an e-book.

### `Magazine`
- **What it does:** `get_loan_limit_days()` returns 7, from `Magazine.LOAN_LIMIT_DAYS`.

### `Thesis`
- **What it does:** It has a required `supervisor`, and the setter rejects blank values. `can_be_borrowed_by()` returns `member.has_research_access()`, and the note is "Faculty borrowing only".
- **OOP concept:** Polymorphism. The thesis asks the member what they're allowed to do instead of checking `isinstance(member, Faculty)`. A new member type with research access would work without changing `Thesis`.

### `ItemFactory`
- **What it does:** `ItemFactory.create(data)` reads `data["type"]` and returns the right subclass, using `match` (Python's version of C's `switch`). It converts form and JSON strings such as `"2021"` to numbers, and raises `ValueError` for an unknown type or a missing or invalid field. `item.to_dict()` and `ItemFactory.create()` are exact opposites, which saving and loading in Phase 5 relies on.
- **OOP concept:** Factory pattern. Nothing else in the program writes `Book(...)` or `Thesis(...)` directly.

### Decisions
- Magazines are lent for 7 days (`Magazine.LOAN_LIMIT_DAYS`).
- `author` is used for every type: the publisher or editor for a magazine, the student writer for a thesis.
- A missing `total_copies` defaults to 1, but an explicit `0` is rejected. A test caught that `x or 1` would have silently turned 0 into 1.

---

## Phase 3: Loan, Reservation, FinePolicy strategies

**Files:** `services/fine_policy.py`, `models/loan.py`, `models/reservation.py`

### `FinePolicy` (abstract), `StudentFinePolicy`, `FacultyFinePolicy`
- **What it does:** `FinePolicy` declares `get_daily_rate()` and `get_max_fine()` as abstract. It implements `calculate_fine(days)` once as `min(days × rate, cap)`, and `describe()` gives the rule in words ("Rs 10 per day, up to Rs 500"). The rates are class-level settings, so each one exists in exactly one place:
  - Student: `DAILY_RATE = 10`, `MAX_FINE = 500`
  - Faculty: `DAILY_RATE = 5`, `MAX_FINE = 300`
- **OOP concept:** Strategy pattern, plus abstraction and inheritance. A strategy is an object that holds one way of doing a job, and it can be swapped for another.

### `Member.get_fine_policy()`
- **What it does:** `Student` returns a `StudentFinePolicy` and `Faculty` returns a `FacultyFinePolicy`.
- **OOP concept:** Polymorphism. Each member type chooses its own strategy.

### `Loan`
- **What it does:** One item borrowed by one member. It stores member, item, issue date, due date and return date, all read-only. The only change allowed is `mark_returned()`, which refuses a second return or a date before the issue date.
  - `days_overdue()` counts to today while the item is out, and stops at the return date, so the fine stops growing once the item is back.
  - `calculate_fine()` contains no rates; it asks `member.get_fine_policy()`.
  - The due date is passed in, because `Library.issue()` decides it.
- **OOP concept:** Encapsulation and delegation (Loan passes the fine calculation to the policy object).

### `Reservation`
- **What it does:** Stores member, item and `created_at`, all read-only, plus a `notified` flag that can only be switched on, through `mark_notified()`, once the member has been told a copy is held for them. The flag was added in Phase 5 so it can be saved. `__lt__` compares `created_at`, with `user_id` as a tie-breaker, so `sorted(reservations)` returns the waitlist with the earliest first.
- **OOP concept:** Encapsulation and operator overloading.

### Decisions
- Date methods take an optional `today` so tests can pretend it's a different day. The app doesn't pass it.
- `Member.add_loan()` rejects a loan that belongs to a different member.
- Each `Loan` has a `loan_id` (added in Phase 5), given by `Library` when it issues the loan.

---

## Phase 4: Library singleton + NotificationCenter

**Files:** `services/library.py`, `services/notification_center.py`; changes to `exceptions.py`, `models/users.py`, `models/items.py`

### `Library`
- **What it does:** The single object that owns all items, users, loans and reservations, stored in private `_items`, `_users`, `_loans` and `_reservations`. It provides `issue()`, `return_item()`, `reserve()`, `search()`, `get_waitlist()` and `get_status_text()`.
- **How the Singleton works:** `__new__` creates the object the first time and returns that same object every time after. Python still runs `__init__` on every `Library()` call, so the `_initialized` flag stops it from wiping the data. **Common viva question.** `Library.reset()` exists only for tests.
- **OOP concept:** Singleton pattern and encapsulation.

### `Library.issue()`
- **What it does:** Runs every check first and only changes state if all of them pass, so a refused issue never leaves anything half-done. It asks the objects instead of containing the rules itself:
  - `item.can_be_borrowed_by(member)` → `PermissionDenied`
  - `member.check_can_borrow(today)` → `UnpaidFines`, `OverdueLoans` or `LimitExceeded`
  - Is a copy free, after copies held for the waitlist? → `ItemNotAvailable`
  - The due date is the shorter of `member.get_loan_days()` and `item.get_loan_limit_days()`: 7 days for a magazine, 14 for a student's book, 30 for a faculty member's book.
- **OOP concept:** Polymorphism. There is no `if type == ...` anywhere in `issue()`.

### Overdue rule (`Member.check_can_borrow()`)
- **What it does:** Raises `OverdueLoans` if any loan is past its due date. A fine is added only when the item comes back, so without this check a member with a long-overdue book would show a balance of 0 and could keep borrowing.

### `Library.return_item()`
- **What it does:** Marks the loan returned, then asks the loan for its fine (which asks the member's fine policy) and adds any fine to the member's balance. The loan moves to the member's history, the copy goes back on the shelf, and `NotificationCenter.notify()` is called.

### `NotificationCenter`
- **What it does:** Keeps an ordered line of waiting members for each item. Members are added with `subscribe()` when they reserve and removed with `unsubscribe()` once they borrow. `notify()` sends a message to the next person in line by calling `member.receive_notification()`, then takes them out of the line, so the next returned copy goes to the person after them.
- **OOP concept:** Observer pattern. The return code doesn't need to know who's waiting or how they're told.

### `Library.reserve()`
- **What it does:** Refuses a reservation in four cases: the member can't borrow the item, they already reserved it, they already have it on loan, or a copy is free right now.

### Holding copies for the waitlist
- **What it does:** A returned copy is held for the people in line, in order. Someone not on the waitlist gets `ItemNotAvailable`.

### `search()` and `get_status_text()`
- **What they do:** `search()` requires every word to appear in the title, author or subject, ignoring case, and returns the results sorted by title. `get_status_text()` builds the status in words, e.g. "3 of 3 available", "Read in library only · 2 of 2 available", "All copies issued · 1 waiting", "Returned copies on hold · 2 waiting" or "Available online". E-books are recognised through `has_unlimited_copies()`, never by checking their type.

### Decisions
- Issue, return and reserve can be done by a librarian for any member, or by a member for their own account. A student cannot act for someone else.
- New exceptions: `OverdueLoans` and `NotFound`, both subclasses of `LibraryException`.
- Notifications are kept in a list on `Member` and saved to the database (Phase 5).

### Added after Phase 4: `remove_item()` and `cancel_reservation()`
- **`remove_item(actor, item_id)`:** Librarians only, and refused while any copy is on loan. Anyone waiting for the item gets a message and their reservation is cancelled. The item's past loans are also removed from members' history, so the database never has a loan pointing at an item that no longer exists.
- **`cancel_reservation(actor, member_id, item_id)`:** A member can cancel their own reservation, and a librarian can cancel anyone's. If a returned copy was being held for that member, it passes to the next person in line, and they're notified.
- **`_notify_held_copies(item)`:** One helper used by both `return_item()` and `cancel_reservation()`. If there are N free copies, the first N people in line should each have been told. Anyone in that group whose reservation isn't `notified` yet gets a message.

---

## Phase 5: Repository + SQLite persistence

**Files:** `storage/database.py`, `storage/repositories.py`; changes to `models/loan.py`, `models/reservation.py`, `services/library.py`, `.env.example`

### `Database` (`storage/database.py`)
- **What it does:** Owns one SQLite connection and creates the five tables (`items`, `users`, `notifications`, `loans`, `reservations`) if they don't exist. `execute()` runs one SQL statement with `?` placeholders. `transaction()` groups statements so they either all succeed or are all undone.
- **DB path:** `LIBRARY_DB_PATH` from `.env`, or `library.db` in the project folder if it isn't set. A relative path is taken from the project folder, not from wherever the app was started. `*.db` is in `.gitignore`.
- **OOP concept:** Encapsulation. The rest of the program never touches `sqlite3` directly.

### `Repository(Generic[T])` (abstract)
- **What it does:** A base class for saving and loading one kind of object. The SQL for `save()`, `find()`, `all()`, `delete()` and `clear()` is written once, here. Each subclass only sets which table and columns it uses (`TABLE`, `COLUMNS`, `KEY_COLUMNS`) and implements two abstract methods: `_to_row(obj)` (object → row) and `_from_row(row)` (row → object).
- **What `Generic[T]` means:** `T` is a placeholder type, like a C++ template parameter. `ItemRepository(Repository[LibraryItem])` means "a repository whose `find()` returns a `LibraryItem`", which lets type checkers and editors catch mistakes.
- **OOP concept:** Generics, abstraction, inheritance, and the Template Method idea: the base class fixes the steps and the subclasses fill in the details.

### `ItemRepository`
- **What it does:** Saves the common fields as columns. Type-specific fields (`isbn`, `supervisor`, `issue_number`, `file_format`) go into one JSON column called `extra`. Loading turns the row back into a dict and passes it to `ItemFactory.create()`, so every item comes back as the right subclass.
- **OOP concept:** Reuse. The Factory (Phase 2) and `to_dict()` make loading items a few lines.

### `UserRepository`
- **What it does:** Saves the role, name, **password hash** (never the plain password) and fine balance. The role string picks the class to rebuild (`"Student"` → `Student`). It overrides `save()`, `delete()` and `clear()` to handle the `notifications` table too: it calls `super().save()` and then adds the notifications.
- **OOP concept:** Method overriding with `super()`, which extends the parent's behaviour instead of replacing it.

### `LoanRepository` / `ReservationRepository`
- **What they do:** Rows store only ids (`user_id`, `item_id`). To rebuild an object, the repository is given the already-loaded users and items, and looks up the real objects. A loaded loan points to the same `Member` object the library holds, not to a copy.

### `Library.save_to(db)` and `Library.load_from(db)`
- **`save_to`:** Writes everything in one transaction. It clears the tables children-first and inserts parents-first so foreign keys are never broken. If anything fails, the old saved data is kept.
- **`load_from`:** Loads in dependency order:
  1. items;
  2. users;
  3. loans, each added to its member, with returned ones moved to history through the normal `add_loan()` / `close_loan()`;
  4. reservations, in waitlist order. Members not yet notified go back into the `NotificationCenter` line.
  The next loan id continues after the highest saved one.
- **Tested:** `test_restart_keeps_state` builds a busy library, saves it, resets the singleton (a "restart"), loads into a fresh `Library` and checks that every item, user, fine, notification, loan, history entry, waitlist and status text matches. It then checks the loaded library still works.

### Decisions
- **All SQL lives in `storage/`.** A test (`test_no_sql_outside_storage`) fails if SQL appears anywhere else.
- **SQL injection:** table and column names come only from class constants, and values always go through `?` placeholders.
- **Saves are full snapshots.** `save_to()` rewrites every table. That's simple and safe for a library of this size, and Phase 6 can call it after each change.
- **`loan_id` is the first argument of `Loan(...)`, and `Library` assigns it.** That way the id exists before the loan is saved.
- **`Reservation.notified` is stored**, so after a restart nobody is told twice and nobody is skipped.
