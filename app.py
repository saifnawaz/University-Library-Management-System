"""Flask web API. Routes only: read the request, call Library, save, return JSON.

No library rules live here. Permissions, limits, fines and availability are all
decided by Library and the model classes; a route just passes the logged-in
user along and turns the result (or the exception) into JSON.
"""

from __future__ import annotations

import logging
import os
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request, session
from werkzeug.exceptions import HTTPException

from exceptions import LibraryException, NotAuthenticated, NotFound
from models.users import User
from services.library import Library
from storage.database import PROJECT_ROOT, Database

T = TypeVar("T")


def create_app(db_path: str | None = None, secret_key: str | None = None) -> Flask:
    """Build the Flask app and load the library from the database.

    db_path and secret_key default to the values in .env; tests pass their own.
    """
    load_dotenv(PROJECT_ROOT / ".env")
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config["SECRET_KEY"] = secret_key or os.getenv("FLASK_SECRET_KEY")
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("FLASK_SECRET_KEY is not set. Add it to .env (see .env.example).")
    app.config["SESSION_COOKIE_HTTPONLY"] = True   # page scripts cannot read the cookie
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"  # basic protection against CSRF

    db = Database(db_path)
    db_file = db.path
    library = Library()
    library.load_from(db)
    db.close()
    write_lock = threading.Lock()  # one change + save at a time

    # ---- helpers (request reading and saving only, no library rules) ----

    def current_user() -> User:
        """The logged-in user, or raise NotAuthenticated."""
        user_id = session.get("user_id")
        if not user_id:
            raise NotAuthenticated()
        try:
            return library.get_user(user_id)
        except NotFound:
            session.clear()
            raise NotAuthenticated() from None

    def body() -> dict[str, Any]:
        """The JSON body of the request as a dict."""
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError("Send a JSON object in the request body.")
        return data

    def text_field(data: dict[str, Any], name: str) -> str:
        """A required text field from the request body."""
        value = data.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"'{name}' is required.")
        return value.strip()

    def change(action: Callable[[], T]) -> T:
        """Run a change to the library, then save everything to the database."""
        with write_lock:
            result = action()
            save_db = Database(db_file)
            try:
                library.save_to(save_db)
            finally:
                save_db.close()
            return result

    # ---- errors: always clean JSON, never a stack trace ----

    def error(kind: str, message: str, status: int) -> tuple[Response, int]:
        return jsonify(error={"type": kind, "message": message}), status

    @app.errorhandler(LibraryException)
    def handle_library_error(e: LibraryException) -> tuple[Response, int]:
        return error(type(e).__name__, e.message, e.http_status)

    @app.errorhandler(ValueError)
    def handle_bad_input(e: ValueError) -> tuple[Response, int]:
        return error("InvalidInput", str(e), 400)

    @app.errorhandler(HTTPException)
    def handle_http_error(e: HTTPException) -> tuple[Response, int]:
        return error(type(e).__name__, e.description or e.name, e.code or 500)

    @app.errorhandler(Exception)
    def handle_unexpected(e: Exception) -> tuple[Response, int]:
        app.logger.exception("Unexpected error")  # full details go to the server log only
        return error("ServerError", "Something went wrong. Please try again.", 500)

    # ---- pages (static HTML; each page's JS loads its data from the API) ----

    @app.get("/")
    def login_page() -> Response:
        return app.send_static_file("login.html")

    # URL -> HTML file. Each page loads its own data from the API.
    pages = {
        "/dashboard": "dashboard.html",
        "/catalog": "catalog.html",
        "/catalog/<item_id>": "item.html",
        "/loans": "loans.html",
        "/reservations": "reservations.html",
        "/staff": "staff.html",
        "/staff/desk": "staff-desk.html",
        "/staff/members": "staff-members.html",
        "/staff/reports": "staff-reports.html",
    }
    for url, filename in pages.items():
        # "filename=filename" freezes the current value for this lambda; without it every
        # page would serve the last file in the loop. **_ ignores URL parts like item_id.
        app.add_url_rule(url, endpoint=f"page:{filename}",
                         view_func=lambda filename=filename, **_: app.send_static_file(filename))

    # ---- login ----

    @app.post("/api/login")
    def login() -> Response:
        data = body()
        user = library.authenticate(text_field(data, "user_id"), str(data.get("password", "")))
        session.clear()
        session["user_id"] = user.user_id
        return jsonify(user.to_dict())

    @app.post("/api/logout")
    def logout() -> Response:
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/me")
    def me() -> Response:
        return jsonify(current_user().to_dict())

    # ---- catalog ----

    @app.get("/api/items")
    def catalog() -> Response:
        return jsonify(library.catalog(current_user(), request.args.get("q", "")))

    @app.get("/api/items/<item_id>")
    def item_detail(item_id: str) -> Response:
        return jsonify(library.item_details(current_user(), item_id))

    # ---- borrowing ----
    # member_id is optional: a member acts for themself, a librarian names the member.
    # Library decides whether the logged-in user may act for that member.

    @app.post("/api/loans")
    def borrow() -> tuple[Response, int]:
        user, data = current_user(), body()
        member_id = data.get("member_id") or user.user_id
        loan = change(lambda: library.issue(user, member_id, text_field(data, "item_id")))
        return jsonify(loan.to_dict()), 201

    @app.post("/api/loans/return")
    def return_item() -> Response:
        user, data = current_user(), body()
        member_id = data.get("member_id") or user.user_id
        loan = change(lambda: library.return_item(user, member_id, text_field(data, "item_id")))
        return jsonify(loan.to_dict())

    @app.post("/api/reservations")
    def reserve() -> tuple[Response, int]:
        user, data = current_user(), body()
        member_id = data.get("member_id") or user.user_id
        reservation = change(lambda: library.reserve(user, member_id, text_field(data, "item_id")))
        return jsonify(reservation.to_dict()), 201

    @app.delete("/api/reservations/<item_id>")
    def cancel_reservation(item_id: str) -> Response:
        user = current_user()
        member_id = request.args.get("member_id") or user.user_id
        change(lambda: library.cancel_reservation(user, member_id, item_id))
        return jsonify(ok=True)

    # ---- the member's own account ----

    def loans_json(member_id: str) -> Response:
        """A member's current loans, history and fines (Library checks who may see them)."""
        member = library.get_member(current_user(), member_id)
        return jsonify(
            current=[loan.to_dict() for loan in member.loans],
            history=[loan.to_dict() for loan in reversed(member.history)],  # newest first
            fines=member.fines,
            fine_policy=member.get_fine_policy().describe(),
        )

    @app.get("/api/me/loans")
    def my_loans() -> Response:
        return loans_json(current_user().user_id)

    @app.get("/api/me/reservations")
    def my_reservations() -> Response:
        user = current_user()
        return jsonify(library.reservations_for(user, user.user_id))

    @app.get("/api/me/notifications")
    def my_notifications() -> Response:
        user = current_user()
        return jsonify(library.get_member(user, user.user_id).notifications)

    @app.post("/api/fines/pay")
    def pay_fine() -> Response:
        user, data = current_user(), body()
        member_id = data.get("member_id") or user.user_id
        try:
            amount = float(data.get("amount"))
        except (TypeError, ValueError):
            raise ValueError("'amount' must be a number.") from None
        member = change(lambda: library.pay_fine(user, member_id, amount))
        return jsonify(member.to_dict())

    # ---- librarian ----

    @app.post("/api/items")
    def add_item() -> tuple[Response, int]:
        user, data = current_user(), body()
        item = change(lambda: library.create_item(user, data))
        return jsonify(library.describe_item(item, user)), 201

    @app.post("/api/items/<item_id>/withdraw")
    def withdraw_item(item_id: str) -> Response:
        user = current_user()
        item = change(lambda: library.withdraw_item(user, item_id))
        return jsonify(library.describe_item(item, user))

    @app.get("/api/members")
    def members() -> Response:
        return jsonify([m.to_dict() for m in library.list_members(current_user())])

    @app.get("/api/members/<member_id>")
    def member_detail(member_id: str) -> Response:
        return jsonify(library.get_member(current_user(), member_id).to_dict())

    @app.get("/api/members/<member_id>/loans")
    def member_loans(member_id: str) -> Response:
        return loans_json(member_id)

    @app.get("/api/members/<member_id>/reservations")
    def member_reservations(member_id: str) -> Response:
        return jsonify(library.reservations_for(current_user(), member_id))

    @app.get("/api/reports/overdue")
    def overdue_report() -> Response:
        return jsonify([loan.to_dict() for loan in library.overdue_loans(current_user())])

    @app.get("/api/reports/stats")
    def stats_report() -> Response:
        return jsonify(library.stats(current_user()))

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(debug=os.getenv("FLASK_DEBUG") == "1")
