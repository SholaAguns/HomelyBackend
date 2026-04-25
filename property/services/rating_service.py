"""
Stage 3 Rating System - Core calculation logic
Implements 5 scoring strategies and rating aggregation
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


        # Step 2-5: Calculate rating for all enabled criteria
        weighted_scores = []
        weights = []
        breakdown = {}

        # Process only enabled criteria
        criteria_list = list(self.rating_criteria.criteria.filter(enabled=True))
        logger.debug(f"🎯 RATING: Processing {len(criteria_list)} enabled criteria")

        for criterion in criteria_list:
            try:
                logger.debug(f"📊 RATING: Processing criterion '{criterion.name}' (weight: {criterion.weight})")

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



    def _extract_from_property(self, criterion) -> Any:
        """Extract value from property field"""
        logger.debug(f"🏠 EXTRACT: Getting property field '{criterion.field_name}'")
        if not criterion.field_name:
            raise ValueError(f"Missing field_name for property source: {criterion.name}")

        value = getattr(self.property, criterion.field_name)
        logger.debug(f"🏠 EXTRACT: Retrieved value: {value}")
        return value

    def _extract_from_context_report(self, criterion, data_path) -> Any:
        """Extract value from context data"""
        logger.debug(f"📍 EXTRACT: Getting context data from field '{criterion.field_name}'")
        if not criterion.field_name:
            raise ValueError(f"Missing field_name for context source: {criterion.name}")

        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name=criterion.field_name)
            logger.debug(f"📍 EXTRACT: Context data status: {context_data.status}")

            if context_data.status != 'COMPLETE':
                raise ValueError(f"Context data not available: {criterion.field_name}")


            # Navigate JSON path
            data = context_data.data
            if data_path:
                logger.debug(f"📍 EXTRACT: Navigating path: {data_path}")
                for key in data_path.split('.'):
                    data = data[key]

            logger.debug(f"📍 EXTRACT: Retrieved value: {data}")
            return data

        except ContextData.DoesNotExist:
            logger.error(f"📍 EXTRACT: Context data not found for field: {criterion.field_name}")
            raise ValueError(f"Context data not found: {criterion.field_name}")


    def extract_raw_value(self, criterion) -> Any:
        """Extract raw value for a criterion without scoring"""
        if criterion.source == 'property':
            return self._extract_from_property(criterion)
        elif criterion.source == 'context_report':
            # For context data, need to know the path - use field_name as path
            return self._extract_from_context_report(criterion, criterion.field_name)
        else:
            raise ValueError(f"Unsupported criterion source: {criterion.source}")

    def score_criterion(self, criterion) -> Tuple[Any, Decimal]:
        field = (criterion.field_name or criterion.name).lower()

        logger.debug(f"🎯 SCORE: Determining scoring method for field '{field}'")

        if 'price' in field:
            return self._score_price(criterion)
        elif 'bathroom' in field:
            return self._score_bathrooms(criterion)
        elif 'bedroom' in field:
            return self._score_bedrooms(criterion)
        elif 'saved_locations' in field:
            return self._score_saved_location_distance(criterion)
        elif 'poi' in field:
            return self._score_poi_distance(criterion)
        elif 'council' in field or 'tax' in field:
            return self._score_council_tax(criterion)
        elif 'crime' in field:
            return self._score_crime(criterion)
        elif 'mobile' in field:
            return self._score_mobile(criterion)
        elif 'broadband' in field:
            return self._score_broadband(criterion)
        else:
            raise ValueError(f"No scoring function for criterion with name: {field}")

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

        value = self._extract_from_property(criterion)

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

        value = self._extract_from_property(criterion)

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

        value = self._extract_from_property(criterion)

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

    def _score_saved_location_distance(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"📍 DISTANCE: Scoring criterion '{criterion.name}'")

        if not criterion.saved_location_uuid:
            raise ValueError("Mising saved_location_id required for distance rating")

        target_location_id = criterion.saved_location_uuid

        # Get saved_locations ContextData
        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name='saved_locations')

            if context_data.status != 'COMPLETE':
                raise ValueError(f"SavedLocation context data not available: {context_data.status}")

            # Find distance for this location in the data
            distances = context_data.data.get('distances', [])
            for distance_data in distances:
                logger.debug(f"📍 DISTANCE: Checking distance data with name {distance_data['location_name']} and uuid {distance_data['location_uuid']}")
                if distance_data['location_uuid'] == str(target_location_id):
                    distance_km = distance_data['distance_km']
                    logger.debug(f"📍 DISTANCE: Found distance = {distance_km} km")
                    return self._score_distance(distance_km)

            # If location not found in context data
            raise ValueError(f"Distance to saved_location_id={target_location_id} not found in context data")

        except ContextData.DoesNotExist:
            logger.error(f"📍 DISTANCE: SavedLocation context data not found")
            raise ValueError("SavedLocation context data not found. Ensure Stage 2 has been completed.")


    def _score_poi_distance(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"📍 DISTANCE: Scoring criterion '{criterion.name}'")
        if not criterion.poi_category:
            raise ValueError("Missing poi_category required for POI distance rating")

        # Get saved_locations ContextData
        from property.models import ContextData
        try:
            context_data = self.property.context_data.get(service_name='poi')

            if context_data.status != 'COMPLETE':
                raise ValueError(f"POI context data not available: {context_data.status}")

            # Find distance for this poi location in the data
            places_by_category = context_data.data.get('poi_types', {})
            logger.debug(f"📍 POI: Available categories: {list(places_by_category.keys())}")
            logger.debug(f"📍 POI: Looking for category: {criterion.poi_category}")
            places = places_by_category[criterion.poi_category]



            if not places:
                raise ValueError(f"Distance to place of interest={criterion.poi_category} for property {self.property.uuid}  not found in context data")

            nearest_place = min(places, key=lambda p: p['straight_distance_km'] or float('inf'))

            distance_km = nearest_place['straight_distance_km']

            return self._score_distance(distance_km)

        except ContextData.DoesNotExist:
            logger.error(f"📍 DISTANCE: SavedLocation context data not found")
            raise ValueError("SavedLocation context data not found. Ensure Stage 2 has been completed.")

    @staticmethod
    def _score_distance(value) -> Tuple[Any, Decimal]:

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

        value = self._extract_from_context_report(criterion, 'band')

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

        value = self._extract_from_context_report(criterion, 'crime_rating')

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

        value = self._extract_from_context_report(criterion, "scores.overall_coverage")

        logger.debug(f"📱 MOBILE: Overall coverage score = {value}")
        score = Decimal(str(round(float(value), 2)))
        return value, score

    def _score_broadband(self, criterion) -> Tuple[Any, Decimal]:
        logger.debug(f"🌐 BROADBAND: Scoring criterion '{criterion.name}'")

        value = self._extract_from_context_report(criterion, "max_download_mbps")

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



def calculate_and_persist_rating(property_id: int) -> Dict:
    from property.models import Property, CriterionScore

    logger.info(f"💾 PERSIST: Starting rating calculation and persistence for property_id={property_id}")

    property_obj = Property.objects.get(id=property_id)

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
