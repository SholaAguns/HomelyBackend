# Architecture Decisions - Homely Project
**Date:** 2026-01-06
**Status:** Finalized
**Source:** Clarification Questions 2026-01-06

This document consolidates all architectural decisions made during workflow diagram review and serves as the single source of truth for implementation.

---

## Decision Summary Table

| #   | Category                  | Decision                       | Implementation Impact                                 |
| --- | ------------------------- | ------------------------------ | ----------------------------------------------------- |
| 1   | Rating Criteria Strategy  | Reference-with-Copy-on-Write   | Use FK reference, auto-fork on edit                   |
| 2   | Stage 2 Trigger           | Manual with Bulk Option        | "Retrieve Context Reports" button (individual + bulk) |
| 3   | Property Addition Rules   | Flexible (no context required) | Allow property addition anytime                       |
| 4   | Context Button Behavior   | Redirect to Config Form        | Button redirects if no context options exist          |
| 5   | Rating Criteria Timing    | Optional                       | Can be added anytime after list creation              |
| 6   | Rating Trigger            | Manual                         | User must trigger rating calculation                  |
| 7   | Context Options Addition  | Automatic Service Run          | New services run immediately on existing properties   |
| 8   | Context Options Removal   | Ask User Confirmation          | Prompt before deleting context data                   |
| 9   | Service Completion Event  | Database + WebSocket           | Post-save signal triggers WebSocket message           |
| 10  | Completion Aggregation    | Check After Each Service       | Every service completion checks if all done           |
| 11  | Service Failure Handling  | Partial Success                | Property reaches Stage2Complete with failed services  |
| 12  | Failed Service Marking    | Mark as FAILED                 | Distinct from COMPLETE, enables retry tracking        |
| 13  | Caching Strategy          | Smart Service-Specific         | Each service defines cache key and TTL                |
| 14  | Cache Storage             | Redis                          | Leverages existing Celery infrastructure              |
| 15  | Field Change Detection    | Approved Matrix                | Postcode → 5 services, others → rating only           |
| 16  | Field Change Confirmation | Required                       | Show confirmation dialog before rerunning services    |

---

## Detailed Decisions

### 1. Rating Criteria - Reference-with-Copy-on-Write Pattern

**Decision:** Use foreign key reference with automatic copy-on-write when edited.

**Implementation:**
```python
# Models
class RatingCriteria(models.Model):
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User)
    # ... criteria configuration fields

class PropertyList(models.Model):
    rating_criteria = models.ForeignKey(RatingCriteria, null=True, blank=True)
    rating_criteria_source = models.ForeignKey(RatingCriteria, null=True, related_name='derived_lists')
    # ^ Tracks original if forked

# In PropertyList view when user edits criteria
def edit_rating_criteria(property_list, new_criteria_data):
    # Check if criteria is shared (referenced by other lists)
    if property_list.rating_criteria.propertylist_set.count() > 1:
        # Fork: Create new criteria instance
        new_criteria = RatingCriteria.objects.create(
            **new_criteria_data,
            owner=property_list.owner,
            is_template=False
        )
        property_list.rating_criteria_source = property_list.rating_criteria
        property_list.rating_criteria = new_criteria
        property_list.save()
    else:
        # Update in place (only this list uses it)
        property_list.rating_criteria.update(**new_criteria_data)
```

**UI Behavior:**
- When selecting existing criteria: "Using 'My Criteria Template'"
- When forking on edit: "Using custom criteria (based on 'My Criteria Template')"
- Template creators can see: "Used by 5 lists"

**Benefits:**
- Efficient storage for common patterns
- Clear template lineage
- Automatic isolation on customization
- No surprise side effects

---

### 2. Stage 2 Triggering - Manual with Bulk Option

**Decision:** User must manually trigger Stage 2 services (not automatic on property creation), with bulk retrieval option.

**Rationale:**
- User control over API costs
- Supports batch property addition workflow
- Prevents accidental expensive operations

**UI Implementation:**

**Individual Property Detail Page:**
```
[Property Details]
Status: New

[Retrieve Context Reports] button
```

**Property List Detail Page:**
```
[List of Properties]
- Property A (Status: New)
- Property B (Status: New)
- Property C (Status: Stage2Complete)

[Retrieve Reports for All New Properties] button (count badge: 2)
```

**API Endpoints:**
```
POST /api/properties/{id}/run-stage2/          # Individual
POST /api/property-lists/{id}/bulk-stage2/     # Bulk
```

