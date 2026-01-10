# Automatic Rerun Workflows
**Date:** 2026-01-06
**Diagram Type:** Detailed Workflows
**Purpose:** Shows how field changes trigger automatic service reruns and rating recalculations

---

## Overview

The Homely system automatically maintains data consistency by detecting when property field changes require:
1. **Service reruns** (e.g., postcode change → rerun Crime, Schools, POI, Broadband, Mobile)
2. **Rating recalculation** (e.g., price change → recalculate overall rating)

This document details three related workflows:
- **Workflow A:** Property Field Edit with Service Dependencies
- **Workflow B:** Property Field Edit with Rating Dependencies Only
- **Workflow C:** Context Options Modification (Bulk Rerun)

---

## Workflow A: Property Field Edit with Service Dependencies

### Trigger
User edits a property field that affects context services (e.g., postcode, coordinates).

### Example Scenario
User changes postcode from "SW1A 1AA" to "N1 9AG"

---

### Detailed Flow

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ Property Edit Form                   │
│ - User modifies "Postcode" field    │
│ - Changes: SW1A 1AA → N1 9AG        │
│ - Clicks [Save]                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Detect Changed Fields      │
│                                       │
│ const changedFields = this.           │
│   detectChangedFields();              │
│                                       │
│ Result: ['postcode']                  │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Check Field Dependencies    │
│                                       │
│ const affectedServices = this.        │
│   getAffectedServices(changedFields); │
│                                       │
│ Dependency Map (hardcoded or from    │
│ API):                                 │
│   'postcode' → ['crime', 'schools',  │
│                 'poi', 'broadband',   │
│                 'mobile']             │
│                                       │
│ Result: 5 services affected           │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Decision: Are Services Affected?      │
└──────────┬────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
   YES           NO
    │             │
    │             ▼
    │    ┌────────────────────────┐
    │    │ Save Without Rerun     │
    │    │                        │
    │    │ PUT /api/properties/   │
    │    │      {id}/             │
    │    │                        │
    │    │ Backend updates field, │
    │    │ no services triggered  │
    │    └────────────────────────┘
    │
    ▼
┌───────────────────────────────────────┐
│ Frontend: Show Confirmation Dialog    │
│                                       │
│ ┌─────────────────────────────────┐   │
│ │ Rerun Context Services?         │   │
│ │                                 │   │
│ │ Changing postcode will          │   │
│ │ re-retrieve:                    │   │
│ │   • Crime Report                │   │
│ │   • Schools Report              │   │
│ │   • Places of Interest          │   │
│ │   • Broadband Info              │   │
│ │   • Mobile Coverage             │   │
│ │                                 │   │
│ │ This may incur API costs.       │   │
│ │                                 │   │
│ │ ☐ Don't ask again               │   │
│ │                                 │   │
│ │ [Cancel] [Save and Rerun]       │   │
│ └─────────────────────────────────┘   │
└──────────────┬────────────────────────┘
               │
      ┌────────┴────────┐
      │                 │
   Cancel         Confirmed
      │                 │
      ▼                 │
