"""
Crime data service using UK Police API
"""
import requests
import logging
import time
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
        has_postcode_or_coordinates = property_obj.postcode or (property_obj.latitude and property_obj.longitude)

        if not has_postcode_or_coordinates:
            raise ValueError("Property must have postcode or coordinates to retrieve crime data")

        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode sector (first 4 chars) for broader sharing"""
        if property_obj.postcode:
            postcode_sector = property_obj.postcode.replace(' ', '')[:4].upper()
            cache_key = f"crime:{postcode_sector}"
            logger.debug(f"Crime Service: returning cache key with postcode {cache_key}")
            return cache_key
        lat = round(property_obj.latitude, 4)
        lon = round(property_obj.longitude, 4)
        cache_key = f"crime:{lat}-{lon}"
        logger.debug(f"Crime Service: returning cache key with coordinates {cache_key}")
        return cache_key


    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        self.validate_property_data(property_obj)

        location_id = self._get_location_id(
            property_obj.latitude,
            property_obj.longitude
        )

        if not location_id:
            logger.warning(f"No location ID found for {property_obj.postcode}")
            postcode_sector = property_obj.postcode.replace(' ', '')[:4].upper()
            return {
                'total_crimes': 0,
                'crime_rating': 'Unknown',
                'categories': {},
                'months_analyzed': 0,
                'period': '12 months',
                'data_source': 'UK Police API',
                'postcode_sector': postcode_sector,
                'top_categories': [],
                'error': 'No location data available'
            }

        # Fetch crime data for last 12 months
        crime_result = self._fetch_crimes_by_location(location_id)

        # Aggregate and analyze
        analysis = self._analyze_crime_data(crime_result['crimes'], crime_result['monthly_breakdown'])

        # Add metadata fields
        postcode_sector = property_obj.postcode.replace(' ', '')[:4].upper()
        analysis['period'] = '12 months'
        analysis['data_source'] = 'UK Police API'
        analysis['postcode_sector'] = postcode_sector

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

    def _fetch_crimes_by_location(self, location_id: str, months_range: int = 13) -> Dict[str, Any]:
        all_crimes = []
        monthly_breakdown = []

        # UK Police API allows fetching by month
        # Format: YYYY-MM
        current_date = datetime.now()

        for month in range(1, months_range):
            date = current_date - timedelta(days=30 * month)
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
                crime_count = len(crimes) if crimes else 0

                if crimes:
                    all_crimes.extend(crimes)

                monthly_breakdown.append({
                    'month': date_str,
                    'crime_count': crime_count,
                    'status': 'success'
                })

                time.sleep(0.5)

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    # No data for this month, continue
                    logger.debug(f"No crime data for {date_str}")
                    monthly_breakdown.append({
                        'month': date_str,
                        'crime_count': None,
                        'status': 'failed',
                        'error': 'No data available'
                    })
                    continue
                else:
                    logger.error(f"HTTP error for {date_str}: {e}")
                    monthly_breakdown.append({
                        'month': date_str,
                        'crime_count': None,
                        'status': 'failed',
                        'error': f'HTTP {e.response.status_code}'
                    })
                    continue
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch crimes for {date_str}: {e}")
                monthly_breakdown.append({
                    'month': date_str,
                    'crime_count': None,
                    'status': 'failed',
                    'error': str(e)
                })
                continue

        # Calculate success/failure counts
        successful_months = sum(1 for m in monthly_breakdown if m['status'] == 'success')
        failed_months = len(monthly_breakdown) - successful_months

        # Only raise if ALL months failed
        if successful_months == 0:
            raise Exception("Failed to retrieve crime data for all months")

        return {
            'crimes': all_crimes,
            'monthly_breakdown': monthly_breakdown,
            'successful_months': successful_months,
            'failed_months': failed_months
        }

    def _analyze_crime_data(self, crimes: list, monthly_breakdown: list) -> Dict[str, Any]:
        """
        Analyze crime data and generate statistics.

        Args:
            crimes: List of crime records from API
            monthly_breakdown: List of monthly success/failure records

        Returns:
            Dict with crime analysis and rating
        """
        successful_months = sum(1 for m in monthly_breakdown if m['status'] == 'success')

        if not crimes:
            return {
                'total_crimes': 0,
                'crime_rating': 'Very Low',
                'categories': {},
                'months_analyzed': successful_months,
                'average_per_month': 0,
                'monthly_breakdown': monthly_breakdown
            }

        # Count by category
        categories = {}
        for crime in crimes:
            category = crime.get('category', 'other-crime')
            category_name = self._format_category_name(category)
            categories[category_name] = categories.get(category_name, 0) + 1

        total_crimes = len(crimes)
        # Calculate average based on successful months only
        avg_per_month = total_crimes / successful_months if successful_months > 0 else 0

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
            'months_analyzed': successful_months,
            'average_per_month': round(avg_per_month, 1),
            'top_categories': self._get_top_categories(categories, 5),
            'monthly_breakdown': monthly_breakdown
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
