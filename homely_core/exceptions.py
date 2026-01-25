"""
Custom exception handlers for DRF API
"""
import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)


def custom_exception_handler(exc, context):
    """
    Custom exception handler that provides standardized error responses
    and automatic logging for all exceptions.
    """
    # Call DRF's default exception handler first
    response = exception_handler(exc, context)

    if response is not None:
        # Standardize error response format
        custom_response_data = {
            'error': True,
            'status_code': response.status_code,
        }

        # Handle validation errors (400)
        if response.status_code == status.HTTP_400_BAD_REQUEST:
            custom_response_data['message'] = 'Validation error'
            custom_response_data['details'] = response.data

        # Handle other errors
        else:
            # Extract error message
            if isinstance(response.data, dict):
                custom_response_data['message'] = response.data.get('detail', str(exc))
                custom_response_data['details'] = response.data
            else:
                custom_response_data['message'] = str(exc)
                custom_response_data['details'] = response.data

        response.data = custom_response_data

    else:
        # Handle unexpected server errors (500)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        response = Response(
            {
                'error': True,
                'status_code': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': 'Internal server error',
                'details': str(exc) if logger.level == logging.DEBUG else 'An unexpected error occurred'
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    # Log all errors
    if response.status_code >= 500:
        logger.error(f"Server error: {exc}", exc_info=True)
    elif response.status_code >= 400:
        logger.warning(f"Client error: {exc}")

    return response
