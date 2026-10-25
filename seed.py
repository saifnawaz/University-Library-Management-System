"""Fill the database with demo accounts, items, loans and a waitlist.

Run from the project root:
    .venv\\Scripts\\python seed.py           (only if the database is empty)
    .venv\\Scripts\\python seed.py --reset   (replace everything in the database)

All changes go through Library, so the seed data obeys the same rules as the app.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

from models.users import Faculty, Librarian, Student, User
from services.library import Library
from storage.database import Database

# (user_id, name, password, class) - demo passwords only, never use these for real.
ACCOUNTS = [
    ("lib01", "Sara Qureshi", "librarian123", Librarian),
    ("stu01", "Ayesha Khan", "student123", Student),
    ("stu02", "Bilal Ahmed", "student123", Student),
    ("fac01", "Dr. Imran Malik", "faculty123", Faculty),
]

ITEMS = [
    # ---- books ----
    {"type": "book", "item_id": "B001", "title": "Clean Code", "author": "Robert C. Martin",
     "year": 2008, "subject": "Software Engineering", "total_copies": 3, "isbn": "9780132350884",
     "description": "Principles and practices for writing readable, maintainable code: "
                    "naming, functions, refactoring and unit tests."},
    {"type": "book", "item_id": "B002", "title": "Introduction to Algorithms",
     "author": "Cormen, Leiserson, Rivest, Stein", "year": 2009, "subject": "Algorithms",
     "total_copies": 2, "isbn": "9780262033848",
     "description": "Comprehensive textbook on algorithms and data structures: sorting, "
                    "graphs, dynamic programming and complexity."},
    {"type": "book", "item_id": "B003",
     "title": "Design Patterns: Elements of Reusable Object-Oriented Software",
     "author": "Gamma, Helm, Johnson, Vlissides", "year": 1994,
     "subject": "Software Engineering", "total_copies": 2, "isbn": "9780201633610",
     "description": "The classic catalogue of object-oriented design patterns such as "
                    "Singleton, Factory, Strategy and Observer."},
    {"type": "book", "item_id": "B004", "title": "The Pragmatic Programmer",
     "author": "David Thomas, Andrew Hunt", "year": 2019, "subject": "Software Engineering",
     "total_copies": 2, "isbn": "9780135957059",
     "description": "Practical advice on the craft of programming, from debugging to "
                    "automation and working in teams."},
    {"type": "book", "item_id": "B005", "title": "Artificial Intelligence: A Modern Approach",
     "author": "Stuart Russell, Peter Norvig", "year": 2020, "subject": "Artificial Intelligence",
     "total_copies": 2, "isbn": "9780134610993",
     "description": "Standard AI textbook covering search, knowledge representation, "
                    "machine learning and intelligent agents."},
    {"type": "book", "item_id": "B006", "title": "Database System Concepts",
     "author": "Silberschatz, Korth, Sudarshan", "year": 2019, "subject": "Databases",
     "total_copies": 1, "isbn": "9780078022159",
     "description": "Relational databases, SQL, normalisation, transactions and "
                    "query processing."},
    # ---- reference books ----
    {"type": "reference", "item_id": "R001", "title": "A Dictionary of Computer Science",
     "author": "Oxford University Press", "year": 2016, "subject": "Computer Science",
     "total_copies": 2,
     "description": "Definitions of terms across computing, from algorithms to networking."},
    {"type": "reference", "item_id": "R002", "title": "The Chicago Manual of Style",
     "author": "University of Chicago Press", "year": 2017, "subject": "Writing",
     "total_copies": 1,
     "description": "Reference guide to citation, grammar and style for academic writing."},
    # ---- e-books ----
    {"type": "ebook", "item_id": "E001", "title": "Automate the Boring Stuff with Python",
     "author": "Al Sweigart", "year": 2019, "subject": "Programming", "file_format": "EPUB",
     "description": "Beginner-friendly Python: scripts for files, spreadsheets, web "
                    "scraping and everyday automation."},
    {"type": "ebook", "item_id": "E002", "title": "Think Python", "author": "Allen B. Downey",
     "year": 2015, "subject": "Programming", "file_format": "PDF",
     "description": "An introduction to Python and to thinking like a computer scientist."},
    {"type": "ebook", "item_id": "E003", "title": "Eloquent JavaScript",
     "author": "Marijn Haverbeke", "year": 2018, "subject": "Web Development",
     "file_format": "PDF",
     "description": "JavaScript from the basics to the browser and Node.js, with exercises."},
    # ---- magazines ----
    {"type": "magazine", "item_id": "M001", "title": "Communications of the ACM",
     "author": "ACM", "year": 2026, "subject": "Computer Science", "total_copies": 2,
     "issue_number": "Vol. 69 No. 9",
     "description": "Monthly magazine on research and practice in computing."},
    {"type": "magazine", "item_id": "M002", "title": "IEEE Spectrum", "author": "IEEE",
     "year": 2026, "subject": "Engineering", "total_copies": 1, "issue_number": "October 2026",
     "description": "News and features on engineering, electronics and technology."},
    # ---- theses (fictional demo data) ----
    {"type": "thesis", "item_id": "T001",
     "title": "Explainable Models for Early Diabetes Prediction", "author": "Hira Nadeem",
     "year": 2024, "subject": "Machine Learning", "supervisor": "Dr. Imran Malik",
     "description": "Interpretable machine learning for predicting diabetes risk from "
                    "patient records."},
    {"type": "thesis", "item_id": "T002",
     "title": "Energy-Aware Task Scheduling in Edge Computing", "author": "Usman Tariq",
     "year": 2023, "subject": "Distributed Systems", "supervisor": "Dr. Sana Javed",
     "description": "Scheduling algorithms that reduce energy use on edge devices."},
    {"type": "thesis", "item_id": "T003",
     "title": "Urdu Sentiment Analysis with Transformer Models", "author": "Maryam Siddiqui",
     "year": 2025, "subject": "Natural Language Processing", "supervisor": "Dr. Imran Malik",
     "description": "Fine-tuning transformer language models to classify sentiment in "
                    "Urdu text."},
]


def days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


def build_library() -> Library:
    """Create the demo library in memory, using only normal Library methods."""
    Library.reset()
    lib = Library()
    for user_id, name, password, cls in ACCOUNTS:
        lib.add_user(cls(user_id, name, User.hash_password(password)))
    staff = lib.get_user("lib01")
    for data in ITEMS:
        lib.create_item(staff, data)

    # Loans, in date order (each issue is checked against the rules on that day).
    lib.issue(staff, "stu01", "B004", today=days_ago(40))
    lib.issue(staff, "stu02", "M001", today=days_ago(30))        # magazine: due in 7 days
    lib.return_item(staff, "stu01", "B004", today=days_ago(30))  # back on time
    lib.issue(staff, "stu02", "B002", today=days_ago(25))        # due 11 days ago: overdue
    lib.return_item(staff, "stu02", "M001", today=days_ago(20))  # 3 days late: Rs 30 fine
    lib.issue(staff, "fac01", "M002", today=days_ago(12))        # due 5 days ago: overdue
    lib.issue(staff, "fac01", "B002", today=days_ago(10))        # last copy of B002
    lib.issue(staff, "fac01", "T001", today=days_ago(5))
    lib.issue(staff, "stu01", "B001", today=days_ago(4))
    lib.issue(staff, "stu01", "E001", today=days_ago(2))

    # Waitlist: both copies of B002 are out, so Ayesha joins the line.
    lib.reserve(staff, "stu01", "B002")
    return lib


def main() -> None:
    reset = "--reset" in sys.argv[1:]
    db = Database()
    try:
        if not db.is_empty() and not reset:
            print(f"The database already has data: {db.path}")
            print("Run with --reset to replace it with the demo data.")
            sys.exit(1)
        lib = build_library()
        lib.save_to(db)
    finally:
        db.close()

    print(f"Demo data saved to {db.path}\n")
    print(f"{'Role':<10} {'User id':<8} {'Password':<13} Name")
    print(f"{'-' * 10} {'-' * 8} {'-' * 13} {'-' * 16}")
    for user_id, name, password, cls in ACCOUNTS:
        print(f"{cls.__name__:<10} {user_id:<8} {password:<13} {name}")
    print("\nWhat to look at:")
    print("  stu01  2 of 3 items on loan, waiting for 'Introduction to Algorithms'")
    print("  stu02  an overdue book and an unpaid Rs 30 fine, so borrowing is blocked")
    print("  fac01  a thesis on loan and an overdue magazine")


if __name__ == "__main__":
    main()
