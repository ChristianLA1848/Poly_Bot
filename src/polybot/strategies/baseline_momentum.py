from polybot.models import Decision, DecisionAction, OrderbookSnapshot
from polybot.strategies.base import StrategyContext


def _no_trade(
    strategy: str,
    context: StrategyContext,
    *,
    reason: str,
    reason_code: str,
    estimated_probability: float = 0.5,
    expected_return: float = 0.0,
    market_probability: float | None = None,
    edge: float | None = None,
) -> Decision:
    return Decision(
        strategy=strategy,
        action=DecisionAction.NO_TRADE,
        market_id=context.market.market_id,
        token_id="",
        target_price=0.0,
        estimated_probability=estimated_probability,
        confidence=0.0,
        expected_return=expected_return,
        max_slippage=0.0,
        reason=reason,
        created_at=context.now,
        reason_code=reason_code,
        market_probability=market_probability,
        edge=edge,
    )


def _expected_return(probability: float, book: OrderbookSnapshot) -> float:
    if book.best_ask <= 0:
        return 0.0
    return probability / book.best_ask - 1


def _price_delta(context: StrategyContext) -> float | None:
    if context.reference_start_price <= 0:
        return None
    return (
        context.feed.reference_price - context.reference_start_price
    ) / context.reference_start_price


class BaselineMomentumStrategy:
    name = "baseline_momentum"

    def decide(self, context: StrategyContext) -> Decision:
        delta = _price_delta(context)
        if delta is None:
            return _no_trade(
                self.name,
                context,
                reason="reference start price must be positive",
                reason_code="invalid_reference",
            )

        if abs(delta) < 0.0005:
            return _no_trade(
                self.name,
                context,
                reason="price delta too small",
                reason_code="delta_too_small",
            )

        if delta > 0:
            book = context.up_book
            action = DecisionAction.BUY_UP
        else:
            book = context.down_book
            action = DecisionAction.BUY_DOWN

        estimated_probability = min(0.95, max(0.05, 0.5 + abs(delta) * 40))
        confidence = min(0.99, 0.5 + abs(delta) * 50)
        market_probability = book.best_ask
        edge = estimated_probability - market_probability

        return Decision(
            strategy=self.name,
            action=action,
            market_id=context.market.market_id,
            token_id=book.token_id,
            target_price=book.best_ask,
            estimated_probability=estimated_probability,
            confidence=confidence,
            expected_return=_expected_return(estimated_probability, book),
            max_slippage=0.01,
            reason=f"btc delta {delta:.5f}",
            created_at=context.now,
            reason_code=(
                "momentum_up" if action == DecisionAction.BUY_UP else "momentum_down"
            ),
            market_probability=market_probability,
            edge=edge,
        )
