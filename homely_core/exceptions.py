"""
Custom exception handlers for DRF API
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

_STATUS_ERROR_MAP = {
    status.HTTP_400_BAD_REQUEST: ('VALIDATION_ERROR', 'One or more fields are invalid.'),
    status.HTTP_401_UNAUTHORIZED: ('AUTHENTICATION_REQUIRED', 'Authentication required.'),
    status.HTTP_403_FORBIDDEN: ('PERMISSION_DENIED', 'You do not have permission to do this.'),
    status.HTTP_404_NOT_FOUND: ('NOT_FOUND', 'The requested resource was not found.'),
    status.HTTP_409_CONFLICT: ('CONFLICT', 'This action conflicts with existing data.'),
    status.HTTP_429_TOO_MANY_REQUESTS: ('RATE_LIMITED', 'Too many requests. Please try again later.'),
    status.HTTP_500_INTERNAL_SERVER_ERROR: ('SERVER_ERROR', 'Something went wrong. Please try again.'),
}


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides standardized error responses
    and automatic logging for all exceptions.
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_code, safe_message = _STATUS_ERROR_MAP.get(
            response.status_code,
            ('ERROR', 'An unexpected error occurred.')
        )

        custom_response_data = {
            'error': True,
            'status_code': response.status_code,
            'error_code': error_code,
            'message': safe_message,
        }

        if response.status_code == status.HTTP_400_BAD_REQUEST:
            custom_response_data['field_errors'] = response.data

        response.data = custom_response_data

    else:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        response = Response(
            {
                'error': True,
                'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'error_code': 'SERVER_ERROR',
                'message': 'Something went wrong. Please try again.',
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    if response.status_code >= 500:
        logger.error(f"Server error: {exc}", exc_info=True)
    elif response.status_code >= 400:
        logger.warning(f"Client error: {exc}")

    return response
