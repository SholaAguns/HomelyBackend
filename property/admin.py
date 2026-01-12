from django.contrib import admin
from .models import (
    PropertyList, Property, ContextOptions, ContextData,
    RatingCriteria, Criterion, CriterionScore, SavedLocation,
    StateTransitionLog
)


@admin.register(PropertyList)
class PropertyListAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'state', 'created_at')
    list_filter = ('state', 'created_at')
    search_fields = ('title', 'owner__username', 'owner__email')
    readonly_fields = ('state', 'created_at', 'updated_at')


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'postcode', 'price', 'bedrooms', 'state', 'created_at')
    list_filter = ('state', 'created_at', 'bedrooms', 'bathrooms')
    search_fields = ('title', 'postcode', 'address_line_1')
    readonly_fields = ('state', 'normalized_address', 'overall_rating', 'created_at', 'updated_at')


@admin.register(ContextOptions)
class ContextOptionsAdmin(admin.ModelAdmin):
    list_display = ('property_list', 'enable_crime', 'enable_schools', 'enable_broadband', 'enable_mobile', 'enable_poi')
    list_filter = ('enable_crime', 'enable_schools', 'enable_broadband', 'enable_mobile', 'enable_poi')


@admin.register(ContextData)
class ContextDataAdmin(admin.ModelAdmin):
    list_display = ('property', 'service_name', 'status', 'retry_count', 'created_at')
    list_filter = ('status', 'service_name', 'created_at')
    search_fields = ('property__title', 'service_name')
    readonly_fields = ('created_at', 'last_attempt_at', 'completed_at')


@admin.register(RatingCriteria)
class RatingCriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'owner__username', 'owner__email')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Criterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating_criteria', 'source', 'scoring_strategy', 'weight', 'is_dealbreaker')
    list_filter = ('source', 'scoring_strategy', 'is_dealbreaker')
    search_fields = ('name', 'rating_criteria__name')


@admin.register(CriterionScore)
class CriterionScoreAdmin(admin.ModelAdmin):
    list_display = ('property', 'criterion', 'normalized_score', 'weighted_score', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('property__title', 'criterion__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SavedLocation)
class SavedLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'address', 'latitude', 'longitude')
    list_filter = ('created_at',)
    search_fields = ('name', 'address', 'user__username')


@admin.register(StateTransitionLog)
class StateTransitionLogAdmin(admin.ModelAdmin):
    list_display = ('content_object', 'from_state', 'to_state', 'transition_name', 'triggered_by', 'timestamp')
    list_filter = ('from_state', 'to_state', 'triggered_by_system', 'timestamp')
    search_fields = ('transition_name',)
    readonly_fields = ('timestamp',)