┌──────────┐            │
│ ABORT    │            │
│ No save  │            │
│ No rerun │            │
└──────────┘            │
                        │
                        ▼
              ┌───────────────────────────────┐
              │ Frontend: Send API Request    │
              │                               │
              │ PUT /api/properties/{id}/     │
              │                               │
              │ Body: {                       │
              │   postcode: "N1 9AG",         │
              │   _trigger_reruns: true       │
              │ }                             │
              └──────────┬────────────────────┘
                         │
                         ▼
              ┌───────────────────────────────────┐
              │ Backend: Property Update View     │
              │                                   │
              │ 1. Authenticate user              │
              │ 2. Authorize (user can edit)      │
              │ 3. Load existing property         │
              └──────────┬────────────────────────┘
                         │
                         ▼
              ┌────────────────────────────────────┐
              │ Backend: Track Field Changes       │
              │                                    │
              │ old_values = {                     │
              │   'postcode': 'SW1A 1AA',          │
              │   'price': 350000,                 │
              │   ...                              │
              │ }                                  │
              │                                    │
              │ # Save new values                  │
              │ serializer.save()                  │
              │                                    │
              │ # Detect what changed              │
              │ changed_fields = detect_changes(   │
              │   old_values, property             │
              │ )                                  │
              │                                    │
              │ Result: ['postcode']               │
              └──────────┬─────────────────────────┘
                         │
                         ▼
              ┌─────────────────────────────────────┐
              │ Backend: Check Service Dependencies │
              │                                     │
              │ FIELD_SERVICE_DEPENDENCIES = {      │
              │   'postcode': ['crime', 'schools',  │
              │                'poi', 'broadband',  │
              │                'mobile'],           │
              │   'latitude': ['poi'],              │
              │   'longitude': ['poi'],             │
              │   ...                               │
              │ }                                   │
              │                                     │
              │ affected_services =                 │
              │   property.get_affected_services(   │
              │     changed_fields                  │
              │   )                                 │
              │                                     │
              │ Result: ['crime', 'schools', 'poi', │
              │          'broadband', 'mobile']     │
              └──────────┬──────────────────────────┘
                         │
                         ▼
              ┌───────────────────────────────────┐
              │ Backend: Invalidate Caches        │
              │                                   │
              │ for service in affected_services: │
              │     service_class =               │
              │       get_service(service)        │
              │     cache_key =                   │
              │       service_class.get_cache_key(│
              │         property                  │
              │       )                           │
              │     cache.delete(cache_key)       │
              │                                   │
              │ (Forces fresh API calls on rerun) │
              └──────────┬────────────────────────┘
                         │
                         ▼
              ┌─────────────────────────────────────┐
              │ Backend: State Transition           │
              │                                     │
              │ IF property.state in                │
              │    ['STAGE2_COMPLETE',              │
              │     'STAGE3_IN_PROGRESS',           │
              │     'STAGE3_COMPLETE']:             │
              │                                     │
              │   property.rerun_services(          │
              │     affected_services               │
              │   )                                 │
              │   → State: STAGE2_IN_PROGRESS      │
              └──────────┬──────────────────────────┘
                         │
                         ▼
              ┌───────────────────────────────────────┐
              │ Backend: Reset Context Data Status    │
              │                                       │
              │ for service in affected_services:     │
              │   ContextData.objects.                │
              │     update_or_create(                 │
              │       property=property,              │
              │       service_name=service,           │
              │       defaults={                      │
              │         'status': 'PENDING',          │
              │         'data': None,                 │
              │         'error_message': None         │
              │       }                               │
              │     )                                 │
              └──────────┬────────────────────────────┘
                         │
                         ▼
              ┌────────────────────────────────────────┐
              │ Backend: Queue Celery Tasks            │
              │                                        │
              │ for service in affected_services:      │
              │   run_service_task.delay(              │
              │     property.id,                       │
              │     service                            │
              │   )                                    │
              │                                        │
              │ Result: 5 Celery tasks queued          │
              │   - run_service_task('crime')          │
              │   - run_service_task('schools')        │
              │   - run_service_task('poi')            │
              │   - run_service_task('broadband')      │
              │   - run_service_task('mobile')         │
              └──────────┬─────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────────────────────┐
              │ Backend: Return API Response        │
              │                                     │
              │ HTTP 200 OK                         │
              │ {                                   │
              │   "id": 123,                        │
              │   "postcode": "N1 9AG",             │
              │   "state": "STAGE2_IN_PROGRESS",    │
              │   "services_rerunning": [           │
              │     "crime", "schools", "poi",      │
              │     "broadband", "mobile"           │
              │   ]                                 │
              │ }                                   │
              └──────────┬──────────────────────────┘
                         │
                         ▼
              ┌──────────────────────────────────────┐
              │ Frontend: Handle Response            │
              │                                      │
              │ • Close edit form                    │
              │ • Update property state display:     │
              │   "Retrieving updated reports..."    │
              │ • Show progress indicator:           │
              │   "0/5 services complete"            │
              │ • Establish WebSocket connection     │
              └──────────┬───────────────────────────┘
                         │
                         │
                         │ (Services run asynchronously)
                         │
                         ▼
              ┌────────────────────────────────────────┐
              │ Celery Worker: Service Execution       │
              │ (Parallel - 5 tasks running)           │
              │                                        │
              │ Each service:                          │
              │ 1. Set status → IN_PROGRESS            │
              │ 2. Check cache (will miss due to       │
              │    invalidation)                       │
              │ 3. Call external API                   │
              │ 4. Store result                        │
              │ 5. Set status → COMPLETE or FAILED     │
              │ 6. Trigger post_save signal            │
              └──────────┬─────────────────────────────┘
                         │
                         ▼
              ┌───────────────────────────────────────┐
              │ Signal Handler: Check Completion      │
              │                                       │
              │ @receiver(post_save,                  │
              │           sender=ContextData)         │
              │ def context_data_updated(...):        │
              │   if all_services_complete():         │
              │     property.complete_stage2()        │
              │     → State: STAGE2_COMPLETE         │
              └──────────┬────────────────────────────┘
                         │
                         ▼
              ┌────────────────────────────────────────┐
              │ Check: Rating Recalculation Needed?    │
              │                                        │
              │ IF property.state ==                   │
              │    'STAGE2_COMPLETE' AND               │
              │ property.property_list                 │
              │         .rating_criteria exists AND    │
              │ property.overall_rating is not None:   │
              │   # Had a rating before, recalculate   │
              │   property.run_stage3()                │
              │   calculate_rating_task.delay(...)     │
              └────────────────────────────────────────┘
                         │
                         ▼
              ┌───────────────────────────────────────┐
              │ Frontend: Real-time Updates           │
              │ (via WebSocket)                       │
              │                                       │
              │ Progress updates as services complete:│
              │ • "Crime report ready" (1/5)          │
              │ • "Schools report ready" (2/5)        │
              │ • "POI report ready" (3/5)            │
              │ • "Broadband report ready" (4/5)      │
              │ • "Mobile coverage ready" (5/5)       │
              │                                       │
              │ Final: "All reports updated ✓"        │
              │                                       │
              │ IF rating recalculated:               │
              │   "Rating updated: 87.5 → 91.2"       │
              └───────────────────────────────────────┘
                         │
                         ▼
                      [END]
