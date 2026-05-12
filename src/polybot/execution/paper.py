from typing import Any

from polybot.models import Decision


class PaperExecutionEngine:
    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        shares = round(stake / decision.target_price, 6) if decision.target_price > 0 else 0.0
        return {
            "mode": "paper",
            "status": "filled",
            "market_id": decision.market_id,
            "token_id": decision.token_id,
            "price": decision.target_price,
            "stake": stake,
            "shares": shares,
        }

    async def cancel_all(self) -> dict[str, Any]:
        return {"mode": "paper", "status": "cancelled"}
