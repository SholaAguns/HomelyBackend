# Backend Technical Specification - Project Refactor

**Date:** 2026-03-31
**Status:** Specification
**Estimated Duration:** 5-7 days

---

## Table of Contents

1. [Overview](#overview)
2. [Database Changes](#database-changes)
3. [Business Logic](#business-logic)
4. [API Endpoints](#api-endpoints)
5. [Serializers](#serializers)
6. [Tasks (Celery)](#tasks-celery)
7. [Utilities](#utilities)
8. [Testing Strategy](#testing-strategy)
9. [Implementation Sequence](#implementation-sequence)

---

## Overview

### Goals
- Move `rating_criteria` from PropertyList to Project
- Move `ContextOptions` from PropertyList to Project
- Implement project-scoped property deduplication
- Add auto-scraping on PropertyList creation
- Add area validation before list creation
- Implement bulk Stage 2/3 at Property and List levels (NOT Project level)

### User Decisions Applied
- ✅ Delete all test data (fresh start)
- ✅ Property dedup priority: UPRN → external_id → postcode+normalized_address
- ✅ Validate Rightmove area before creating PropertyList
- ✅ Title uniqueness: `(project, title)` instead of `(owner, title)`
- ✅ No Project-level bulk operations (Property/List only)
- ✅ Inline ContextOptions setup if missing
- ✅ Title never auto-updates after creation
- ✅ Keep SearchCriteria duplicated per list

---

## Database Changes

### Step 1: Flush Existing Data

**File:** N/A (Command line)

```bash
# Backup database first (optional, since it's test data)
python manage.py dumpdata > backup_test_data.json

# Flush all data
python manage.py flush --no-input
```

### Step 2: Update Models

#### File: `property/models/stage1_models.py`

**Changes to Project model:**

```python
class Project(models.Model):
    """Top-level container for organizing property lists and housing applications"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Collaboration
    viewers = models.ManyToManyField(User, related_name='viewable_projects', blank=True)
    contributors = models.ManyToManyField(User, related_name='editable_projects', blank=True)

    # NEW: Rating criteria (moved from PropertyList)
    rating_criteria = models.ForeignKey(
        'RatingCriteria',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='projects'
    )
    rating_criteria_source = models.ForeignKey(
        'RatingCriteria',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derived_projects',
        help_text='Source criteria if this was created via copy-on-write'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']
        unique_together = [['owner', 'title']]

    def __str__(self):
        return f"{self.title} ({self.owner.username})"
```

**Changes to PropertyList model:**

```python
class PropertyList(models.Model):
    """Container for a collection of properties with shared configuration"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='property_lists')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_lists')
    title = models.CharField(max_length=255)

    # Optional configurations
    # REMOVED: rating_criteria and rating_criteria_source (moved to Project)
    search_criteria = models.ForeignKey(
        SearchCriteria,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='property_lists'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_lists'
        ordering = ['-created_at']
        unique_together = [['project', 'title']]  # CHANGED: from (owner, title)

    def __str__(self):
        return f"{self.title} ({self.project.title})"

    def get_status_summary(self):
        """Returns aggregated status of all properties in list"""
        properties = self.properties.all()
        return {
            'total': properties.count(),
            'new': properties.filter(state='NEW').count(),
            'stage2_in_progress': properties.filter(state='STAGE2_IN_PROGRESS').count(),
            'stage2_complete': properties.filter(state='STAGE2_COMPLETE').count(),
            'stage3_in_progress': properties.filter(state='STAGE3_IN_PROGRESS').count(),
            'stage3_complete': properties.filter(state='STAGE3_COMPLETE').count(),
        }
```

#### File: `property/models/stage2_models.py`

**Changes to ContextOptions model:**

```python
from django.db import models
from .stage1_models import Project  # CHANGED: Import Project instead of PropertyList
import uuid


class ContextOptions(models.Model):
    """Configuration for which context services to enable for a project"""

    # CHANGED: From property_list OneToOne to project OneToOne
    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name='context_options'
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    # Service toggles
    enable_crime = models.BooleanField(default=False)
    enable_schools = models.BooleanField(default=False)
    enable_broadband = models.BooleanField(default=False)
    enable_mobile = models.BooleanField(default=False)
    enable_council_tax = models.BooleanField(default=False)

    # Schools configuration
    school_types = models.JSONField(default=list, blank=True)

    # POI configuration
    enable_poi = models.BooleanField(default=False)
    poi_types = models.JSONField(default=list, blank=True)
    poi_search_radius_meters = models.IntegerField(default=1600)

    # Saved locations configuration
    enable_saved_locations = models.BooleanField(default=False)
    saved_location_uuids = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'context_options'

    def __str__(self):
        return f"Context Options for {self.project.title}"

    def get_enabled_services(self):
        """Returns list of enabled service names"""
        services = []
        if self.enable_crime:
            services.append('crime')
        if self.enable_schools:
            services.append('schools')
        if self.enable_broadband:
            services.append('broadband')
        if self.enable_mobile:
            services.append('mobile')
        if self.enable_poi:
            services.append('poi')
        if self.enable_council_tax:
            services.append('council_tax')
        if self.enable_saved_locations:
            services.append('saved_locations')
        return services
```

**Changes to Property model (add normalized_address if not exists):**

```python
class Property(models.Model):
    # ... existing fields ...

    # Deduplication fields
    normalized_address = models.CharField(max_length=500, blank=True, db_index=True)  # ADD INDEX
    uprn = models.CharField(max_length=50, blank=True, db_index=True)  # ADD INDEX

    # ... rest of model ...
```

### Step 3: Create Migrations

```bash
# Generate migrations
python manage.py makemigrations property --name refactor_project_context_rating

# Review migration file
# Should show:
# - Add rating_criteria to Project
# - Remove rating_criteria from PropertyList
# - Change ContextOptions FK: property_list → project
# - Change PropertyList unique_together
# - Add indexes to Property.normalized_address and Property.uprn
```

**Expected Migration Operations:**

1. Add `Project.rating_criteria` (nullable FK)
2. Add `Project.rating_criteria_source` (nullable FK)
3. Remove `PropertyList.rating_criteria`
4. Remove `PropertyList.rating_criteria_source`
5. Alter `PropertyList` unique_together constraint
6. Alter `ContextOptions.project` field (from property_list)
7. Remove `ContextOptions.property_list` field
8. Add index to `Property.normalized_address`
9. Add index to `Property.uprn`

### Step 4: Run Migrations

```bash
python manage.py migrate property
```

---

## Business Logic

### 1. Property Deduplication Service

#### File: `property/services/property_deduplication.py` (NEW) - put in utils instead

```python
"""
Property deduplication logic for project-scoped uniqueness.

Deduplication Rules:
- Properties are unique within a Project (not globally)
- If property exists in another list in SAME project: reuse
- If property exists in another list in DIFFERENT project: create duplicate

Priority for matching:
1. UPRN (UK Property Reference Number) - most authoritative
2. external_id (Rightmove listing ID)
3. postcode + normalized_address (fallback)
"""

from django.db.models import Q
from property.models import Property, Project
import re


def normalize_address(address):
    """
    Normalize address for comparison.

    - Lowercase
    - Remove extra spaces
    - Replace common abbreviations
    - Remove punctuation

    Examples:
        "123 Main St." → "123 main street"
        "Flat 4B, Park Lane" → "flat 4b park lane"
    """
    if not address:
        return ""

    normalized = address.lower().strip()

    # Replace abbreviations
    replacements = {
        r'\bst\b\.?': 'street',
        r'\brd\b\.?': 'road',
        r'\bave\b\.?': 'avenue',
        r'\bdr\b\.?': 'drive',
        r'\bln\b\.?': 'lane',
        r'\bapt\b\.?': 'apartment',
        r'\bfl\b\.?': 'floor',
    }

    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized)

    # Remove punctuation and extra spaces
    normalized = re.sub(r'[^\w\s]', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()

    return normalized


def find_existing_property_in_project(property_data, project):
    """
    Find existing property in project using priority-based matching.

    Args:
        property_data (dict): Property data with potential keys:
            - uprn (optional)
            - external_id (optional)
            - postcode (required)
            - address_line_1 (required)
        project (Project): Project instance

    Returns:
        Property or None: Existing property if found
    """
    # Priority 1: UPRN (most authoritative)
    if property_data.get('uprn'):
        existing = Property.objects.filter(
            property_lists__project=project,
            uprn=property_data['uprn']
        ).first()
        if existing:
            return existing

    # Priority 2: Rightmove external_id
    if property_data.get('external_id'):
        existing = Property.objects.filter(
            property_lists__project=project,
            external_id=property_data['external_id']
        ).first()
        if existing:
            return existing

    # Priority 3: Postcode + normalized address (fallback)
    if property_data.get('postcode') and property_data.get('address_line_1'):
        normalized = normalize_address(property_data['address_line_1'])
        existing = Property.objects.filter(
            property_lists__project=project,
            postcode=property_data['postcode'],
            normalized_address=normalized
        ).first()
        if existing:
            return existing

    return None


def get_or_create_property_in_project(property_data, project):
    """
    Get existing property in project or create new one.

    If property exists in same project:
        - Update its details (price may have changed)
        - Return existing property

    If property exists in different project:
        - Create new duplicate (different project = different context)

    Args:
        property_data (dict): Property data
        project (Project): Project instance

    Returns:
        tuple: (property, created) where created is bool
    """
    existing = find_existing_property_in_project(property_data, project)

    if existing:
        # Update existing property with latest data
        update_fields = []

        # Update fields that might change (price, description, etc.)
        updatable_fields = [
            'title', 'price', 'bedrooms', 'bathrooms', 'square_area',
            'garden', 'parking', 'furnished_status', 'external_url',
            'latitude', 'longitude', 'city', 'address_line_2'
        ]

        for field in updatable_fields:
            if field in property_data and property_data[field] is not None:
                if getattr(existing, field) != property_data[field]:
                    setattr(existing, field, property_data[field])
                    update_fields.append(field)

        if update_fields:
            existing.save(update_fields=update_fields + ['updated_at'])

        return existing, False

    else:
        # Create new property
        # Ensure normalized_address is set
        if 'address_line_1' in property_data:
            property_data['normalized_address'] = normalize_address(
                property_data['address_line_1']
            )

        property = Property.objects.create(**property_data)
        return property, True


def bulk_deduplicate_properties_in_project(properties_data, project):
    """
    Bulk deduplication for scraping results.

    Args:
        properties_data (list[dict]): List of property data dicts
        project (Project): Project instance

    Returns:
        dict: {
            'created': [Property],
            'updated': [Property],
            'total': int
        }
    """
    created = []
    updated = []

    for prop_data in properties_data:
        prop, was_created = get_or_create_property_in_project(prop_data, project)

        if was_created:
            created.append(prop)
        else:
            updated.append(prop)

    return {
        'created': created,
        'updated': updated,
        'total': len(created) + len(updated)
    }
```

### 2. Title Generation Utility

#### File: `property/utils/title_generation.py` (NEW)

```python
"""
Auto-generate unique PropertyList titles from search criteria area.
"""

from property.models import PropertyList


def generate_unique_list_title(area, project):
    """
    Generate unique PropertyList title within a project.

    If "Manchester" exists, generates "Manchester 2", "Manchester 3", etc.

    Args:
        area (str): Search criteria area
        project (Project): Project instance

    Returns:
        str: Unique title

    Examples:
        >>> generate_unique_list_title("London", project)
        "London"

        >>> # If "London" already exists
        >>> generate_unique_list_title("London", project)
        "London 2"
    """
    base_title = area.strip()
    title = base_title
    counter = 2

    while PropertyList.objects.filter(
        project=project,
        title=title
    ).exists():
        title = f"{base_title} {counter}"
        counter += 1

    return title
```

### 3. Rightmove Area Validation

#### File: `property/utils/rightmove_validation.py` (NEW)

```python
"""
Validate Rightmove search areas before creating PropertyLists.
"""

from typing import Tuple, List
import requests
from django.core.cache import cache


def validate_rightmove_area(area: str) -> Tuple[bool, str]:
    """
    Validate that area exists on Rightmove.

    Uses Rightmove's location autocomplete API to check if area is valid.
    Caches results for 7 days to avoid repeated API calls.

    Args:
        area: Location string (e.g., "Manchester", "SW1A 1AA")

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "") if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_rightmove_area("Manchester")
        (True, "")

        >>> validate_rightmove_area("NotARealPlace12345")
        (False, "Location not found on Rightmove")
    """
    cache_key = f"rightmove_area_valid:{area.lower()}"

    # Check cache first
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        # Rightmove autocomplete API
        response = requests.get(
            "https://www.rightmove.co.uk/api/_autocomplete",
            params={
                'query': area,
                'limit': 1
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()

            # Check if any results returned
            if data.get('results') and len(data['results']) > 0:
                result = (True, "")
                cache.set(cache_key, result, timeout=60*60*24*7)  # 7 days
                return result
            else:
                result = (False, f"Location '{area}' not found on Rightmove")
                cache.set(cache_key, result, timeout=60*60*24)  # 1 day
                return result
        else:
            # API error, allow creation but warn
            return (True, "")  # Don't block on API errors

    except requests.RequestException:
        # Network error, allow creation
        return (True, "")  # Don't block on network errors


def get_area_suggestions(area: str, limit: int = 5) -> List[str]:
    """
    Get suggested areas similar to input (for typo correction).

    Args:
        area: Invalid area string
        limit: Max number of suggestions

    Returns:
        List of suggested area names

    Examples:
        >>> get_area_suggestions("Mancester")  # Typo
        ["Manchester", "Manchester City Centre", "Manchester Piccadilly"]
    """
    try:
        response = requests.get(
            "https://www.rightmove.co.uk/api/_autocomplete",
            params={
                'query': area,
                'limit': limit
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            return [
                result.get('displayName', result.get('name', ''))
                for result in data.get('results', [])
            ]
    except requests.RequestException:
        pass

    return []
```

### 4. Updated Context Data Retrieval

#### File: `property/tasks.py` (UPDATE)

**Update `retrieve_context_data` task:**

```python
@shared_task
def retrieve_context_data(property_id):
    """
    Retrieve context data for a property using Project-level ContextOptions.

    UPDATED: Now uses project.context_options instead of property_list.context_options
    """
    from property.models import Property
    from property.services.context_service_factory import context_service_factory

    try:
        property = Property.objects.get(id=property_id)

        # Get ContextOptions from project (via any property list)
        prop_list = property.property_lists.first()
        if not prop_list:
            logger.warning(f"Property {property_id} has no property lists")
            return

        project = prop_list.project

        # CHANGED: Use project.context_options instead of prop_list.context_options
        if not hasattr(project, 'context_options'):
            logger.warning(f"Project {project.id} has no context options configured")
            return

        context_options = project.context_options
        enabled_services = context_options.get_enabled_services()

        if not enabled_services:
            logger.info(f"No services enabled for project {project.id}")
            property.complete_stage2()
            property.save()
            return

        # Trigger state transition
        if property.state == 'NEW':
            property.run_stage2()
            property.save()

        # Run each enabled service
        for service_name in enabled_services:
            service = context_service_factory.get_service(service_name)

            # ... rest of existing logic ...

    except Property.DoesNotExist:
        logger.error(f"Property {property_id} not found")
```

---

## API Endpoints

### 1. Project Endpoints (UPDATE)

#### File: `property/views.py`

**Add new actions to ProjectViewSet:**

```python
class ProjectViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    @action(detail=True, methods=['get'], url_path='context-options')
    def context_options(self, request, uuid=None):
        """
        GET /api/property/projects/{uuid}/context-options/

        Get or create context options for project (inline setup support).
        """
        project = self.get_object()

        # Get or create context options
        context_options, created = ContextOptions.objects.get_or_create(
            project=project
        )

        serializer = ContextOptionsSerializer(context_options)
        return Response({
            **serializer.data,
            'is_configured': any([
                context_options.enable_crime,
                context_options.enable_schools,
                context_options.enable_broadband,
                context_options.enable_mobile,
                context_options.enable_poi,
                context_options.enable_council_tax,
                context_options.enable_saved_locations
            ])
        })

    @context_options.mapping.put
    @context_options.mapping.patch
    def update_context_options(self, request, uuid=None):
        """
        PUT/PATCH /api/property/projects/{uuid}/context-options/

        Update project context options.
        """
        project = self.get_object()

        context_options, created = ContextOptions.objects.get_or_create(
            project=project
        )

        serializer = ContextOptionsSerializer(
            context_options,
            data=request.data,
            partial=request.method == 'PATCH'
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def stats(self, request, uuid=None):
        """
        GET /api/property/projects/{uuid}/stats/

        Get project statistics.
        """
        project = self.get_object()

        # Get all properties across all lists
        all_properties = Property.objects.filter(
            property_lists__project=project
        ).distinct()

        # Get unique areas
        areas = SearchCriteria.objects.filter(
            property_lists__project=project
        ).values_list('area', flat=True).distinct()

        # Calculate stats
        stats = {
            'property_lists_count': project.property_lists.count(),
            'total_properties': all_properties.count(),
            'areas_count': len(areas),
            'areas': list(areas),
            'properties_by_state': {
                'new': all_properties.filter(state='NEW').count(),
                'stage2_in_progress': all_properties.filter(state='STAGE2_IN_PROGRESS').count(),
                'stage2_complete': all_properties.filter(state='STAGE2_COMPLETE').count(),
                'stage3_in_progress': all_properties.filter(state='STAGE3_IN_PROGRESS').count(),
                'stage3_complete': all_properties.filter(state='STAGE3_COMPLETE').count(),
            },
            'has_context_options': hasattr(project, 'context_options'),
            'has_rating_criteria': project.rating_criteria is not None
        }

        # Price stats
        prices = all_properties.values_list('price', flat=True)
        if prices:
            stats['average_price'] = sum(prices) / len(prices)
            stats['min_price'] = min(prices)
            stats['max_price'] = max(prices)

        return Response(stats)
```

### 2. PropertyList Endpoints (UPDATE)

**Update PropertyListViewSet.create with validation and auto-scraping:**

```python
class PropertyListViewSet(viewsets.ModelViewSet):
    # ... existing code ...

    def create(self, request, *args, **kwargs):
        """
        POST /api/property/property-lists/

        Create PropertyList with auto-scraping.

        Request body:
        {
            "project_uuid": "...",
            "search_criteria": {
                "area": "Manchester",
                "price_min": 200000,
                "price_max": 400000,
                // ... other search fields
            }
        }

        Response:
        {
            "uuid": "...",
            "title": "Manchester",  // Auto-generated
            "project_uuid": "...",
            "scraping_task_id": "...",
            "scraping_status": "QUEUED",
            // ... other fields
        }
        """
        from property.utils.rightmove_validation import validate_rightmove_area, get_area_suggestions
        from property.utils.title_generation import generate_unique_list_title
        from property.tasks import scrape_rightmove_properties

        # Extract data
        project_uuid = request.data.get('project_uuid')
        search_criteria_data = request.data.get('search_criteria')

        if not project_uuid or not search_criteria_data:
            return Response({
                'error': 'project_uuid and search_criteria are required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get project
        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            return Response({
                'error': f'Project {project_uuid} not found'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate user has access to project
        if project.owner != request.user:
            # TODO: Check if user is contributor
            return Response({
                'error': 'You do not have permission to add lists to this project'
            }, status=status.HTTP_403_FORBIDDEN)

        # Validate Rightmove area
        area = search_criteria_data.get('area')
        is_valid, error_msg = validate_rightmove_area(area)

        if not is_valid:
            suggestions = get_area_suggestions(area)
            return Response({
                'error': error_msg,
                'suggestions': suggestions
            }, status=status.HTTP_400_BAD_REQUEST)

        # Generate unique title
        title = generate_unique_list_title(area, project)

        # Create SearchCriteria
        search_criteria = SearchCriteria.objects.create(**search_criteria_data)

        # Create PropertyList
        property_list = PropertyList.objects.create(
            owner=request.user,
            project=project,
            title=title,
            search_criteria=search_criteria
        )

        # Trigger async scraping
        task = scrape_rightmove_properties.delay(
            property_list_id=property_list.id,
            search_criteria_id=search_criteria.id
        )

        # Serialize response
        serializer = self.get_serializer(property_list)

        return Response({
            **serializer.data,
            'scraping_task_id': str(task.id),
            'scraping_status': 'QUEUED'
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='run-stage2-bulk')
    def run_stage2_bulk(self, request, uuid=None):
        """
        POST /api/property/property-lists/{uuid}/run-stage2-bulk/

        Run Stage 2 on all properties in this list.
        """
        from property.tasks import bulk_retrieve_context_data_for_list

        property_list = self.get_object()

        # Check if project has context options
        if not hasattr(property_list.project, 'context_options'):
            return Response({
                'error': 'Project has no context options configured',
                'action_required': 'configure_context_options'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get eligible properties
        eligible_properties = property_list.properties.filter(
            state__in=['NEW', 'STAGE2_COMPLETE']
        )

        if not eligible_properties.exists():
            return Response({
                'message': 'No properties eligible for Stage 2',
                'eligible_count': 0
            })

        # Trigger task
        task = bulk_retrieve_context_data_for_list.delay(property_list.id)

        return Response({
            'message': f'Stage 2 triggered for {eligible_properties.count()} properties',
            'eligible_count': eligible_properties.count(),
            'task_id': str(task.id)
        })

    @action(detail=True, methods=['post'], url_path='run-stage3-bulk')
    def run_stage3_bulk(self, request, uuid=None):
        """
        POST /api/property/property-lists/{uuid}/run-stage3-bulk/

        Run Stage 3 on all properties in this list.
        """
        from property.tasks import bulk_calculate_ratings_for_list

        property_list = self.get_object()

        # Check if project has rating criteria
        if not property_list.project.rating_criteria:
            return Response({
                'error': 'Project has no rating criteria configured',
                'action_required': 'configure_rating_criteria'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get eligible properties
        eligible_properties = property_list.properties.filter(
            state='STAGE2_COMPLETE'
        )

        if not eligible_properties.exists():
            return Response({
                'message': 'No properties eligible for Stage 3 (must complete Stage 2 first)',
                'eligible_count': 0
            })

        # Trigger task
        task = bulk_calculate_ratings_for_list.delay(property_list.id)

        return Response({
            'message': f'Stage 3 triggered for {eligible_properties.count()} properties',
            'eligible_count': eligible_properties.count(),
            'task_id': str(task.id)
        })
```

### 3. Property Endpoints (No major changes)

Property-level Stage 2/3 endpoints remain unchanged, just update to use project context options.

---

## Serializers

### File: `property/serializers.py`

**Update ProjectSerializer:**

```python
class ProjectSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')
    property_lists_count = serializers.SerializerMethodField()
    viewers = serializers.SlugRelatedField(
        slug_field='email',
        queryset=User.objects.all(),
        many=True,
        required=False
    )
    contributors = serializers.SlugRelatedField(
        slug_field='email',
        queryset=User.objects.all(),
        many=True,
        required=False
    )

    # NEW FIELDS
    rating_criteria_uuid = serializers.PrimaryKeyRelatedField(
        queryset=RatingCriteria.objects.none(),
        source='rating_criteria',
        write_only=True,
        pk_field=serializers.UUIDField(),
        required=False,
        allow_null=True
    )
    rating_criteria_name = serializers.ReadOnlyField(source='rating_criteria.name')
    has_rating_criteria = serializers.SerializerMethodField()
    has_context_options = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'uuid', 'owner', 'title', 'description',
            'viewers', 'contributors', 'property_lists_count',
            'rating_criteria_uuid', 'rating_criteria_name',
            'has_rating_criteria', 'has_context_options',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set rating_criteria queryset based on user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            self.fields['rating_criteria_uuid'].queryset = \
                RatingCriteria.objects.filter(owner=request.user)

    def get_property_lists_count(self, obj):
        return obj.property_lists.count()

    def get_has_rating_criteria(self, obj):
        return obj.rating_criteria is not None

    def get_has_context_options(self, obj):
        return hasattr(obj, 'context_options')

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)
```

**Update PropertyListSerializer:**

```python
class PropertyListSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')
    project_uuid = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        source='project',
        write_only=True,
        pk_field=serializers.UUIDField()
    )
    project_title = serializers.ReadOnlyField(source='project.title')

    # REMOVED: rating_criteria fields (now at project level)
    # NEW: Read rating criteria from project
    rating_criteria_name = serializers.ReadOnlyField(source='project.rating_criteria.name')

    properties_count = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()
    highest_price = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    search_criteria = SearchCriteriaSerializer(read_only=True)

    class Meta:
        model = PropertyList
        fields = [
            'uuid', 'owner', 'title',
            'project_uuid', 'project_title',
            'rating_criteria_name',  # Read from project
            'search_criteria',
            'properties_count', 'status_summary',
            'average_price', 'highest_price', 'lowest_price',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'created_at', 'updated_at']

    # ... existing methods unchanged ...
```

**Update ContextOptionsSerializer:**

```python
class ContextOptionsSerializer(serializers.ModelSerializer):
    project_uuid = serializers.UUIDField(source='project.uuid', read_only=True)
    project_title = serializers.ReadOnlyField(source='project.title')

    class Meta:
        model = ContextOptions
        fields = [
            'uuid', 'project_uuid', 'project_title',
            'enable_crime', 'enable_schools', 'school_types',
            'enable_broadband', 'enable_mobile', 'enable_council_tax',
            'enable_poi', 'poi_types', 'poi_search_radius_meters',
            'enable_saved_locations', 'saved_location_uuids',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'project_uuid', 'created_at', 'updated_at']
```

---

## Tasks (Celery)

### File: `property/tasks.py`

**Add new bulk operation tasks:**

```python
@shared_task
def bulk_retrieve_context_data_for_list(property_list_id):
    """
    Run Stage 2 for all eligible properties in a PropertyList.

    Eligible: state in ['NEW', 'STAGE2_COMPLETE']
    """
    from property.models import PropertyList

    try:
        prop_list = PropertyList.objects.get(id=property_list_id)

        # Get eligible properties
        eligible_properties = prop_list.properties.filter(
            state__in=['NEW', 'STAGE2_COMPLETE']
        )

        logger.info(
            f"Bulk Stage 2 for list {prop_list.id}: "
            f"{eligible_properties.count()} properties"
        )

        # Queue individual tasks
        for prop in eligible_properties:
            retrieve_context_data.delay(prop.id)

        return {
            'property_list_id': property_list_id,
            'properties_queued': eligible_properties.count()
        }

    except PropertyList.DoesNotExist:
        logger.error(f"PropertyList {property_list_id} not found")
        raise


@shared_task
def bulk_calculate_ratings_for_list(property_list_id):
    """
    Run Stage 3 for all eligible properties in a PropertyList.

    Eligible: state == 'STAGE2_COMPLETE'
    Requires: Project has rating_criteria configured
    """
    from property.models import PropertyList

    try:
        prop_list = PropertyList.objects.get(id=property_list_id)

        # Check rating criteria
        if not prop_list.project.rating_criteria:
            logger.error(
                f"PropertyList {property_list_id}: "
                f"Project has no rating criteria configured"
            )
            raise ValueError("Project has no rating criteria configured")

        # Get eligible properties
        eligible_properties = prop_list.properties.filter(
            state='STAGE2_COMPLETE'
        )

        logger.info(
            f"Bulk Stage 3 for list {prop_list.id}: "
            f"{eligible_properties.count()} properties"
        )

        # Queue individual tasks
        for prop in eligible_properties:
            calculate_property_rating.delay(prop.id)

        return {
            'property_list_id': property_list_id,
            'properties_queued': eligible_properties.count()
        }

    except PropertyList.DoesNotExist:
        logger.error(f"PropertyList {property_list_id} not found")
        raise
```

**Update scraping task to use deduplication:**

```python
@shared_task
def scrape_rightmove_properties(property_list_id, search_criteria_id):
    """
    Scrape properties from Rightmove and add to PropertyList.

    UPDATED: Now uses project-scoped deduplication.
    """
    from property.models import PropertyList, SearchCriteria
    from property.services.rightmove_service import RightmoveService
    from property.services.property_deduplication import bulk_deduplicate_properties_in_project

    try:
        prop_list = PropertyList.objects.get(id=property_list_id)
        search_criteria = SearchCriteria.objects.get(id=search_criteria_id)
        project = prop_list.project

        # Scrape properties
        service = RightmoveService()
        scraped_properties = service.scrape_properties_by_search(search_criteria)

        # Deduplicate within project
        result = bulk_deduplicate_properties_in_project(
            scraped_properties,
            project
        )

        # Add to property list (both created and updated)
        for prop in result['created'] + result['updated']:
            prop.property_lists.add(prop_list)

        logger.info(
            f"Scraping complete for list {prop_list.id}: "
            f"{result['total']} properties "
            f"({len(result['created'])} new, {len(result['updated'])} updated)"
        )

        return {
            'property_list_id': property_list_id,
            'total': result['total'],
            'created': len(result['created']),
            'updated': len(result['updated'])
        }

    except Exception as e:
        logger.error(f"Scraping failed for list {property_list_id}: {e}")
        raise
```

---

## Utilities

### File Structure

```
property/
├── services/
│   └── property_deduplication.py (NEW)
└── utils/
    ├── title_generation.py (NEW)
    └── rightmove_validation.py (NEW)
```

All utility code provided in [Business Logic](#business-logic) section above.

---

## Testing Strategy

### Unit Tests

#### File: `property/tests/test_property_deduplication.py` (NEW)

```python
from django.test import TestCase
from django.contrib.auth.models import User
from property.models import Project, Property
from property.services.property_deduplication import (
    normalize_address,
    find_existing_property_in_project,
    get_or_create_property_in_project
)


class PropertyDeduplicationTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='test',
            email='test@test.com'
        )
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

    def test_normalize_address(self):
        """Address normalization works correctly"""
        self.assertEqual(
            normalize_address("123 Main St."),
            "123 main street"
        )
        self.assertEqual(
            normalize_address("Flat 4B, Park Rd"),
            "flat 4b park road"
        )

    def test_dedup_by_uprn(self):
        """Deduplication works with UPRN (highest priority)"""
        # ... test code ...

    def test_dedup_by_external_id(self):
        """Deduplication works with external_id"""
        # ... test code ...

    def test_dedup_by_postcode_address(self):
        """Deduplication works with postcode + address fallback"""
        # ... test code ...

    def test_different_project_creates_duplicate(self):
        """Same property in different project creates duplicate"""
        # ... test code ...
```

#### File: `property/tests/test_title_generation.py` (NEW)

```python
from django.test import TestCase
from django.contrib.auth.models import User
from property.models import Project, PropertyList
from property.utils.title_generation import generate_unique_list_title


class TitleGenerationTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(username='test', email='test@test.com')
        self.project = Project.objects.create(owner=self.user, title='Project')

    def test_unique_title_first_use(self):
        """First use of area name doesn't add number"""
        title = generate_unique_list_title("Manchester", self.project)
        self.assertEqual(title, "Manchester")

    def test_unique_title_increments(self):
        """Duplicate titles increment correctly"""
        PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title="Manchester"
        )

        title = generate_unique_list_title("Manchester", self.project)
        self.assertEqual(title, "Manchester 2")

        PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title="Manchester 2"
        )

        title = generate_unique_list_title("Manchester", self.project)
        self.assertEqual(title, "Manchester 3")
```

### Integration Tests

#### File: `property/tests/test_propertylist_creation_api.py` (NEW)

```python
from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from property.models import Project, PropertyList
from unittest.mock import patch


class PropertyListCreationAPITest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='test',
            email='test@test.com',
            password='test'
        )
        self.client.force_authenticate(self.user)

        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

    @patch('property.utils.rightmove_validation.validate_rightmove_area')
    @patch('property.tasks.scrape_rightmove_properties.delay')
    def test_create_list_with_valid_area(self, mock_scrape, mock_validate):
        """PropertyList creation succeeds with valid area"""
        mock_validate.return_value = (True, "")
        mock_scrape.return_value.id = "task-123"

        data = {
            'project_uuid': str(self.project.uuid),
            'search_criteria': {
                'area': 'Manchester',
                'price_min': 200000,
                'price_max': 400000
            }
        }

        response = self.client.post('/api/property/property-lists/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Manchester')
        self.assertIn('scraping_task_id', response.data)

        # Verify PropertyList created
        self.assertTrue(
            PropertyList.objects.filter(
                project=self.project,
                title='Manchester'
            ).exists()
        )

    @patch('property.utils.rightmove_validation.validate_rightmove_area')
    def test_create_list_with_invalid_area(self, mock_validate):
        """PropertyList creation fails with invalid area"""
        mock_validate.return_value = (False, "Location not found")

        data = {
            'project_uuid': str(self.project.uuid),
            'search_criteria': {
                'area': 'InvalidPlace123',
                'price_min': 200000
            }
        }

        response = self.client.post('/api/property/property-lists/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)
        self.assertIn('suggestions', response.data)

        # Verify PropertyList NOT created
        self.assertFalse(
            PropertyList.objects.filter(
                project=self.project
            ).exists()
        )
```

---

## Implementation Sequence

### Day 1: Database & Models
**Duration:** 4-6 hours

1. ✅ Flush test database
2. ✅ Update `Project` model (add rating_criteria fields)
3. ✅ Update `PropertyList` model (remove rating_criteria, change unique_together)
4. ✅ Update `ContextOptions` model (change FK to project)
5. ✅ Update `Property` model (add indexes)
6. ✅ Generate and run migrations
7. ✅ Verify migrations with `python manage.py check`

**Verification:**
```bash
python manage.py shell
>>> from property.models import Project, PropertyList, ContextOptions
>>> p = Project.objects.create(owner=user, title="Test")
>>> p.context_options  # Should not exist yet
>>> co = ContextOptions.objects.create(project=p)
>>> p.context_options  # Should return ContextOptions instance
```

### Day 2: Business Logic & Utilities
**Duration:** 6-8 hours

1. ✅ Create `property/services/property_deduplication.py`
   - `normalize_address()`
   - `find_existing_property_in_project()`
   - `get_or_create_property_in_project()`
   - `bulk_deduplicate_properties_in_project()`
2. ✅ Create `property/utils/title_generation.py`
   - `generate_unique_list_title()`
3. ✅ Create `property/utils/rightmove_validation.py`
   - `validate_rightmove_area()`
   - `get_area_suggestions()`
4. ✅ Write unit tests for all utilities

**Verification:**
```bash
python manage.py test property.tests.test_property_deduplication
python manage.py test property.tests.test_title_generation
```

### Day 3: Serializers & API Endpoints
**Duration:** 6-8 hours

1. ✅ Update `ProjectSerializer`
2. ✅ Update `PropertyListSerializer`
3. ✅ Update `ContextOptionsSerializer`
4. ✅ Add `ProjectViewSet.context_options()` endpoint
5. ✅ Add `ProjectViewSet.stats()` endpoint
6. ✅ Update `PropertyListViewSet.create()` with validation
7. ✅ Add `PropertyListViewSet.run_stage2_bulk()`
8. ✅ Add `PropertyListViewSet.run_stage3_bulk()`

**Verification:**
```bash
# Start server
python manage.py runserver

# Test endpoints
curl -X POST http://localhost:8000/api/property/projects/ \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title": "Test Project"}'

curl -X GET http://localhost:8000/api/property/projects/{uuid}/stats/
```

### Day 4: Tasks & Context Retrieval
**Duration:** 4-6 hours

1. ✅ Update `retrieve_context_data()` task to use project.context_options
2. ✅ Add `bulk_retrieve_context_data_for_list()` task
3. ✅ Add `bulk_calculate_ratings_for_list()` task
4. ✅ Update `scrape_rightmove_properties()` to use deduplication
5. ✅ Test Celery tasks

**Verification:**
```bash
# Start Celery worker
celery -A homely worker -l info

# Test in Django shell
>>> from property.tasks import scrape_rightmove_properties
>>> task = scrape_rightmove_properties.delay(list_id, criteria_id)
>>> task.status
```

### Day 5: Integration Tests & Bug Fixes
**Duration:** 6-8 hours

1. ✅ Write integration tests for PropertyList creation API
2. ✅ Write integration tests for bulk operations
3. ✅ Test end-to-end flow:
   - Create Project
   - Create PropertyList (auto-scrape)
   - Run Stage 2 bulk
   - Run Stage 3 bulk
4. ✅ Fix any bugs discovered
5. ✅ Update API documentation

**Verification:**
```bash
python manage.py test property.tests.test_propertylist_creation_api
python manage.py test property.tests.test_bulk_operations
```

### Day 6-7: Final Testing & Documentation
**Duration:** 4-8 hours

1. ✅ Run full test suite
2. ✅ Manual testing of all endpoints
3. ✅ Performance testing (deduplication with 1000+ properties)
4. ✅ Update Postman/Swagger docs
5. ✅ Code review & cleanup
6. ✅ Merge to main branch

---

## Checklist

### Pre-Implementation
- [ ] Review and approve this spec
- [ ] Create feature branch: `git checkout -b feature/project-refactor`
- [ ] Backup test database (optional)

### Phase 1: Database
- [ ] Flush test data
- [ ] Update Project model
- [ ] Update PropertyList model
- [ ] Update ContextOptions model
- [ ] Update Property model (indexes)
- [ ] Generate migrations
- [ ] Run migrations
- [ ] Verify with shell

### Phase 2: Business Logic
- [ ] Create property_deduplication.py
- [ ] Create title_generation.py
- [ ] Create rightmove_validation.py
- [ ] Write unit tests
- [ ] All tests pass

### Phase 3: API
- [ ] Update ProjectSerializer
- [ ] Update PropertyListSerializer
- [ ] Update ContextOptionsSerializer
- [ ] Add Project endpoints
- [ ] Update PropertyList.create()
- [ ] Add bulk operation endpoints
- [ ] Test endpoints manually

### Phase 4: Tasks
- [ ] Update retrieve_context_data
- [ ] Add bulk_retrieve_context_data_for_list
- [ ] Add bulk_calculate_ratings_for_list
- [ ] Update scrape_rightmove_properties
- [ ] Test Celery tasks

### Phase 5: Testing
- [ ] Write integration tests
- [ ] End-to-end testing
- [ ] Fix bugs
- [ ] Performance testing
- [ ] Code review

### Phase 6: Deploy
- [ ] Update documentation
- [ ] Merge to main
- [ ] Deploy to staging
- [ ] Verify on staging
- [ ] Deploy to production (when ready)

---

## Success Criteria

✅ All test data flushed
✅ Migrations applied successfully
✅ All unit tests pass (100% coverage on new code)
✅ All integration tests pass
✅ PropertyList creation validates area
✅ Auto-scraping works on list creation
✅ Deduplication works (UPRN → external_id → postcode+address)
✅ Title auto-generation works
✅ Bulk Stage 2/3 at list level works
✅ Project-level context options work
✅ Project-level rating criteria work
✅ No regressions in existing functionality

---

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Rightmove validation API changes | High | Graceful fallback (allow creation on API errors) |
| Deduplication misses matches | Medium | Use multiple strategies (UPRN/external_id/address) |
| Scraping performance degrades | Medium | Monitor task queue, add rate limiting if needed |
| Title conflicts after refactor | Low | Unique constraint prevents duplicates |
| Context options migration issues | N/A | Fresh start (no migration needed) |

---

## Notes

- Since we're flushing all data, no complex migration scripts needed
- Focus on correctness over optimization initially
- Add logging at key points for debugging
- Consider adding Sentry for error tracking
- Monitor Celery queue depth during scraping
