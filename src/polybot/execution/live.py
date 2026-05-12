import inspect
from typing import Any

from polybot.models import Decision


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

        size = round(stake / decision.target_price, 6)
        response = await _resolve_response(
            create_and_post_order(
                token_id=decision.token_id,
                price=decision.target_price,
                size=size,
                side="BUY",
            )
        )
        return {"mode": "live", "status": "submitted", "response": response}

    async def cancel_all(self) -> dict[str, Any]:
        cancel_all = getattr(self.clob_client, "cancel_all", None)
        if cancel_all is None:
            raise RuntimeError("clob_client is missing cancel_all")

        response = await _resolve_response(cancel_all())
        return {"mode": "live", "status": "cancelled", "response": response}
