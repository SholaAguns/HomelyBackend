"""
Transformers to convert service response data to match frontend report data models
"""
from property.serializers import (
    PoiReportDataSerializer,
    SchoolsReportDataSerializer,
    CrimeReportDataSerializer,
    BroadbandReportDataSerializer,
    MobileCoverageReportDataSerializer,
    CouncilTaxReportDataSerializer,
)


def transform_poi_data(service_data):
    """
    Transform POI service response to match PoiReportDataSerializer

    Backend: poi_types, types_searched, total_pois_found, search_radius_meters
    Frontend: by_category, categories, total_places, search_radius_km, data_source
    """
    if not service_data:
        return None

    poi_types = service_data.get('poi_types', {})

    # Transform places in each category
    by_category = {}
    for category, places in poi_types.items():
        transformed_places = []
        for place in places:
            transformed_places.append({
                'place_id': place.get('place_id', ''),
                'name': place.get('name', 'Unknown'),
                'address': place.get('address'),
                'latitude': place.get('latitude', 0.0),
                'longitude': place.get('longitude', 0.0),
                'distance_km': place.get('straight_distance_km', 0.0),
                'straight_distance_km': place.get('straight_distance_km'),
                'walking_distance_km': place.get('walking_distance_km'),
                'walking_time_min': place.get('walking_time_min'),
                'driving_distance_km': place.get('driving_distance_km'),
                'driving_time_min': place.get('driving_time_min'),
                'website_url': place.get('website_url') or None,
                'phone_number': place.get('phone_number') or None,
                'google_maps_url': place.get('google_maps_url', ''),
                'rating': place.get('rating'),
                'user_ratings_total': place.get('user_ratings_total'),
            })
        by_category[category] = transformed_places

    transformed = {
        'total_places': service_data.get('total_pois_found', 0),
        'categories': service_data.get('types_searched', []),
        'by_category': by_category,
        'data_source': 'Google Places API',
        'search_radius_km': service_data.get('search_radius_meters', 0) / 1000,
    }

    # Validate through serializer
    serializer = PoiReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_schools_data(service_data):
    """
    Transform Schools service response to match SchoolsReportDataSerializer

    Keep: nursery_schools, primary_schools, secondary_schools, all_through_schools, minimal statistics, note
    Only include school types that were requested
    """
    if not service_data:
        return None

    # Transform statistics - only keep fields that exist (based on requested types)
    backend_stats = service_data.get('statistics', {})
    statistics = {}

    # Only include counts that exist in the backend response
    if 'nursery_count' in backend_stats:
        statistics['nursery_count'] = backend_stats['nursery_count']
        statistics['closest_nursery_km'] = backend_stats.get('closest_nursery_km')

    if 'primary_count' in backend_stats:
        statistics['primary_count'] = backend_stats['primary_count']
        statistics['closest_primary_km'] = backend_stats.get('closest_primary_km')

    if 'secondary_count' in backend_stats:
        statistics['secondary_count'] = backend_stats['secondary_count']
        statistics['closest_secondary_km'] = backend_stats.get('closest_secondary_km')

    if 'all_through_count' in backend_stats:
        statistics['all_through_count'] = backend_stats['all_through_count']

    # Transform schools - only include types that exist
    transformed = {
        'statistics': statistics,
        'note': service_data.get('note'),
    }

    # Only include school lists that exist in the service data
    if 'nursery_schools' in service_data:
        transformed['nursery_schools'] = service_data['nursery_schools']
    if 'primary_schools' in service_data:
        transformed['primary_schools'] = service_data['primary_schools']
    if 'secondary_schools' in service_data:
        transformed['secondary_schools'] = service_data['secondary_schools']
    if 'all_through_schools' in service_data:
        transformed['all_through_schools'] = service_data['all_through_schools']

    # Validate through serializer
    serializer = SchoolsReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_crime_data(service_data):
    """
    Transform Crime service response to match CrimeReportDataSerializer

    Assuming backend already has correct structure, but verify fields match
    """
    if not service_data:
        return None

    transformed = {
        'total_crimes': service_data.get('total_crimes', 0),
        'period': service_data.get('period', ''),
        'crime_rating': service_data.get('crime_rating', ''),
        'top_categories': service_data.get('top_categories', []),
        'data_source': service_data.get('data_source', ''),
        'postcode_sector': service_data.get('postcode_sector', ''),
    }

    # Validate through serializer
    serializer = CrimeReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_broadband_data(service_data):
    """
    Transform Broadband service response to match BroadbandReportDataSerializer

    Assuming backend already has correct structure, but verify fields match
    """
    if not service_data:
        return None

    transformed = {
        'max_download_mbps': service_data.get('max_download_mbps', 0),
        'max_upload_mbps': service_data.get('max_upload_mbps', 0),
        'full_fibre': service_data.get('full_fibre'),
        'data_source': service_data.get('data_source', ''),
        'granularity': service_data.get('granularity', ''),
    }

    # Validate through serializer
    serializer = BroadbandReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_mobile_data(service_data):
    """
    Transform Mobile service response to match MobileCoverageReportDataSerializer

    Ofcom dataset provides aggregate coverage by network count, not per-operator.
    Frontend now displays aggregate coverage data.
    """
    if not service_data:
        return None

    # Get scores and set defaults for missing values
    scores = service_data.get('scores', {})
    if not scores.get('four_g_coverage'):
        scores['four_g_coverage'] = 0
    if not scores.get('five_g_coverage'):
        scores['five_g_coverage'] = 0
    if not scores.get('overall_coverage'):
        scores['overall_coverage'] = 0

    # Build data structure for validation
    transformed = {
        'scores': scores,
        'four_g_coverage': service_data.get('four_g_coverage', {}),
        'data_source': service_data.get('data_source', ''),
        'granularity': service_data.get('granularity', ''),
    }

    # Optional fields
    if 'five_g_coverage_high_confidence' in service_data:
        transformed['five_g_coverage_high_confidence'] = service_data['five_g_coverage_high_confidence']

    if 'laua_name' in service_data:
        transformed['laua_name'] = service_data['laua_name']

    # Validate through serializer
    serializer = MobileCoverageReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_council_tax_data(service_data):
    """
    Transform Council Tax service response to match CouncilTaxReportDataSerializer

    Council tax band data is relatively simple, just pass through with validation
    """
    if not service_data:
        return None

    transformed = {
        'band': service_data.get('band'),
        'band_range': service_data.get('band_range'),
        'local_authority': service_data.get('local_authority'),
        'address': service_data.get('address'),
        'is_exact_match': service_data.get('is_exact_match', True),
        'country': service_data.get('country', 'England'),
        'retrieved_at': service_data.get('retrieved_at'),
    }

    # Validate through serializer
    serializer = CouncilTaxReportDataSerializer(data=transformed)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def transform_context_data(service_name, service_data):
    """
    Main transformer that routes to appropriate service-specific transformer

    Args:
        service_name: One of 'poi', 'schools', 'crime', 'broadband', 'mobile'
        service_data: Raw service response data

    Returns:
        Transformed data matching frontend model
    """
    transformers = {
        'poi': transform_poi_data,
        'schools': transform_schools_data,
        'crime': transform_crime_data,
        'broadband': transform_broadband_data,
        'mobile': transform_mobile_data,
        'council_tax': transform_council_tax_data,
    }

    transformer = transformers.get(service_name)
    if not transformer:
        return service_data  # Return as-is if no transformer

    return transformer(service_data)