```

---

## Workflow B: Property Field Edit with Rating Dependencies Only

### Trigger
User edits a property field that affects rating but NOT context services (e.g., price, bedrooms, garden).

### Example Scenario
User changes price from £350,000 to £375,000

---

### Simplified Flow

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ Property Edit Form                   │
│ - User modifies "Price" field       │
│ - Changes: £350,000 → £375,000      │
│ - Clicks [Save]                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Detect Changed Fields      │
│                                       │
│ Result: ['price']                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Check Dependencies          │
│                                       │
│ Affected services: [] (none)          │
│ Affects rating: YES                   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: NO Confirmation Required    │
│ (Only services trigger confirmation)  │
│                                       │
│ Send API request directly:            │
│ PUT /api/properties/{id}/             │
│ { price: 375000 }                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Save Field                   │
│                                       │
│ property.price = 375000               │
│ property.save()                       │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Check Rating Dependencies    │
│                                       │
│ FIELD_RATING_DEPENDENCIES = {         │
│   'price': True,                      │
│   'bedrooms': True,                   │
│   'garden': True,                     │
│   ...                                 │
│ }                                     │
│                                       │
│ needs_recalc = property.              │
│   needs_rating_recalculation(         │
│     ['price']                         │
│   )                                   │
│                                       │
│ Result: True                          │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Trigger Rating Recalculation │
│                                       │
│ IF property.state ==                  │
│    'STAGE3_COMPLETE' AND              │
│ property.property_list                │
│         .rating_criteria exists:      │
│                                       │
│   property.recalculate_rating()       │
│   → State: STAGE3_IN_PROGRESS        │
│                                       │
│   calculate_rating_task.delay(        │
│     property.id                       │
│   )                                   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Celery: Rating Recalculation          │
│                                       │
│ (See Stage 3 workflow for details)    │
│                                       │
│ Result:                               │
│   Old rating: 87.5                    │
│   New rating: 84.2                    │
│   (Price increased, score decreased)  │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: State Transition             │
│                                       │
│ property.complete_stage3()            │
│ → State: STAGE3_COMPLETE             │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Display Updated Rating      │
│ (via WebSocket)                       │
│                                       │
│ "Rating updated: 87.5 → 84.2"         │
│                                       │
│ Badge color changes from green to     │
│ yellow (rating dropped below 85)      │
└───────────────────────────────────────┘
               │
               ▼
            [END]
```

---

## Workflow C: Context Options Modification (Bulk Rerun)

### Trigger
User adds new context options to a Property List that already has properties.

### Example Scenario
List has options: [Crime, Schools]. User adds: [Broadband, Mobile]. List has 3 properties at `STAGE2_COMPLETE`.

---

