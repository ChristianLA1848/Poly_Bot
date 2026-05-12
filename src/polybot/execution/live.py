import inspect
from types import SimpleNamespace
from typing import Any

from polybot.models import Decision


def _build_order_args(
    *,
    token_id: str,
    price: float,
    size: float,
) -> Any:
    try:
        from py_clob_client_v2 import OrderArgs
        from py_clob_client_v2.order_builder.constants import BUY
    except ImportError:
        return SimpleNamespace(token_id=token_id, price=price, size=size, side="BUY")

    return OrderArgs(token_id=token_id, price=price, size=size, side=BUY)


async def _resolve_response(response: Any) -> Any:
    if inspect.isawaitable(response):
        return await response
    return response


class LiveExecutionEngine:
    def __init__(self, clob_client: Any) -> None:
        self.clob_client = clob_client

    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        create_and_post_order = getattr(self.clob_client, "create_and_post_order", None)
        if create_and_post_order is None:
            raise RuntimeError("clob_client is missing create_and_post_order")

        if not 0 < decision.target_price < 1:
            raise ValueError("target_price must be greater than 0 and less than 1")
        if stake <= 0:
            raise ValueError("stake must be greater than 0")

        shares = round(stake / decision.target_price, 6)
        order_args = _build_order_args(
            token_id=decision.token_id,
            price=decision.target_price,
            size=shares,
        )
        try:
            response = create_and_post_order(order_args)
        except TypeError:
            response = create_and_post_order(
                token_id=decision.token_id,
                price=decision.target_price,
                size=shares,
                side="BUY",
            )

        return {
            "mode": "live",
            "status": "submitted",
            "market_id": decision.market_id,
            "token_id": decision.token_id,
            "price": decision.target_price,
            "stake": stake,
            "shares": shares,
            "response": await _resolve_response(response),
        }

    async def cancel_all(self) -> dict[str, Any]:
        cancel_all = getattr(self.clob_client, "cancel_all", None)
        if cancel_all is None:
            raise RuntimeError("clob_client is missing cancel_all")

        response = await _resolve_response(cancel_all())
        return {"mode": "live", "status": "cancelled", "response": response}
