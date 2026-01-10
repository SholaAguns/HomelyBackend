# Service Error and Retry Flow
**Date:** 2026-01-06
**Diagram Type:** Detailed Workflow
**Purpose:** Shows how service failures are handled and how users can retry failed services

---

## Overview

When context services call external APIs, failures can occur due to:
- Network timeouts
- API rate limiting
- Invalid/malformed data
- External service downtime
- Authentication errors

The Homely system handles these failures gracefully with:
1. **Error classification** (transient vs. permanent)
2. **Automatic retries** with exponential backoff (Celery-level)
3. **Manual retries** (user-initiated)
4. **Partial success** (property completes even with failed services)
5. **Detailed error logging** for debugging

---

## Workflow: Service Execution with Error Handling

```
┌─────────────────────────────────────┐
│ Entry Point                          │
│                                     │
│ run_service_task.delay(              │
│   property_id=123,                  │
│   service_name='crime'              │
│ )                                   │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Celery Worker: Task Starts            │
│                                       │
│ @shared_task(                         │
│   bind=True,                          │
│   max_retries=3,                      │
│   default_retry_delay=60              │
│ )                                     │
│ def run_service_task(self,            │
│         property_id, service_name):   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Update ContextData Status:            │
│ IN_PROGRESS                           │
│                                       │
│ context_data, created =               │
│   ContextData.objects.                │
│     update_or_create(                 │
│       property_id=property_id,        │
│       service_name=service_name,      │
│       defaults={                      │
│         'status': 'IN_PROGRESS',      │
│         'started_at': now()           │
│       }                               │
│     )                                 │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Send WebSocket Update                 │
│                                       │
│ channel_layer.group_send(             │
│   f'property_{property_id}',          │
│   {                                   │
│     'type': 'service_update',         │
│     'service': service_name,          │
│     'status': 'IN_PROGRESS'           │
│   }                                   │
│ )                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Load Property and Service Config      │
│                                       │
│ property = Property.objects.get(      │
│   pk=property_id                      │
│ )                                     │
│                                       │
│ service_class = SERVICE_REGISTRY[     │
│   service_name                        │
│ ]                                     │
│ service = service_class()             │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ TRY BLOCK BEGINS                      │
│ ──────────────────────────────────    │
│                                       │
│ try:                                  │
│   # Service execution                 │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Check Cache                           │
│                                       │
│ cache_key = service.get_cache_key(    │
│   property                            │
│ )                                     │
│ cached_data = cache.get(cache_key)    │
└──────────────┬────────────────────────┘
               │
      ┌────────┴────────┐
      │                 │
  Cache Hit        Cache Miss
      │                 │
      ▼                 │
┌──────────┐            │
│ Use      │            │
│ cached   │            │
│ data     │            │
│          │            │
│ Skip API │            │
│ call     │            │
└────┬─────┘            │
     │                  │
     │                  ▼
     │      ┌───────────────────────────┐
     │      │ Fetch Data from API       │
     │      │                           │
     │      │ data = service.           │
     │      │   fetch_data(property)    │
     │      │                           │
     │      │ (Calls external API)      │
     │      └──────────┬────────────────┘
     │                 │
     └─────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Validate Response Data                │
│                                       │
│ if not service.validate_data(data):   │
│   raise DataValidationError(          │
│     "Invalid response format"         │
│   )                                   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Store in Cache                        │
│                                       │
│ cache.set(                            │
│   cache_key,                          │
│   data,                               │
│   timeout=service.get_cache_ttl()     │
│ )                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Update ContextData: SUCCESS           │
│                                       │
│ context_data.status = 'COMPLETE'      │
│ context_data.data = data              │
│ context_data.error_message = None     │
│ context_data.completed_at = now()     │
│ context_data.save()                   │
│ # → Triggers post_save signal         │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Success Path END                      │
│                                       │
│ Signal handler checks completion      │
│ WebSocket sends success update        │
│ Task returns normally                 │
└───────────────────────────────────────┘
               │
               ▼
            [END]

┌───────────────────────────────────────┐
│ EXCEPTION HANDLER                     │
│ ──────────────────────────────────    │
│                                       │
│ except Exception as exc:              │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Classify Error Type                   │
└──────────────┬────────────────────────┘
               │
     ┌─────────┴─────────┬──────────────────┬─────────────┐
     │                   │                  │             │
  Transient         Rate Limit       Permanent      Unknown
  (Network)         (429, 503)       (400, 404)       (500)
     │                   │                  │             │
     ▼                   ▼                  ▼             ▼
┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────┐
│ Timeout  │  │ Too Many     │  │ Invalid Data │  │ Server │
│ DNS      │  │ Requests     │  │ Auth Failed  │  │ Error  │
│ Refused  │  │              │  │ Not Found    │  │        │
└────┬─────┘  └──────┬───────┘  └──────┬───────┘  └────┬───┘
     │               │                  │               │
     │               │                  │               │
     └───────────────┴──────────────────┴───────────────┘
                     │
                     ▼
          ┌──────────────────────────┐
          │ Log Error Details        │
          │                          │
          │ logger.error(            │
          │   f"{service_name}       │
          │    failed: {exc}",       │
          │   extra={                │
          │     'property_id': ...,  │
          │     'error_type': ...,   │
          │     'retries': self.     │
          │       request.retries,   │
          │     'traceback': ...     │
          │   }                      │
          │ )                        │
          └──────────┬───────────────┘
                     │
                     ▼
          ┌──────────────────────────────┐
          │ Check: Should Retry?         │
          │                              │
          │ IF error is transient AND    │
          │    self.request.retries < 3: │
          └──────────┬───────────────────┘
                     │
           ┌─────────┴─────────┐
           │                   │
         YES                  NO
           │                   │
           │                   ▼
           │         ┌────────────────────────┐
           │         │ Mark as FAILED         │
           │         │                        │
           │         │ context_data.status =  │
           │         │   'FAILED'             │
           │         │ context_data.          │
           │         │   error_message = str( │
           │         │     exc)               │
           │         │ context_data.          │
           │         │   error_type =         │
           │         │     classify_error(exc)│
           │         │ context_data.          │
           │         │   failed_at = now()    │
           │         │ context_data.save()    │
           │         │ # → Triggers post_save │
           │         └──────────┬─────────────┘
           │                    │
           │                    ▼
           │         ┌────────────────────────┐
           │         │ Send WebSocket Error   │
           │         │                        │
           │         │ channel_layer.         │
           │         │   group_send(          │
           │         │   f'property_{id}',    │
           │         │   {                    │
           │         │     'type':            │
           │         │       'service_update',│
           │         │     'service': name,   │
           │         │     'status': 'FAILED',│
           │         │     'error': msg       │
           │         │   }                    │
           │         │ )                      │
           │         └──────────┬─────────────┘
           │                    │
           │                    ▼
           │                 [END]
           │
           ▼
┌─────────────────────────────────────┐
│ Retry with Exponential Backoff     │
│                                     │
│ retry_count = self.request.retries  │
│ countdown = 60 * (2 ** retry_count) │
│ # 1st retry: 60s                    │
│ # 2nd retry: 120s                   │
│ # 3rd retry: 240s                   │
│                                     │
│ raise self.retry(                   │
│   exc=exc,                          │
│   countdown=countdown               │
│ )                                   │
│ # Celery requeues task              │
└─────────────────────────────────────┘
               │
               ▼
    (Task requeued, will retry
     after countdown seconds)
```