### Detailed Flow

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ Context Options Edit Form            │
│ - User checks "Broadband" checkbox  │
│ - User checks "Mobile" checkbox     │
│ - Clicks [Save]                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Send API Request            │
│                                       │
│ PUT /api/context-options/{list_id}/   │
│                                       │
│ Body: {                               │
│   enabled_services: [                 │
│     "crime", "schools",               │
│     "broadband", "mobile"  // NEW     │
│   ]                                   │
│ }                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Context Options Update View  │
│                                       │
│ 1. Authenticate user                  │
│ 2. Authorize (user owns list)         │
│ 3. Load existing context options      │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Detect Added Services        │
│                                       │
│ old_services = set([                  │
│   'crime', 'schools'                  │
│ ])                                    │
│                                       │
│ new_services = set([                  │
│   'crime', 'schools',                 │
│   'broadband', 'mobile'               │
│ ])                                    │
│                                       │
│ added_services =                      │
│   new_services - old_services         │
│                                       │
│ Result: {'broadband', 'mobile'}       │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Save Context Options         │
│                                       │
│ context_options.update(               │
│   enabled_services=new_services       │
│ )                                     │
│ context_options.save()                │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Decision: Were New Services Added?    │
└──────────┬────────────────────────────┘
           │
    ┌──────┴──────┐
    │             │
   YES           NO
    │             │
    │             ▼
    │    ┌────────────────────────┐
    │    │ Return Success         │
    │    │ No bulk rerun needed   │
    │    └────────────────────────┘
    │
    ▼
┌───────────────────────────────────────────┐
│ Backend: Get Eligible Properties          │
│                                           │
│ properties = Property.objects.filter(     │
│   property_list=property_list             │
│ ).exclude(                                │
│   state='NEW'  // Skip NEW properties     │
│ )                                         │
│                                           │
│ Result: 3 properties (all STAGE2_COMPLETE)│
└──────────────┬────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────┐
│ Backend: Trigger Bulk Rerun               │
│                                           │
│ for property in properties:               │
│   # State transition                      │
│   property.rerun_services(                │
│     added_services                        │
│   )                                       │
│   → State: STAGE2_IN_PROGRESS            │
│                                           │
│   # Reset context data status             │
│   for service in added_services:          │
│     ContextData.objects.                  │
│       update_or_create(                   │
│         property=property,                │
│         service_name=service,             │
│         defaults={'status': 'PENDING'}    │
│       )                                   │
│                                           │
│   # Queue Celery tasks                    │
│   for service in added_services:          │
│     run_service_task.delay(               │
│       property.id, service                │
│     )                                     │
│                                           │
│ Total tasks queued: 3 props * 2 svcs = 6 │
└──────────────┬────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────┐
│ Backend: Return API Response              │
│                                           │
│ HTTP 200 OK                               │
│ {                                         │
│   "success": true,                        │
│   "services_added": [                     │
│     "broadband", "mobile"                 │
│   ],                                      │
│   "properties_affected": 3,               │
│   "tasks_queued": 6                       │
│ }                                         │
└──────────────┬────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────┐
│ Frontend: Show Success Notification       │
│                                           │
│ "Context options updated successfully.    │
│  Retrieving Broadband and Mobile reports  │
│  for 3 properties..."                     │
│                                           │
│ • Navigate to Property List detail page   │
│ • Show progress indicators on each        │
│   property card                           │
└──────────────┬────────────────────────────┘
               │
               │ (Services run asynchronously)
               │
               ▼
┌────────────────────────────────────────────┐
│ Celery Workers: Service Execution          │
│ (6 tasks running in parallel)              │
│                                            │
│ Property 1:                                │
│   - Broadband service                      │
│   - Mobile service                         │
│                                            │
│ Property 2:                                │
│   - Broadband service                      │
│   - Mobile service                         │
│                                            │
│ Property 3:                                │
│   - Broadband service                      │
│   - Mobile service                         │
└──────────────┬─────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────┐
│ Signal Handlers: Completion Detection     │
│                                           │
│ As each service completes:                │
│ • Update ContextData status               │
│ • Send WebSocket update                   │
│ • Check if all services done              │
│   (original + new)                        │
│                                           │
│ When last service completes for property: │
│ • Transition → STAGE2_COMPLETE           │
│                                           │
│ (Each property completes independently)   │
└──────────────┬────────────────────────────┘
               │
               ▼
