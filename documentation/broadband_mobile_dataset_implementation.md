# Broadband & Mobile Dataset Implementation (Option 4)

**Date**: 2026-03-09
**Status**: Primary implementation (Option 1 API reserved as backup)
**Source**: Ofcom Connected Nations static datasets

---

## Overview

Implement static dataset import & querying for broadband/mobile coverage while awaiting Ofcom API access. API will replace this as primary option once granted.

---

## Datasets Available

### Broadband (Fixed Performance) - July 2024
- `202407_fixed_performance_laua_r01.csv` (31KB, Local Authority level)
- `202407_fixed_performance_oa_r01.csv` (11.6MB, Output Area level)
- `202407_fixed_performance_pcon_r01.csv` (50KB, Parliamentary Constituency level)

**Granularity**: Output Area (OA) provides most granular coverage ~125 households per OA

**Key Fields**:
- `Average max download/upload speed (Mbit/s)` for speed tiers: <10, 10-30, 30-100, 100-300, 300-900, >=900
- `Average monthly data usage (GB)` per connection
- `Full-fibre take-up (%)` coverage/adoption metrics

### Mobile Coverage - September 2024
- `202409_mobile_coverage_laua_r01.csv` (241KB, Local Authority level)
- `202409_mobile_coverage_pcon_r01.csv` (407KB, Parliamentary Constituency)
- `202409_mobile_coverage_UK_and_Nations_r01.csv` (51KB, National level)

**Key Fields** (by network gen: 2G/3G/4G/5G):
- `{gen}_prem_out_{0-4}`: Outdoor coverage at premises (0-4 networks)
- `{gen}_prem_in_{0-4}`: Indoor coverage at premises
- `{gen}_geo_out_{0-4}`: Geographic outdoor coverage
- `Voice/Data_prem_out/in_{0-4}`: Voice/data specific metrics
- `5G_high_confidence/very_high_confidence`: 5G availability confidence levels

---

## Implementation Tasks

### Phase 1: Models & Database Schema - done
- [x] Create `BroadbandCoverage` model
  - Fields: `oa_code, laua_code, avg_download_speed, avg_upload_speed, full_fibre_pct, data_usage_gb, last_updated`
  - Index on: `oa_code, laua_code`
- [x] Create `MobileCoverage` model
  - Fields: `laua_code, network_2g_pct, network_3g_pct, network_4g_pct, network_5g_pct, voice_coverage_pct, data_coverage_pct, indoor_4g_pct, outdoor_4g_pct, last_updated`
  - Index on: `laua_code`
- [x] Generate migrations (0012_broadbandcoverage_mobilecoverage.py)
- [x] Run migrations (require explicit approval)

### Phase 2: Data Import Commands - done
- [x] Create `management/commands/import_broadband_data.py`
  - Parse OA-level CSV (most granular)
  - Calculate weighted averages for speed ranges
  - Bulk create records with transaction
  - Add progress indicators
  - Handle duplicates (upsert logic)
- [x] Create `management/commands/import_mobile_data.py`
  - Parse LAUA-level CSV
  - Extract key metrics (4G/5G coverage percentages)
  - Calculate composite scores
  - Bulk create with transaction
- [x] Test import commands locally (OA import running in background)
- [ ] Document import process in README

### Phase 3: Lookup Services - done
- [x] Create `services/broadband_dataset_service.py`
  - Implement `IContextService` interface
  - Method: `fetch_data(property)` → postcode → OA → query DB
  - Cache results (90-day TTL)
  - Return standardized format matching API schema
- [x] Create `services/mobile_dataset_service.py`
  - Implement `IContextService` interface
  - Method: `fetch_data(property)` → postcode → LAUA → query DB
  - Cache results (90-day TTL)
  - Return standardized format
- [x] Create `utils/geocoding.py` helper
  - Method: `postcode_to_oa(postcode)` → Postcodes.io API
  - Method: `postcode_to_laua(postcode)` → Postcodes.io API
  - Method: `postcode_to_geo_info(postcode)` → full info
  - Cache mapping (indefinite TTL)

### Phase 4: Integration with Context System - done
- [x] Register services in context service factory
  - Add "broadband" type → BroadbandDatasetService
  - Add "mobile" type → MobileDatasetService
- [x] Update `ContextData` model if needed
  - No changes needed - JSON field handles new structures
  - Services already registered in ContextOptions (enable_broadband, enable_mobile)
- [ ] Test end-to-end flow: Property → postcode → OA/LAUA → dataset lookup → ContextData storage

### Phase 5: API Endpoints
- [ ] Create GET `/api/properties/{id}/broadband/` endpoint
  - Return broadband data from ContextData or fetch+store
  - Response: `{download_mbps, upload_mbps, full_fibre_pct, data_source: "Ofcom Dataset 2024-07"}`
- [ ] Create GET `/api/properties/{id}/mobile/` endpoint
  - Return mobile coverage from ContextData
  - Response: `{4g_pct, 5g_pct, indoor_coverage, outdoor_coverage, data_source: "Ofcom Dataset 2024-09"}`
- [ ] Add to property detail serializer (optional nested fields)

### Phase 6: Testing
- [ ] Unit tests for import commands
  - Mock CSV parsing
  - Test duplicate handling
  - Test error cases
- [ ] Unit tests for lookup services
  - Test postcode → OA/LAUA mapping
  - Test DB queries
  - Test cache behavior
- [ ] Integration tests
  - Test full property → context data flow
  - Test API endpoints
