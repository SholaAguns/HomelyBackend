from typing import Optional
from property.services.interface import IPropertyCreationService
from property.services.rightmove_service import RightmoveService

TEXT_SERVICES = [
]

URL_SERVICES = [
    RightmoveService,
    # Future services: HTMLParserService, ZooplaService, etc.
]


def property_creation_service_factory(
    input_data: str,
    input_type: str
) -> Optional[IPropertyCreationService]:
   
    if input_type == "text":
        services = TEXT_SERVICES
    elif input_type == "url":
        services = URL_SERVICES
    else:
        return None

    for service_class in services:
        service = service_class()
        if service.can_handle(input_data):
            return service

    return None
 