---

## Manual Retry Workflow

### Trigger
User clicks "Retry" button next to a failed service on Property detail page.

### Flow

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ Property Detail Page                 │
│ ┌─────────────────────────────────┐ │
│ │ Reports:                        │ │
│ │ ✓ Crime - Ready                 │ │
│ │ ✓ Schools - Ready               │ │
│ │ ✗ Broadband - Failed (timeout)  │ │
│ │   [Retry]                       │ │
│ │ ✓ Mobile - Ready                │ │
│ └─────────────────────────────────┘ │
│                                     │
│ User clicks [Retry] for Broadband   │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Send Retry Request          │
│                                       │
│ POST /api/properties/{id}/            │
│      retry-service/                   │
│                                       │
│ Body: {                               │
│   service_name: "broadband"           │
│ }                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend API View                      │
│                                       │
│ 1. Authenticate user                  │
│ 2. Authorize (user can edit property)│
│ 3. Load property                      │
│ 4. Validate service exists            │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Check Current Status         │
│                                       │
│ context_data = ContextData.objects.   │
│   get(                                │
│     property=property,                │
│     service_name='broadband'          │
│   )                                   │
│                                       │
│ if context_data.status != 'FAILED':   │
│   return HTTP 400 "Service not failed"│
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Reset Status                 │
│                                       │
│ context_data.status = 'PENDING'       │
│ context_data.error_message = None     │
│ context_data.error_type = None        │
│ context_data.retry_count += 1         │
│ context_data.save()                   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Clear Cache                  │
│ (Force fresh API call)                │
│                                       │
│ service = BroadbandService()          │
│ cache_key = service.get_cache_key(    │
│   property                            │
│ )                                     │
│ cache.delete(cache_key)               │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Queue Retry Task             │
│                                       │
│ run_service_task.delay(               │
│   property.id,                        │
│   'broadband'                         │
│ )                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Return Response              │
│                                       │
│ HTTP 200 OK                           │
│ {                                     │
│   "success": true,                    │
│   "service": "broadband",             │
│   "status": "PENDING",                │
│   "message": "Retry initiated"        │
│ }                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Update UI                   │
│                                       │
│ • Change button text: [Retry] →      │
│   [Retrying...]                       │
│ • Show spinner                        │
│ • Subscribe to WebSocket for updates  │
└──────────────┬────────────────────────┘
               │
               │ (Task executes - see main flow above)
               │
               ▼