┌───────────────────────────────────────────┐
│ Frontend: Real-time Progress Updates      │
│ (via WebSocket)                           │
│                                           │
│ Property List Detail Page shows:          │
│                                           │
│ ┌─────────────────────────────────────┐   │
│ │ 123 Main St                         │   │
│ │ Retrieving reports... 4/7 complete  │   │
│ │ ▓▓▓▓▓▓░░░░░░░ 57%                   │   │
│ └─────────────────────────────────────┘   │
│                                           │
│ ┌─────────────────────────────────────┐   │
│ │ 456 Oak Ave                         │   │
│ │ Retrieving reports... 6/7 complete  │   │
│ │ ▓▓▓▓▓▓▓▓▓▓░░░ 86%                   │   │
│ └─────────────────────────────────────┘   │
│                                           │
│ ┌─────────────────────────────────────┐   │
│ │ 789 Elm Rd                          │   │
│ │ All reports ready ✓                 │   │
│ └─────────────────────────────────────┘   │
└───────────────────────────────────────────┘
               │
               ▼
            [END]
```

---

## Special Case: Context Options Removal

### Trigger
User removes context options from a Property List (e.g., unchecks "Broadband").

### Flow with User Confirmation

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ Context Options Edit Form            │
│ - User unchecks "Broadband"         │
│ - Clicks [Save]                     │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Detect Removed Services      │
│                                       │
│ old: ['crime', 'schools', 'broadband']│
│ new: ['crime', 'schools']             │
│                                       │
│ removed: ['broadband']                │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Count Affected Properties    │
│                                       │
│ GET /api/property-lists/{id}/         │
│     context-data-count/               │
│     ?services=broadband               │
│                                       │
│ Response: { count: 3 }                │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Show Confirmation Dialog    │
│                                       │
│ ┌─────────────────────────────────┐   │
│ │ Delete Existing Data?           │   │
│ │                                 │   │
│ │ Removing Broadband will delete  │   │
│ │ existing data for 3 properties. │   │
│ │                                 │   │
│ │ This action cannot be undone.   │   │
│ │                                 │   │
│ │ [Cancel]                        │   │
│ │ [Delete Data and Continue]      │   │
│ └─────────────────────────────────┘   │
└──────────────┬────────────────────────┘
               │
      ┌────────┴────────┐
      │                 │
   Cancel         Confirmed
      │                 │
      ▼                 │
┌──────────┐            │
│ ABORT    │            │
│ Keep     │            │
│ Broadband│            │
│ enabled  │            │
└──────────┘            │
                        │
                        ▼
              ┌───────────────────────────────┐
              │ Frontend: Send Delete Request │
              │                               │
              │ PUT /api/context-options/     │
              │     {list_id}/                │
              │                               │
              │ Body: {                       │
              │   enabled_services: [         │
              │     "crime", "schools"        │
              │   ],                          │
              │   _confirm_delete: true       │
              │ }                             │
              └──────────┬────────────────────┘
                         │
                         ▼
              ┌────────────────────────────────┐
              │ Backend: Delete Context Data   │
              │                                │
              │ ContextData.objects.filter(    │
              │   property__property_list=list,│
              │   service_name='broadband'     │
              │ ).delete()                     │
              │                                │
              │ Deleted: 3 records             │
              └──────────┬───────────────────── │
                         │
                         ▼
              ┌────────────────────────────────┐
              │ Backend: Save Context Options  │
              │                                │
              │ context_options.update(        │
              │   enabled_services=[           │
              │     'crime', 'schools'         │
              │   ]                            │
              │ )                              │
              └──────────┬─────────────────────┘
                         │
                         ▼
              ┌────────────────────────────────┐
              │ Frontend: Show Notification    │
              │                                │
              │ "Broadband data deleted for    │
              │  3 properties."                │
              └────────────────────────────────┘
                         │
                         ▼
                      [END]
```

---

## Field Dependency Matrix (Reference)

This matrix is used by both frontend and backend to determine which services/ratings need rerun.

```python
# Backend: property/models.py
class Property(models.Model):
    FIELD_SERVICE_DEPENDENCIES = {
        'postcode': ['crime', 'schools', 'poi', 'broadband', 'mobile'],
        'latitude': ['poi'],
        'longitude': ['poi'],
        'address_line_1': [],
        'address_line_2': [],
        'city': [],
        'price': [],
        'bedrooms': [],
        'bathrooms': [],
        'square_area': [],
        'garden': [],
        'parking': [],
        'furnished_status': [],
        'property_type': [],
        'council_tax_band': [],
        'epc_rating': [],
    }

    FIELD_RATING_DEPENDENCIES = {
        'price': True,
        'bedrooms': True,
        'bathrooms': True,
        'square_area': True,
        'garden': True,
        'parking': True,
        'furnished_status': True,
        'council_tax_band': True,
        'epc_rating': True,
        'postcode': True,  # Affects POI distance criteria
        # Context data changes also trigger rating
    }
```