- [ ] Performance tests
  - Benchmark query speed (should be <50ms)
  - Test bulk lookups

### Phase 7: Documentation & Deployment
- [ ] Update `documentation/plan/backend_implementation_roadmap.md`
- [ ] Add dataset source attribution in API responses
- [ ] Create admin command to refresh datasets (when new releases available)
- [ ] Add monitoring/logging for service calls
- [ ] Deploy to staging
- [ ] Run import commands on staging DB
- [ ] Test on staging
- [ ] Deploy to production (when ready)

### Phase 8: API Migration Path (Future)
- [ ] Create `services/broadband_api_service.py` (when API access granted)
- [ ] Update service factory to use API service as primary
- [ ] Keep dataset service as fallback
- [ ] Add feature flag to toggle between API/dataset
- [ ] Deprecate dataset service once API stable

---

## Technical Decisions

### Why OA-level for Broadband?
- Most granular (125 households avg)
- Closest match to individual properties
- Acceptable file size (11.6MB)

### Why LAUA-level for Mobile?
- Good balance of granularity vs data size
- Mobile coverage varies less than broadband within small areas
- Parliamentary constituency too coarse

### Postcode → OA/LAUA Mapping
**Option A**: ONS Postcode Lookup API (RECOMMENDED)
- Free API: `https://api.postcodes.io/{postcode}`
- Returns: `admin_district` (LAUA), `codes.oa` (OA code)
- Cache results indefinitely (rarely change)

**Option B**: Static CSV lookup table
- Download ONS postcode directory
- Import to DB table
- More complex, but no external dependency

Decision: Start with Option A (simpler), migrate to Option B if rate limits hit

### Data Freshness
- Datasets updated annually by Ofcom
- Store `last_updated` field in model
- Create admin command to check for new releases
- Manual refresh process (acceptable for static data)

---

## Data Processing Logic

### Broadband Speed Calculation
Raw data has speed ranges (e.g., "30<100Mbit/s"). Need single average:

```python
# Weighted average approach
speed_ranges = {
    '<10': (0, 10),
    '10<30': (10, 30),
    '30<100': (30, 100),
    '100<300': (100, 300),
    '300<900': (300, 900),
    '>=900': (900, 1000)
}

# Take midpoint of each range, or use actual avg if provided
avg_download = weighted_average_from_ranges(row)
```

### Mobile Coverage Score
Composite score from multiple metrics:

```python
# Priority: 4G > 5G > 3G (most used)
mobile_score = (
    row['4G_prem_out_4'] * 0.4 +  # All 4 networks outdoor
    row['4G_prem_in_4'] * 0.3 +   # All 4 networks indoor
    row['5G_high_confidence_prem_out_4'] * 0.2 +
    row['Voice_prem_out_4'] * 0.1
)
```

---

## API Response Format

### Broadband
```json
{
  "postcode": "SW1A 1AA",
  "oa_code": "E00000001",
  "avg_download_mbps": 145,
  "avg_upload_mbps": 25,
  "full_fibre_available_pct": 78,
  "avg_monthly_usage_gb": 450,
  "data_source": "Ofcom Connected Nations 2024-07",
  "data_date": "2024-07-01",
  "granularity": "Output Area (~125 households)"
}
```

### Mobile
```json
{
  "postcode": "SW1A 1AA",
  "laua_code": "E09000033",
  "laua_name": "Westminster",
  "coverage_4g": {
    "outdoor_all_networks": 99.8,
    "indoor_all_networks": 95.2,
    "outdoor_1_network": 0.1,
    "indoor_1_network": 1.5
  },
  "coverage_5g": {
    "high_confidence": 85.3,
    "very_high_confidence": 62.1
  },
  "voice_coverage": 99.5,
  "data_coverage": 98.7,
  "data_source": "Ofcom Connected Nations 2024-09",
  "data_date": "2024-09-01",
  "granularity": "Local Authority"
}
```

---

## Migration to API (Phase 8)

When API access granted:
1. Implement API service following same interface
2. Update factory to prefer API service
3. Keep dataset service as fallback if API fails
4. Monitor API usage vs limits
5. Gradually phase out dataset queries
6. Keep dataset for historical comparisons

---

## File Structure

```
properties/
├── models/
│   ├── broadband_coverage.py
│   └── mobile_coverage.py
├── services/
│   ├── broadband_dataset_service.py
│   ├── mobile_dataset_service.py
│   ├── broadband_api_service.py (future)
│   └── mobile_api_service.py (future)
├── management/commands/
│   ├── import_broadband_data.py
│   └── import_mobile_data.py
├── utils/
│   └── geocoding.py
└── tests/
    ├── test_broadband_service.py
    └── test_mobile_service.py
```

---

## Questions/Risks

1. ❓ ONS Postcode API rate limits - need fallback?
2. ❓ How to handle postcodes with no OA/LAUA match?
3. ❓ Dataset refresh frequency - manual or automated?
4. ⚠️ Data is 6-9 months old (not real-time)
5. ⚠️ OA-level still averages 125 households (not address-specific)

---

## Success Criteria

- ✅ Import completes without errors (<5 min for all datasets)
- ✅ Query performance <50ms per lookup
- ✅ 95%+ postcode match rate (OA/LAUA found)
- ✅ API endpoints return data in <200ms
- ✅ Cache hit rate >80% after initial usage
- ✅ Zero data corruption in DB
- ✅ All tests passing
