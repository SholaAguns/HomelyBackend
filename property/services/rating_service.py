"""
Stage 3 Rating System - Core calculation logic
Implements 5 scoring strategies, dealbreaker evaluation, and rating aggregation
"""
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from django.db.models import QuerySet
import logging
from property.utils.scoring_strategies import (
    score_min_max,
    score_inverted_min_max,
    score_ordinal,
    score_boolean,
    score_threshold
)

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
        logger.debug(f"🎯 RATING: Starting calculation for property {self.property.uuid} ({self.property.title})")
        logger.debug(f"🎯 RATING: Using rating criteria: {self.rating_criteria.name}")
        logger.debug(f"🎯 RATING: Number of properties in comparison set: {self.all_properties.count()}")

        # Step 1: Evaluate dealbreakers first
        logger.debug("🎯 RATING: Step 1 - Evaluating dealbreakers...")
        passed_dealbreakers, reason = self.evaluate_dealbreakers()
        if not passed_dealbreakers:
            logger.warning(f"❌ RATING: Property disqualified - {reason}")
            return Decimal('0.00'), {}, True, reason
        logger.debug("✅ RATING: Passed all dealbreakers")

        # Step 2-5: Calculate rating for all enabled criteria
        weighted_scores = []
        weights = []
        breakdown = {}

        # Process only enabled criteria
        criteria_list = list(self.rating_criteria.criteria.filter(enabled=True))
        logger.debug(f"🎯 RATING: Processing {len(criteria_list)} enabled criteria")

        for criterion in criteria_list:
            try:
                logger.debug(f"📊 RATING: Processing criterion '{criterion.name}' (weight: {criterion.weight}, strategy: {criterion.scoring_strategy})")

                # Step 2 & 3: Extract raw value and score (normalize)
                raw_value, normalized_score = self.score_criterion(criterion)
                logger.debug(f"  → Raw value: {raw_value} (type: {type(raw_value).__name__})")
                logger.debug(f"  → Normalized score: {normalized_score}")

                # Step 4: Apply weight
                weight_decimal = Decimal(str(criterion.weight))
                weighted_score = normalized_score * weight_decimal
                logger.debug(f"  → Weighted score: {weighted_score} (normalized {normalized_score} × weight {weight_decimal})")

                # Only include in weighted calculation if weight > 0
                if weight_decimal > 0:
                    weighted_scores.append(float(weighted_score))
                    weights.append(float(weight_decimal))
                    logger.debug(f"  → Added to weighted calculation (weight > 0)")
                else:
                    logger.debug(f"  → Skipped weighted calculation (weight = 0)")

                # Convert raw_value to JSON-serializable format
                if isinstance(raw_value, Decimal):
                    raw_value_json = float(raw_value)
                else:
                    raw_value_json = raw_value

                # Always include in breakdown regardless of weight
                breakdown[criterion.name] = {
                    'raw_value': raw_value_json,
                    'normalized_score': float(normalized_score),
                    'weighted_score': float(weighted_score),
                    'weight': float(weight_decimal)
                }
                logger.debug(f"✅ RATING: Criterion '{criterion.name}' calculated successfully")

            except Exception as e:
                logger.error(f"❌ RATING: Error calculating criterion '{criterion.name}': {e}", exc_info=True)
                # Skip this criterion if error
                continue

        # Step 5: Calculate overall rating
        logger.debug(f"🎯 RATING: Step 5 - Calculating overall rating...")
        logger.debug(f"  → Total weighted scores: {weighted_scores}")
        logger.debug(f"  → Total weights: {weights}")

        if not weights:
            overall_rating = Decimal('0.00')
            logger.warning("⚠️ RATING: No weights available, overall rating set to 0")
        else:
            overall_rating = Decimal(str(sum(weighted_scores) / sum(weights)))
            logger.debug(f"  → Sum of weighted scores: {sum(weighted_scores)}")
            logger.debug(f"  → Sum of weights: {sum(weights)}")
            logger.debug(f"  → Overall rating: {overall_rating}")

        logger.info(f"✅ RATING: Calculation complete for property {self.property.uuid} - Overall: {overall_rating}")
        return overall_rating, breakdown, False, None

    def evaluate_dealbreakers(self) -> Tuple[bool, Optional[str]]:
        dealbreaker_criteria = self.rating_criteria.criteria.filter(enabled=True, is_dealbreaker=True)
        logger.debug(f"🚫 DEALBREAKER: Found {dealbreaker_criteria.count()} enabled dealbreaker criteria")

        for criterion in dealbreaker_criteria:
            try:
                logger.debug(f"🚫 DEALBREAKER: Evaluating '{criterion.name}'")
                raw_value = self.extract_raw_value(criterion)
                logger.debug(f"  → Value: {raw_value}")
                logger.debug(f"  → Threshold config: {criterion.dealbreaker_threshold}")

                if not self._meets_dealbreaker_threshold(raw_value, criterion):
                    reason = f"Failed dealbreaker: {criterion.name}"
                    if criterion.dealbreaker_threshold:
                        threshold = criterion.dealbreaker_threshold
                        reason += f" (Required: {threshold.get('operator')} {threshold.get('value')})"
                    logger.warning(f"❌ DEALBREAKER: Failed - {reason}")
                    return False, reason

                logger.debug(f"✅ DEALBREAKER: Passed '{criterion.name}'")

            except Exception as e:
                logger.error(f"❌ DEALBREAKER: Error evaluating {criterion.name}: {e}", exc_info=True)
                # Treat extraction errors as dealbreaker failure
                return False, f"Failed dealbreaker: {criterion.name} (data unavailable)"

        return True, None

    def _meets_dealbreaker_threshold(self, value: Any, criterion) -> bool:
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
        logger.debug(f"🏠 EXTRACT: Getting property field '{criterion.field_name}'")
        if not criterion.field_name:
            raise ValueError(f"Missing field_name for property source: {criterion.name}")

        value = getattr(self.property, criterion.field_name)
        logger.debug(f"🏠 EXTRACT: Retrieved value: {value}")
        return value

    def _extract_from_context(self, criterion) -> Any:
        """Extract value from context data"""
        logger.debug(f"📍 EXTRACT: Getting context data from service '{criterion.service_name}'")
        if not criterion.service_name:
            raise ValueError(f"Missing service_name for context source: {criterion.name}")

        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name=criterion.service_name)
            logger.debug(f"📍 EXTRACT: Context data status: {context_data.status}")

            if context_data.status != 'COMPLETE':
                raise ValueError(f"Context data not available: {criterion.service_name}")

            # Navigate JSON path
            data = context_data.data
            if criterion.data_path:
                logger.debug(f"📍 EXTRACT: Navigating path: {criterion.data_path}")
                for key in criterion.data_path.split('.'):
                    data = data[key]

            logger.debug(f"📍 EXTRACT: Retrieved value: {data}")
            return data

        except ContextData.DoesNotExist:
            logger.error(f"📍 EXTRACT: Context data not found for service: {criterion.service_name}")
            raise ValueError(f"Context data not found: {criterion.service_name}")

    def _extract_calculated(self, criterion) -> Any:
        """Extract calculated value (e.g., distance to saved location)"""
        # For now, only support distance to saved location
        if 'distance' in criterion.name.lower():
            return self._get_distance_from_context(criterion)

        raise ValueError(f"Unsupported calculated criterion: {criterion.name}")

    def _get_distance_from_context(self, criterion) -> float:
        if not criterion.dealbreaker_threshold or 'saved_location_id' not in criterion.dealbreaker_threshold:
            raise ValueError("Missing saved_location_id for distance criterion")

        target_location_id = criterion.dealbreaker_threshold['saved_location_id']
        logger.debug(f"📍 DISTANCE: Retrieving distance for saved_location_id={target_location_id}")

        # Get saved_locations ContextData
        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name='saved_locations')

            if context_data.status != 'COMPLETE':
                raise ValueError(f"SavedLocation context data not available: {context_data.status}")

            # Find distance for this location in the data
            distances = context_data.data.get('distances', [])
            for distance_data in distances:
                if distance_data['location_id'] == target_location_id:
                    distance_km = distance_data['distance_km']
                    logger.debug(f"📍 DISTANCE: Found distance = {distance_km} km")
                    return distance_km

            # If location not found in context data
            raise ValueError(f"Distance to saved_location_id={target_location_id} not found in context data")

        except ContextData.DoesNotExist:
            logger.error(f"📍 DISTANCE: SavedLocation context data not found")
            raise ValueError("SavedLocation context data not found. Ensure Stage 2 has been completed.")

    def score_criterion(self, criterion) -> Tuple[Any, Decimal]:
        field = (criterion.field_name or criterion.name).lower()

        logger.debug(f"🎯 SCORE: Determining scoring method for field '{field}'")

        if 'price' in field:
            return self._score_price(criterion)
        elif 'bathroom' in field:
            return self._score_bathrooms(criterion)
        elif 'bedroom' in field:
            return self._score_bedrooms(criterion)
        elif 'distance' in field:
            return self._score_distance(criterion)
        elif 'council' in field or 'tax' in field:
            return self._score_council_tax(criterion)
        elif 'crime' in field:
            return self._score_crime(criterion)
        elif 'mobile' in field:
            return self._score_mobile(criterion)
        elif 'broadband' in field:
            return self._score_broadband(criterion)
        else:
            return self._score_by_strategy(criterion)

    def _get_min_max_values(self, criterion) -> Tuple[float, float]:
        values = []
        for prop in self.all_properties:
            try:
                prop_value = RatingService(prop, self.rating_criteria).extract_raw_value(criterion)
                if prop_value is not None:
                    values.append(float(prop_value))
            except:
                continue

        if not values:
            return (0.0, 0.0)

        return (min(values), max(values))

    def _score_price(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"💰 PRICE: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        min_val = None
        max_val = None

        property_list = self.property.property_lists.first()
        if property_list and property_list.search_criteria:
            search_criteria = property_list.search_criteria
            if search_criteria.price_min:
                min_val = float(search_criteria.price_min)
            if search_criteria.price_max:
                max_val = float(search_criteria.price_max)

            if min_val or max_val:
                logger.debug(f"💰 PRICE: Using search criteria range - min: {min_val}, max: {max_val}")

        if min_val is None and max_val is None:
            logger.debug(f"💰 PRICE: Search criteria not available, calculating from properties")
            min_val, max_val = self._get_min_max_values(criterion)

        if not min_val and not max_val:
            logger.debug(f"💰 PRICE: No values found, returning 100")
            return value, Decimal('100.00')

        if min_val is None:
            min_val = 0.0
        if max_val is None:
            max_val = float(value)

        logger.debug(f"💰 PRICE: Final range - min: {min_val}, max: {max_val}, current: {value}")
        score = score_inverted_min_max(float(value), min_val, max_val)
        return value, score

    def _score_bathrooms(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🚿 BATHROOMS: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        thresholds = [
            (4, 100.0),
            (3, 75.0),
            (2, 50.0),
            (1, 25.0),
            (0, 0.0),
        ]

        logger.debug(f"🚿 BATHROOMS: Value = {value}, using threshold scoring")
        score = score_threshold(float(value), thresholds)
        return value, score

    def _score_bedrooms(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🛏️ BEDROOMS: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        thresholds = [
            (4, 100.0),
            (3, 75.0),
            (2, 50.0),
            (1, 25.0),
            (0, 0.0),
        ]

        logger.debug(f"🛏️ BEDROOMS: Value = {value}, using threshold scoring")
        score = score_threshold(float(value), thresholds)
        return value, score

    def _score_distance(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"📍 DISTANCE: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        thresholds = [
            (1, 100.0),
            (3, 80.0),
            (5, 60.0),
            (10, 40.0),
            (15, 20.0),
            (20, 10.0),
            (0, 0.0),
        ]

        logger.debug(f"📍 DISTANCE: Value = {value} km, using threshold scoring")

        distance_km = float(value)

        for threshold, sc in thresholds:
            if distance_km <= threshold:
                logger.debug(f"📍 DISTANCE: {distance_km} km <= {threshold} km, score = {sc}")
                return value, Decimal(str(sc))

        logger.debug(f"📍 DISTANCE: {distance_km} km > 20 km, score = 0")
        return value, Decimal('0.00')

    def _score_council_tax(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🏛️ COUNCIL_TAX: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        ordinal_mapping = {
            'A': 100,
            'B': 85,
            'C': 70,
            'D': 55,
            'E': 40,
            'F': 25,
            'G': 10,
            'H': 0,
        }

        band = str(value).upper()
        logger.debug(f"🏛️ COUNCIL_TAX: Band = {band}")
        score = score_ordinal(band, ordinal_mapping)
        return value, score

    def _score_crime(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🚨 CRIME: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        ordinal_mapping = {
            'Very Low': 100,
            'Low': 75,
            'Moderate': 50,
            'High': 25,
            'Very High': 0,
            'Unknown': 50,
        }

        rating = str(value)
        logger.debug(f"🚨 CRIME: Rating = {rating}")
        score = score_ordinal(rating, ordinal_mapping)
        return value, score

    def _score_mobile(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"📱 MOBILE: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        logger.debug(f"📱 MOBILE: Overall coverage score = {value}")
        score = Decimal(str(round(float(value), 2)))
        return value, score

    def _score_broadband(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🌐 BROADBAND: Scoring criterion '{criterion.name}'")

        value = self.extract_raw_value(criterion)

        thresholds = [
            (300, 100.0),
            (100, 75.0),
            (30, 50.0),
            (10, 25.0),
            (0, 0.0),
        ]

        logger.debug(f"🌐 BROADBAND: Value = {value} Mbps, using threshold scoring")
        score = score_threshold(float(value), thresholds)
        return value, score

    def _score_by_strategy(self, criterion) -> Tuple[Any, Decimal]:
        value = self.extract_raw_value(criterion)

        strategy = criterion.scoring_strategy
        logger.debug(f"⚙️ STRATEGY: Using {strategy} strategy for '{criterion.name}'")

        if strategy == 'min_max':
            min_val, max_val = self._get_min_max_values(criterion)
            if not min_val and not max_val:
                return value, Decimal('100.00')
            score = score_min_max(float(value), min_val, max_val)
            return value, score

        elif strategy == 'inverted':
            min_val, max_val = self._get_min_max_values(criterion)
            if not min_val and not max_val:
                return value, Decimal('100.00')
            score = score_inverted_min_max(float(value), min_val, max_val)
            return value, score

        elif strategy == 'ordinal':
            score = score_ordinal(value, criterion.ordinal_mapping)
            return value, score

        elif strategy == 'boolean':
            score = score_boolean(value, criterion.boolean_true_is_better)
            return value, score

        elif strategy == 'threshold':
            score = score_threshold(float(value), criterion.thresholds)
            return value, score

        else:
            raise ValueError(f"Unknown scoring strategy: {strategy}")


def calculate_and_persist_rating(property_id: int) -> Dict:
    from property.models import Property, CriterionScore

    logger.info(f"💾 PERSIST: Starting rating calculation and persistence for property_id={property_id}")

    property_obj = Property.objects.get(id=property_id)
    logger.debug(f"💾 PERSIST: Property: {property_obj.uuid} - {property_obj.title}")

    # Get rating criteria from project
    project = property_obj.property_lists.first().project
    logger.debug(f"💾 PERSIST: Project: {project.title}")

    if not project.rating_criteria:
        logger.error(f"💾 PERSIST: No rating criteria configured for project: {project.title}")
        raise ValueError(f"No rating criteria configured for project: {project.title}")

    logger.debug(f"💾 PERSIST: Using rating criteria: {project.rating_criteria.name}")

    # Calculate rating
    logger.debug(f"💾 PERSIST: Initializing RatingService...")
    service = RatingService(property_obj, project.rating_criteria)
    overall_rating, breakdown, disqualified, reason = service.calculate_rating()

    logger.info(f"💾 PERSIST: Calculation complete - Overall: {overall_rating}, Disqualified: {disqualified}")

    # Persist results
    logger.debug(f"💾 PERSIST: Saving results to property...")
    property_obj.overall_rating = overall_rating
    property_obj.rating_breakdown = breakdown
    property_obj.disqualified = disqualified
    property_obj.disqualification_reason = reason or ''
    property_obj.save()
    logger.debug(f"💾 PERSIST: Property saved")

    # Persist individual criterion scores for all enabled criteria
    logger.debug(f"💾 PERSIST: Saving individual criterion scores...")
    criterion_count = 0
    for criterion in project.rating_criteria.criteria.filter(enabled=True):
        if criterion.name in breakdown:
            crit_data = breakdown[criterion.name]

            # Extract raw value and ensure it's properly handled
            raw_val = crit_data['raw_value']

            CriterionScore.objects.update_or_create(
                property=property_obj,
                criterion=criterion,
                defaults={
                    'raw_value': raw_val,
                    'normalized_score': Decimal(str(crit_data['normalized_score'])),
                    'weighted_score': Decimal(str(crit_data['weighted_score']))
                }
            )
            criterion_count += 1
            logger.debug(f"  → Saved score for '{criterion.name}' (weight: {criterion.weight})")

    logger.debug(f"💾 PERSIST: Saved {criterion_count} criterion scores")
    logger.info(f"✅ PERSIST: Rating calculation and persistence complete for property {property_obj.uuid}")

    return {
        'overall_rating': float(overall_rating),
        'breakdown': breakdown,
        'disqualified': disqualified,
        'disqualification_reason': reason
    }
