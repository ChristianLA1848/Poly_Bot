from datetime import UTC, datetime

import pytest

from polybot.execution import LiveExecutionEngine, PaperExecutionEngine
from polybot.models import Decision, DecisionAction


def _decision(target_price: float = 0.25) -> Decision:
    return Decision(
        strategy="test",
        action=DecisionAction.BUY_UP,
        market_id="0xabc",
        token_id="token-up",
        target_price=target_price,
        estimated_probability=0.60,
        confidence=0.75,
        expected_return=0.10,
        max_slippage=0.005,
        reason="test decision",
        created_at=datetime(2026, 5, 12, 21, 0, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_paper_place_order_fills_buy_with_computed_shares():
    engine = PaperExecutionEngine()

    result = await engine.place_order(_decision(target_price=0.25), stake=10.0)

    assert result == {
        "mode": "paper",
        "status": "filled",
        "market_id": "0xabc",
        "token_id": "token-up",
        "price": 0.25,
        "stake": 10.0,
        "shares": 40.0,
    }


@pytest.mark.asyncio
async def test_paper_place_order_uses_zero_shares_for_zero_target_price():
    engine = PaperExecutionEngine()

    result = await engine.place_order(_decision(target_price=0.0), stake=10.0)

    assert result["shares"] == 0.0


@pytest.mark.asyncio
async def test_paper_cancel_all_returns_cancelled_status():
    engine = PaperExecutionEngine()

    result = await engine.cancel_all()

    assert result == {"mode": "paper", "status": "cancelled"}


class KeywordOnlyClobClient:
    def __init__(self) -> None:
        self.orders: list[dict[str, object]] = []

    def create_and_post_order(
        self,
        *,
        token_id: str,
        price: float,
        size: float,
        side: str,
    ) -> dict[str, object]:
        order = {
            "token_id": token_id,
            "price": price,
            "size": size,
            "side": side,
        }
        self.orders.append(order)
        return {"order_id": "live-order-1", **order}

    def cancel_all(self) -> dict[str, object]:
        return {"cancelled": True}


@pytest.mark.asyncio
async def test_live_place_order_calls_sdk_shaped_client_with_order_args():
    class SdkShapedClobClient:
        def __init__(self) -> None:
            self.order_args: object | None = None

        def create_and_post_order(self, order_args: object) -> dict[str, object]:
            self.order_args = order_args
            return {"order_id": "live-order-1"}

    client = SdkShapedClobClient()
    engine = LiveExecutionEngine(client)

    result = await engine.place_order(_decision(target_price=0.30), stake=10.0)

    assert client.order_args is not None
    assert getattr(client.order_args, "token_id") == "token-up"
    assert getattr(client.order_args, "price") == 0.30
    assert getattr(client.order_args, "size") == 33.333333
    assert getattr(client.order_args, "side") == "BUY"
    assert result == {
        "mode": "live",
        "status": "submitted",
        "market_id": "0xabc",
        "token_id": "token-up",
        "price": 0.30,
        "stake": 10.0,
        "shares": 33.333333,
        "response": {"order_id": "live-order-1"},
    }


@pytest.mark.asyncio
async def test_live_place_order_keeps_keyword_fallback_for_simple_clients():
    client = KeywordOnlyClobClient()
    engine = LiveExecutionEngine(client)

    result = await engine.place_order(_decision(target_price=0.30), stake=10.0)

    assert client.orders == [
        {
            "token_id": "token-up",
            "price": 0.30,
            "size": 33.333333,
            "side": "BUY",
        }
    ]
    assert result["shares"] == 33.333333


@pytest.mark.asyncio
async def test_live_place_order_supports_async_client_method():
    class AsyncClobClient:
        def __init__(self) -> None:
            self.order_args: object | None = None

        async def create_and_post_order(self, order_args: object) -> dict[str, object]:
            self.order_args = order_args
            return {"order_id": "async-order-1"}

    client = AsyncClobClient()
    engine = LiveExecutionEngine(client)

    result = await engine.place_order(_decision(target_price=0.40), stake=10.0)

    assert client.order_args is not None
    assert getattr(client.order_args, "size") == 25.0
    assert result == {
        "mode": "live",
        "status": "submitted",
        "market_id": "0xabc",
        "token_id": "token-up",
        "price": 0.40,
        "stake": 10.0,
        "shares": 25.0,
        "response": {"order_id": "async-order-1"},
    }


@pytest.mark.asyncio
async def test_live_cancel_all_calls_injected_client():
    client = KeywordOnlyClobClient()
    engine = LiveExecutionEngine(client)

    result = await engine.cancel_all()

    assert result == {
        "mode": "live",
        "status": "cancelled",
        "response": {"cancelled": True},
    }


@pytest.mark.asyncio
async def test_live_cancel_all_supports_async_client_method():
    class AsyncCancelClobClient:
        async def cancel_all(self) -> dict[str, object]:
            return {"cancelled": True}

    engine = LiveExecutionEngine(AsyncCancelClobClient())

    result = await engine.cancel_all()

    assert result == {
        "mode": "live",
        "status": "cancelled",
        "response": {"cancelled": True},
    }


@pytest.mark.parametrize("target_price", [0.0, -0.1, 1.0, 1.2])
@pytest.mark.asyncio
async def test_live_place_order_rejects_invalid_target_price(target_price: float):
    engine = LiveExecutionEngine(KeywordOnlyClobClient())

    with pytest.raises(ValueError, match="target_price"):
        await engine.place_order(_decision(target_price=target_price), stake=10.0)


@pytest.mark.parametrize("stake", [0.0, -1.0])
@pytest.mark.asyncio
async def test_live_place_order_rejects_invalid_stake(stake: float):
    engine = LiveExecutionEngine(KeywordOnlyClobClient())

    with pytest.raises(ValueError, match="stake"):
        await engine.place_order(_decision(target_price=0.50), stake=stake)


@pytest.mark.asyncio
async def test_live_place_order_raises_when_client_has_no_order_method():
    engine = LiveExecutionEngine(object())

    with pytest.raises(RuntimeError, match="create_and_post_order"):
        await engine.place_order(_decision(), stake=10.0)


@pytest.mark.asyncio
async def test_live_cancel_all_raises_when_client_has_no_cancel_method():
    engine = LiveExecutionEngine(object())

    with pytest.raises(RuntimeError, match="cancel_all"):
        await engine.cancel_all()
