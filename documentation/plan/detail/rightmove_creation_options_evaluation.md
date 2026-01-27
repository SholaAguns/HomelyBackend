# Rightmove Creation Options - Evaluation & Implementation Guide

## Evaluation

### Current State
1. **Existing Infrastructure**
   - `create_from_input` endpoint (property/views.py:187) - extracts single property from URL
   - Factory pattern with IPropertyCreationService interface
   - RightmoveService (services folder) - basic HTML scraping for single property
   - POC RightmoveService (poc folder) - full search API integration with bulk scraping

2. **POC Code Capabilities**
   - Fetches location IDs from Rightmove typeahead API
   - Scrapes search results pages with pagination
   - Extracts comprehensive property data (35+ fields)
   - Creates Property and PropertyImage models
   - Handles Customer/agent data
   - Already creates properties and adds to PropertyList

### Gap Analysis

**Option 1: Create Properties by Search**
- ✅ Service code exists in poc/rightmove_service.py
- ❌ No search criteria serializers (poc has it but needs integration)
- ❌ No bulk property creation endpoint
- ❌ No async task handling for long-running scrapes
- ❌ No progress tracking (websocket or polling endpoint)
- ❌ No queue management for property creation

**Option 2: Individual Property from URL**
- ✅ Endpoint exists (create_from_input)
- ✅ Factory pattern in place
- ❌ Current RightmoveService is basic HTML scraping
- ❌ POC service uses property ID extraction + API calls (more robust)
- ❌ POC service has richer data extraction (images, customer, dates, etc.)

## Recommended Approach

### Strategic Decision: Unified Service
Merge POC RightmoveService capabilities into production codebase with two modes:
1. **Single property mode** - extract ID from URL, fetch single property
2. **Bulk search mode** - use search criteria, fetch all matching properties

### Why This Works
- Reuse 90% of POC code (already tested)
- Single service = easier maintenance
- Both modes use same data extraction logic
- Can share caching, rate limiting, error handling

## Implementation Plan

### Phase 1: Service Layer Enhancement (2-3 days)
**Goal:** Enhance RightmoveService to support both modes

**Tasks:**
- [ ] Move POC helper methods to production RightmoveService
  - `clean_price`, `safe_int`, `clean_date`
  - `fetch_page` (JSON extraction from __NEXT_DATA__)
  - `get_location_id` (typeahead API)

- [ ] Add `extract_property_id_from_url(url)` method
  - Regex: `/properties/(\d+)` or `/property-to-rent/\d+\.html`

- [ ] Add `fetch_single_property(property_id)` method
  - Build URL: `BASE_URL + "/properties/" + property_id`
  - Reuse data extraction logic
  - Return dict matching Property model

- [ ] Refactor `extract_property_data(url)` to call `fetch_single_property`
  - Extract ID from URL
  - Fetch via API instead of HTML scraping
  - More robust, gets same data as search results

- [ ] Add `scrape_properties_by_search(search_criteria, property_list)` method
  - Copy from POC with modifications
  - Return list of property dicts instead of creating models
  - Separate data extraction from model creation

**Files to modify:**
- `property/services/rightmove_service.py` - main changes
- `property/services/interface.py` - add optional methods for bulk services

### Phase 2: Serializers & Models (1 day)
**Goal:** Create serializers for search criteria and bulk responses

**Tasks:**
- [ ] Copy SearchCriteria model from POC to production
  - Move `poc/models.py` SearchCriteria to `property/models.py`
  - Create migration
  - Consider: should SearchCriteria be reusable across PropertyLists?

- [ ] Create SearchCriteriaSerializer
  - Copy from `poc/propertylist_serializers.py`
  - Fields: area, bedrooms_min/max, price_min/max, radius, property_types, max_days_since_added

- [ ] Create BulkPropertyCreationSerializer
  - Input: search_criteria dict
  - Output: list of property data dicts + metadata

**Files to create/modify:**
- `property/models.py` - add SearchCriteria (if not exists)
- `property/serializers/searchcriteria_serializers.py` - new file
- `property/migrations/000X_searchcriteria.py` - new migration

### Phase 3: Async Task Infrastructure (2 days) - done
**Goal:** Handle long-running scrapes asynchronously

**Decision Point: Queue vs Immediate**
User asked: "Should we wait till all properties are created or queue creation?"

**Recommendation: Queue + Progress Updates**

**Reasons:**
- Search can return 100+ properties
- Scraping takes 5-10 seconds per page (with delays)
- User shouldn't wait 5+ minutes on HTTP request
- Can show progress indicators
- Can handle failures gracefully

