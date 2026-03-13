"""
Transformers to convert service response data to match frontend report data models
"""


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
                'name': place.get('name'),
                'distance_km': place.get('straight_distance_km'),
                'address': place.get('address'),
                'rating': place.get('rating'),
                'user_ratings_total': place.get('user_ratings_total'),
            })
        by_category[category] = transformed_places

    return {
        'total_places': service_data.get('total_pois_found', 0),
        'categories': service_data.get('types_searched', []),
        'by_category': by_category,
        'data_source': 'Google Places API',
        'search_radius_km': service_data.get('search_radius_meters', 0) / 1000,
    }


def transform_schools_data(service_data):
    """
    Transform Schools service response to match SchoolsReportDataSerializer

    Remove: all_through_schools and extra statistics fields
    Keep: primary_schools, secondary_schools, minimal statistics, note
    """
    if not service_data:
        return None

    # Transform statistics - only keep fields frontend expects
    backend_stats = service_data.get('statistics', {})
    statistics = {
        'primary_count': backend_stats.get('primary_count', 0),
        'secondary_count': backend_stats.get('secondary_count', 0),
        'closest_primary_km': backend_stats.get('closest_primary_km'),
        'closest_secondary_km': backend_stats.get('closest_secondary_km'),
    }

    # Transform schools - assuming they already have correct fields
    # If not, we would transform here

    return {
        'statistics': statistics,
        'primary_schools': service_data.get('primary_schools', []),
        'secondary_schools': service_data.get('secondary_schools', []),
        'note': service_data.get('note'),
    }


def transform_crime_data(service_data):
    """
    Transform Crime service response to match CrimeReportDataSerializer

    Assuming backend already has correct structure, but verify fields match
    """
    if not service_data:
        return None

    return {
        'total_crimes': service_data.get('total_crimes', 0),
        'period': service_data.get('period', ''),
        'crime_rating': service_data.get('crime_rating', ''),
        'top_categories': service_data.get('top_categories', []),
        'data_source': service_data.get('data_source', ''),
        'postcode_sector': service_data.get('postcode_sector', ''),
    }


def transform_broadband_data(service_data):
    """
    Transform Broadband service response to match BroadbandReportDataSerializer

    Assuming backend already has correct structure, but verify fields match
    """
    if not service_data:
        return None

    return {
        'max_download_mbps': service_data.get('max_download_mbps', 0),
        'max_upload_mbps': service_data.get('max_upload_mbps', 0),
        'full_fibre': service_data.get('full_fibre'),
        'data_source': service_data.get('data_source', ''),
        'granularity': service_data.get('granularity', ''),
    }


def transform_mobile_data(service_data):
    """
    Transform Mobile service response to match MobileCoverageReportDataSerializer

    Ofcom dataset provides aggregate coverage by network count, not per-operator.
    Frontend now displays aggregate coverage data.
    """
    if not service_data:
        return None

    # Return the data structure that frontend expects
    result = {
        'scores': service_data.get('scores', {}),
        '4g_coverage': service_data.get('4g_coverage', {}),
        'data_source': service_data.get('data_source', ''),
        'granularity': service_data.get('granularity', ''),
    }

    # Optional fields
    if '5g_coverage_high_confidence' in service_data:
        result['5g_coverage_high_confidence'] = service_data['5g_coverage_high_confidence']

    if 'laua_name' in service_data:
        result['laua_name'] = service_data['laua_name']

    return result


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
    }

    transformer = transformers.get(service_name)
    if not transformer:
        return service_data  # Return as-is if no transformer

    return transformer(service_data)