┌───────────────────────────────────────┐
│ Outcome 1: Success                    │
│                                       │
│ WebSocket message:                    │
│ {                                     │
│   service: 'broadband',               │
│   status: 'COMPLETE',                 │
│   data: {...}                         │
│ }                                     │
│                                       │
│ UI updates:                           │
│ ✓ Broadband - Ready                   │
│ [View Details]                        │
└───────────────────────────────────────┘
               │
               ▼
            [END]

┌───────────────────────────────────────┐
│ Outcome 2: Failed Again               │
│                                       │
│ WebSocket message:                    │
│ {                                     │
│   service: 'broadband',               │
│   status: 'FAILED',                   │
│   error: 'API timeout (attempt 2)'    │
│ }                                     │
│                                       │
│ UI updates:                           │
│ ✗ Broadband - Failed (attempt 2)      │
│ [Retry Again]                         │
│                                       │
│ (User can retry multiple times)       │
└───────────────────────────────────────┘
               │
               ▼
            [END]
```

---

## Error Types and Messages

### 1. Network Errors (Transient - Retry Automatically)

**Exceptions:**
- `requests.exceptions.Timeout`
- `requests.exceptions.ConnectionError`
- `socket.gaierror` (DNS failure)

**Error Classification:**
```python
error_type = 'NETWORK_ERROR'
is_transient = True
should_retry = True
```

**User-facing Message:**
```
"Network error - will retry automatically"
```

### 2. Rate Limiting (Transient - Retry with Backoff)

**HTTP Status Codes:**
- `429 Too Many Requests`
- `503 Service Unavailable`

**Error Classification:**
```python
error_type = 'RATE_LIMIT'
is_transient = True
should_retry = True
retry_delay = 300  # 5 minutes
```

**User-facing Message:**
```
"API rate limit exceeded - retrying in 5 minutes"
```

### 3. Authentication Errors (Permanent - Manual Investigation)

**HTTP Status Codes:**
- `401 Unauthorized`
- `403 Forbidden`

**Error Classification:**
```python
error_type = 'AUTH_ERROR'
is_transient = False
should_retry = False
```

**User-facing Message:**
```
"Authentication failed - please contact support"
```

### 4. Invalid Data (Permanent - Developer Fix Required)

**HTTP Status Codes:**
- `400 Bad Request`
- `422 Unprocessable Entity`

**Exceptions:**
- `DataValidationError`
- `ValueError`

**Error Classification:**
```python
error_type = 'DATA_ERROR'
is_transient = False
should_retry = False
```

**User-facing Message:**
```
"Invalid property data - unable to retrieve report"
```

### 5. Resource Not Found (Permanent - Expected for Some Properties)

**HTTP Status Codes:**
- `404 Not Found`

**Error Classification:**
```python
error_type = 'NOT_FOUND'
is_transient = False
should_retry = False
```

**User-facing Message:**
```
"No data available for this location"
```

**Examples:**
- Broadband data not available in rural areas
- Crime data not available for new postcodes

### 6. Server Errors (Transient - Retry)

**HTTP Status Codes:**
- `500 Internal Server Error`
- `502 Bad Gateway`
- `504 Gateway Timeout`

**Error Classification:**
```python
error_type = 'SERVER_ERROR'
is_transient = True
should_retry = True
```

**User-facing Message:**
```
"External service error - will retry automatically"
```

---

## Error Classification Implementation

```python
# services/error_handler.py

