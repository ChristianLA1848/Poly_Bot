from polybot.config import StakingSection
from polybot.models import Decision


def calculate_stake(
    config: StakingSection,
    decision: Decision,
    max_stake: float,
) -> float:
    if config.mode == "fixed":
        return min(config.fixed_stake, max_stake)

    if config.mode == "fractional_kelly":
        if decision.target_price >= 1.0:
            return 0.0
        kelly = (decision.estimated_probability - decision.target_price) / (
            1.0 - decision.target_price
        )
        stake = max(0.0, kelly) * config.kelly_fraction * max_stake
        return round(min(stake, max_stake), 2)

    if config.mode == "confidence_tiering":
        if decision.confidence >= 0.80:
            stake = config.high_confidence_stake
        elif decision.confidence >= 0.65:
            stake = config.medium_confidence_stake
        else:
            stake = config.low_confidence_stake
        return min(stake, max_stake)

    raise ValueError(f"Unknown staking mode: {config.mode}")
