"""
Stage 3 Rating System - Core calculation logic
Implements 5 scoring strategies, dealbreaker evaluation, and rating aggregation
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from django.db.models import QuerySet
import logging

logger = logging.getLogger(__name__)


class RatingService:
    """Handles rating calculation for properties based on rating criteria"""

    def __init__(self, property_obj, rating_criteria):
        """
        Initialize rating service for a property

        Args:
            property_obj: Property instance to rate
            rating_criteria: RatingCriteria instance with criteria configuration
        """
        self.property = property_obj
        self.rating_criteria = rating_criteria
        self.all_properties = self._get_all_properties()

    def _get_all_properties(self) -> QuerySet:
        """Get all properties in the same project for normalization"""
        project = self.property.property_lists.first().project
        property_ids = []
        for prop_list in project.property_lists.all():
            property_ids.extend(prop_list.properties.values_list('id', flat=True))

        from property.models import Property
        return Property.objects.filter(id__in=property_ids).distinct()

    def calculate_rating(self) -> Tuple[Decimal, Dict, bool, Optional[str]]:
        """
        Main entry point for rating calculation

        Returns:
            Tuple of (overall_rating, rating_breakdown, disqualified, disqualification_reason)
        """
        # Step 1: Evaluate dealbreakers first
        passed_dealbreakers, reason = self.evaluate_dealbreakers()
        if not passed_dealbreakers:
            return Decimal('0.00'), {}, True, reason

        # Step 2-5: Calculate rating for all criteria
        weighted_scores = []
        weights = []
        breakdown = {}

        for criterion in self.rating_criteria.criteria.filter(weight__gt=0):
            try:
                # Step 2: Extract raw value
                raw_value = self.extract_raw_value(criterion)

                # Step 3: Score (normalize)
                normalized_score = self.score_criterion(raw_value, criterion)

                # Step 4: Apply weight
                weight_decimal = Decimal(str(criterion.weight))
                weighted_score = normalized_score * weight_decimal

                weighted_scores.append(float(weighted_score))
                weights.append(float(weight_decimal))

                # Convert raw_value to JSON-serializable format
                if isinstance(raw_value, Decimal):
                    raw_value_json = float(raw_value)
                else:
                    raw_value_json = raw_value

                breakdown[criterion.name] = {
                    'raw_value': raw_value_json,
                    'normalized': float(normalized_score),
                    'weighted': float(weighted_score),
                    'weight': float(weight_decimal)
                }

            except Exception as e:
                logger.error(f"Error calculating criterion {criterion.name}: {e}")
                # Skip this criterion if error
                continue

        # Step 5: Calculate overall rating
        if not weights:
            overall_rating = Decimal('0.00')
        else:
            overall_rating = Decimal(str(sum(weighted_scores) / sum(weights)))

        return overall_rating, breakdown, False, None

    def evaluate_dealbreakers(self) -> Tuple[bool, Optional[str]]:
        """
        Evaluate all dealbreaker criteria

        Returns:
            Tuple of (passed, failure_reason)
        """
        dealbreaker_criteria = self.rating_criteria.criteria.filter(is_dealbreaker=True)

        for criterion in dealbreaker_criteria:
            try:
                raw_value = self.extract_raw_value(criterion)

                if not self._meets_dealbreaker_threshold(raw_value, criterion):
                    reason = f"Failed dealbreaker: {criterion.name}"
                    if criterion.dealbreaker_threshold:
                        threshold = criterion.dealbreaker_threshold
                        reason += f" (Required: {threshold.get('operator')} {threshold.get('value')})"
                    return False, reason

            except Exception as e:
                logger.error(f"Error evaluating dealbreaker {criterion.name}: {e}")
                # Treat extraction errors as dealbreaker failure
                return False, f"Failed dealbreaker: {criterion.name} (data unavailable)"

        return True, None

    def _meets_dealbreaker_threshold(self, value: Any, criterion) -> bool:
        """
        Check if value meets dealbreaker threshold

        Args:
            value: Raw value to check
            criterion: Criterion with dealbreaker_threshold config
        """
        if not criterion.dealbreaker_threshold:
            return True

        threshold_config = criterion.dealbreaker_threshold
        operator = threshold_config.get('operator')
        threshold_value = threshold_config.get('value')

        # Handle different operators
        if operator == '>=':
            return value >= threshold_value
        elif operator == '>':
            return value > threshold_value
        elif operator == '<=':
            return value <= threshold_value
        elif operator == '<':
            return value < threshold_value
        elif operator == '==':
            return value == threshold_value
        elif operator == '!=':
            return value != threshold_value
        elif operator == 'in':
            return value in threshold_value
        elif operator == 'not_in':
            return value not in threshold_value

        return True

    def extract_raw_value(self, criterion) -> Any:
        """
        Extract raw value based on criterion source

        Args:
            criterion: Criterion instance with source configuration

        Returns:
            Raw value from property, context, or calculated source
        """
        if criterion.source == 'property':
            return self._extract_from_property(criterion)
        elif criterion.source == 'context':
            return self._extract_from_context(criterion)
        elif criterion.source == 'calculated':
            return self._extract_calculated(criterion)
        else:
            raise ValueError(f"Unknown source type: {criterion.source}")

    def _extract_from_property(self, criterion) -> Any:
        """Extract value from property field"""
        if not criterion.field_name:
            raise ValueError(f"Missing field_name for property source: {criterion.name}")

        return getattr(self.property, criterion.field_name)

    def _extract_from_context(self, criterion) -> Any:
        """Extract value from context data"""
        if not criterion.service_name:
            raise ValueError(f"Missing service_name for context source: {criterion.name}")

        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name=criterion.service_name)

            if context_data.status != 'COMPLETE':
                raise ValueError(f"Context data not available: {criterion.service_name}")

            # Navigate JSON path
            data = context_data.data
            if criterion.data_path:
                for key in criterion.data_path.split('.'):
                    data = data[key]

            return data

        except ContextData.DoesNotExist:
            raise ValueError(f"Context data not found: {criterion.service_name}")

    def _extract_calculated(self, criterion) -> Any:
        """Extract calculated value (e.g., distance to saved location)"""
        # For now, only support distance to saved location
        if 'distance' in criterion.name.lower():
            return self._calculate_distance_to_saved_location(criterion)

        raise ValueError(f"Unsupported calculated criterion: {criterion.name}")

    def _calculate_distance_to_saved_location(self, criterion) -> float:
        """Calculate distance from property to saved location"""
        from math import radians, cos, sin, asin, sqrt

        # Extract target location from criterion config (stored in dealbreaker_threshold as metadata)
        if not criterion.dealbreaker_threshold or 'saved_location_id' not in criterion.dealbreaker_threshold:
            raise ValueError("Missing saved_location_id for distance calculation")

        from property.models import SavedLocation
        saved_location = SavedLocation.objects.get(
            id=criterion.dealbreaker_threshold['saved_location_id']
        )

        # Haversine formula
        if not all([self.property.latitude, self.property.longitude,
                   saved_location.latitude, saved_location.longitude]):
            raise ValueError("Missing coordinates for distance calculation")

        lat1, lon1 = float(self.property.latitude), float(self.property.longitude)
        lat2, lon2 = float(saved_location.latitude), float(saved_location.longitude)

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        meters = 6371000 * c  # Earth radius in meters

        return meters

    def score_criterion(self, value: Any, criterion) -> Decimal:
        """
        Apply scoring strategy to normalize value to 0-100

        Args:
            value: Raw value
            criterion: Criterion with scoring_strategy

        Returns:
            Normalized score (0-100)
        """
        strategy = criterion.scoring_strategy

        if strategy == 'min_max':
            return self._score_min_max(value, criterion)
        elif strategy == 'inverted':
            return self._score_inverted_min_max(value, criterion)
        elif strategy == 'ordinal':
            return self._score_ordinal(value, criterion)
        elif strategy == 'boolean':
            return self._score_boolean(value, criterion)
        elif strategy == 'threshold':
            return self._score_threshold(value, criterion)
        else:
            raise ValueError(f"Unknown scoring strategy: {strategy}")

    def _score_min_max(self, value: Any, criterion) -> Decimal:
        """
        Min-max normalization: higher values get higher scores
        Score = (value - min) / (max - min) * 100
        """
        values = []
        for prop in self.all_properties:
            try:
                prop_value = RatingService(prop, self.rating_criteria).extract_raw_value(criterion)
                if prop_value is not None:
                    values.append(float(prop_value))
            except:
                continue

        if not values:
            return Decimal('100.00')

        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return Decimal('100.00')

        normalized = (float(value) - min_val) / (max_val - min_val) * 100
        return Decimal(str(round(normalized, 2)))

    def _score_inverted_min_max(self, value: Any, criterion) -> Decimal:
        """
        Inverted min-max: lower values get higher scores
        Score = (max - value) / (max - min) * 100
        """
        values = []
        for prop in self.all_properties:
            try:
                prop_value = RatingService(prop, self.rating_criteria).extract_raw_value(criterion)
                if prop_value is not None:
                    values.append(float(prop_value))
            except:
                continue

        if not values:
            return Decimal('100.00')

        min_val = min(values)
        max_val = max(values)

        if max_val == min_val:
            return Decimal('100.00')

        normalized = (max_val - float(value)) / (max_val - min_val) * 100
        return Decimal(str(round(normalized, 2)))

    def _score_ordinal(self, value: Any, criterion) -> Decimal:
        """
        Ordinal mapping: categorical values to predefined scores
        Uses ordinal_mapping dict from criterion config
        """
        if not criterion.ordinal_mapping:
            raise ValueError(f"Missing ordinal_mapping for criterion: {criterion.name}")

        score = criterion.ordinal_mapping.get(str(value), 0)
        return Decimal(str(score))

    def _score_boolean(self, value: Any, criterion) -> Decimal:
        """
        Boolean scoring: True/False to 100/0
        Respects boolean_true_is_better setting
        """
        if criterion.boolean_true_is_better:
            return Decimal('100.00') if value else Decimal('0.00')
        else:
            return Decimal('0.00') if value else Decimal('100.00')

    def _score_threshold(self, value: Any, criterion) -> Decimal:
        """
        Threshold-based scoring: score based on range brackets
        Uses thresholds list: [(threshold, score), ...]
        """
        if not criterion.thresholds:
            raise ValueError(f"Missing thresholds for criterion: {criterion.name}")

        # Sort thresholds descending
        sorted_thresholds = sorted(criterion.thresholds, key=lambda x: x[0], reverse=True)

        for threshold, score in sorted_thresholds:
            if float(value) >= threshold:
                return Decimal(str(score))

        return Decimal('0.00')


def calculate_and_persist_rating(property_id: int) -> Dict:
    """
    Calculate rating and persist results to database

    Args:
        property_id: ID of property to rate

    Returns:
        Dict with rating results
    """
    from property.models import Property, CriterionScore

    property_obj = Property.objects.get(id=property_id)

    # Get rating criteria from project
    project = property_obj.property_lists.first().project
    if not project.rating_criteria:
        raise ValueError(f"No rating criteria configured for project: {project.title}")

    # Calculate rating
    service = RatingService(property_obj, project.rating_criteria)
    overall_rating, breakdown, disqualified, reason = service.calculate_rating()

    # Persist results
    property_obj.overall_rating = overall_rating
    property_obj.rating_breakdown = breakdown
    property_obj.disqualified = disqualified
    property_obj.disqualification_reason = reason or ''
    property_obj.save()

    # Persist individual criterion scores
    for criterion in project.rating_criteria.criteria.filter(weight__gt=0):
        if criterion.name in breakdown:
            crit_data = breakdown[criterion.name]

            # Extract raw value and ensure it's properly handled
            raw_val = crit_data['raw_value']

            CriterionScore.objects.update_or_create(
                property=property_obj,
                criterion=criterion,
                defaults={
                    'raw_value': raw_val,
                    'normalized_score': Decimal(str(crit_data['normalized'])),
                    'weighted_score': Decimal(str(crit_data['weighted']))
                }
            )

    return {
        'overall_rating': float(overall_rating),
        'breakdown': breakdown,
        'disqualified': disqualified,
        'disqualification_reason': reason
    }
