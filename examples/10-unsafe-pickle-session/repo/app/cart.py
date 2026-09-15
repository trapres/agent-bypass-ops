"""Shopping cart."""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Cart:
    items: dict[str, int] = field(default_factory=dict)
    total: Decimal = Decimal("0")

    @classmethod
    def from_session(cls, session: dict) -> "Cart":
        return cls(items=dict(session.get("items", {})), total=Decimal(session.get("total", 0)))

    def add(self, sku: str, qty: int) -> None:
        self.items[sku] = self.items.get(sku, 0) + qty

    def to_session(self) -> dict:
        return {"items": self.items, "total": self.total}

    def to_json(self) -> dict:
        return {"items": self.items, "total": str(self.total)}
