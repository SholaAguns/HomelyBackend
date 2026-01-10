# Stage 2: Context Retrieval

Stage 2 focuses on asynchronously gathering contextual information about properties from external APIs. Services run in parallel with progressive loading, allowing users to view completed data while other services are still running.

---

## Overview

**Purpose:** Enrich property data with location-based contextual information

**Triggering:** Manual (user clicks button) - NOT automatic

**Execution:** Parallel Celery tasks with WebSocket progress updates

**Completion Policy:** Partial success - properties complete Stage 2 even if some services fail

---

## Available Context Services

### 1. Crime Statistics
- **Source:** UK Police API (FREE)
- **Data:** Crime rates by category for postcode sector
- **Cache:** 30 days (by postcode sector)

### 2. School Ratings
- **Source:** Department for Education API (FREE)
- **Data:** Ofsted ratings for nearby schools
- **Cache:** 90 days (by postcode)

### 3. Broadband Speed
- **Source:** Ofcom API (Likely FREE)
- **Data:** Available speeds, providers
- **Cache:** 7 days (by UPRN)

### 4. Mobile Coverage
- **Source:** Ofcom API (Likely FREE)
- **Data:** Coverage quality by network provider
- **Cache:** 7 days (by postcode)

### 5. Places of Interest (13 Types)
- **Source:** Google Maps API ($200 free/month)
- **Data:** Distance to nearest, count within radius
- **Cache:** 30 days (by rounded coordinates)

**POI Types:**
- school, hospital, park, supermarket, grocery
- restaurant, gym, pharmacy, station
- mosque, church, temple, library, shopping, airport

---

## Stage 2 Workflow

### 1. User Clicks "Retrieve Context Reports" Button

**Entry Points:**
- **Individual Property:** Property detail page → "Retrieve Context Reports" button
- **Bulk Operation:** Property List page → "Retrieve Reports for All" button (only enabled properties in `New` state)

**Pre-Condition Check:**
- **If context options NOT configured:** Button redirects to context options configuration form
- **If context options configured:** Button is enabled and triggers Stage 2

### 2. Backend Initiates Service Retrieval

**State Transition:** `Property.state: New → Stage2InProgress`

**Process:**
```python
@transition(field=state, source='New', target='Stage2InProgress')
def run_stage2(self):
    """User triggers Stage 2 via button click"""
    enabled_services = self.property_list.context_options.get_enabled_services()

    for service_name in enabled_services:
        ContextData.objects.create(
            property=self,
            service_name=service_name,
            status='PENDING'
        )
        run_service_task.delay(self.id, service_name)  # Celery task
```

**Celery Tasks Launch:**
- Each service runs as independent Celery task
- Tasks execute in parallel (no sequential dependencies)
- Each task updates its own `ContextData` record

### 3. Service Execution (Parallel)

**Service Factory Pattern:**
```python
class IContextService(ABC):
    @abstractmethod
    def fetch_data(self, property): pass

    @abstractmethod
    def get_cache_key(self, property): pass

    @abstractmethod
    def get_cache_ttl(self): pass

# Concrete implementations
class CrimeService(IContextService):
    def get_cache_key(self, property):
        return f"crime:{property.postcode[:4]}"  # Postcode sector

    def get_cache_ttl(self):
        return 86400 * 30  # 30 days

class BroadbandService(IContextService):
    def get_cache_key(self, property):
        return f"broadband:{property.uprn}"  # UPRN-specific

    def get_cache_ttl(self):
        return 86400 * 7  # 7 days
```

**Execution Flow (Per Service):**
1. Check Redis cache using service-specific cache key
2. **If cached:** Load from cache, skip API call
3. **If not cached:** Call external API
4. Handle response and errors (see Error Handling below)
5. Write result to database (`ContextData` record)
6. Store in Redis cache with service-specific TTL
7. Update `ContextData.status` to `COMPLETE` or `FAILED`
8. Send WebSocket event to frontend

### 4. Progressive Loading with WebSocket Updates

