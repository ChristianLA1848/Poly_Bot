from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Position:
    market_id: str
    token_id: str
    stake: float
    shares: float
    entry_price: float
    mark_price: float


class PositionManager:
    def __init__(self) -> None:
        self.positions: dict[str, Position] = {}

    def record_fill(
        self,
        market_id: str,
        token_id: str,
        stake: float,
        shares: float,
        price: float,
    ) -> None:
        self.positions[token_id] = Position(
            market_id=market_id,
            token_id=token_id,
            stake=stake,
            shares=shares,
            entry_price=price,
            mark_price=price,
        )

    def mark_price(self, token_id: str, price: float) -> None:
        position = self.positions.get(token_id)
        if position is None:
            return

        self.positions[token_id] = replace(position, mark_price=price)

    def unrealized_pnl(self) -> float:
        pnl = sum(
            (position.mark_price - position.entry_price) * position.shares
            for position in self.positions.values()
        )
        return round(pnl, 2)

    def open_positions_count(self) -> int:
        return len(self.positions)
