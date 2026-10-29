# University Library Management System

OOP course final project. A university library app with a Python OOP backend and a web frontend. The course is graded on OOP, so the OOP design is the most important part of this codebase.

## Golden rule

ALL library business logic lives in Python classes inside `models/` and `services/`.

- `app.py` (Flask) routes stay thin: read the request, call one Library / service method, return JSON. No business rules in routes.
- JavaScript in `static/` only sends requests, renders responses and handles UI (animations, dark mode, live filtering of already-loaded data).
- JS may do convenience form checks, but Python must always re-validate the same thing.
- If you ever find an `if` in JS or in a route that decides a library rule (limits, fines, permissions, availability), move it into a class.

## Stack

- Python 3.11+, Flask
- SQLite via the built-in `sqlite3` module, wrapped by `Repository`
- scikit-learn (TF-IDF + cosine similarity) for content-based recommendations
- An LLM API for the chatbot; key read from `.env` (never hardcoded, never committed)
- Frontend: plain HTML, CSS, JS using `fetch()`

## Folder structure

```
models/        # User hierarchy, LibraryItem hierarchy, Loan, Reservation
services/      # Library, FinePolicy, ItemFactory, NotificationCenter,
               # Recommender + strategies, ChatAssistant, TopicGuard
storage/       # Repository, database setup
exceptions.py
app.py         # Flask routes only
seed.py        # demo data (python seed.py, or --reset to replace)
static/        # HTML, CSS, JS
tests/         # smoke tests, extended each phase
docs/mockups/  # UI mockups to match in Phase 7
.env           # API keys (gitignored)
requirements.txt
```

## Roles (exactly 3)

- **Student**: borrow limit 3, loan period 14 days
- **Faculty**: borrow limit 10, loan period 30 days, only role allowed to borrow Thesis
- **Librarian**: adds/removes items, processes issue/return, manages member accounts, sets fine rules, views reports. There is no Admin role.

Student and Faculty inherit from abstract Member; Member and Librarian inherit from abstract User.

## Items

Abstract `LibraryItem` with abstract `can_be_borrowed_by(member)`:

- Book: any member can borrow
- ReferenceBook (subclass of Book): nobody can borrow, read in library only
- EBook: any member, unlimited copies
- Magazine: any member, shorter loan period than a book
- Thesis: Faculty only

Loan due date = the shorter of the member's loan period and the item's limit; this is decided inside `Library.issue()`.

## Class design (follow the UML)

- **User** (abstract): user_id, name, password_hash, get_role() abstract, check_password()
- **Member** (abstract): loans, history, fines; abstract get_borrow_limit(), get_loan_days(), get_fine_policy(); can_borrow()
- **Loan**: member, item, issue/due/return dates, is_overdue(), calculate_fine()
- **Reservation**: member, item, created_at (waitlist)
- **FinePolicy** (abstract, Strategy pattern): StudentFinePolicy, FacultyFinePolicy. Exact fine rates not decided yet; keep them configurable, not hardcoded in many places
- **Library** (Singleton via `__new__`): owns items, users, loans, reservations; issue(), return_item(), reserve(), search()
- **ItemFactory** (Factory): static create(data) returns the correct LibraryItem subclass
- **NotificationCenter** (Observer): subscribe(item_id, member), notify(item_id) when a reserved item is returned
- **Repository(Generic[T])**: save(), find(), all(); all SQL lives here
- **Recommender**: holds a list of RecommendationStrategy objects and combines their results
- **RecommendationStrategy** (abstract): ContentBasedStrategy (TF-IDF), CollaborativeStrategy (people who borrowed X also borrowed Y)
- **ChatAssistant**: private `_system_prompt`, a TopicGuard, an LLM client; ask(member, question), private `_build_context()` that pulls real data from Library and Recommender
- **StaffAssistant** (subclass of ChatAssistant): the librarian's assistant; overrides the system prompt and `_build_context()` with staff data (overdue loans, members, waitlists, reports). Its panel already sits, switched off, at the bottom of the staff overview.
- **TopicGuard** (abstract): LLMTopicGuard, KeywordTopicGuard

## Error handling (Phase 6)

- Flask must catch both `LibraryException` and `ValueError` (models raise `ValueError` for bad input such as an empty name or a negative payment) and return clean JSON errors, never a stack trace or raw error page.

## Chatbot rules

- Only answers library questions (books, availability, loans, fines, reservations, recommendations, library rules). Anything else (weather, GPA, general chat) gets a fixed polite refusal.
- TopicGuard runs BEFORE the main LLM call; the system prompt is a second layer, not the only one.
- The LLM must never invent book data; it only uses context passed from Python.
- LLM is called only from Python, never from JS.
- If the API fails, return a fallback message instead of crashing the app.