class ServiceError(Exception):
    """Base exception for service errors"""
    def __init__(self, message, error_type, is_transient=False):
        super().__init__(message)
        self.error_type = error_type
        self.is_transient = is_transient

def classify_error(exc):
    """Classify exception and determine retry strategy"""

    # Network errors
    if isinstance(exc, (
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
        socket.gaierror
    )):
        return {
            'type': 'NETWORK_ERROR',
            'message': 'Network connection failed',
            'is_transient': True,
            'should_retry': True,
            'user_message': 'Network error - will retry automatically'
        }

    # HTTP errors
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code

        if status_code == 429:
            return {
                'type': 'RATE_LIMIT',
                'message': 'API rate limit exceeded',
                'is_transient': True,
                'should_retry': True,
                'retry_delay': 300,
                'user_message': 'API rate limit - retrying in 5 minutes'
            }

        elif status_code in [401, 403]:
            return {
                'type': 'AUTH_ERROR',
                'message': 'Authentication failed',
                'is_transient': False,
                'should_retry': False,
                'user_message': 'Authentication failed - contact support'
            }

        elif status_code == 404:
            return {
                'type': 'NOT_FOUND',
                'message': 'Resource not found',
                'is_transient': False,
                'should_retry': False,
                'user_message': 'No data available for this location'
            }

        elif status_code >= 500:
            return {
                'type': 'SERVER_ERROR',
                'message': f'Server error: {status_code}',
                'is_transient': True,
                'should_retry': True,
                'user_message': 'External service error - will retry'
            }

    # Data validation errors
    if isinstance(exc, (ValueError, DataValidationError)):
        return {
            'type': 'DATA_ERROR',
            'message': 'Invalid data format',
            'is_transient': False,
            'should_retry': False,
            'user_message': 'Invalid property data - unable to retrieve'
        }

    # Unknown error
    return {
        'type': 'UNKNOWN_ERROR',
        'message': str(exc),
        'is_transient': False,
        'should_retry': False,
        'user_message': 'An unexpected error occurred - please retry'
    }
