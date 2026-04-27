from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count, Avg, Q
from property.models.stage1_models import *
from property.models.stage2_models import *
from property.models.stage3_models import *
from property.models.models_poi import *
from property.models.models_school import *
from property.models.models_connectivity import *

# Customize admin site branding
admin.site.site_header = 'Homely Admin Dashboard'
admin.site.site_title = 'Homely Admin'
admin.site.index_title = 'Property Management System'


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    fields = ('url', 'source_url', 'caption', 'order')
    readonly_fields = ('created_at',)


class CriterionInline(admin.TabularInline):
    model = Criterion
    extra = 0
    fields = ('name', 'source', 'weight')


@admin.register(SearchCriteria)
class SearchCriteriaAdmin(admin.ModelAdmin):
    list_display = ('area', 'bedrooms_range', 'price_range', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('area',)
    readonly_fields = ('created_at', 'updated_at')

    def bedrooms_range(self, obj):
        return f"{obj.bedrooms_min or 'any'}-{obj.bedrooms_max or 'any'}"
    bedrooms_range.short_description = 'Bedrooms'

    def price_range(self, obj):
        return f"£{obj.price_min or 0:,}-£{obj.price_max or 0:,}"
    price_range.short_description = 'Price'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'property_lists_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'owner__username', 'owner__email', 'description')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    filter_horizontal = ('viewers', 'contributors')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'title', 'owner', 'description')
        }),
        ('Configuration', {
            'fields': ('rating_criteria', 'rating_criteria_source'),
            'classes': ('collapse',)
        }),
        ('Collaboration', {
            'fields': ('viewers', 'contributors'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def property_lists_count(self, obj):
        return obj.property_lists.count()
    property_lists_count.short_description = 'Property Lists'


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0
    fields = ('title', 'status', 'priority', 'assigned_to', 'due_date', 'order')
    readonly_fields = ('created_at',)


@admin.register(TaskList)
class TaskListAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'tasks_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'project__title', 'description')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    inlines = [TaskInline]
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'title', 'project', 'description')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def tasks_count(self, obj):
        return obj.tasks.count()
    tasks_count.short_description = 'Tasks'


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'task_list', 'status', 'priority', 'assigned_to', 'due_date', 'created_at')
    list_filter = ('status', 'priority', 'created_at', 'due_date')
    search_fields = ('title', 'description', 'task_list__title')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'completed_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'title', 'task_list', 'description')
        }),
        ('Status & Priority', {
            'fields': ('status', 'priority', 'assigned_to', 'due_date', 'order')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PropertyList)
class PropertyListAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'owner', 'property_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('title', 'owner__username', 'owner__email', 'project__title')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'status_summary')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'title', 'project', 'owner')
        }),
        ('Configuration', {
            'fields': ('search_criteria',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('status_summary',),
        }),
    )

    def property_count(self, obj):
        return obj.properties.count()
    property_count.short_description = 'Properties'

    def status_summary(self, obj):
        summary = obj.get_status_summary()
        return format_html(
            '<b>Total:</b> {} | <b>New:</b> {} | <b>Stage2 In Progress:</b> {} | <b>Stage2 Complete:</b> {} | '
            '<b>Stage3 In Progress:</b> {} | <b>Stage3 Complete:</b> {}',
            summary['total'], summary['new'], summary['stage2_in_progress'],
            summary['stage2_complete'], summary['stage3_in_progress'], summary['stage3_complete']
        )
    status_summary.short_description = 'Property Status Summary'


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'postcode', 'price', 'bedrooms', 'bathrooms', 'state', 'overall_rating', 'created_at')
    list_filter = ('state', 'created_at', 'bedrooms', 'bathrooms', 'garden', 'parking', 'disqualified')
    search_fields = ('title', 'postcode', 'address_line_1', 'external_id')
    readonly_fields = ('uuid', 'state', 'normalized_address', 'overall_rating', 'created_at', 'updated_at')
    filter_horizontal = ('property_lists',)
    inlines = [PropertyImageInline]
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'title', 'state', 'property_lists')
        }),
        ('Address', {
            'fields': ('address_line_1', 'address_line_2', 'city', 'postcode', 'normalized_address', 'uprn')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude')
        }),
        ('Property Details', {
            'fields': ('price', 'bedrooms', 'bathrooms', 'square_area', 'garden', 'parking', 'furnished_status')
        }),
        ('Additional Info', {
            'fields': ('council_tax_band', 'epc_rating', 'lease_length', 'floor_level', 'child_suitable',),
            'classes': ('collapse',)
        }),
        ('External References', {
            'fields': ('external_id', 'external_url'),
            'classes': ('collapse',)
        }),
        ('Rating Results', {
            'fields': ('overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ('property', 'caption', 'order', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('property__title', 'caption')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('property', 'order')


@admin.register(PropertyListTask)
class PropertyListTaskAdmin(admin.ModelAdmin):
    list_display = ('property_list', 'task_type', 'status', 'progress', 'created_at', 'completed_at')
    list_filter = ('task_type', 'status', 'created_at')
    search_fields = ('property_list__title', 'celery_task_id')
    readonly_fields = ('uuid', 'celery_task_id', 'created_at', 'updated_at', 'completed_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'property_list', 'task_type', 'status', 'celery_task_id')
        }),
        ('Progress', {
            'fields': ('total_items', 'completed_items', 'failed_items')
        }),
        ('Errors', {
            'fields': ('error_message', 'errors'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

    def progress(self, obj):
        return f"{obj.progress_percentage}% ({obj.completed_items}/{obj.total_items})"
    progress.short_description = 'Progress'


@admin.register(ContextOptions)
class ContextOptionsAdmin(admin.ModelAdmin):
    list_display = ('project', 'enable_crime', 'enable_schools', 'enable_broadband', 'enable_mobile', 'enable_council_tax', 'enable_poi', 'enable_saved_locations')
    list_filter = ('enable_crime', 'enable_schools', 'enable_broadband', 'enable_mobile', 'enable_council_tax', 'enable_poi', 'enable_saved_locations')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    fieldsets = (
        ('Project', {
            'fields': ('uuid', 'project')
        }),
        ('Context Services', {
            'fields': ('enable_crime', 'enable_schools', 'school_types', 'enable_broadband', 'enable_mobile', 'enable_council_tax')
        }),
        ('POI Configuration', {
            'fields': ('enable_poi', 'poi_types', 'poi_search_radius_meters')
        }),
        ('Saved Locations Configuration', {
            'fields': ('enable_saved_locations', 'saved_location_uuids')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(ContextData)
class ContextDataAdmin(admin.ModelAdmin):
    list_display = ('property', 'service_name', 'status', 'retry_count', 'last_attempt_at', 'created_at')
    list_filter = ('status', 'service_name', 'error_type', 'created_at')
    search_fields = ('property__title', 'service_name', 'error_message')
    readonly_fields = ('uuid', 'created_at', 'last_attempt_at', 'completed_at')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'property', 'service_name', 'status')
        }),
        ('Result Data', {
            'fields': ('data',),
            'classes': ('collapse',)
        }),
        ('Error Tracking', {
            'fields': ('error_message', 'error_type', 'retry_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_attempt_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(RatingCriteria)
class RatingCriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'criteria_count', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('name', 'owner__username', 'owner__email')
    readonly_fields = ('uuid', 'created_at', 'updated_at')
    inlines = [CriterionInline]

    def criteria_count(self, obj):
        return obj.criteria.count()
    criteria_count.short_description = 'Criteria'


@admin.register(Criterion)
class CriterionAdmin(admin.ModelAdmin):
    list_display = ('name', 'rating_criteria', 'source', 'weight')
    list_filter = ('source',)
    search_fields = ('name', 'rating_criteria__name')
    fieldsets = (
        ('Basic Info', {
            'fields': ('rating_criteria', 'name')
        }),
        ('Source', {
            'fields': ('source', 'field_name', 'data_path')
        }),
        ('Weight', {
            'fields': ('weight',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(CriterionScore)
class CriterionScoreAdmin(admin.ModelAdmin):
    list_display = ('property', 'criterion', 'raw_value', 'normalized_score', 'weighted_score', 'created_at')
    list_filter = ('created_at', 'criterion__rating_criteria')
    search_fields = ('property__title', 'criterion__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(SavedLocation)
class SavedLocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'postcode', 'address_line_1', 'latitude', 'longitude', 'created_at')
    list_filter = ('created_at', 'user')
    search_fields = ('name', 'postcode', 'address_line_1', 'city', 'user__username')
    readonly_fields = ('uuid', 'created_at', 'updated_at')


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'urn', 'phase', 'establishment_status', 'postcode', 'pupil_count')
    list_filter = ('phase', 'establishment_status', 'gender', 'religious_character')
    search_fields = ('name', 'urn', 'postcode', 'town')
    readonly_fields = ('created_at', 'updated_at', 'ofsted_url_link')
    fieldsets = (
        ('Basic Info', {
            'fields': ('urn', 'name', 'establishment_number', 'establishment_status')
        }),
        ('Location', {
            'fields': ('address_line_1', 'address_line_2', 'locality', 'town', 'county', 'postcode', 'latitude', 'longitude', 'uprn')
        }),
        ('School Characteristics', {
            'fields': ('phase', 'type_of_establishment', 'type_of_establishment_code', 'gender', 'religious_character', 'admissions_policy')
        }),
        ('Capacity', {
            'fields': ('pupil_count', 'school_capacity', 'statutory_low_age', 'statutory_high_age')
        }),
        ('Contact', {
            'fields': ('website', 'phone', 'ofsted_url_link'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('data_source_date', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def ofsted_url_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.ofsted_url, obj.ofsted_url)
    ofsted_url_link.short_description = 'Ofsted Report'


@admin.register(BroadbandCoverage)
class BroadbandCoverageAdmin(admin.ModelAdmin):
    list_display = ('oa_code', 'laua_name', 'max_download', 'max_upload', 'data_date')
    list_filter = ('data_date', 'laua_name')
    search_fields = ('oa_code', 'laua_code', 'laua_name')
    readonly_fields = ('created_at', 'updated_at')

    def max_download(self, obj):
        speed = obj.get_max_download_speed()
        return f"{speed} Mbps" if speed else "N/A"
    max_download.short_description = 'Max Download'

    def max_upload(self, obj):
        speed = obj.get_max_upload_speed()
        return f"{speed} Mbps" if speed else "N/A"
    max_upload.short_description = 'Max Upload'


@admin.register(MobileCoverage)
class MobileCoverageAdmin(admin.ModelAdmin):
    list_display = ('laua_name', 'coverage_4g', 'coverage_5g', 'overall_score', 'data_date')
    list_filter = ('data_date',)
    search_fields = ('laua_code', 'laua_name')
    readonly_fields = ('created_at', 'updated_at')

    def coverage_4g(self, obj):
        return f"{obj.get_4g_coverage_score()}%"
    coverage_4g.short_description = '4G Score'

    def coverage_5g(self, obj):
        return f"{obj.get_5g_coverage_score()}%"
    coverage_5g.short_description = '5G Score'

    def overall_score(self, obj):
        return f"{obj.get_overall_coverage_score()}%"
    overall_score.short_description = 'Overall'


@admin.register(PlaceOfInterest)
class PlaceOfInterestAdmin(admin.ModelAdmin):
    list_display = ('name', 'place_type', 'property', 'straight_distance_km', 'driving_time_min', 'walking_time_min')
    list_filter = ('place_type', 'created_at')
    search_fields = ('name', 'place_id', 'property__title', 'address')
    readonly_fields = ('uuid', 'created_at', 'updated_at', 'google_maps_link')
    fieldsets = (
        ('Basic Info', {
            'fields': ('uuid', 'property', 'place_id', 'place_type', 'name', 'address')
        }),
        ('Location', {
            'fields': ('latitude', 'longitude')
        }),
        ('Contact', {
            'fields': ('website_url', 'phone_number', 'google_maps_link'),
            'classes': ('collapse',)
        }),
        ('Distance Info', {
            'fields': ('straight_distance_km', 'driving_distance_km', 'driving_time_min', 'walking_distance_km', 'walking_time_min')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def google_maps_link(self, obj):
        return format_html('<a href="{}" target="_blank">{}</a>', obj.google_maps_url, obj.google_maps_url)
    google_maps_link.short_description = 'Google Maps URL'


@admin.register(StateTransitionLog)
class StateTransitionLogAdmin(admin.ModelAdmin):
    list_display = ('content_object', 'from_state', 'to_state', 'transition_name', 'triggered_by', 'triggered_by_system', 'timestamp')
    list_filter = ('from_state', 'to_state', 'triggered_by_system', 'timestamp', 'content_type')
    search_fields = ('transition_name',)
    readonly_fields = ('timestamp',)
    fieldsets = (
        ('Transition Info', {
            'fields': ('content_type', 'object_id', 'from_state', 'to_state', 'transition_name')
        }),
        ('Trigger Info', {
            'fields': ('triggered_by', 'triggered_by_system')
        }),
        ('Metadata', {
            'fields': ('metadata', 'timestamp'),
            'classes': ('collapse',)
        }),
    )


