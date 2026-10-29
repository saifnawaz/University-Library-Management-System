"""Recommendations: a Recommender that combines several RecommendationStrategy objects (Strategy)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models.items import LibraryItem
from models.loan import Loan
from models.users import Member


@dataclass(frozen=True)
class Recommendation:
    """One suggested item, how strongly it is suggested, and why (in words)."""

    item: LibraryItem
    score: float
    reason: str


class RecommendationStrategy(ABC):
    """One way of scoring items for a member. Recommender combines several of these."""

    def __init__(self, weight: float = 1.0) -> None:
        """weight: how much this strategy counts when Recommender adds the scores up."""
        if weight <= 0:
            raise ValueError("A strategy's weight must be above 0.")
        self._weight: float = weight

    @property
    def weight(self) -> float:
        """How much this strategy counts in the combined score."""
        return self._weight

    @abstractmethod
    def recommend(self, member: Member, candidates: list[LibraryItem],
                  loans: list[Loan]) -> list[Recommendation]:
        """Score the candidate items for this member. Higher score = better match.

        candidates are already filtered by Recommender; loans is every loan in the
        library (active and returned). Items with no match are left out.
        """

    @staticmethod
    def borrowed_items(member: Member) -> list[LibraryItem]:
        """Everything the member has borrowed, now or before, oldest loan first."""
        seen: dict[str, LibraryItem] = {}
        for loan in sorted(member.history + member.loans, key=lambda l: l.issue_date):
            seen.setdefault(loan.item.item_id, loan.item)
        return list(seen.values())


class ContentBasedStrategy(RecommendationStrategy):
    """Items whose text is close to what the member borrowed (TF-IDF + cosine similarity)."""

    @staticmethod
    def item_text(item: LibraryItem) -> str:
        """The words compared for each item: title, author, subject and description."""
        return f"{item.title} {item.author} {item.subject} {item.description}"

    def recommend(self, member: Member, candidates: list[LibraryItem],
                  loans: list[Loan]) -> list[Recommendation]:
        borrowed = self.borrowed_items(member)
        if not borrowed or not candidates:
            return []

        # TF-IDF turns each item's text into a vector of word weights: words that are
        # common in one item but rare across the catalog count the most.
        vectorizer = TfidfVectorizer(stop_words="english")
        try:
            vectors = vectorizer.fit_transform(
                [self.item_text(i) for i in borrowed + candidates])
        except ValueError:  # no usable words at all (e.g. only stop words)
            return []
        # similarity[c][b]: how close candidate c is to borrowed item b (0 to 1)
        similarity = cosine_similarity(vectors[len(borrowed):], vectors[:len(borrowed)])

        results = []
        for candidate, row in zip(candidates, similarity):
            best = int(row.argmax())  # the borrowed item it is closest to
            if row[best] > 0:
                results.append(Recommendation(
                    candidate, float(row[best]), f"Because you borrowed {borrowed[best].title}"))
        return results


class CollaborativeStrategy(RecommendationStrategy):
    """Members who borrowed X also borrowed Y: items that share borrowers with the member's."""

    def recommend(self, member: Member, candidates: list[LibraryItem],
                  loans: list[Loan]) -> list[Recommendation]:
        mine = {item.item_id: item for item in self.borrowed_items(member)}
        if not mine:
            return []

        # Who borrowed what (each member counted once per item)
        borrowed_by: dict[str, set[str]] = defaultdict(set)
        for loan in loans:
            borrowed_by[loan.member.user_id].add(loan.item.item_id)
        borrowed_by.pop(member.user_id, None)

        # together[y][x] = how many other members borrowed both y and x (x is one of mine)
        together: dict[str, Counter[str]] = defaultdict(Counter)
        for their_items in borrowed_by.values():
            shared = their_items & mine.keys()
            for y in their_items - mine.keys():
                for x in shared:
                    together[y][x] += 1

        results = []
        for candidate in candidates:
            counts = together.get(candidate.item_id)
            if counts:
                x, _ = counts.most_common(1)[0]
                results.append(Recommendation(
                    candidate, float(sum(counts.values())),
                    f"Members who borrowed {mine[x].title} also borrowed this"))
        return results