**Implementation:**
- [x] Create Celery task `scrape_rightmove_properties.task` - done
  - Input: property_list_id, search_criteria dict
  - Output: periodic progress updates via websocket
  - Creates Property models incrementally

- [x] Add task status tracking - done
  - Option A: Use celery result backend (Redis)
  - Option B: Create PropertyListTask model (status, progress, total, errors)
  - **Recommendation:** Option B for better UX and persistence
  - **Implemented:** PropertyListTask model with progress tracking and error handling

- [x] Add websocket consumer for progress updates - done
  - Channel: `property_list.{uuid}.scrape_progress`
  - Messages: `{created: 5, total: 20, status: "in_progress"}`
  - Already have Channels infrastructure (roadmap Phase 2)

**Files to create/modify:**
- `property/tasks.py` - add scrape_rightmove_properties task - done
- `property/stage1_models.py` - add PropertyListTask model - done
- `property/consumers.py` - add progress websocket consumer - done
- `homely_core/routing.py` - add websocket route - done

### Phase 4: API Endpoints (1 day) - done
**Goal:** Expose new creation options via API

**Endpoints to create:**

**4.1 Bulk Search Creation** - done
```python
POST /api/property-lists/{uuid}/create-from-search/
Request:
{
  "search_criteria": {
    "area": "Manchester",
    "bedrooms_min": 2,
    "price_max": 1500,
    "radius": 3
  },
  "max_properties": 100  # optional, default 100
}

Response:
{
  "uuid": "task-uuid",
  "task_type": "SCRAPE_SEARCH",
  "status": "QUEUED",
  "websocket_url": "ws://.../property-list/{uuid}/",
  ...
}
```

**4.2 Progress Polling Endpoint (fallback for no websocket)** - done
```python
GET /api/property-lists/{uuid}/scrape-status/{task_uuid}/

Response:
{
  "uuid": "task-uuid",
  "status": "IN_PROGRESS",
  "completed_items": 15,
  "total_items": 50,
  "failed_items": 0,
  "progress_percentage": 30,
  "errors": [],
  "metadata": {...}
}
```

**4.3 Enhanced create_from_input for Rightmove URLs** - done
```python
POST /api/properties/create-from-input/
Request:
{
  "input_data": "https://www.rightmove.co.uk/properties/123456",
  "input_type": "url",
  "property_list_uuid": "xxx-yyy-zzz"  # NEW: optional, auto-create property
}

Response (with property_list_uuid):
{
  "success": true,
  "property": {
    "uuid": "...",
    "title": "...",
    ...
  },
  "created": true,  # or updated: true if already exists
  "message": "Property created successfully"
}

Response (without property_list_uuid):
{
  "success": true,
  "property_data": {...},
  "message": "Property data extracted successfully"
}
```

**Tasks:**
- [x] Add `create_from_search` action to PropertyListViewSet - done
- [x] Add `scrape_status` action to PropertyListViewSet - done
- [x] Update `create_from_input` in PropertyViewSet - done
  - Add optional `property_list_uuid` parameter
  - If provided, create Property model + add to list
  - If not provided, just return data (current behavior)
  - Handles duplicate detection by external_id

**Files to modify:**
- `property/views.py` - add new actions - done

### Phase 5: Frontend Integration (2-3 days)
**Goal:** UI for new creation options

**Component Changes:**
- [ ] Update PropertyList creation flow
  - Add "Create from Search" option
  - Show search criteria form (area, price, bedrooms, etc.)
  - Submit → get task_id → connect websocket → show progress

- [ ] Add progress indicator component
  - Shows "Creating 15 of 50 properties..."
  - Updates in real-time via websocket
  - Fallback to polling if websocket fails

- [ ] Update create_from_input flow
  - Add "Auto-create" toggle
  - If enabled, property created immediately + redirect to list
  - If disabled, just populate form (current behavior)

**Files to modify:**
- Frontend repo (out of scope for this doc)

### Phase 6: Testing & Edge Cases (1-2 days)

**Test Cases:**
- [ ] Single property creation from URL
- [ ] Bulk creation with 5, 50, 200 properties
- [ ] Pagination handling (multi-page results)
- [ ] Duplicate property detection (existing external_id)
- [ ] Rate limiting (Rightmove blocks)
- [ ] Network failures mid-scrape
- [ ] Invalid search criteria (no results)
- [ ] User cancels mid-scrape

**Edge Cases to Handle:**
1. **Duplicate Properties**
   - Use `update_or_create` with `external_id`
   - POC already does this (line 240)
   - But: should we update existing properties or skip?
   - **Recommendation:** Skip with warning message