```

---

## Retry Strategy with Exponential Backoff

### Celery Task Configuration

```python
# tasks.py
@shared_task(
    bind=True,
    max_retries=3,
    autoretry_for=(
        requests.exceptions.Timeout,
        requests.exceptions.ConnectionError,
    ),
    retry_backoff=True,  # Enable exponential backoff
    retry_backoff_max=600,  # Max 10 minutes
    retry_jitter=True  # Add randomness to prevent thundering herd
)
def run_service_task(self, property_id, service_name):
    try:
        # Service execution...
        pass

    except Exception as exc:
        error_info = classify_error(exc)

        if error_info['should_retry'] and self.request.retries < self.max_retries:
            # Calculate backoff
            retry_count = self.request.retries
            countdown = error_info.get('retry_delay', 60 * (2 ** retry_count))

            logger.warning(
                f"Service {service_name} failed (attempt {retry_count + 1}/3), "
                f"retrying in {countdown}s: {exc}"
            )

            # Update ContextData with retry info
            ContextData.objects.filter(
                property_id=property_id,
                service_name=service_name
            ).update(
                status='PENDING',
                error_message=f"Retrying... (attempt {retry_count + 1}/3)"
            )

            raise self.retry(exc=exc, countdown=countdown)

        else:
            # Max retries reached or permanent error
            logger.error(
                f"Service {service_name} permanently failed: {exc}",
                exc_info=True
            )

            ContextData.objects.filter(
                property_id=property_id,
                service_name=service_name
            ).update(
                status='FAILED',
                error_message=error_info['user_message'],
                error_type=error_info['type'],
                failed_at=timezone.now()
            )
```

---

## UI Components for Error Display

### Property Detail Page - Service Status List

```
Reports:

✓ Crime Report - Ready
  Last updated: 2 hours ago
  [View Details]

✓ Schools Report - Ready
  Last updated: 2 hours ago
  [View Details]

✗ Broadband Report - Failed
  Error: Network error - will retry automatically
  Next retry: in 57 seconds
  Attempt: 2/3
  [Retry Now]

✓ Mobile Coverage - Ready
  Last updated: 2 hours ago
  [View Details]

✓ Places of Interest - Ready
  Last updated: 2 hours ago
  [View Details]
```

### Property Detail Page - Error Alert

```
┌─────────────────────────────────────────┐
│ ⚠ 1 report failed to retrieve           │
│                                         │
│ Broadband data could not be retrieved   │
│ due to a network error. The system will │
│ automatically retry 2 more times.       │
│                                         │
│ [Retry Now] [Dismiss]                   │
└─────────────────────────────────────────┘
```

### Property Card - Error Badge

```
┌─────────────────────────────────────┐
│ 123 Main Street, London             │
│                                     │
│ £350,000 • 3 bed • 2 bath           │
│                                     │
│ Status: Stage 2 Complete ⚠          │
│ Reports: 4/5 ready (1 failed)       │
│                                     │
│ [View Details]  [Edit]              │
└─────────────────────────────────────┘
```

---

## Error Logging and Monitoring

### Structured Logging

```python
import structlog

logger = structlog.get_logger()

# In service task
logger.error(
    "service_execution_failed",
    service_name=service_name,
    property_id=property_id,
    property_postcode=property.postcode,
    error_type=error_info['type'],
    error_message=str(exc),
    is_transient=error_info['is_transient'],
    retry_count=self.request.retries,
    user_id=property.property_list.owner_id,
    timestamp=timezone.now().isoformat()
)
```

**Log Output:**
```json
{
  "event": "service_execution_failed",
  "service_name": "broadband",
  "property_id": 123,
  "property_postcode": "SW1A 1AA",
  "error_type": "NETWORK_ERROR",
  "error_message": "Connection timeout after 30s",
  "is_transient": true,
  "retry_count": 1,
  "user_id": 42,
  "timestamp": "2026-01-06T14:30:45Z"
}
```

### Error Metrics (for Monitoring Dashboard)

```python
# Track error rates
from prometheus_client import Counter, Histogram

service_errors = Counter(
    'service_errors_total',
    'Total service errors',
    ['service_name', 'error_type']
)

service_duration = Histogram(
    'service_duration_seconds',
    'Service execution time',
    ['service_name', 'status']
)