**Bulk Logic:**
```python
def bulk_run_stage2(property_list_id):
    properties = Property.objects.filter(
        property_list_id=property_list_id,
        state='New'  # Only NEW properties
    )
    for prop in properties:
        run_stage2_task.delay(prop.id)
```

---

### 3. Property Addition Without Context Options - Flexible

**Decision:** Properties can be added to lists without context options configured.

**UI Behavior When Context Options Missing:**

**On Property Detail Page:**
- "Retrieve Context Reports" button is present but:
  - **If clicked → Redirects to Context Options configuration form**
  - Message: "Configure context options to retrieve reports for this property"

**On Property List Detail Page:**
- "Retrieve Reports for All New Properties" button:
  - **If clicked and no context options → Redirects to Context Options configuration form**
  - Message: "Configure context options before retrieving reports"

**Implementation:**
```python
# View logic
def retrieve_context_reports_view(request, property_id):
    property = get_object_or_404(Property, pk=property_id)

    if not property.property_list.context_options:
        return redirect('configure_context_options', pk=property.property_list.id)

    # Trigger Stage 2
    run_stage2_task.delay(property_id)
    return redirect('property_detail', pk=property_id)
```

**Benefits:**
- Maximum flexibility for user workflows
- Clear guidance (button click → redirect to setup)
- No blocking, no confusing disabled buttons

---

### 4. Rating Criteria Timing - Optional

**Decision:** Rating criteria are optional and can be added anytime after list creation.

**State Implications:**
- Properties can reach `Stage2Complete` without rating criteria
- Properties display "Not yet rated" until criteria configured
- Rating only possible for properties at `Stage2Complete` or `Stage3Complete`

**UI:**
```
Property Card:
┌─────────────────────────┐
│ 123 Main Street         │
│ Status: Stage2Complete  │
│ Rating: Not yet rated   │
│ [Configure Criteria]    │ ← Links to list's rating criteria form
└─────────────────────────┘
```

---

### 5. Rating Trigger - Manual

**Decision:** When rating criteria are added to a list with existing properties, rating does NOT trigger automatically. User must manually trigger.

**UI Implementation:**

**Property List Detail Page After Adding Criteria:**
```
Rating Criteria: Configured ✓

[Properties]
- Property A (Stage2Complete) - [Calculate Rating] button
- Property B (Stage2Complete) - [Calculate Rating] button
- Property C (New) - Rating not available

[Calculate Ratings for All Eligible Properties] button (count badge: 2)
```

**Individual vs Bulk:**
- Individual: Button on each property card
- Bulk: Single button at list level

**Eligibility:**
- Only properties at `Stage2Complete` or `Stage3Complete`
- Skip properties at `New`, `Stage2InProgress`, `Stage3InProgress`

---

### 6. Context Options Modification - Addition Behavior

**Decision:** When new context options are ADDED, services run FULLY AUTOMATICALLY on existing properties.

**Scenario:**
- List has options: [Crime, Schools]
- User edits to add: [Broadband, Mobile]
- List has 3 properties at `Stage2Complete`

**Behavior:**
1. User saves context options form
2. Backend detects new services: Broadband, Mobile
3. **Immediately triggers** Celery tasks for new services on all properties past `New` state
4. Properties transition: `Stage2Complete` → `Stage2InProgress`
5. WebSocket sends progress updates to frontend
6. When new services complete: `Stage2InProgress` → `Stage2Complete`

**Implementation:**
```python
# In context options save view
def save_context_options(property_list, new_options):
    old_services = set(property_list.context_options.get_enabled_services())
    property_list.context_options.update(new_options)
    new_services = set(property_list.context_options.get_enabled_services())

    added_services = new_services - old_services

    if added_services:
        # Trigger services for all eligible properties
        properties = Property.objects.filter(
            property_list=property_list
        ).exclude(state='New')  # Skip New properties

        for prop in properties:
            prop.state = 'Stage2InProgress'
            prop.save()

            for service_name in added_services:
                run_service_task.delay(prop.id, service_name)
```

**UI Feedback:**
```
Context options updated successfully.
Running Broadband and Mobile reports for 3 existing properties...
```

---

### 7. Context Options Modification - Removal Behavior

**Decision:** When context options are REMOVED, ask user for confirmation before deleting data.

