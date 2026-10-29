# Project Notes (viva preparation)

What each class does, which OOP idea it shows, and why it was built that way.
One section per phase, added as each phase is finished.

## Quick map: OOP concept → where to point in the code

| Concept | Where |
|---|---|
| Encapsulation | `_underscore` attributes + `@property` everywhere; e.g. `User.name` setter, `LibraryItem.total_copies` setter, read-only `Member.loans` (returns a copy) |
| Abstraction | `User`, `Member`, `LibraryItem`, `FinePolicy` are ABCs with `@abstractmethod` |
| Inheritance | `User → Member → Student/Faculty`, `User → Librarian`, `LibraryItem → Book → ReferenceBook`, `FinePolicy → StudentFinePolicy/FacultyFinePolicy` |
| Polymorphism | `item.can_be_borrowed_by(member)`, `member.get_fine_policy()`, `member.has_research_access()`, `user.can_manage_library()`, `item.get_loan_limit_days()`, `user.to_dict()` (Member adds its own fields), `exc.http_status` in the Flask error handler |
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

### Added after Phase 4: `withdraw_item()` and `cancel_reservation()`
- **`withdraw_item(actor, item_id)`:** A **soft delete**. Librarians only, and refused while any copy is on loan. The item isn't deleted: `item.withdraw()` sets a `withdrawn` flag, which hides it from `search()` and `all_items()` and blocks issuing and reserving it. Members' loan history still points to it. Anyone waiting for the item gets a message and their reservation is cancelled. (This first deleted the item and its history as `remove_item()`, and was changed to a soft delete before Phase 6 so history is kept.)
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

---

## Phase 6: Flask routes

**Files:** `app.py`; changes to `exceptions.py`, `services/library.py`, `models/users.py`, `models/loan.py`, `models/reservation.py`, `models/items.py` (withdrawn flag), `storage/` (withdrawn column)

### `create_app()` (`app.py`)
- **What it does:** Builds the Flask app. It reads `FLASK_SECRET_KEY` and the DB path from `.env`, and stops with a clear message if the key is missing. It then loads the `Library` from the database and defines the routes. Tests call `create_app(db_path=..., secret_key=...)` with a temporary database.
- **Why a function:** Flask calls this an "app factory". Each test can build a fresh app on its own database.

### Routes stay thin
- **What each route does:**
  1. Reads the request.
  2. Gets the logged-in user with `current_user()`.
  3. Calls **one** `Library` method, passing the user along.
  4. Saves.
  5. Returns JSON.
- **What routes never contain:** a permission check, a limit, a fine or an availability rule. Those all stay in `Library` and the models. A test (`test_routes_contain_no_rules`) fails if `app.py` mentions `can_manage_library`, `can_be_borrowed_by`, `check_can_borrow`, `Student`, `Librarian` and similar names.
- **`member_id` is optional:** a member acts for themself, and a librarian names the member. `Library._require_self_or_librarian()` decides whether that's allowed, not the route.
- **`change(action)`:** a helper that runs the library change and then saves to the database, under a lock so two requests can't save at the same time. `action` is a `lambda`, a small unnamed function, so `change()` can run the code it's given and then save.

### Login (Flask sessions)
- **What it does:** `POST /api/login` calls `library.authenticate()`, which checks the password hash. The user id is stored in `session`, a cookie signed with the secret key so the browser can't change it. The cookie is `HttpOnly` (JavaScript can't read it) and `SameSite=Lax` (basic protection against CSRF).
- **Bad login message:** a wrong login says "Wrong user id or password." and never reveals which part was wrong.
- **Not logged in:** any route called without a login answers with 401 `NotAuthenticated`.

