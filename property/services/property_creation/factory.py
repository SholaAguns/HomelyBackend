from typing import Optional
from property.services.property_creation.interface import IPropertyCreationService
from property.services.property_creation.rightmove_service import RightmoveService
from property.services.property_creation.zoopla_service import ZooplaService

TEXT_SERVICES = [
    ZooplaService
]

URL_SERVICES = [
    RightmoveService,
    ZooplaService,
]

HTML_SOURCE_MAP = {
    'rightmove': RightmoveService,
    'zoopla': ZooplaService,
}

HTML_DOMAIN_HINTS = [
    ('rightmove.co.uk', RightmoveService),
    ('zoopla.co.uk', ZooplaService),
]


def property_creation_service_factory(
    input_data: str,
    input_type: str,
    source: str = None,
) -> Optional[IPropertyCreationService]:

    if input_type == "text":
        services = TEXT_SERVICES
    elif input_type == "url":
        services = URL_SERVICES
    elif input_type == "html":
        if source and source in HTML_SOURCE_MAP:
            return HTML_SOURCE_MAP[source]()
        for domain, service_class in HTML_DOMAIN_HINTS:
            if domain in input_data[:2000]:
                return service_class()
        return None
    else:
        return None

    for service_class in services:
        service = service_class()
        if service.can_handle(input_data):
            return service

    return None
 