## OOP requirements to show clearly

- Encapsulation: underscore-prefixed attributes + `@property` getters/setters
- Abstraction: ABC + `@abstractmethod`
- Inheritance and polymorphism as in the hierarchies above
- Operator overloading on LibraryItem: `__eq__`, `__str__`, `__lt__` (sorting)
- Custom exceptions in `exceptions.py`: LibraryException base, with ItemNotAvailable, LimitExceeded, UnpaidFines, PermissionDenied
- Design patterns: Singleton, Factory, Strategy, Observer
- Type hints and short docstrings on every class and public method

## UI is a top priority

The frontend must look like a real product, not a college assignment. Treat it with the same care as the OOP design.

### Visual direction: "Classic library"

Warm paper look, serif headings, book-spine colour blocks. Match the mockups in `docs/mockups/` closely.

- **Fonts** (Google Fonts): Fraunces for headings and big numbers, Source Sans 3 for body and UI
- **Colours**:

  | Token        | Hex       |
  |--------------|-----------|
  | page         | `#F5EFE3` |
  | surface      | `#FBF7EF` |
  | border       | `#D9CDB8` |
  | input border | `#C9BA9F` |
  | text         | `#2A1F16` |
  | muted text   | `#5C4A3A` |
  | accent (oxblood)   | `#7A2E12` |
  | secondary (forest) | `#2F4A3A` |

- Small border radius (2-4px), thin 1px borders, no heavy shadows
- Student/Faculty use a light top navigation; the Librarian uses a dark (`#2A1F16`) top bar so staff screens feel distinct
- Item status always shown in words, never colour alone (e.g. "Read in library only", "Faculty borrowing only", "All copies issued · 1 waiting")
- Dark mode: invert to a dark ground (`#2A1F16` family) keeping the same accent and serif headings

### Rules

- One consistent design system: colours, fonts, spacing and border radius defined once as CSS variables and reused everywhere. No random one-off colours.
- Light and dark mode.
- Every screen handles all states: loading, empty (e.g. "no books found"), error, and success. No blank screens, no raw error text.
- Clear feedback for every action: toasts or inline messages for issue, return, reserve, fine payment.
- Responsive: usable on a phone and a laptop.
- Subtle, purposeful motion only (hover, page/card transitions). No flashy effects.
- Role-specific dashboards: Student, Faculty and Librarian each see a layout built for their tasks, not one page with buttons hidden.
- Key screens: login, member dashboard, catalog with search and filters, item detail, my loans and fines, reservations, librarian dashboard with stats, chatbot panel.
- UI work never moves library rules into JS; the golden rule above still applies.

## Git

- Never run `git commit` or `git push`. The author makes all commits; say when work is ready to commit.
- Do not add Co-Authored-By or any Claude attribution to commit messages.

## Running the app

From the project root, with the venv's Python:

- Copy `.env.example` to `.env` and set `FLASK_SECRET_KEY`. `PORT` is optional (default 8765; port 5000 is blocked on the author's machine).
- `.venv\Scripts\python seed.py` loads demo data (`--reset` replaces existing data).
- `.venv\Scripts\python app.py` starts the app at http://127.0.0.1:8765 (or the `PORT` from `.env`).

## Working style

- The author is new to Python (comes from C/C++). After writing each class, explain briefly in simple language what it does and which OOP concept it shows. These explanations matter for the viva.
- Work one phase at a time. Do not jump ahead or build multiple phases in one go.
- Keep code readable over clever.
- Smoke tests live in `tests/smoke_test.py`. Run them from the project root with the venv's Python: `.venv\Scripts\python -m tests.smoke_test`. Extend it with tests for each new phase.
- Viva notes live in `docs/PROJECT_NOTES.md`. After finishing every phase, append a section for it: the classes, what each does, the OOP concept it shows, and the decisions made. Update the "Quick map" table when a phase adds a new concept or pattern, and fix earlier sections if later work changes them.

## Phases

1. Project setup, exceptions.py, user hierarchy (User, Member, Student, Faculty, Librarian)
2. Item hierarchy + ItemFactory
3. Loan, Reservation, FinePolicy strategies
4. Library singleton + NotificationCenter
5. Repository + SQLite persistence
6. Flask routes
7. Frontend
8. Recommender
9. ChatAssistant + TopicGuard
10. Polish, sample data, testing

## Security

- `.env` and the SQLite database file are in `.gitignore`
- Passwords stored as hashes, never plain text