**Scenario:**
- List has options: [Crime, Schools, Broadband]
- User edits to remove: [Broadband]
- List has 3 properties with existing broadband data

**Behavior:**
1. User unchecks "Broadband" in context options form
2. User clicks Save
3. **Confirmation dialog appears:**
   ```
   Removing Broadband will delete existing broadband data for 3 properties.
   This action cannot be undone.

   [Cancel]  [Delete Data and Continue]
   ```
4. If user confirms → Delete `ContextData` records for broadband service
5. If user cancels → Keep broadband option enabled

**Implementation:**
```python
# Frontend (Angular)
onSaveContextOptions() {
    const removedServices = this.detectRemovedServices();

    if (removedServices.length > 0) {
        const count = await this.getAffectedPropertiesCount(removedServices);

        const confirmed = await this.showConfirmDialog(
            `Removing ${removedServices.join(', ')} will delete existing data for ${count} properties. Continue?`
        );

        if (!confirmed) return;
    }

    this.api.saveContextOptions(...);
}

# Backend
def delete_context_data_for_services(property_list, service_names):
    ContextData.objects.filter(
        property__property_list=property_list,
        service_name__in=service_names
    ).delete()
```

---

### 8. Service Completion Event Propagation - Database + WebSocket

**Decision:** Use Django ORM + post_save signals + Django Channels WebSockets.

**Architecture:**
```
Celery Service Task
  ↓ (completes)
Update ContextData.status = 'COMPLETE'
  ↓ (save to DB)
Post-save Signal Fires
  ↓
Signal Handler:
  1. Check if all services complete
  2. Update Property.state if needed
  3. Send WebSocket message
  ↓
Django Channels → WebSocket → Frontend
```

**Implementation:**
```python
# models.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

class ContextData(models.Model):
    property = models.ForeignKey(Property)
    service_name = models.CharField(max_length=50)
    status = models.CharField(
        choices=[
            ('PENDING', 'Pending'),
            ('IN_PROGRESS', 'In Progress'),
            ('COMPLETE', 'Complete'),
            ('FAILED', 'Failed')
        ]
    )
    data = models.JSONField(null=True)
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

@receiver(post_save, sender=ContextData)
def context_data_updated(sender, instance, **kwargs):
    if instance.status in ['COMPLETE', 'FAILED']:
        property = instance.property

        # Check if all services are done
        all_done = property.check_all_services_complete()

        if all_done and property.state == 'Stage2InProgress':
            property.state = 'Stage2Complete'
            property.save()

        # Send WebSocket update
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'property_{property.id}',
            {
                'type': 'service_update',
                'service': instance.service_name,
                'status': instance.status,
                'property_state': property.state,
                'progress': property.get_stage2_progress()
            }
        )

# In Property model
def check_all_services_complete(self):
    """Check if all required services are complete or failed"""
    enabled_services = self.property_list.context_options.get_enabled_services()

    context_data = self.contextdata_set.filter(service_name__in=enabled_services)

    return all(
        cd.status in ['COMPLETE', 'FAILED']
        for cd in context_data
    )

def get_stage2_progress(self):
    """Return progress dict for WebSocket"""
    enabled_services = self.property_list.context_options.get_enabled_services()
    context_data = self.contextdata_set.filter(service_name__in=enabled_services)

    return {
        'total': len(enabled_services),
        'complete': context_data.filter(status='COMPLETE').count(),
        'failed': context_data.filter(status='FAILED').count(),
        'in_progress': context_data.filter(status='IN_PROGRESS').count()
    }
```

**Frontend (Angular):**
```typescript
// WebSocket subscription
this.websocketService.subscribe(`property_${propertyId}`).subscribe(
    (message) => {
        if (message.type === 'service_update') {
            this.updateServiceStatus(message.service, message.status);
            this.updateProgressBar(message.progress);

            if (message.property_state === 'Stage2Complete') {
                this.showCompletionNotification();
            }
        }
    }
);
```

---

### 9. Service Completion Aggregation - Check After Each Service

**Decision:** Every time a service completes (or fails), check if all services are done.

**Implementation:** (See code above in Decision 8)

**Flow:**
1. Service task completes
2. Updates `ContextData.status` = 'COMPLETE' or 'FAILED'
3. `.save()` triggers `post_save` signal
4. Signal handler calls `property.check_all_services_complete()`
5. If all done → Update property state
6. Send WebSocket update regardless (for progress bar)

