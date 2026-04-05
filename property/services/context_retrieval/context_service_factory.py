"""
Factory for creating context service instances
"""
from typing import Optional
from .interface import IContextService
from .crime_service import CrimeService
from .school_service import SchoolRatingService
from .broadband_api_service import BroadbandApiService
from .mobile_api_service import MobileApiService
from .poi_service import POIService
from .council_tax_service import CouncilTaxService
from .saved_location_service import SavedLocationService


def context_service_factory(service_name: str) -> Optional[IContextService]:
    """
    Create context service instance by name.

    Args:
        service_name: Service identifier ('crime', 'schools', 'broadband', etc.')

    Returns:
        IContextService instance

    Raises:
        ValueError: If service name is unknown
    """
    services = {
        'crime': CrimeService,
        'schools': SchoolRatingService,
        'broadband': BroadbandApiService,  # Uses API with dataset fallback
        'mobile': MobileApiService,  # Uses API with dataset fallback
        'poi': POIService,
        'council_tax': CouncilTaxService,
        'saved_locations': SavedLocationService,
    }

    service_class = services.get(service_name)
    if not service_class:
        raise ValueError(f"Unknown context service: {service_name}")

    return service_class()