```typescript
// Frontend: property-edit.service.ts
export const FIELD_SERVICE_DEPENDENCIES = {
  postcode: ['crime', 'schools', 'poi', 'broadband', 'mobile'],
  latitude: ['poi'],
  longitude: ['poi'],
  // ... others have no dependencies
};

export const FIELD_RATING_DEPENDENCIES = [
  'price', 'bedrooms', 'bathrooms', 'square_area',
  'garden', 'parking', 'furnished_status',
  'council_tax_band', 'epc_rating', 'postcode'
];
```

---

## User Preference: "Don't Ask Again"

Users can disable service rerun confirmations for convenience.

### Implementation

```typescript
// Frontend service
export class PropertyEditService {
  private skipConfirmation = false;

  async savePropertyChanges(property: Property, changes: any) {
    const affectedServices = this.getAffectedServices(changes);

    if (affectedServices.length > 0 && !this.skipConfirmation) {
      const result = await this.confirmDialog.show({
        title: 'Rerun Context Services?',
        message: `Changing ${Object.keys(changes).join(', ')} will re-retrieve ...`,
        showDontAskAgain: true
      });

      if (!result.confirmed) {
        return; // Abort
      }

      if (result.dontAskAgain) {
        this.savePreference('skip_service_rerun_confirmation', true);
        this.skipConfirmation = true;
      }
    }

    // Proceed with save...
  }
}
```

```python
# Backend: Store preference
class UserPreference(models.Model):
    user = models.OneToOneField(User)
    skip_service_rerun_confirmation = models.BooleanField(default=False)

# Load on frontend init
GET /api/users/me/preferences/
{
  "skip_service_rerun_confirmation": false
}
```

---

## Performance Optimizations

### 1. Debounce Field Changes

Prevent accidental rapid edits from triggering multiple reruns:

```typescript
// Frontend
private saveSubject = new Subject<PropertyChanges>();

constructor() {
  this.saveSubject
    .pipe(debounceTime(1000)) // Wait 1s after last change
    .subscribe(changes => this.saveChanges(changes));
}

onFieldChange(field: string, value: any) {
  this.saveSubject.next({ [field]: value });
}
```

### 2. Batch Multiple Field Changes

If user edits multiple fields in one session, batch into single save:

```typescript
// Only show confirmation once with all affected services
const changes = {
  postcode: 'N1 9AG',
  price: 375000,
  bedrooms: 4
};

const allAffectedServices = new Set();
for (const field of Object.keys(changes)) {
  const services = FIELD_SERVICE_DEPENDENCIES[field] || [];
  services.forEach(s => allAffectedServices.add(s));
}

// Result: ['crime', 'schools', 'poi', 'broadband', 'mobile']
// Show single confirmation for all 5 services
```

### 3. Smart Cache Invalidation

Only invalidate caches for services that will actually rerun:

```python
def invalidate_caches_for_services(property, service_names):
    """Only invalidate specific service caches"""
    for service_name in service_names:
        service_class = SERVICE_REGISTRY[service_name]
        cache_key = service_class().get_cache_key(property)
        cache.delete(cache_key)
```

---

## Error Handling

### Scenario: Service Rerun Fails

**Problem:** User changes postcode, Crime service fails during rerun.

**Handling:**
- Other services continue normally
- Property transitions to `STAGE2_COMPLETE` with partial success
- UI shows: "4/5 reports updated, Crime failed (API error)"
- User can retry Crime service independently

### Scenario: Rating Recalculation Fails

**Problem:** After price change, rating calculation task crashes.

**Handling:**
- Property remains at `STAGE3_IN_PROGRESS`
- UI shows: "Rating recalculation failed. Please try again."
- User can click "Calculate Rating" button to retry

---

## Summary

**Automatic Rerun Workflows:**

1. **Field Edit with Service Dependencies**
   - Confirmation required
   - Invalidate caches
   - Queue Celery tasks for affected services
   - Real-time progress via WebSocket

2. **Field Edit with Rating Dependencies**
   - No confirmation (lightweight operation)
   - Immediate rating recalculation
   - Updated rating displayed

3. **Context Options Modification**
   - Bulk rerun for all eligible properties
   - Automatic execution (no per-property confirmation)
   - Deletion confirmation for removed services

These workflows ensure data consistency while providing user control over costly operations.