**Efficiency:**
- Each check queries only that property's ContextData (fast)
- No polling, no scheduled tasks
- Event-driven, immediate response

---

### 10. Service Failure Handling - Partial Success

**Decision:** Property reaches `Stage2Complete` even if some services failed.

**Key Requirements:**
- Failed services must be marked with `status='FAILED'` (NOT 'COMPLETE')
- Failed services display error message and retry button
- Rating criteria using failed service data show "N/A" or "No data"
- Overall property is not blocked from Stage 3

**Implementation:**
```python
# In service task
@shared_task
def run_crime_service(property_id):
    try:
        property = Property.objects.get(pk=property_id)
        data = fetch_crime_data(property.postcode)  # External API call

        ContextData.objects.update_or_create(
            property=property,
            service_name='crime',
            defaults={
                'status': 'COMPLETE',
                'data': data,
                'error_message': None
            }
        )
    except Exception as e:
        ContextData.objects.update_or_create(
            property=property,
            service_name='crime',
            defaults={
                'status': 'FAILED',
                'data': None,
                'error_message': str(e)
            }
        )

# In check_all_services_complete
def check_all_services_complete(self):
    """Returns True if all services are COMPLETE or FAILED (not PENDING or IN_PROGRESS)"""
    enabled_services = self.property_list.context_options.get_enabled_services()
    context_data = self.contextdata_set.filter(service_name__in=enabled_services)

    # Check that every enabled service has completed (success or failure)
    return all(cd.status in ['COMPLETE', 'FAILED'] for cd in context_data)
```

**UI Display:**
```
Property Status: Stage2Complete

Reports:
✓ Crime Report - Ready
✓ Schools Report - Ready
✗ Broadband Report - Failed (API error: timeout)  [Retry]
✓ Mobile Coverage - Ready
✓ Places of Interest - Ready

Progress: 4/5 reports successful
```

**Rating Behavior:**
```python
# When calculating rating for criterion that uses failed service data
def calculate_broadband_criterion(property):
    context_data = property.contextdata_set.filter(service_name='broadband').first()

    if not context_data or context_data.status == 'FAILED':
        return {
            'score': None,
            'status': 'NO_DATA',
            'message': 'Broadband data not available'
        }

    # Normal scoring logic
    return {
        'score': calculate_score(context_data.data),
        'status': 'SCORED'
    }

# In overall rating calculation
def calculate_overall_rating(property):
    criteria_scores = []
    for criterion in property.property_list.rating_criteria.get_enabled_criteria():
        score_result = criterion.calculate(property)

        if score_result['status'] == 'SCORED':
            criteria_scores.append(score_result['score'] * criterion.weight)
        # Skip criteria with NO_DATA (don't penalize missing data)

    if len(criteria_scores) == 0:
        return None  # No scoreable criteria

    return sum(criteria_scores) / len(criteria_scores)  # Average of available scores
```

---

### 11. Service Caching - Smart Service-Specific Strategy

**Decision:** Each service defines its own caching logic (cache key generation, TTL, staleness rules).

**Implementation:**
```python
# Base interface
class IContextService(ABC):
    @abstractmethod
    def get_cache_key(self, property):
        """Generate cache key for this property"""
        pass

    @abstractmethod
    def get_cache_ttl(self):
        """Return cache TTL in seconds"""
        pass

    @abstractmethod
    def fetch_data(self, property):
        """Fetch data from external API"""
        pass

    def retrieve(self, property):
        """Main method with caching logic"""
        cache_key = self.get_cache_key(property)

        # Check cache
        cached_data = cache.get(cache_key)
        if cached_data is not None:
            logger.info(f"Cache hit for {cache_key}")
            return cached_data

        # Cache miss - fetch from API
        logger.info(f"Cache miss for {cache_key}, fetching from API")
        data = self.fetch_data(property)

        # Store in cache
        cache.set(cache_key, data, timeout=self.get_cache_ttl())

        return data

# Concrete implementations
class CrimeService(IContextService):
    def get_cache_key(self, property):
        # Cache by postcode SECTOR (e.g., "SW1A 1")
        sector = property.postcode[:property.postcode.rfind(' ')]
        return f"crime:{sector}"

    def get_cache_ttl(self):
        return 30 * 24 * 60 * 60  # 30 days (crime stats updated monthly)

    def fetch_data(self, property):
        return call_police_api(property.postcode)

class BroadbandService(IContextService):
    def get_cache_key(self, property):
        # Cache by exact UPRN (unique property reference)
        return f"broadband:{property.uprn}"

    def get_cache_ttl(self):
        return 7 * 24 * 60 * 60  # 7 days

    def fetch_data(self, property):
        return call_ofcom_api(property.postcode)

class SchoolRatingService(IContextService):
    def get_cache_key(self, property):
        # Schools cached by postcode (district-level search)
        return f"schools:{property.postcode}"

    def get_cache_ttl(self):
        return 90 * 24 * 60 * 60  # 90 days (Ofsted ratings change infrequently)

    def fetch_data(self, property):
        return call_dfe_api(property.postcode)

class PlacesOfInterestService(IContextService):
    def get_cache_key(self, property):
        # POI cached by lat/lon rounded to 4 decimals (~11m precision)
        lat = round(property.latitude, 4)
        lon = round(property.longitude, 4)
        poi_types = ','.join(sorted(self.enabled_poi_types))
        return f"poi:{lat}:{lon}:{poi_types}"

    def get_cache_ttl(self):
        return 30 * 24 * 60 * 60  # 30 days

    def fetch_data(self, property):
        return call_google_places_api(property.latitude, property.longitude)
```

