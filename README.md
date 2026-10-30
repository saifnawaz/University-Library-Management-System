# The Reading Room: University Library Management System

A web app for running a university library, built as the final project for our Object-Oriented Programming course. Students and faculty search the catalog, borrow, reserve, and keep track of their loans and fines. Librarians issue and return items, manage members and see reports. All the library rules live in Python classes; the Flask routes and the JavaScript frontend only pass requests along and show the results. Each role also has a chat assistant (Google Gemini) that answers from the library's own data.

## Features by role

**Student**
- Borrow up to 3 items for 14 days each; late fines Rs 10 per day, up to Rs 500
- Search the catalog with filters for type and "I can borrow now"
- Reserve items when every copy is out, see your place in line, and get a notification when a copy is held for you (held for 3 days by default)
- My loans: due dates, fines (current and building up), payment, history
- Recommendations ("Because you borrowed Clean Code")
- "Ask the librarian" chat about books, availability, loans, fines and reservations

**Faculty**
- Everything a student can do, with a limit of 10 items for 30 days and lower fines (Rs 5 per day, up to Rs 300)
- The only role that can borrow theses

**Librarian**
- Front-desk overview: items on loan, overdue loans, fines, waitlists, most borrowed items
- Issue & return: look up a member, issue, return, take fine payments, manage their reservations
- Add items and withdraw them from the catalog
- Members list and reports
- Staff assistant chat: overdue loans, fines, waitlists, member accounts and statistics

Item rules: reference books are read in the library only, e-books have unlimited copies, magazines are lent for at most 7 days, and theses are for faculty only. Item status is always shown in words.

## Tech stack

- Python 3.11+, Flask
- SQLite (built-in `sqlite3`) behind a generic `Repository` layer
- scikit-learn (TF-IDF and cosine similarity) for recommendations
- Google Gemini through the official `google-genai` SDK, for the chat assistants
- Plain HTML, CSS and JavaScript (`fetch()`), light and dark mode, works on phones

## OOP concepts and design patterns

| Concept / pattern | Where it is in the code |
|---|---|
| Encapsulation | `_underscore` attributes with `@property` getters and setters, e.g. `User.name`, `LibraryItem.total_copies`, `Library.hold_days`, `ChatHistory` |
| Abstraction | Abstract base classes with `@abstractmethod`: `User`, `Member`, `LibraryItem`, `FinePolicy`, `RecommendationStrategy`, `TopicGuard`, `LLMClient` |
| Inheritance | `User → Member → Student / Faculty`, `User → Librarian`, `LibraryItem → Book → ReferenceBook`, `ChatAssistant → StaffAssistant` (`models/`, `services/`) |
| Polymorphism | `item.can_be_borrowed_by(member)`, `member.get_fine_policy()`, `strategy.recommend(...)`, `guard.is_library_question(...)` |
| Operator overloading | `LibraryItem.__eq__`, `__hash__`, `__lt__`, `__str__`; `Reservation.__lt__` (waitlist order) |
| Custom exceptions | `exceptions.py`: `LibraryException` with `ItemNotAvailable`, `LimitExceeded`, `UnpaidFines`, `PermissionDenied` and more |
| Singleton | `Library` (`services/library.py`), through `__new__` |
| Factory | `ItemFactory.create(data)` (`services/item_factory.py`) |
| Strategy | `FinePolicy` subclasses (`services/fine_policy.py`); recommendation strategies combined by `Recommender` (`services/recommender.py`) |
| Observer | `NotificationCenter` (`services/notification_center.py`) tells the next waiting member when a copy is held |
| Template method | `ChatAssistant.ask()` fixes the steps; `StaffAssistant` overrides who may ask, the prompt and the context |
| Generics | `Repository(Generic[T])` (`storage/repositories.py`) |

`docs/PROJECT_NOTES.md` explains every class and decision in more detail.

## UML diagrams

Class diagrams for the whole project, split into six parts (users and items, library core, storage, recommendations, AI assistants, exceptions): see [docs/UML.md](docs/UML.md).


## Live demo

Try it here: [saifnawaz.pythonanywhere.com](https://saifnawaz.pythonanywhere.com)

Use the "Try a demo account" buttons on the login page to sign in as a student, faculty member or librarian. No sign-up needed.


## How to run

From the project root on Windows (on macOS or Linux, use `.venv/bin/python` instead of `.venv\Scripts\python`):

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

| Setting | Needed? | What it does |
|---|---|---|
| `FLASK_SECRET_KEY` | yes | Any long random string; signs the login cookie |
| `GEMINI_API_KEY` | optional | Turns on the chat assistants; without it they reply with a polite "not available" message |
| `PORT` | optional | Default 8765 |
| `HOLD_DAYS` | optional | Days a held copy waits to be collected, default 3 |
| `LLM_TOPIC_GUARD` | optional | `1` (default): Gemini also checks questions the keyword check isn't sure about. `0`: keywords only, one Gemini call per question |
| `DEMO_MODE` | optional | `1` shows demo logins and a "Reset demo data" button on the sign-in page |

Load the demo data and start the app:

```
.venv\Scripts\python seed.py            (add --reset to replace existing data)
.venv\Scripts\python app.py
```

Then open http://127.0.0.1:8765 (or the `PORT` you set).

## Demo logins

| Role | User ID | Password | What to look at |
|---|---|---|---|
| Student | `stu01` | `student123` | 2 of 3 items on loan, first in line for "Introduction to Algorithms" |
| Student | `stu02` | `student123` | An overdue book and an unpaid Rs 30 fine, so borrowing is paused |
| Student | `stu03` | `student123` | New member: popular picks, and a copy held for her to collect |
| Faculty | `fac01` | `faculty123` | A thesis on loan and an overdue magazine |
| Librarian | `lib01` | `librarian123` | Front desk, members, reports and the staff assistant |

These passwords are for the demo data only.

## Tests

```
.venv\Scripts\python -m tests.smoke_test
```

The smoke tests cover the models, the rules, saving and loading, every route, the recommender and both assistants. They use a fake LLM client and never call the internet.

## Folder structure

```
models/        User and LibraryItem hierarchies, Loan, Reservation
services/      Library, ItemFactory, FinePolicy, NotificationCenter, Recommender,
               ChatAssistant, StaffAssistant, ChatHistory, TopicGuard, LLMClient,
               RateLimiter, DemoMode
storage/       Database (tables) and the repositories (all SQL is here)
static/        HTML pages, css/, js/
tests/         smoke_test.py
docs/          PROJECT_NOTES.md (class-by-class notes), mockups/
exceptions.py  custom exceptions
app.py         Flask routes
seed.py        demo data
```

## Screenshots

<!-- Replace each placeholder with an image, e.g. ![Member dashboard](docs/screenshots/member-dashboard.png) -->

- Sign-in page: _screenshot to come_
- Member dashboard with "Ask the librarian": _screenshot to come_
- Catalog with filters: _screenshot to come_
- Item detail: _screenshot to come_
- My loans and fines: _screenshot to come_
- Librarian overview with the staff assistant: _screenshot to come_
- Issue & return: _screenshot to come_
- Dark mode and phone view: _screenshot to come_

## Team

- Saif Nawaz
- Muhammad Saad
