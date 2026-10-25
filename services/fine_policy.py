"""Fine policies: how much a member pays for a late return (Strategy pattern)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class FinePolicy(ABC):
    """Abstract rule for turning 'days overdue' into a fine amount (in Rs).

    Each member type picks a policy object; Loan asks that object for the fine,
    so changing the rules never needs a change in Loan.
    """

    @abstractmethod
    def get_daily_rate(self) -> float:
        """Fine charged per day overdue, in Rs."""

    @abstractmethod
    def get_max_fine(self) -> float:
        """Highest fine one loan can reach, in Rs."""

    def calculate_fine(self, days_overdue: int) -> float:
        """Return the fine for this many days overdue, never more than the cap."""
        if days_overdue <= 0:
            return 0.0
        return min(days_overdue * self.get_daily_rate(), self.get_max_fine())

    def describe(self) -> str:
        """Rule in words for the UI and chatbot, e.g. 'Rs 10 per day, up to Rs 500'."""
        return f"Rs {self.get_daily_rate():g} per day, up to Rs {self.get_max_fine():g}"


class StudentFinePolicy(FinePolicy):
    """Fine rules for students."""

    DAILY_RATE: float = 10.0
    MAX_FINE: float = 500.0

    def get_daily_rate(self) -> float:
        return self.DAILY_RATE

    def get_max_fine(self) -> float:
        return self.MAX_FINE


class FacultyFinePolicy(FinePolicy):
    """Fine rules for faculty members."""

    DAILY_RATE: float = 5.0
    MAX_FINE: float = 300.0

    def get_daily_rate(self) -> float:
        return self.DAILY_RATE

    def get_max_fine(self) -> float:
        return self.MAX_FINE