**Cache Storage:** Redis (as decided)

**Configuration:**
```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'homely',
        'TIMEOUT': 300,  # Default 5 minutes (overridden by service-specific TTL)
    }
}
```

**Cache Invalidation:**
- Automatic via TTL
- Manual invalidation on field change:
  ```python
  # When postcode changes
  def invalidate_postcode_caches(property):
      # Clear crime, schools, POI, broadband, mobile
      services = ['crime', 'schools', 'poi', 'broadband', 'mobile']
      for service_class in [CrimeService, SchoolsService, ...]:
          service = service_class()
          cache_key = service.get_cache_key(property)
          cache.delete(cache_key)
  ```

---

### 12. Field Change Detection - Dependency Matrix

**Decision:** Approved dependency matrix.

**Implementation:**
```python
# Property model
FIELD_SERVICE_DEPENDENCIES = {
    'postcode': ['crime', 'schools', 'poi', 'broadband', 'mobile'],
    'latitude': ['poi'],
    'longitude': ['poi'],
    # Fields that only affect rating, not services:
    'bedrooms': [],
    'price': [],
    'square_area': [],
    'garden': [],
    'furnished_status': [],
    'council_tax_band': [],
    'epc_rating': [],
    'bathrooms': [],
    'property_type': [],
}

FIELD_RATING_DEPENDENCIES = {
    'postcode': True,  # Affects POI distance criteria
    'bedrooms': True,
    'price': True,
    'square_area': True,
    'garden': True,
    'furnished_status': True,
    'council_tax_band': True,
    'epc_rating': True,
    'bathrooms': True,
    # Any context data change also triggers rating
}

def get_affected_services(self, changed_fields):
    """Returns set of service names that need rerunning"""
    services = set()
    for field in changed_fields:
        services.update(self.FIELD_SERVICE_DEPENDENCIES.get(field, []))
    return services

def needs_rating_recalculation(self, changed_fields):
    """Returns True if any changed field affects rating"""
    return any(
        self.FIELD_RATING_DEPENDENCIES.get(field, False)
        for field in changed_fields
    )
```

---

### 13. Field Change Confirmation - Required

**Decision:** Show confirmation dialog before rerunning services due to field changes.

**Implementation:**

**Frontend (Angular):**
```typescript
// In property edit form
async onSave() {
    const changedFields = this.detectChangedFields();
    const affectedServices = this.getAffectedServices(changedFields);

    if (affectedServices.length > 0) {
        const confirmed = await this.confirmDialog.show({
            title: 'Rerun Context Services?',
            message: `Changing ${changedFields.join(', ')} will re-retrieve ${affectedServices.join(', ')} reports. This may incur API costs.`,
            confirmText: 'Save and Rerun Services',
            cancelText: 'Cancel',
            showDontAskAgain: true  // Power users can disable
        });

        if (!confirmed) {
            return;  // Cancel save
        }
    }

    // Proceed with save
    await this.api.updateProperty(this.property.id, this.formData);

    // Backend will automatically trigger services
}
```

