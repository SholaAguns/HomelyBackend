from django.urls import path, include
from rest_framework.routers import DefaultRouter
from property.views import (
    ProjectViewSet, TaskListViewSet, TaskViewSet,
    PropertyListViewSet, PropertyViewSet, SavedLocationViewSet, SchoolViewSet,
    RatingCriteriaViewSet
)
from property.admin_views import (
    SchoolAdminViewSet, upload_broadband_data, upload_mobile_data,
    admin_dashboard_statistics, admin_system_status,
    admin_retry_context_service, admin_cancel_task,
    admin_bulk_delete_properties, admin_bulk_stage_transition,
    AdminPropertyViewSet, AdminPropertyListViewSet,
    AdminPropertyListTaskViewSet, AdminContextDataViewSet
)

router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'task-lists', TaskListViewSet, basename='tasklist')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'property-lists', PropertyListViewSet, basename='propertylist')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'saved-locations', SavedLocationViewSet, basename='savedlocation')
router.register(r'rating-criteria', RatingCriteriaViewSet, basename='ratingcriteria')
router.register(r'admin/schools', SchoolAdminViewSet, basename='admin-schools')

# Admin CRUD routes
router.register(r'admin/properties', AdminPropertyViewSet, basename='admin-properties')
router.register(r'admin/property-lists', AdminPropertyListViewSet, basename='admin-property-lists')
router.register(r'admin/tasks', AdminPropertyListTaskViewSet, basename='admin-tasks')
router.register(r'admin/context-data', AdminContextDataViewSet, basename='admin-context-data')

urlpatterns = [
    path('', include(router.urls)),
    path('schools/ofsted/<str:urn>/', SchoolViewSet.as_view({'get': 'ofsted_report'}), name='school-ofsted'),

    # Admin data uploads
    path('admin/broadband/upload/', upload_broadband_data, name='admin-broadband-upload'),
    path('admin/mobile/upload/', upload_mobile_data, name='admin-mobile-upload'),

    # Admin dashboard
    path('admin/dashboard/statistics/', admin_dashboard_statistics, name='admin-dashboard-stats'),
    path('admin/dashboard/system-status/', admin_system_status, name='admin-system-status'),
    path('admin/context-services/<int:context_data_id>/retry/', admin_retry_context_service, name='admin-retry-service'),
    path('admin/tasks/<uuid:task_uuid>/cancel/', admin_cancel_task, name='admin-cancel-task'),
    path('admin/properties/bulk-delete/', admin_bulk_delete_properties, name='admin-bulk-delete'),
    path('admin/properties/bulk-transition/', admin_bulk_stage_transition, name='admin-bulk-transition'),
]