### One error handler, clean JSON
- **What it does:** Every error comes back as `{"error": {"type": ..., "message": ...}}` with a status code, never a stack trace.
  - `LibraryException`: each exception class carries its own `http_status`: 400 by default, 401 `NotAuthenticated`, 403 `PermissionDenied`, 404 `NotFound`, 409 for state conflicts (`ItemNotAvailable`, `LimitExceeded`, `UnpaidFines`, `OverdueLoans`). The handler is one line: `e.http_status`.
  - `ValueError`: 400 `InvalidInput`, e.g. a bad year or a missing field.
  - Flask's own errors, such as an unknown URL (404) or a wrong method (405), also come back as the same JSON.
  - Anything unexpected: 500 with a polite message. The details go to the server log only.
- **OOP concept:** Polymorphism. The handler doesn't need a table of status codes; it asks the exception object.

### Endpoints
| Method | URL | Calls |
|---|---|---|
| POST | `/api/login`, `/api/logout` | `library.authenticate()` |
| GET | `/api/me` | `user.to_dict()` |
| GET | `/api/items?q=` | `library.catalog()` (search + status + actions) |
| GET | `/api/items/<id>` | `library.item_details()` |
| POST | `/api/loans` | `library.issue()` |
| POST | `/api/loans/return` | `library.return_item()` |
| POST | `/api/reservations` | `library.reserve()` |
| DELETE | `/api/reservations/<item_id>` | `library.cancel_reservation()` |
| GET | `/api/me/loans`, `/api/me/reservations`, `/api/me/notifications` | `library.get_member()`, `library.reservations_for()` |
| POST | `/api/fines/pay` | `library.pay_fine()` |
| POST | `/api/items` | `library.create_item()` (uses `ItemFactory`) |
| POST | `/api/items/<id>/withdraw` | `library.withdraw_item()` |
| GET | `/api/reports/overdue`, `/api/reports/stats` | `library.overdue_loans()`, `library.stats()` |

### How objects become JSON
- **What it does:** Each model describes itself with `to_dict()`: `User`, `Member`, `Loan`, `Reservation`, `LibraryItem`. `Member.to_dict()` calls `super().to_dict()` and adds the fine balance, borrow limit and so on.
- **What `Library` adds:** facts only it knows, through `describe_item()` and `reservations_for()`: the status text, the waitlist position, and **what the viewer may do** (`actions.can_borrow`, `actions.can_reserve`, `actions.reason`).
- **How `actions` is worked out:** by the same `_check_can_issue()` and `_check_can_reserve()` methods that `issue()` and `reserve()` use. The frontend just shows or hides buttons from these values, so JavaScript never decides a rule.
- **What's never sent:** the password hash. `User.to_dict()` leaves it out.

### Decisions
- **`remove_item()` became `withdraw_item()`, a soft delete** (see Phase 4). The flag is a new `withdrawn` column. Older database files get the column added automatically when they're opened (`ADDED_COLUMNS` in `storage/database.py`).
- **Every change saves the whole library** (`save_to()`) before the response is sent. That's simple and safe at this size.
- **`POST /api/fines/pay` was added** although it wasn't in the endpoint list, because the UI needs fine-payment feedback. A member can pay their own fine, and a librarian can record a payment for anyone.
- **Not built yet:** creating member accounts and changing fine rules from the API (librarian screens); serving the frontend pages (Phase 7).

---

## Seed data (`seed.py`)

- **What it does:** Builds a demo library: 1 librarian, 2 students, 1 faculty member, 16 items across all five types, active, overdue and returned loans, a fine, and a waitlist. It then saves everything to the database and prints the demo logins.
- **Why it goes through `Library`:** It uses only normal `Library` methods (`create_item`, `issue`, `return_item`, `reserve`), with past dates passed as `today=`. That way the demo data obeys exactly the same rules as the app. For example, loans are issued in date order, so the overdue check sees the right day.
- **Safety:** It refuses to touch a database that already has data unless you pass `--reset` (checked with `Database.is_empty()`).

---

## Phase 7 (part 1): Login, member dashboard, catalog

