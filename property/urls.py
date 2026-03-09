from django.urls import path, include
from rest_framework.routers import DefaultRouter
from property.views import PropertyListViewSet, PropertyViewSet, SavedLocationViewSet, SchoolViewSet
from property.admin_views import SchoolAdminViewSet

router = DefaultRouter()
router.register(r'property-lists', PropertyListViewSet, basename='propertylist')
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'saved-locations', SavedLocationViewSet, basename='savedlocation')
router.register(r'admin/schools', SchoolAdminViewSet, basename='admin-schools')

urlpatterns = [
    path('', include(router.urls)),
    path('schools/ofsted/<str:urn>/', SchoolViewSet.as_view({'get': 'ofsted_report'}), name='school-ofsted'),
]
