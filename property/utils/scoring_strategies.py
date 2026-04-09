"""
Scoring strategy functions for rating calculations
Each function normalizes values to 0-100 range
"""
from decimal import Decimal
from typing import Any, List, Tuple
import logging

logger = logging.getLogger(__name__)


def score_min_max(value: float, min_val: float, max_val: float) -> Decimal:
    if max_val == min_val:
        logger.warning(f"📈 MIN_MAX: All values equal, returning 100")
        return Decimal('100.00')

    normalized = (value - min_val) / (max_val - min_val) * 100
    logger.debug(f"📈 MIN_MAX: Normalized score = {normalized}")
    return Decimal(str(round(normalized, 2)))


def score_inverted_min_max(value: float, min_val: float, max_val: float) -> Decimal:
    if max_val == min_val:
        logger.warning(f"📉 INVERTED: All values equal, returning 100")
        return Decimal('100.00')

    normalized = (max_val - value) / (max_val - min_val) * 100
    logger.debug(f"📉 INVERTED: Normalized score = {normalized}")
    return Decimal(str(round(normalized, 2)))


def score_ordinal(value: Any, ordinal_mapping: dict) -> Decimal:
    if not ordinal_mapping:
        raise ValueError("Missing ordinal_mapping")

    score = ordinal_mapping.get(str(value), 0)
    logger.debug(f"🏷️ ORDINAL: Mapped score = {score}")
    return Decimal(str(score))


def score_boolean(value: bool, true_is_better: bool = True) -> Decimal:
    if true_is_better:
        score = Decimal('100.00') if value else Decimal('0.00')
    else:
        score = Decimal('0.00') if value else Decimal('100.00')
    logger.debug(f"✓/✗ BOOLEAN: Score = {score}")
    return score


def score_threshold(value: float, thresholds: List[Tuple[float, float]]) -> Decimal:
    if not thresholds:
        raise ValueError("Missing thresholds")

    # Sort thresholds descending
    sorted_thresholds = sorted(thresholds, key=lambda x: x[0], reverse=True)

    for threshold, score in sorted_thresholds:
        if value >= threshold:
            logger.debug(f"🎚️ THRESHOLD: Value {value} >= {threshold}, score = {score}")
            return Decimal(str(score))

    logger.debug(f"🎚️ THRESHOLD: Value below all thresholds, score = 0")
    return Decimal('0.00')