**Files:** `static/login.html`, `static/dashboard.html`, `static/catalog.html`, `static/staff.html` (placeholder), `static/css/tokens.css`, `static/css/app.css`, `static/js/{api,ui,theme,login,dashboard,catalog}.js`, `static/favicon.svg`; page routes in `app.py`.

### How the frontend is organised
- **One file of design tokens (`tokens.css`):** every colour, font, spacing step, radius and animation timing is a CSS variable. Dark mode only redefines the colour variables under `[data-theme="dark"]`. A test (`test_no_raw_colours_outside_tokens`) fails if a colour value appears anywhere else.
- **`theme.js`:** runs in `<head>` before the page draws, picks the saved theme or the system setting, and avoids a flash of the wrong colours. The toggle saves the choice in `localStorage`; if storage is blocked, the toggle still works for that page.
- **`api.js`:** one `fetch` wrapper. Every failure becomes an `ApiError` with the readable message from the Python exception, or a friendly message if the server can't be reached.
- **`ui.js`:** shared helpers:
  - `h()` builds elements. It sets text with `textContent`, never `innerHTML`, so data from the API can't inject HTML.
  - It also provides the nav bar, toasts, loading, empty and error states, and date and money formatting.
- **JS uses ES modules** (`import` / `export`), so each page script imports only what it needs.

### The golden rule in the UI
- **Python decides every button.** Each item from `/api/items` carries `actions` (`can_borrow`, `can_reserve`, `reason`, `has_loan`, `queue_position`). These are worked out by the same `_check_can_issue()` and `_check_can_reserve()` that the real `issue()` and `reserve()` use. JavaScript only shows a button when the flag is true.
- **Facts the UI needs were added to Python, not worked out in JS:**
  - `Member.to_dict()`: `loans_remaining`, `borrow_block_reason`
  - `Loan.to_dict()`: `days_left`, `item_type_key`
  - `describe_item()`: `available_now` (a copy is on the shelf for someone not already waiting)
- **The banner, "Borrowing is paused · Bilal Ahmed has unpaid fines of Rs 30.", shows `borrow_block_reason` word for word.** JS never checks fines or limits itself.
- **The only JS-side checks are convenience ones** (an empty login form). The server checks the same things again.

### Screens
- **Login:** a split layout with a decorative shelf of book spines. Errors show inline ("Wrong user id or password."). After login, the user goes to `/dashboard` (members) or `/staff` (librarians).
- **Member dashboard:**
  - A "can borrow" / "borrowing is paused" banner, plus four tiles: on loan, overdue, reservations and fines.
  - The current loans list says "Due 4 Nov · in 10 days" or "Overdue by 11 days · Rs 110 so far", along with reservations ("Number 1 in line" / "Ready to collect"), notifications and the member's borrowing rules.
  - **Role-specific:** Faculty also get a Research collection panel (theses) and "Research access" in their rules.
- **Catalog:**
  - Search runs on the server, debounced so it doesn't send a request on every keystroke.
  - Filtering by type and "Available now" happens in the browser on the loaded results.
  - Cards show a coloured book spine per type, status in words, and Borrow / Reserve buttons from `actions`.
  - Borrowing or reserving shows a toast and refreshes just that card and the banner.
- **States:** every screen has a loading state (skeletons), an empty state ("No items match …" with Clear search), an error state with "Try again", and toasts for success and failure.

### Decisions
- **The mockups weren't in `docs/mockups/` when part 1 was first built.** It was later reworked to match them (see "Phase 7 (part 2)" below).
- **One HTML file per page**, each served by a route in `app.py` with no logic in it, instead of a single-page app. That's simpler to follow, and each page's script is small.
- **Dark mode keeps oxblood for filled buttons**, but uses a lighter oxblood (`--color-accent-ink`) for text, because dark oxblood text on a dark background isn't readable.
- **The reason text is hidden on cards when the status already explains it** (e.g. "Faculty borrowing only"). Python sets `actions.reason` to `None` in that case.

---

## Phase 7 (part 2): Matching the mockups, member pages, librarian pages

