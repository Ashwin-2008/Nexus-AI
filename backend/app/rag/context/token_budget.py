"""Token budgeting for context construction."""
from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Approximate tokens (~4 characters/token); deliberately conservative."""
    return max(1, len(text or "") // 4)


class TokenBudget:
    def __init__(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("token budget must be positive")
        self.limit = limit
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def fits(self, text: str, *, overhead: int = 0) -> bool:
        return self.used + estimate_tokens(text) + overhead <= self.limit

    def consume(self, text: str, *, overhead: int = 0) -> bool:
        cost = estimate_tokens(text) + overhead
        if self.used + cost > self.limit:
            return False
        self.used += cost
        return True

    def as_dict(self) -> dict[str, int]:
        return {"limit": self.limit, "used": self.used, "remaining": self.remaining}
