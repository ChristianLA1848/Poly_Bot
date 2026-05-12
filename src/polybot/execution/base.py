from typing import Any, Protocol

from polybot.models import Decision


class ExecutionEngine(Protocol):
    async def place_order(self, decision: Decision, stake: float) -> dict[str, Any]:
        ...

    async def cancel_all(self) -> dict[str, Any]:
        ...