**Files:** new pages `item.html`, `loans.html`, `reservations.html`, `staff-desk.html`, `staff-members.html`, `staff-reports.html` (and their `js/` files); new `js/actions.js`, `js/item-form.js`, `js/staff-common.js`; `tokens.css` and `app.css` reworked; small additions to `services/library.py`, `models/users.py`, `models/loan.py`, `models/reservation.py` and `app.py`.

### Part 1 brought in line with `docs/mockups/`
- **Brand and type:** the library is "The Reading Room" (the staff bar adds "· Front desk"). Page titles use Fraunces at weight 400 (40px dashboard, 38px elsewhere), section headings 22px at 600, body text 15px.
- **Navigation:** plain text links 22px apart, with the current page in oxblood and a 2px underline.
  - Members: Dashboard, Catalog, My loans, Reservations, Ask the librarian.
  - Librarians: Overview, Catalog, Issue & return, Members, Reports, on the dark bar.
- **Login:** a dark left panel with the mockup headline and four spine blocks. The right side has "Library ID", "Forgot password?", a 50px Sign in button, and the circulation-desk footnote.
- **Stats:** a ruled strip (lines above and below) with 34px Fraunces numbers, instead of separate cards.
- **Books:** 2:3 covers with the title on them, coloured by type from the mockup palette:
  - book: oxblood
  - reference: brown
  - e-book: tan, with dark text
  - magazine: forest
  - thesis: ink
- **One button per book:**
  - **Borrow:** oxblood outline
  - **Join waitlist:** neutral outline
  - **Disabled grey button with a short label:** for any other case, e.g. "Not available to students"
- **Catalog:** "The stacks" heading, the search box on the right, and a sidebar with type checkboxes and an availability radio ("Everything" / "I can borrow now").
- **Colours added from the mockups:** `#E3D8C5` (muted text on dark), `#3A2D22` (inputs on dark), `#E8DFCF` (table row lines), `#EFE7D8` (disabled), `#FFFFFF` (staff desk inputs). All are tokens.

### New pages
- **Item detail (`/catalog/<id>`):** a large cover, the facts as a definition list, the status in words, and the same single action as the catalog, plus the full reason in words. Librarians get "Withdraw from catalog", which needs a second click to confirm.
- **My loans (`/loans`):** a stat strip, current loans ("Due in 10 days" / "Overdue by 11 days · Rs 110 so far"), a fines panel with a payment form, the member's borrowing rules, and a history table.
- **Reservations (`/reservations`):** place in line or "Ready to collect", a Cancel button, and notifications.
- **Librarian overview (`/staff`):** today's numbers, a Quick issue panel (Member ID + Item ID → Issue or Return), the overdue table, and "Most borrowed, last 30 days" drawn as a row of book blocks whose height shows how often each was borrowed.
- **Issue & return (`/staff/desk`):** look up a member and see their loans with Return buttons, an issue box, fine payment, and their reservations with Cancel.
- **Members (`/staff/members`):** every member with loans, overdue items, fines and whether they can borrow, filtered in the browser.
- **Reports (`/staff/reports`):** collection and membership counts, every overdue loan, and most borrowed of all time.
- **Catalog for librarians:** an "Add an item" form. JS only shows the extra field for the chosen type (ISBN, file format, issue or supervisor); `ItemFactory` validates everything.

### Python additions so JS still decides no rules
- **`actions.unavailable_label`:** the short text for a disabled button. Python picks it from which rule said no:
  - the item's own restriction → `"Not available to students"`, using the new polymorphic `User.get_role_plural()`; `Faculty` overrides it to return "faculty"
  - fines, overdue items or the limit → `"Borrowing paused"`
  - no free copy → `"Not available right now"`
