from django.urls import path, include
from rest_framework.routers import DefaultRouter
from property.views import PropertyListViewSet, PropertyViewSet, SavedLocationViewSet
from property.admin_views import SchoolAdminViewSet

router = DefaultRouter()
router.register(r'property-lists', PropertyListViewSet, basename='propertylist')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'saved-locations', SavedLocationViewSet, basename='savedlocation')
router.register(r'admin/schools', SchoolAdminViewSet, basename='admin-schools')

urlpatterns = [
    path('', include(router.urls)),
]
