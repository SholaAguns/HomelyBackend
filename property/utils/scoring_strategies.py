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
    return Decimal(str(round(normalized, 2)))


def score_inverted_min_max(value: float, min_val: float, max_val: float) -> Decimal:
    if max_val == min_val:
        logger.warning(f"📉 INVERTED: All values equal, returning 100")
        return Decimal('100.00')

    normalized = (max_val - value) / (max_val - min_val) * 100
    return Decimal(str(round(normalized, 2)))


def score_ordinal(value: Any, ordinal_mapping: dict) -> Decimal:
    if not ordinal_mapping:
        raise ValueError("Missing ordinal_mapping")

    score = ordinal_mapping.get(str(value), 0)
    return Decimal(str(score))


def score_boolean(value: bool, true_is_better: bool = True) -> Decimal:
    if true_is_better:
        score = Decimal('100.00') if value else Decimal('0.00')
    else:
        score = Decimal('0.00') if value else Decimal('100.00')
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
    return Decimal('0.00')

def score_straight_distance(value) -> Tuple[Any, Decimal]:
    thresholds = [
        (1, 100.0),
        (3, 80.0),
        (5, 60.0),
        (10, 40.0),
        (15, 20.0),
        (20, 10.0),
        (30, 5.0),
        (0, 0.0),
    ]

    distance_km = float(value)

    for threshold, sc in thresholds:
        if distance_km <= threshold:
            logger.debug(f"📍 DISTANCE: {distance_km} km <= {threshold} km, score = {sc}")
            return value, Decimal(str(sc))

    return value, Decimal('0.00')


def score_walking_time(value) -> Tuple[Any, Decimal]:

    thresholds = [
        (5, 100.0),
        (10, 80.0),
        (15, 60.0),
        (20, 40.0),
        (25, 20.0),
        (30, 10.0),
        (0, 0.0),
    ]

    distance_min = float(value)

    for threshold, sc in thresholds:
        if distance_min <= threshold:
            logger.debug(f"📍 WALKING Time:: {distance_min} min <= {threshold} min, score = {sc}")
            return value, Decimal(str(sc))

    return value, Decimal('0.00')

def score_driving_time(value) -> Tuple[Any, Decimal]:

    thresholds = [
        (10, 100.0),
        (20, 80.0),
        (30, 60.0),
        (45, 40.0),
        (60, 20.0),
        (90, 10.0),
        (120, 5.0),
        (0, 0.0),
    ]

    distance_min = float(value)

    for threshold, sc in thresholds:
        if distance_min <= threshold:
            logger.debug(f"📍 Driving Time:: {distance_min} min <= {threshold} min, score = {sc}")
            return value, Decimal(str(sc))

    return value, Decimal('0.00')