**Backend:**
```python
# In property update view
from django.db.models import signals

class PropertyUpdateView(UpdateAPIView):
    def perform_update(self, serializer):
        # Track changed fields
        instance = self.get_object()
        old_values = {
            field: getattr(instance, field)
            for field in instance.FIELD_SERVICE_DEPENDENCIES.keys()
        }

        # Save changes
        serializer.save()

        # Detect what changed
        changed_fields = [
            field for field, old_val in old_values.items()
            if getattr(instance, field) != old_val
        ]

        if changed_fields:
            # Trigger affected services
            affected_services = instance.get_affected_services(changed_fields)

            if affected_services:
                instance.state = 'Stage2InProgress'
                instance.save()

                for service_name in affected_services:
                    run_service_task.delay(instance.id, service_name)

            # Trigger rating recalculation if needed
            if instance.needs_rating_recalculation(changed_fields):
                if instance.property_list.rating_criteria:
                    calculate_rating_task.delay(instance.id)
```

**User Preference Storage:**
```python
# For "Don't ask again" checkbox
class UserPreference(models.Model):
    user = models.OneToOneField(User)
    skip_service_rerun_confirmation = models.BooleanField(default=False)
```

---

## State Machine Definitions

Based on these decisions, here are the formal state machines:

### PropertyList State Machine

```
States:
- DRAFT: Initial state after creation
- ACTIVE: Has context options or properties (or both)

Transitions:
- create() → DRAFT
- add_context_options() → ACTIVE
- add_first_property() → ACTIVE
```

**Note:** PropertyList states are simple. Most state complexity lives in Property model.

### Property State Machine

```
States:
- NEW: Initial state after creation
- STAGE2_IN_PROGRESS: Context services running
- STAGE2_COMPLETE: All context services complete/failed
- STAGE3_IN_PROGRESS: Rating calculation running
- STAGE3_COMPLETE: Rating calculated

Transitions:
- create() → NEW
- run_stage2() → STAGE2_IN_PROGRESS
- all_services_complete() → STAGE2_COMPLETE
- run_stage3() → STAGE3_IN_PROGRESS
- rating_calculated() → STAGE3_COMPLETE
- edit_field_with_service_deps() → STAGE2_IN_PROGRESS (from STAGE2_COMPLETE or STAGE3_*)
- edit_field_with_rating_deps() → STAGE3_IN_PROGRESS (from STAGE3_COMPLETE)
```

**Implementation with django-fsm:**
```python
from django_fsm import FSMField, transition

class Property(models.Model):
    state = FSMField(default='NEW', protected=True)

    @transition(field=state, source='NEW', target='STAGE2_IN_PROGRESS')
    def run_stage2(self):
        """Triggered by user clicking 'Retrieve Context Reports'"""
        enabled_services = self.property_list.context_options.get_enabled_services()
        for service_name in enabled_services:
            ContextData.objects.create(
                property=self,
                service_name=service_name,
                status='PENDING'
            )
            run_service_task.delay(self.id, service_name)

    @transition(field=state, source='STAGE2_IN_PROGRESS', target='STAGE2_COMPLETE')
    def complete_stage2(self):
        """Called by signal handler when all services done"""
        pass

    @transition(field=state, source=['STAGE2_COMPLETE', 'STAGE3_COMPLETE'], target='STAGE3_IN_PROGRESS')
    def run_stage3(self):
        """Triggered by user clicking 'Calculate Rating'"""
        calculate_rating_task.delay(self.id)

    @transition(field=state, source='STAGE3_IN_PROGRESS', target='STAGE3_COMPLETE')
    def complete_stage3(self):
        """Called by rating task when complete"""
        pass

    @transition(field=state, source=['STAGE2_COMPLETE', 'STAGE3_IN_PROGRESS', 'STAGE3_COMPLETE'], target='STAGE2_IN_PROGRESS')
    def rerun_services(self, service_names):
        """Triggered by field change or manual retry"""
        for service_name in service_names:
            ContextData.objects.update_or_create(
                property=self,
                service_name=service_name,
                defaults={'status': 'PENDING'}
            )
            run_service_task.delay(self.id, service_name)
```

---

## Implementation Priority

Based on architectural decisions, here's the recommended implementation order:

### Phase 1: Core Infrastructure (Weeks 1-2)
1. Django models (Property, PropertyList, ContextOptions, RatingCriteria, ContextData)
2. State machines (django-fsm integration)
3. WebSocket infrastructure (Django Channels setup)
4. Redis cache configuration

