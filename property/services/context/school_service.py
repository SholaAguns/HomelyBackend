"""
School rating service using local GIAS database
"""
import logging
from typing import Dict, Any
from decimal import Decimal
from .interface import IContextService

logger = logging.getLogger(__name__)


class SchoolRatingService(IContextService):
    """
    Retrieves nearby schools from local GIAS database with Ofsted ratings.

    Data source: Schools table (imported from GIAS CSV) + Ofsted website scraping
    Cache: 90 days (school data) + 30 days (Ofsted ratings)
    Query: Distance-based radius search

    Includes Ofsted ratings for each school in Stage 2 response.
    """

    CACHE_TTL = 86400 * 90  # 90 days
    DEFAULT_RADIUS_KM = 5  # ~2 miles
    MAX_SCHOOLS_PER_PHASE = 10

    def get_service_name(self) -> str:
        return 'schools'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required location data"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for school search")

        if not property_obj.latitude or not property_obj.longitude:
            raise ValueError("Property must have latitude/longitude for school search")

        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode"""
        return f"schools:{property_obj.postcode}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj) -> Dict[str, Any]:
        """
        Fetch nearby schools from database with Ofsted ratings.

        Returns schools within radius, separated by phase (primary/secondary).
        Includes Ofsted ratings for each school (cached 30 days).
        """
        from property.models import School
        from property.services.location_service import LocationService
        from property.services.ofsted_service import OfstedService

        self.validate_property_data(property_obj)

        prop_lat = float(property_obj.latitude)
        prop_lng = float(property_obj.longitude)

        # Get all open schools (filter by postcode sector for performance)
        postcode_sector = property_obj.postcode.replace(' ', '')[:4].upper()

        # Query schools in same postcode sector first (performance optimization)
        nearby_schools = School.objects.filter(
            establishment_status__icontains='Open',
            postcode__startswith=postcode_sector
        ).exclude(
            latitude__isnull=True
        ).exclude(
            longitude__isnull=True
        )

        # Calculate distances
        schools_with_distance = []

        for school in nearby_schools:
            try:
                distance_km = LocationService.calculate_distance(
                    prop_lat, prop_lng,
                    float(school.latitude), float(school.longitude)
                )

                if distance_km <= self.DEFAULT_RADIUS_KM:
                    schools_with_distance.append({
                        'school': school,
                        'distance_km': distance_km,
                        'distance_miles': distance_km * 0.621371
                    })
            except (ValueError, TypeError) as e:
                logger.warning(f"Error calculating distance for school {school.urn}: {e}")
                continue

        # Sort by distance
        schools_with_distance.sort(key=lambda x: x['distance_km'])

        # Separate by phase
        primary_schools = []
        secondary_schools = []
        all_through_schools = []
        other_schools = []

        for item in schools_with_distance:
            school = item['school']
            phase = school.phase.lower() if school.phase else ''

            # Fetch Ofsted data for this school
            ofsted_data = OfstedService.get_ofsted_report(school.urn)

            # Extract Ofsted info (handle errors gracefully)
            ofsted_info = None
            if 'error' not in ofsted_data:
                ofsted_info = {
                    'overall_rating': ofsted_data.get('overall_rating'),
                    'inspection_date': ofsted_data.get('inspection_date'),
                    'sub_judgements': ofsted_data.get('sub_judgements', {}),
                    'cached': ofsted_data.get('cached', False)
                }
            else:
                # Log error but don't fail
                logger.warning(f"Could not fetch Ofsted for school {school.urn}: {ofsted_data.get('error')}")
                ofsted_info = {
                    'error': ofsted_data.get('error'),
                    'overall_rating': None,
                    'inspection_date': None
                }

            school_data = {
                'urn': school.urn,
                'name': school.name,
                'distance_km': round(item['distance_km'], 2),
                'distance_miles': round(item['distance_miles'], 2),
                'phase': school.phase,
                'type': school.type_of_establishment,
                'postcode': school.postcode,
                'address': school.address_line_1,
                'town': school.town,
                'pupil_count': school.pupil_count,
                'school_capacity': school.school_capacity,
                'gender': school.gender,
                'religious_character': school.religious_character,
                'admissions_policy': school.admissions_policy,
                'age_range': f"{school.statutory_low_age}-{school.statutory_high_age}" if school.statutory_low_age and school.statutory_high_age else None,
                'website': school.website,
                'phone': school.phone,
                'ofsted_url': school.ofsted_url,
                'ofsted': ofsted_info
            }

            if 'primary' in phase:
                primary_schools.append(school_data)
            elif 'secondary' in phase:
                secondary_schools.append(school_data)
            elif 'all through' in phase or 'all-through' in phase:
                all_through_schools.append(school_data)
            else:
                other_schools.append(school_data)

        # Limit results per phase
        primary_schools = primary_schools[:self.MAX_SCHOOLS_PER_PHASE]
        secondary_schools = secondary_schools[:self.MAX_SCHOOLS_PER_PHASE]
        all_through_schools = all_through_schools[:5]

        # Calculate statistics
        total_schools = len(primary_schools) + len(secondary_schools) + len(all_through_schools) + len(other_schools)

        closest_primary_km = primary_schools[0]['distance_km'] if primary_schools else None
        closest_secondary_km = secondary_schools[0]['distance_km'] if secondary_schools else None

        avg_distance_km = None
        if schools_with_distance:
            avg_distance_km = round(
                sum(s['distance_km'] for s in schools_with_distance) / len(schools_with_distance),
                2
            )

        return {
            'primary_schools': primary_schools,
            'secondary_schools': secondary_schools,
            'all_through_schools': all_through_schools,
            'statistics': {
                'total_schools_found': total_schools,
                'primary_count': len(primary_schools),
                'secondary_count': len(secondary_schools),
                'all_through_count': len(all_through_schools),
                'search_radius_km': self.DEFAULT_RADIUS_KM,
                'search_radius_miles': round(self.DEFAULT_RADIUS_KM * 0.621371, 1),
                'closest_primary_km': closest_primary_km,
                'closest_primary_miles': round(closest_primary_km * 0.621371, 2) if closest_primary_km else None,
                'closest_secondary_km': closest_secondary_km,
                'closest_secondary_miles': round(closest_secondary_km * 0.621371, 2) if closest_secondary_km else None,
                'average_distance_km': avg_distance_km,
                'average_distance_miles': round(avg_distance_km * 0.621371, 2) if avg_distance_km else None
            },
            'note': 'Ofsted ratings included for each school (cached 30 days). Full details via /api/schools/ofsted/{urn}/'
        }