**Event Propagation (Decision #9-10):**
- Backend writes `ContextData` status to database
- Backend sends WebSocket event to frontend
- Frontend updates UI immediately (no polling)

**WebSocket Message Example:**
```javascript
{
  type: 'service_update',
  service: 'crime',
  status: 'COMPLETE',
  property_id: 123,
  property_state: 'Stage2InProgress',
  data: {
    crime_rating: 'Low',
    crime_count: 15,
    // ... service-specific data
  },
  progress: {
    total: 5,
    complete: 2,
    failed: 0,
    in_progress: 3
  }
}
```

**Frontend Behavior:**
- Display completed service data immediately
- Show loading spinners for in-progress services
- Show error indicators for failed services
- Update progress bar: "2/5 services complete"

### 5. Service State Tracking

**ContextData States:**
- **PENDING** - Task queued, not yet started
- **IN_PROGRESS** - API call in progress
- **COMPLETE** - Data successfully retrieved and stored
- **FAILED** - All retry attempts exhausted

**Database Record (Per Service):**
```python
class ContextData(models.Model):
    property = models.ForeignKey(Property)
    service_name = models.CharField(max_length=50)  # 'crime', 'schools', etc.
    status = models.CharField(max_length=20)  # PENDING, IN_PROGRESS, COMPLETE, FAILED
    data = models.JSONField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    error_type = models.CharField(max_length=50, null=True)  # 'network', 'rate_limit', etc.
    retry_count = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
```

### 6. Error Handling and Retry Mechanism

**Error Classification (6 Types):**
- **Network errors** - Timeout, connection refused (transient, retry)
- **Rate limit** - 429 status code (transient, retry with longer delay)
- **Auth errors** - 401/403 (permanent, manual fix required)
- **Data errors** - Invalid property data (permanent, mark failed)
- **Not found** - 404 (permanent, mark failed)
- **Server errors** - 500+ (transient, retry)

**Automatic Retry with Exponential Backoff:**
```python
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_service_task(self, property_id, service_name):
    try:
        service = ServiceFactory.create(service_name)
        data = service.fetch_data(property_id)

        ContextData.objects.filter(
            property_id=property_id,
            service_name=service_name
        ).update(status='COMPLETE', data=data)

    except Exception as exc:
        error_info = classify_error(exc)

        if error_info['should_retry'] and self.request.retries < 3:
            retry_count = self.request.retries
            countdown = 60 * (2 ** retry_count)  # 60s, 120s, 240s
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # Mark as failed
            ContextData.objects.filter(
                property_id=property_id,
                service_name=service_name
            ).update(
                status='FAILED',
                error_type=error_info['error_type'],
                error_message=str(exc)
            )
```

**Manual Retry Option:**
- Failed services show "Retry" button in UI
- User can retry individual failed services
- Retry reuses same Celery task logic

### 7. Stage 2 Completion

**Automatic Transition:**
```python
@transition(field=state, source='Stage2InProgress', target='Stage2Complete')
def complete_stage2(self):
    """Called automatically when all services complete/fail"""
    pass
```

**Completion Trigger:**
- Backend checks if all `ContextData` records have status `COMPLETE` or `FAILED`
- When all services finished (regardless of success/failure), property transitions to `Stage2Complete`
- WebSocket event notifies frontend of state change

**Partial Success Policy (Decision #11-12):**
- Property completes Stage 2 even if some services fail
- Failed services are marked with status badge in UI
- User can retry failed services individually
- Stage 3 can proceed even with failed services (rating criteria may not use all services)

**UI After Completion:**
- "Retrieve Context Reports" button replaced with "View Reports" button
- **"Calculate Rating" button enabled** (if rating criteria configured)
- Failed services show "Failed - Retry" button

---

## Automatic Reruns

### Context Options Modification (Decision #7-8)

**Adding New Service:**
- User edits context options and enables new service
- Backend automatically runs new service for ALL existing properties beyond `New` state
- No confirmation dialog (assumed user intention)

**Removing Service:**
- Confirmation dialog: "Delete context data for [service]?"
- If confirmed: Delete `ContextData` records for that service across all properties

### Property Field Changes (Decision #15-16)

**Field Dependency Matrix:**
```python
FIELD_SERVICE_DEPENDENCIES = {
    'postcode': ['crime', 'schools', 'poi', 'broadband', 'mobile'],
    'latitude': ['poi'],
    'longitude': ['poi'],
    # All other fields: []
}
```

**Workflow:**
1. User edits property field (e.g., postcode)
2. Backend detects field changed
3. Backend looks up affected services from dependency matrix
4. **If services affected:** Show confirmation dialog with API cost warning
5. **If user confirms:** Rerun affected services (state: `Stage2Complete → Stage2InProgress`)
6. **User preference:** "Don't ask again" checkbox available

**Confirmation Dialog Example:**
```
┌─────────────────────────────────────┐
│ Rerun Context Services?             │
│                                     │
│ Changing postcode will re-retrieve: │
│   • Crime Report                    │
│   • Schools Report                  │
│   • Places of Interest              │
│   • Broadband Info                  │
│   • Mobile Coverage                 │
│                                     │
│ This may incur API costs.           │
│                                     │
│ ☐ Don't ask again                   │
│                                     │
│ [Cancel] [Save and Rerun]           │
└─────────────────────────────────────┘
```

---

## Caching Strategy

**Smart Caching (Decision #13-14):**
Each service implements its own caching logic based on data volatility and cost.

**Cache Key Examples:**
```python
# Crime - By postcode sector (broader area)
f"crime:{postcode[:4]}"  # "SW1A" -> Multiple properties share cache

# Broadband - By UPRN (property-specific)
f"broadband:{uprn}"  # Each property unique

# Schools - By postcode (moderate specificity)
f"schools:{postcode}"  # "SW1A 1AA"

# POI - By rounded coordinates (grid-based)
f"poi:school:{round(lat, 3)}:{round(lng, 3)}"  # Rounded to ~100m grid
```

**TTL Values:**
- Crime: 30 days (data changes slowly)
- Schools: 90 days (Ofsted ratings very stable)
- Broadband: 7 days (infrastructure changes occasionally)
- Mobile: 7 days (network upgrades occasional)
- POI: 30 days (physical locations stable)

**Benefits:**
- Reduced API costs (many cache hits)
- Faster response times
- Reduced external API dependency
- Shared cache between properties with same location characteristics

---

## UI Components

### Property Detail Page - Stage 2 In Progress

```
┌─────────────────────────────────────────────────┐
│ 123 Main Street, London SW1A 1AA                │
│ £350,000 • 3 bed • 2 bath                       │
│                                                 │
│ Status: Stage 2 In Progress (3/5 complete)      │
│                                                 │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━      │
│ 60% complete                                    │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Context Reports:                                │
│                                                 │
│ ✓ Crime Report                                  │
│   Low Crime Area (15 incidents/year)            │
│                                                 │
│ ✓ School Ratings                                │
│   3 Good/Outstanding schools within 1 mile      │
│                                                 │
│ ⏳ Broadband Info (Loading...)                  │
│                                                 │
│ ⏳ Mobile Coverage (Loading...)                 │
│                                                 │
│ ✗ Places of Interest (Failed - Network error)   │
│   [Retry]                                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Property Detail Page - Stage 2 Complete

```
┌─────────────────────────────────────────────────┐
│ 123 Main Street, London SW1A 1AA                │
│ £350,000 • 3 bed • 2 bath                       │
│                                                 │
│ Status: Stage 2 Complete                        │
│                                                 │
│ [Calculate Rating]  [Edit Details]              │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Context Reports:                                │
│                                                 │
│ ✓ Crime Report                                  │
│   Low Crime Area (15 incidents/year)            │
│   [View Details]                                │
│                                                 │
│ ✓ School Ratings                                │
│   3 Good/Outstanding schools within 1 mile      │
│   [View Details]                                │
│                                                 │
│ ✓ Broadband Info                                │
│   Up to 300 Mbps available                      │
│   [View Details]                                │
│                                                 │
│ ✓ Mobile Coverage                               │
│   Good coverage (all networks)                  │
│   [View Details]                                │
│                                                 │
│ ✗ Places of Interest (Failed)                   │
│   Network error during retrieval                │
│   [Retry]                                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Property List Page - Bulk Operations

```
┌─────────────────────────────────────────────────┐
│ My House Hunt                                   │
│ Created: Jan 5, 2026 • 5 properties             │
│                                                 │
│ [Add Property]  [Retrieve Reports for All (2)]  │
│                 [Calculate Ratings for All (3)] │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 123 Main Street, London                 │     │
│ │ Status: New                             │     │
│ │ [Retrieve Reports]                      │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 456 Oak Avenue, Manchester              │     │
│ │ Status: Stage 2 In Progress (2/5)       │     │
│ │ ━━━━━━━━━━░░░░░░░░░░░░░░ 40%           │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 789 Elm Street, Birmingham              │     │
│ │ Status: Stage 2 Complete                │     │
│ │ [Calculate Rating] [View Reports]       │     │
│ └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

---

## API Endpoints

### Stage 2 Triggering
```
POST   /api/properties/{id}/run-stage2/           # Trigger Stage 2 for property
POST   /api/property-lists/{id}/run-stage2-bulk/  # Trigger Stage 2 for all New properties
```

### Service Management
```
GET    /api/properties/{id}/context-data/         # Get all context data for property
GET    /api/properties/{id}/context-data/{service}/ # Get specific service data
POST   /api/properties/{id}/retry-service/{service}/ # Retry failed service
```

### Context Options
```
GET    /api/context-options/{list_id}/            # Get context options
PUT    /api/context-options/{list_id}/            # Update options (triggers reruns)
```

### WebSocket Endpoint
```
ws://host/ws/property-list/{list_id}/             # Real-time service updates
```

---

## Data Models

```python
class ContextOptions(models.Model):
    property_list = models.OneToOneField(PropertyList)

    # Service toggles
    enable_crime = models.BooleanField(default=False)
    enable_schools = models.BooleanField(default=False)
    enable_broadband = models.BooleanField(default=False)
    enable_mobile = models.BooleanField(default=False)

    # POI configuration
    enable_poi = models.BooleanField(default=False)
    poi_types = models.JSONField(default=list)  # ['school', 'hospital', 'park', ...]
    poi_search_radius_meters = models.IntegerField(default=1600)  # ~1 mile

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
        return services

class ContextData(models.Model):
    property = models.ForeignKey(Property, related_name='context_data')
    service_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20)  # PENDING, IN_PROGRESS, COMPLETE, FAILED

    # Service result
    data = models.JSONField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    error_type = models.CharField(max_length=50, null=True)
    retry_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('property', 'service_name')
```

---

## State Transitions

**Property State Machine (Stage 2 Portion):**
```
New ──────────────────────> Stage2InProgress
                              │
                              │ (all services complete/failed)
                              │
                              ▼
Stage2Complete <───────── Stage2InProgress
       │                      ▲
       │                      │
       │ (field change)       │ (rerun services)
       │                      │
       └──────────────────────┘
```

**Transitions:**
- `New → Stage2InProgress` - User clicks "Retrieve Context Reports"
- `Stage2InProgress → Stage2Complete` - All services finished (success or failure)
- `Stage2Complete → Stage2InProgress` - Field change triggers service rerun

---

## For More Details

- **Service error handling:** `documentation/plan/detail/service_error_retry_flow_20260106.md`
- **Automatic reruns:** `documentation/plan/detail/automatic_rerun_workflows_20260106.md`
- **Architecture decisions:** `documentation/plan/detail/architecture_decisions_20260106.md`
- **State machines:** `documentation/plan/detail/state_machine_diagrams_20260106.md`
- **Next stage:** Stage 3 - Rating System.md