2. **Rate Limiting**
   - POC has 5-second delay between pages (line 296)
   - Add retry logic with exponential backoff
   - Detect HTTP 429 responses

3. **Partial Failures**
   - Some properties fail to parse
   - Continue scraping, log errors
   - Return summary: "Created 45/50, 5 failed"

4. **Long-running Tasks**
   - Set celery task timeout (15 minutes?)
   - Show timeout warning in UI
   - Allow task cancellation

## Technical Decisions

### Decision 1: Immediate vs Queued Creation
**Choice:** Queued with progress updates

**Rationale:**
- Better UX (no long HTTP requests)
- Can handle 100+ properties
- Shows progress
- Allows cancellation
- Standard pattern for async work

### Decision 2: Websocket vs Polling
**Choice:** Websocket primary, polling fallback

**Rationale:**
- Already have Channels infrastructure
- Real-time updates
- Lower server load than polling
- Polling as graceful degradation

### Decision 3: Search Criteria Storage
**Choice:** Store in SearchCriteria model linked to PropertyList

**Rationale:**
- Can re-run searches
- Audit trail
- Allow search refinement
- Already in POC models

### Decision 4: Service Extraction Pattern
**Choice:** Service returns data dicts, endpoint handles model creation

**Rationale:**
- Separation of concerns
- Service can be used for preview without creating
- Easier testing
- Matches current `create_from_input` pattern

### Decision 5: Property Ownership
**Choice:** Properties belong to PropertyList (many-to-many preserved)

**Rationale:**
- Same property can appear in multiple lists
- Matches current model design
- Deduplication via external_id
- User can remove from list without deleting property

## Migration Strategy

### Database Changes
```python
# New migration
class Migration:
    operations = [
        # 1. SearchCriteria already exists in POC
        # 2. PropertyListTask for tracking async scrapes
        CreateModel(
            name='PropertyListTask',
            fields=[
                ('id', models.AutoField()),
                ('uuid', models.UUIDField(unique=True, default=uuid.uuid4)),
                ('property_list', models.ForeignKey('PropertyList')),
                ('task_type', models.CharField(max_length=50)),  # 'scrape_search'
                ('status', models.CharField(max_length=20)),  # queued, in_progress, completed, failed
                ('celery_task_id', models.CharField(max_length=255, null=True)),
                ('total_items', models.IntegerField(default=0)),
                ('completed_items', models.IntegerField(default=0)),
                ('errors', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ]
        ),
    ]
```

### Data Migration
- No data migration needed (new features)
- Existing properties unaffected

## API Design Summary

### New Endpoints
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/property-lists/{uuid}/create-from-search/` | POST | Start bulk scrape task |
| `/api/property-lists/{uuid}/scrape-status/{task_id}/` | GET | Get scrape progress |
| `/api/properties/create-from-input/` (enhanced) | POST | Create single property from URL |

### Websocket Channels
| Channel | Purpose |
|---------|---------|
| `property_list.{uuid}.scrape_progress` | Real-time scrape progress |

## Effort Estimate

| Phase | Effort | Priority |
|-------|--------|----------|
| 1. Service Enhancement | 2-3 days | High |
| 2. Serializers | 1 day | High |
| 3. Async Tasks | 2 days | High |
| 4. Endpoints | 1 day | High |
| 5. Frontend | 2-3 days | Medium |
| 6. Testing | 1-2 days | High |
| **Total** | **9-12 days** | |

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Rightmove blocks scraping | Medium | High | Add delays, rotate user agents, respect robots.txt |
| Scrape takes too long | Medium | Medium | Set timeouts, show progress, allow cancellation |
| Duplicate properties | High | Low | Use update_or_create with external_id |
| Websocket connection fails | Low | Medium | Polling fallback |
| API structure changes | Medium | High | Add tests, monitor errors, log parsing failures |

## Next Steps

1. **Immediate:**
   - Review this proposal
   - Decide on queue vs immediate approach - queue
   - Choose websocket vs polling - websocket

2. **Short-term:**
   - Create feature branch
   - Implement Phase 1 (Service Enhancement)
   - Test single property extraction with POC service

3. **Medium-term:**
   - Build out async infrastructure
   - Create endpoints
   - Frontend integration

## Questions for Stakeholder

1. Should duplicate properties be updated or skipped? - updated
2. Is 5-second delay between pages acceptable (trade-off: slow scrape vs rate limiting)? - yes since we are queuing
3. Should users be able to cancel in-progress scrapes? - not for now
4. What's max number of properties per search? (limit to prevent abuse) - 100
5. Should search criteria be editable after creation?- yes