- **`Library.list_members()`:** librarians only.
- **`Library.stats()`:** adds `most_borrowed_recent` (the last `RECENT_DAYS` = 30 days), each entry with its type for the cover colour.
- **New API routes:** `/api/members`, `/api/members/<id>`, `/api/members/<id>/loans` and `/api/members/<id>/reservations`. A member can open their own account; a librarian can open anyone's. `Library` decides which, as before.
- **More fields in JSON:** `Member.to_dict()` adds `overdue_loans`; `Loan.to_dict()` adds `item_author` and `member_role`; `Reservation.to_dict()` adds `item_author` and the item type.
- **E-book status:** now reads "Always available" (mockup wording).

### Decisions
- **"Picked for you" waits for the recommender (Phase 8).** Until then the dashboard shows "Ready to borrow" (students) or "From the research collection" (faculty). Each is built from the catalog's own `actions`, so nothing is invented.
- **The "Ask the librarian" panel is in place but switched off**, with the note "Coming soon". It will be connected in Phase 9.
- **Mockup text was changed where it promised something the app can't do:**
  - "renew" is gone from the login text.
  - "See shelf location" and "Open e-book" aren't used.
  - "Forgot password?" says to ask at the circulation desk.
- **Pages use `startPage("member" | "staff" | "any")`** so a librarian opening a member page (or the other way round) is sent to their own home page. The API still checks permissions on every request.

---

## Phase 7: fixes after testing

### 1. Current fine vs total fine (worked out in Python)
- **The problem:** the staff overview showed "Fines pending Rs 30" while the overdue table showed Rs 110 and Rs 25. Two different numbers carried the same name.
- **The model now has three clear amounts**, in `Member` (`models/users.py`):
  - **Current fine** (`current_fine` property): already charged when a late item came back, unpaid, and **payable now**. This was called `fines` before. The database column is still named `fines`, so old files load.
  - **Accruing fine** (`accruing_fine()`): what the overdue items still out will add when they're returned. It's the sum of `loan.calculate_fine()` over current loans, so the Strategy pattern still decides the amounts.
  - **Total fine** (`total_fine()`): current + accruing, i.e. what the member would owe if everything came back today.
- **`Library.stats()` now reports `current_fines`, `accruing_fines` and `total_fines`.** Every page labels them the same way: "Current fine, payable now" and "Total fine, with overdue items". Overdue tables call their column "Adds on return", so it never looks like a third kind of fine.

### 2. What to do next, after paying
- **`LibraryException` takes an optional `next_step`:** a short sentence saying what the user can do about the problem. `Member.check_can_borrow()` fills it in for each rule:
  - `UnpaidFines` → "Pay the current fine of Rs 30 to borrow again."
  - `OverdueLoans` → 'Return "Introduction to Algorithms" to borrow again.'
  - `LimitExceeded` → "Return an item to borrow another."
- **Where it shows:** `Member.to_dict()` includes `borrow_next_step`, and the Flask error JSON includes `next_step`. Because of that, the paused notice, toasts and refused-borrow errors all show the next step.
- **After paying:** the toast says "Fine paid. Return "Introduction to Algorithms" to borrow again.", and the page reloads, so the notice, figures and buttons change straight away.
- **OOP concept:** extending the base exception once gives every subclass the new field (inheritance).

### 3. Calmer layout
- **Sizes:** content up to 1200px wide, body text 16px, nothing under 14px (a Playwright check measures every text element on every page), 48–64px between sections (`--space-section`).
- **Fewer boxes:** list rows, rules, info panels, tables, empty states and notices have no borders. They use whitespace and thin dividers. Only forms you act on (Quick issue, Add an item, Issue to member) keep a box.
- **Fewer things per screen:**
  - **My loans** has three parts: On your desk; one Fines section (two figures, the pay form, the rules as one muted line); History.
  - **Dashboard:** the stat strip hides zero values, and "Ready to borrow" only shows items the member can actually borrow. It disappears while borrowing is paused.
- **Tables:** rows have 18px padding and dates never wrap. On phones, each row turns into "Label: value" lines. `h()` copies the column headers onto the cells (`labelledTable()`), so nothing scrolls sideways.
