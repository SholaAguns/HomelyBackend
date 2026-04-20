from functools import wraps
from rest_framework.response import Response
from rest_framework import status


def get_project_from_object(obj):
    """Extract project from various object types"""
    if hasattr(obj, 'project'):
        return obj.project
    elif hasattr(obj, 'property_lists'):
        prop_list = obj.property_lists.first()
        return prop_list.project if prop_list else None
    return obj


def check_project_owner(user, project):
    """Check if user is project owner"""
    return project.owner == user


def check_project_contributor(user, project):
    """Check if user is owner or contributor"""
    return project.owner == user or project.contributors.filter(id=user.id).exists()


def require_project_owner(get_object_func=None):
    """
    Decorator to require project owner permission.

    Usage:
        @require_project_owner()
        def my_action(self, request, uuid=None):
            ...

    Or specify custom object getter:
        @require_project_owner(lambda self: self.get_some_object())
        def my_action(self, request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(self, request, *args, **kwargs):
            if get_object_func:
                obj = get_object_func(self)
            else:
                obj = self.get_object()

            project = get_project_from_object(obj)

            if not project:
                return Response(
                    {'error': 'Project not found for this resource.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not check_project_owner(request.user, project):
                return Response(
                    {'error': 'Only the project owner can perform this action.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            return view_func(self, request, *args, **kwargs)

        return wrapped_view
    return decorator


def require_project_contributor(get_object_func=None):
    """
    Decorator to require project owner or contributor permission.

    Usage:
        @require_project_contributor()
        def my_action(self, request, uuid=None):
            ...

    Or specify custom object getter:
        @require_project_contributor(lambda self: self.get_some_object())
        def my_action(self, request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(self, request, *args, **kwargs):
            if get_object_func:
                obj = get_object_func(self)
            else:
                obj = self.get_object()

            project = get_project_from_object(obj)

            if not project:
                return Response(
                    {'error': 'Project not found for this resource.'},
                    status=status.HTTP_404_NOT_FOUND
                )

            if not check_project_contributor(request.user, project):
                return Response(
                    {'error': 'Only owners and contributors can perform this action.'},
                    status=status.HTTP_403_FORBIDDEN
                )

            return view_func(self, request, *args, **kwargs)

        return wrapped_view
    return decorator