### Phase 2: Stage 1 - Creation (Weeks 3-4)
5. Property List CRUD
6. Property creation (manual form, extract from text/URL)
7. Deduplication logic
8. Saved locations feature

### Phase 3: Stage 2 - Context Retrieval (Weeks 5-7)
9. Context Options configuration UI
10. IContextService interface + factory
11. Concrete service implementations (Crime, Schools, Broadband, Mobile, POI)
12. Celery tasks for async execution
13. Service completion aggregation (signals + WebSocket)
14. Caching layer (Redis integration)
15. Manual trigger buttons (individual + bulk)
16. Progress indicators

### Phase 4: Stage 2 - Advanced Features (Week 8)
17. Service retry mechanism
18. Field change detection + confirmation dialog
19. Context options modification (add/remove services)
20. Failed service handling

### Phase 5: Stage 3 - Rating System (Weeks 9-10)
21. Rating Criteria configuration UI
22. Copy-on-write implementation for criteria
23. Criterion scoring strategies (normalization, inverted, etc.)
24. Dealbreaker logic
25. Overall rating calculation
26. Rating trigger (manual, individual + bulk)

### Phase 6: Collaboration & Polish (Weeks 11-12)
27. User permissions (viewers, contributors)
28. Real-time collaboration (WebSocket for multi-user edits)
29. Comments and tags
30. UI/UX refinements

---

## API Endpoint Summary

Based on decisions, here are the required API endpoints:

### Property Lists
```
GET    /api/property-lists/                    # List all lists for user
POST   /api/property-lists/                    # Create new list
GET    /api/property-lists/{id}/               # Get list details
PUT    /api/property-lists/{id}/               # Update list
DELETE /api/property-lists/{id}/               # Delete list
POST   /api/property-lists/{id}/bulk-stage2/   # Bulk retrieve reports
POST   /api/property-lists/{id}/bulk-stage3/   # Bulk calculate ratings
```

### Properties
```
GET    /api/properties/                        # List all properties for user
POST   /api/properties/                        # Create property
GET    /api/properties/{id}/                   # Get property details
PUT    /api/properties/{id}/                   # Update property (triggers field change logic)
DELETE /api/properties/{id}/                   # Delete property
POST   /api/properties/{id}/run-stage2/        # Trigger Stage 2 for property
POST   /api/properties/{id}/run-stage3/        # Trigger Stage 3 for property
POST   /api/properties/{id}/retry-service/     # Retry failed service
```

### Context Options
```
GET    /api/context-options/{list_id}/         # Get context options for list
PUT    /api/context-options/{list_id}/         # Update context options
```

### Rating Criteria
```
GET    /api/rating-criteria/                   # List all criteria (user's + templates)
POST   /api/rating-criteria/                   # Create new criteria
GET    /api/rating-criteria/{id}/              # Get criteria details
PUT    /api/rating-criteria/{id}/              # Update criteria (triggers copy-on-write if shared)
DELETE /api/rating-criteria/{id}/              # Delete criteria
```

### Context Data
```
GET    /api/context-data/?property={id}        # Get all context data for property
GET    /api/context-data/{id}/                 # Get specific context data
```

---

## WebSocket Events

### Channels
```
property_{id}           # Property-specific updates
property_list_{id}      # List-wide updates
```

### Message Types

**From Backend to Frontend:**
```javascript
// Service progress update
{
    type: 'service_update',
    service: 'crime',
    status: 'COMPLETE',  // or 'FAILED', 'IN_PROGRESS'
    property_id: 123,
    property_state: 'STAGE2_COMPLETE',
    progress: {
        total: 5,
        complete: 3,
        failed: 1,
        in_progress: 1
    }
}

// Rating calculation update
{
    type: 'rating_update',
    property_id: 123,
    property_state: 'STAGE3_COMPLETE',
    overall_rating: 87.5,
    criterion_scores: [...]
}

// Collaborative edit notification
{
    type: 'property_edited',
    property_id: 123,
    edited_by: 'user@example.com',
    fields_changed: ['price', 'bedrooms']
}
```

---

## Conclusion

All architectural decisions have been documented and are ready for implementation. The next steps are:

1. ✅ Create state machine diagrams
2. ✅ Update existing workflow diagrams
3. ✅ Create Stage 3 rating workflow
4. ✅ Create automatic rerun workflows
5. ✅ Create service error/retry flows

These diagrams will be generated next, incorporating all decisions from this document.
