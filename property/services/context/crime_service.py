"""
Crime data service using UK Police API
"""
import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from .interface import IContextService

logger = logging.getLogger(__name__)


class CrimeService(IContextService):
    """
    Retrieves crime statistics from UK Police API.

    API: https://data.police.uk/api/
    Rate limit: 15 requests/second with burst of 30
    Cost: FREE
    Cache: 30 days by postcode sector
    """

    BASE_URL = "https://data.police.uk/api"
    CACHE_TTL = 86400 * 30  # 30 days

    def get_service_name(self) -> str:
        return 'crime'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has postcode and coordinates"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for crime data")

        if not property_obj.latitude or not property_obj.longitude:
            raise ValueError("Property must have latitude/longitude for crime data")

        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode sector (first 4 chars) for broader sharing"""
        postcode_sector = property_obj.postcode.replace(' ', '')[:4].upper()
        return f"crime:{postcode_sector}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj) -> Dict[str, Any]:
        """
        Fetch crime data from UK Police API.

        Retrieves last 12 months of crime at property location.
        Aggregates by crime category.

        Returns:
            Dict with crime statistics and breakdown by category
        """
        self.validate_property_data(property_obj)

        # Get location ID first
        location_id = self._get_location_id(
            property_obj.latitude,
            property_obj.longitude
        )

        if not location_id:
            logger.warning(f"No location ID found for {property_obj.postcode}")
            return {
                'total_crimes': 0,
                'crime_rating': 'Unknown',
                'categories': {},
                'months_analyzed': 0,
                'error': 'No location data available'
            }

        # Fetch crime data for last 12 months
        crime_data = self._fetch_crimes_by_location(location_id)

        # Aggregate and analyze
        analysis = self._analyze_crime_data(crime_data)

        return analysis

    def _get_location_id(self, lat: float, lng: float) -> str:
        """
        Get location ID for coordinates.

        The Police API requires a location_id which is obtained
        from the locate-neighbourhood endpoint.
        """
        try:
            url = f"{self.BASE_URL}/locate-neighbourhood"
            params = {'q': f"{lat},{lng}"}

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            force = data.get('force')
            neighbourhood = data.get('neighbourhood')

            if force and neighbourhood:
                # Get location ID from neighbourhood
                return self._get_neighbourhood_location(force, neighbourhood)

            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get location ID: {e}")
            raise

    def _get_neighbourhood_location(self, force: str, neighbourhood: str) -> str:
        """Get the location ID from neighbourhood boundary"""
        try:
            url = f"{self.BASE_URL}/{force}/{neighbourhood}/boundary"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            boundary = response.json()
            if boundary and len(boundary) > 0:
                # Use center point of boundary
                lats = [float(p['latitude']) for p in boundary]
                lngs = [float(p['longitude']) for p in boundary]
                center_lat = sum(lats) / len(lats)
                center_lng = sum(lngs) / len(lngs)
                return f"{center_lat},{center_lng}"

            return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get neighbourhood location: {e}")
            return None

    def _fetch_crimes_by_location(self, location_id: str, months: int = 12) -> list:
        """
        Fetch crime data for multiple months.

        Args:
            location_id: Location identifier (lat,lng format)
            months: Number of months to retrieve (default 12)

        Returns:
            List of crime records
        """
        all_crimes = []

        # UK Police API allows fetching by month
        # Format: YYYY-MM
        current_date = datetime.now()

        for i in range(months):
            date = current_date - timedelta(days=30 * i)
            date_str = date.strftime('%Y-%m')

            try:
                url = f"{self.BASE_URL}/crimes-at-location"
                params = {
                    'lat': location_id.split(',')[0],
                    'lng': location_id.split(',')[1],
                    'date': date_str
                }

                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()

                crimes = response.json()
                if crimes:
                    all_crimes.extend(crimes)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # No data for this month, continue
                    logger.debug(f"No crime data for {date_str}")
                    continue
                else:
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch crimes for {date_str}: {e}")
                # Continue with other months
                continue

        return all_crimes

    def _analyze_crime_data(self, crimes: list) -> Dict[str, Any]:
        """
        Analyze crime data and generate statistics.

        Args:
            crimes: List of crime records from API

        Returns:
            Dict with crime analysis and rating
        """
        if not crimes:
            return {
                'total_crimes': 0,
                'crime_rating': 'Low',
                'categories': {},
                'months_analyzed': 12,
                'average_per_month': 0
            }

        # Count by category
        categories = {}
        for crime in crimes:
            category = crime.get('category', 'other-crime')
            category_name = self._format_category_name(category)
            categories[category_name] = categories.get(category_name, 0) + 1

        total_crimes = len(crimes)
        avg_per_month = total_crimes / 12

        # Determine rating based on average crimes per month
        # These thresholds are approximate - adjust based on UK statistics
        if avg_per_month < 5:
            rating = 'Very Low'
        elif avg_per_month < 15:
            rating = 'Low'
        elif avg_per_month < 30:
            rating = 'Moderate'
        elif avg_per_month < 50:
            rating = 'High'
        else:
            rating = 'Very High'

        return {
            'total_crimes': total_crimes,
            'crime_rating': rating,
            'categories': categories,
            'months_analyzed': 12,
            'average_per_month': round(avg_per_month, 1),
            'top_categories': self._get_top_categories(categories, 5)
        }

    def _format_category_name(self, category: str) -> str:
        """Format API category to readable name"""
        category_map = {
            'all-crime': 'All crime',
            'anti-social-behaviour': 'Anti-social behaviour',
            'bicycle-theft': 'Bicycle theft',
            'burglary': 'Burglary',
            'criminal-damage-arson': 'Criminal damage and arson',
            'drugs': 'Drugs',
            'other-theft': 'Other theft',
            'possession-of-weapons': 'Possession of weapons',
            'public-order': 'Public order',
            'robbery': 'Robbery',
            'shoplifting': 'Shoplifting',
            'theft-from-the-person': 'Theft from the person',
            'vehicle-crime': 'Vehicle crime',
            'violent-crime': 'Violence and sexual offences',
            'other-crime': 'Other crime'
        }
        return category_map.get(category, category.replace('-', ' ').title())

    def _get_top_categories(self, categories: dict, limit: int = 5) -> list:
        """Get top N crime categories by count"""
        sorted_categories = sorted(
            categories.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return [
            {'category': cat, 'count': count}
            for cat, count in sorted_categories[:limit]
        ]