class PopularityStrategy(RecommendationStrategy):
    """The most borrowed items. Needs no history, so it is the fallback for new members."""

    def recommend(self, member: Member, candidates: list[LibraryItem],
                  loans: list[Loan]) -> list[Recommendation]:
        times = Counter(loan.item.item_id for loan in loans)
        results = []
        for candidate in candidates:
            n = times[candidate.item_id]
            if n:
                label = "once" if n == 1 else f"{n} times"
                results.append(Recommendation(candidate, float(n), f"Popular: borrowed {label}"))
        return results


class Recommender:
    """Combines the scores of several strategies into one ranked list of suggestions.

    The library rules for what may be suggested live here, in one place: never an
    item the member has borrowed or is waiting for, a withdrawn item, or an item
    they may not borrow.
    """

    def __init__(self, strategies: Iterable[RecommendationStrategy],
                 fallback: RecommendationStrategy | None = None) -> None:
        """strategies are combined; fallback is used when they find too little."""
        self._strategies: list[RecommendationStrategy] = list(strategies)
        self._fallback: RecommendationStrategy | None = fallback

    @property
    def strategies(self) -> list[RecommendationStrategy]:
        """The combined strategies (a copy)."""
        return list(self._strategies)

    def add_strategy(self, strategy: RecommendationStrategy) -> None:
        """Add another way of scoring items."""
        self._strategies.append(strategy)

    def candidates(self, member: Member, items: Iterable[LibraryItem],
                   reserved_ids: Iterable[str] = ()) -> list[LibraryItem]:
        """Items that may be suggested to this member, sorted by title.

        reserved_ids: items the member is already on the waitlist for.
        """
        skip = {item.item_id for item in RecommendationStrategy.borrowed_items(member)}
        skip.update(reserved_ids)
        return sorted(
            item for item in items
            if not item.withdrawn
            and item.item_id not in skip
            and item.can_be_borrowed_by(member)
        )

    def recommend(self, member: Member, items: Iterable[LibraryItem], loans: list[Loan],
                  reserved_ids: Iterable[str] = (), limit: int = 3) -> list[Recommendation]:
        """The best `limit` suggestions for the member, best first, each with a reason.

        Each strategy's scores are scaled to 0..1 (its best item gets 1) and multiplied
        by its weight, then added up. The reason comes from the strategy that
        contributed most to that item. If this gives fewer than `limit` items (always
        the case for a member with no history), the fallback fills the rest.
        """
        candidates = self.candidates(member, items, reserved_ids)
        totals: dict[LibraryItem, float] = defaultdict(float)
        reasons: dict[LibraryItem, tuple[float, str]] = {}

        for strategy in self._strategies:
            results = strategy.recommend(member, candidates, loans)
            top = max((r.score for r in results), default=0.0)
            if top <= 0:
                continue
            for r in results:
                part = strategy.weight * r.score / top
                totals[r.item] += part
                if part > reasons.get(r.item, (0.0, ""))[0]:
                    reasons[r.item] = (part, r.reason)

        # Best score first; equal scores in title order (LibraryItem.__lt__)
        ranked = sorted(totals, key=lambda item: (-totals[item], item))[:limit]
        picks = [Recommendation(item, totals[item], reasons[item][1]) for item in ranked]

        if len(picks) < limit and self._fallback is not None:
            chosen = {p.item for p in picks}
            extra = self._fallback.recommend(
                member, [c for c in candidates if c not in chosen], loans)
            extra.sort(key=lambda r: (-r.score, r.item))
            picks += extra[:limit - len(picks)]
        return picks