# In task
service_errors.labels(
    service_name='broadband',
    error_type='NETWORK_ERROR'
).inc()
```

---

## Admin Interface for Error Investigation

### Django Admin: ContextData Error View

```python
# admin.py
@admin.register(ContextData)
class ContextDataAdmin(admin.ModelAdmin):
    list_display = [
        'property', 'service_name', 'status',
        'created_at', 'error_type', 'retry_count'
    ]
    list_filter = ['status', 'service_name', 'error_type']
    search_fields = ['property__postcode', 'error_message']

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Show failed services first
        return qs.order_by('-status', '-created_at')

    readonly_fields = ['error_traceback', 'created_at', 'updated_at']

    fieldsets = (
        ('Basic Info', {
            'fields': ('property', 'service_name', 'status')
        }),
        ('Data', {
            'fields': ('data',),
            'classes': ('collapse',)
        }),
        ('Error Details', {
            'fields': (
                'error_type',
                'error_message',
                'error_traceback',
                'retry_count',
                'failed_at'
            ),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'started_at', 'completed_at')
        }),
    )

# Error summary view
class ErrorSummaryAdmin(admin.ModelAdmin):
    """Custom admin view for error analytics"""
    change_list_template = 'admin/error_summary.html'

    def changelist_view(self, request, extra_context=None):
        # Aggregate error statistics
        error_stats = ContextData.objects.filter(
            status='FAILED'
        ).values(
            'service_name', 'error_type'
        ).annotate(
            count=models.Count('id')
        ).order_by('-count')

        extra_context = extra_context or {}
        extra_context['error_stats'] = error_stats

        return super().changelist_view(request, extra_context=extra_context)
```

---

## Recovery Strategies

### 1. Automatic Healing for Common Failures

**Strategy:** Detect patterns and auto-fix

**Example:** Postcode normalization
```python
def fetch_crime_data(postcode):
    # Normalize postcode before API call
    normalized = normalize_postcode(postcode)  # "sw1a1aa" → "SW1A 1AA"

    try:
        return call_police_api(normalized)
    except HTTPError as e:
        if e.status_code == 400:
            # Try alternative formats
            for format_attempt in [
                normalized.replace(' ', ''),  # "SW1A1AA"
                normalized.lower()            # "sw1a 1aa"
            ]:
                try:
                    return call_police_api(format_attempt)
                except HTTPError:
                    continue

        raise  # Give up, let error handler take over
```

### 2. Fallback Data Sources

**Strategy:** Use alternative APIs if primary fails

**Example:** Broadband data
```python
class BroadbandService(IContextService):
    def fetch_data(self, property):
        try:
            # Primary: Ofcom API
            return self.fetch_from_ofcom(property.postcode)
        except Exception as e:
            logger.warning(f"Ofcom failed, trying fallback: {e}")

            try:
                # Fallback: Third-party aggregator
                return self.fetch_from_broadband_checker(property.postcode)
            except Exception:
                # Both failed, raise original exception
                raise e
```

### 3. Partial Data Acceptance

**Strategy:** Accept incomplete but useful data

**Example:** POI service
```python
def fetch_places_of_interest(property):
    results = {}
    enabled_types = property.property_list.context_options.poi_types

    for poi_type in enabled_types:
        try:
            results[poi_type] = call_google_places_api(
                property.coordinates,
                poi_type
            )
        except Exception as e:
            logger.warning(f"POI type {poi_type} failed: {e}")
            results[poi_type] = None  # Partial failure

    # Success if at least 1 type succeeded
    if any(results.values()):
        return results
    else:
        raise ServiceError("All POI types failed")
```

---

## Summary

**Service Error and Retry Flow:**

1. **Service execution** in Celery task with try/except
2. **Error classification** (transient vs. permanent)
3. **Automatic retries** with exponential backoff (max 3 attempts)
4. **Status tracking** in ContextData (FAILED + error details)
5. **User notification** via WebSocket with user-friendly messages
6. **Manual retry** option via API endpoint
7. **Partial success** policy (property completes even with failures)
8. **Error logging** for monitoring and debugging
9. **Recovery strategies** (normalization, fallbacks, partial data)

This ensures robust handling of external API failures while maintaining good UX.
