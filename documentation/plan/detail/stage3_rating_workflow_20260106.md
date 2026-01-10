# Stage 3: Rating Workflow Diagram
**Date:** 2026-01-06
**Diagram Type:** Detailed Workflow
**Purpose:** Shows how properties are rated based on weighted criteria

---

## Overview

Stage 3 is the rating calculation phase where properties are evaluated against configured criteria and assigned a score. This workflow shows both **individual** and **bulk** rating triggers.

---

## Workflow Diagram (Textual Representation)

This can be converted to draw.io using standard flowchart shapes.

### Entry Points

**Entry Point 1: Individual Property Rating**
- **Trigger:** User clicks "Calculate Rating" button on Property detail page
- **Prerequisites:**
  - Property state = `STAGE2_COMPLETE` or `STAGE3_COMPLETE`
  - PropertyList has `rating_criteria` configured

**Entry Point 2: Bulk Rating**
- **Trigger:** User clicks "Calculate Ratings for All Eligible Properties" on PropertyList detail page
- **Prerequisites:**
  - At least one property with state = `STAGE2_COMPLETE` or `STAGE3_COMPLETE`
  - PropertyList has `rating_criteria` configured

---

## Detailed Flow

```
┌─────────────────────────────────────┐
│ User Action                          │
│                                     │
│ [Calculate Rating] button clicked   │
│ (Individual or Bulk)                │
└──────────────┬──────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Frontend: Validate Prerequisites    │
│                                      │
│ • Property state eligible?          │
│ • Rating criteria configured?       │
└──────────────┬───────────────────────┘
               │
     ┌─────────┴─────────┐
     │                   │
   YES                  NO
     │                   │
     │                   ▼
     │         ┌──────────────────────┐
     │         │ Show Error Message   │
     │         │                      │
     │         │ "Please configure    │
     │         │ rating criteria"     │
     │         └──────────────────────┘
     │
     ▼
┌───────────────────────────────────────┐
│ Frontend: Send API Request           │
│                                       │
│ POST /api/properties/{id}/run-stage3/│
│                                       │
│ OR (bulk):                            │
│ POST /api/property-lists/{id}/       │
│      bulk-stage3/                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend API View                      │
│                                       │
│ • Authenticate user                   │
│ • Authorize (user can edit property) │
│ • Get property/properties             │
│ • Validate state                      │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Trigger State Transition              │
│                                       │
│ property.run_stage3()                 │
│ → State: STAGE3_IN_PROGRESS          │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Queue Celery Task                     │
│                                       │
│ calculate_rating_task.delay(          │
│     property_id=123                   │
│ )                                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Establish WebSocket        │
│                                       │
│ Subscribe to:                         │
│   property_{id} channel               │
│                                       │
│ Display: "Calculating rating..."      │
└──────────────┬────────────────────────┘
               │
               │ (Async boundary - frontend waits for WebSocket)
               │
               ▼
┌───────────────────────────────────────┐
│ CELERY TASK:                          │
│ calculate_rating_task(property_id)    │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Load Models                           │
│                                       │
│ property = Property.objects.get(      │
│     pk=property_id                    │
│ )                                     │
│ criteria = property.property_list     │
│            .rating_criteria           │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Get Enabled Criteria                  │
│                                       │
│ enabled_criteria = criteria           │
│     .get_enabled_criteria()           │
│                                       │
│ Result: List of criterion objects:    │
│  - SystemCriterion (price, bedrooms)  │
│  - UserCriterion (garden, POI dist)   │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Initialize Results Storage            │
│                                       │
│ criterion_scores = []                 │
│ disqualified = False                  │
│ disqualification_reason = None        │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ LOOP: For Each Criterion              │
└──────────────┬────────────────────────┘
               │
               ▼
        ┌──────────────────────┐
        │ Criterion Evaluator   │
        │ (Sub-workflow)        │
        └──────────┬────────────┘
                   │
                   ▼
        ┌───────────────────────────────────┐
        │ 1. Fetch Criterion Configuration  │
        │                                   │
        │ • Name (e.g., "Price")            │
        │ • Weight (0, 0.5, 1, 1.5)         │
        │ • Dealbreaker enabled?            │
        │ • Dealbreaker threshold           │
        │ • Scoring strategy:               │
        │   - min_max_normalization         │
        │   - inverted_normalization        │
        │   - ordinal_mapping               │
        │   - boolean                       │
        │   - threshold_based               │
        └───────────┬───────────────────────┘
                    │
                    ▼
        ┌───────────────────────────────────┐
        │ 2. Retrieve Property Data         │
        │                                   │
        │ • For system criteria:            │
        │   data = property.price           │
        │   data = property.bedrooms        │
        │                                   │
        │ • For user criteria:              │
        │   data = property.contextdata_set │
        │          .get(service='poi').data │
        └───────────┬───────────────────────┘
                    │
                    ▼
        ┌───────────────────────────────────┐
        │ 3. Check Data Availability        │
        │                                   │
        │ Is data available?                │
        └──────┬────────────────────────────┘
               │
     ┌─────────┴─────────┐
     │                   │
   YES                  NO
     │                   │
     │                   ▼
     │         ┌──────────────────────┐
     │         │ Mark Criterion:      │
     │         │ status = 'NO_DATA'   │
     │         │ score = None         │
     │         │                      │
     │         │ Skip to next         │
     │         └──────────────────────┘
     │
     ▼
┌────────────────────────────────────────┐
│ 4. Apply Scoring Strategy              │
│                                        │
│ Based on criterion.scoring_strategy:   │
└──────────────┬─────────────────────────┘
               │
     ┌─────────┴──────────┬────────────┬──────────┐
     │                    │            │          │
  Min-Max          Inverted      Ordinal    Boolean
     │                    │            │          │
     ▼                    ▼            ▼          ▼
┌─────────────┐  ┌───────────────┐ ┌──────────┐ ┌─────────┐
│ Normalize   │  │ Invert then   │ │ Map      │ │ True=   │
│ 0-100 scale │  │ normalize     │ │ category │ │ 100     │
│             │  │               │ │ to score │ │ False=0 │
│ e.g., Price │  │ e.g., Crime   │ │          │ │         │
│ £200k-£500k │  │ High=0        │ │ A=100    │ │ Garden: │
│ → 0-100     │  │ Low=100       │ │ B=80     │ │ True    │
└─────────────┘  └───────────────┘ └──────────┘ └─────────┘
     │                    │            │          │
     └────────────────────┴────────────┴──────────┘
                         │
                         ▼
              ┌────────────────────────┐
              │ raw_score (0-100)      │
              └───────────┬────────────┘
                          │
                          ▼
              ┌────────────────────────────────┐
              │ 5. Check Dealbreaker           │
              │                                │
              │ IF criterion.is_dealbreaker:   │
              │   IF raw_score < threshold:    │
              │     DISQUALIFY property        │
              └───────────┬────────────────────┘
                          │
                ┌─────────┴─────────┐
                │                   │
          Disqualified           Passed
                │                   │
                │                   ▼
                │         ┌──────────────────────┐
                │         │ 6. Apply Weight      │
                │         │                      │
                │         │ weighted_score =     │
                │         │   raw_score * weight │
                │         │                      │
                │         │ e.g., 80 * 1.5 = 120 │
                │         └──────────┬───────────┘
                │                    │
                │                    ▼
                │         ┌────────────────────────┐
                │         │ 7. Store Criterion     │
                │         │    Score               │
                │         │                        │
                │         │ CriterionScore.create( │
                │         │   property=property,   │
                │         │   criterion=criterion, │
                │         │   raw_score=80,        │
                │         │   weighted_score=120,  │
                │         │   status='SCORED'      │
                │         │ )                      │
                │         │                        │
                │         │ criterion_scores.      │
                │         │   append(120)          │
                │         └──────────┬─────────────┘
                │                    │
                ▼                    │
      ┌──────────────────┐           │
      │ DISQUALIFIED     │           │
      │                  │           │
      │ Set flag:        │           │
      │ disqualified=True│           │
      │ reason="Price    │           │
      │  below £200k"    │           │
      │                  │           │
      │ STOP evaluating  │           │
      │ other criteria   │           │
      └──────────────────┘           │
                                     │
                            ┌────────┴────────┐
                            │ More criteria?  │
                            └────┬────────┬───┘
                                YES      NO
                                 │        │
                                 │        ▼
                   ┌─────────────┘   ┌───────────────────────┐
                   │                 │ End of Loop           │
                   │                 └───────────┬───────────┘
                   │                             │
                   └─────────────────────────────┘
                                     │
                                     ▼
                          ┌──────────────────────────┐
                          │ Check If Disqualified    │
                          └──────┬───────────────────┘
                                 │
                       ┌─────────┴─────────┐
                       │                   │
                    YES                   NO
                       │                   │
                       │                   ▼
                       │        ┌────────────────────────────┐
                       │        │ 8. Aggregate Scores        │
                       │        │                            │
                       │        │ total_weighted =           │
                       │        │   sum(criterion_scores)    │
                       │        │                            │
                       │        │ num_scored =               │
                       │        │   len(criterion_scores)    │
                       │        │                            │
                       │        │ overall_rating =           │
                       │        │   total_weighted /         │
                       │        │   num_scored               │
                       │        │                            │
                       │        │ Normalize to 0-100:        │
                       │        │   (if using weighted sums) │
                       │        │                            │
                       │        │ Example:                   │
                       │        │   (120+100+90) / 3 = 103   │
                       │        │   → Clamp to 100           │
                       │        └──────────┬─────────────────┘
                       │                   │
                       ▼                   ▼
            ┌────────────────────┐  ┌──────────────────────┐
            │ 9a. Store Result:  │  │ 9b. Store Result:    │
            │     DISQUALIFIED   │  │      RATED           │
            │                    │  │                      │
            │ property.          │  │ property.            │
            │   overall_rating = │  │   overall_rating =   │
            │   None             │  │   87.5               │
            │                    │  │                      │
            │ property.          │  │ property.            │
            │   disqualified =   │  │   disqualified =     │
            │   True             │  │   False              │
            │                    │  │                      │
            │ property.          │  │ property.            │
            │   disqualification_│  │   disqualification_  │
            │   reason = "Price  │  │   reason = None      │
            │   below threshold" │  │                      │
            │                    │  │ property.            │
            │                    │  │   rating_breakdown = │
            │                    │  │   {criterion_scores} │
            └────────┬───────────┘  └──────────┬───────────┘
                     │                         │
                     └────────────┬────────────┘
                                  │
                                  ▼
                       ┌────────────────────────────┐
                       │ 10. State Transition       │
                       │                            │
                       │ property.complete_stage3() │
                       │ → State: STAGE3_COMPLETE   │
                       │                            │
                       │ property.save()            │
                       └──────────┬─────────────────┘
                                  │
                                  ▼
                       ┌────────────────────────────┐
                       │ 11. Send WebSocket Update  │
                       │                            │
                       │ channel_layer.group_send(  │
                       │   f'property_{id}',        │
                       │   {                        │
                       │     type: 'rating_update', │
                       │     property_state:        │
                       │       'STAGE3_COMPLETE',   │
                       │     overall_rating: 87.5,  │
                       │     disqualified: False    │
                       │   }                        │
                       │ )                          │
                       └──────────┬─────────────────┘
                                  │
                                  ▼
                       ┌────────────────────────────┐
                       │ Frontend: Receive Update   │
                       │                            │
                       │ • Hide "Calculating..."    │
                       │ • Display rating badge:    │
                       │   "87.5" with color coding │
                       │   (Green: >80, Yellow:     │
                       │    60-80, Red: <60)        │
                       │                            │
                       │ • OR if disqualified:      │
                       │   Display "Disqualified"   │
                       │   badge with reason        │
                       │                            │
                       │ • Enable "View Rating      │
                       │   Breakdown" link          │
                       └──────────┬─────────────────┘
                                  │
                                  ▼
                              [END]
```

---

## Scoring Strategy Details

### 1. Min-Max Normalization (Higher is Better)

**Used for:** Price (lower budget = higher score), Bedrooms, Square Area

**Formula:**
```
normalized_score = ((value - min) / (max - min)) * 100

Example - Price:
  Range: £200,000 - £500,000
  Property price: £300,000

  normalized = ((300000 - 200000) / (500000 - 200000)) * 100
            = (100000 / 300000) * 100
            = 33.3
```

**Configuration:**
```python
{
    "strategy": "min_max_normalization",
    "min_value": 200000,
    "max_value": 500000,
    "invert": False  # Higher value = higher score
}
```

---

### 2. Inverted Normalization (Lower is Better)

**Used for:** Crime rating, Distance to POI

**Formula:**
```
normalized_score = 100 - (((value - min) / (max - min)) * 100)

Example - Crime Score:
  Range: 0 - 100 (crime index)
  Property crime score: 60

  normalized = 100 - (((60 - 0) / (100 - 0)) * 100)
            = 100 - 60
            = 40

  (Lower crime = higher rating score)
```

**Configuration:**
```python
{
    "strategy": "inverted_normalization",
    "min_value": 0,
    "max_value": 100,
    "invert": True
}
```

---

### 3. Ordinal Mapping (Categories)

**Used for:** EPC Rating (A-G), Council Tax Band (A-H)

**Mapping:**
```python
EPC_RATING_SCORES = {
    'A': 100,
    'B': 85,
    'C': 70,
    'D': 55,
    'E': 40,
    'F': 25,
    'G': 10
}

Example:
  Property EPC: 'C'
  Score: 70
```

**Configuration:**
```python
{
    "strategy": "ordinal_mapping",
    "mapping": {
        "A": 100,
        "B": 85,
        ...
    }
}
```

---

### 4. Boolean (Yes/No)

**Used for:** Garden, Parking, Furnished

**Mapping:**
```
True → 100
False → 0
```

**Configuration:**
```python
{
    "strategy": "boolean",
    "true_score": 100,
    "false_score": 0
}
```

---

### 5. Threshold-Based (Custom Ranges)

**Used for:** Broadband speed, Mobile coverage

**Ranges:**
```python
BROADBAND_THRESHOLDS = [
    {"min": 0, "max": 10, "score": 0},      # <10 Mbps: Unusable
    {"min": 10, "max": 30, "score": 40},    # 10-30 Mbps: Poor
    {"min": 30, "max": 100, "score": 70},   # 30-100 Mbps: Good
    {"min": 100, "max": None, "score": 100} # >100 Mbps: Excellent
]

Example:
  Property broadband: 75 Mbps
  Score: 70
```

**Configuration:**
```python
{
    "strategy": "threshold_based",
    "thresholds": [
        {"min": 0, "max": 10, "score": 0},
        ...
    ]
}
```

---

## Dealbreaker Logic

### Example 1: Price Dealbreaker

**Configuration:**
```python
{
    "criterion": "price",
    "is_dealbreaker": True,
    "dealbreaker_threshold": 50,  # Minimum score required
    "dealbreaker_message": "Price exceeds budget"
}
```

**Scenario:**
- User's max budget: £350,000
- Property price: £450,000
- Price criterion configured with max £400,000
- Normalized score: ((450000 - 200000) / (400000 - 200000)) * 100 = 125 → clamp to 100
- **But wait:** Price is inverted (lower is better), so: 100 - 125 = -25 → clamp to 0
- **Result:** Score = 0, which is < 50 threshold
- **Outcome:** Property DISQUALIFIED

---

### Example 2: School Rating Dealbreaker

**Configuration:**
```python
{
    "criterion": "school_rating",
    "is_dealbreaker": True,
    "dealbreaker_threshold": 70,
    "dealbreaker_message": "No Good or Outstanding schools nearby"
}
```

**Scenario:**
- Nearby schools: 2 schools, both "Requires Improvement"
- Average Ofsted score: 50
- **Result:** Score = 50, which is < 70 threshold
- **Outcome:** Property DISQUALIFIED

---

## Weight Application

### Weight Values

| Weight Name | Multiplier | Usage |
|-------------|------------|-------|
| Very Important | 1.5 | User's top priorities |
| Important | 1.0 | Standard criteria |
| Nice to Have | 0.5 | Desirable but not critical |
| Not Important | 0.0 | Disabled (not scored) |

### Example Calculation

**Criteria Configuration:**
```
1. Price: Weight = Very Important (1.5)
2. Bedrooms: Weight = Important (1.0)
3. Garden: Weight = Nice to Have (0.5)
4. Crime: Weight = Important (1.0)
5. Schools: Weight = Very Important (1.5)
```

**Raw Scores:**
```
1. Price: 80
2. Bedrooms: 100
3. Garden: 100 (has garden)
4. Crime: 60
5. Schools: 90
```

**Weighted Scores:**
```
1. Price: 80 * 1.5 = 120
2. Bedrooms: 100 * 1.0 = 100
3. Garden: 100 * 0.5 = 50
4. Crime: 60 * 1.0 = 60
5. Schools: 90 * 1.5 = 135
```

**Aggregation:**
```
Total weighted score = 120 + 100 + 50 + 60 + 135 = 465
Number of criteria = 5
Average = 465 / 5 = 93

Overall Rating: 93 / 100
```

**Note:** Some implementations may cap individual weighted scores at 100 before aggregation to prevent "Very Important" criteria from dominating. This is a design choice.

---

## Bulk Rating Flow

When user clicks "Calculate Ratings for All Eligible Properties":

```
┌─────────────────────────────────────┐
│ Frontend: Bulk Rating Button Click │
└──────────────┬──────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Send API Request            │
│                                       │
│ POST /api/property-lists/{id}/       │
│      bulk-stage3/                     │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Backend: Get Eligible Properties      │
│                                       │
│ properties = Property.objects.filter( │
│     property_list=list,               │
│     state__in=['STAGE2_COMPLETE',     │
│                'STAGE3_COMPLETE']      │
│ )                                     │
│                                       │
│ Count: 5 properties eligible          │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Queue Multiple Celery Tasks           │
│                                       │
│ for prop in properties:               │
│     prop.run_stage3()                 │
│     calculate_rating_task.delay(      │
│         prop.id                       │
│     )                                 │
│                                       │
│ Result: 5 tasks queued                │
└──────────────┬────────────────────────┘
               │
               ▼
┌───────────────────────────────────────┐
│ Frontend: Show Bulk Progress          │
│                                       │
│ "Calculating ratings for 5            │
│  properties..."                       │
│                                       │
│ Progress: 2/5 complete                │
│                                       │
│ (Updates via WebSocket as each        │
│  property completes)                  │
└───────────────────────────────────────┘
```

Each property follows the individual rating workflow (see main diagram above).

---

## Error Handling

### Missing Data Errors

**Scenario:** Rating criterion requires context data that failed to retrieve.

**Example:**
- Criterion: "Broadband Speed" (weight: Important)
- Context data: Broadband service FAILED (API timeout)

**Handling:**
```python
def calculate_broadband_criterion(property):
    context_data = property.contextdata_set.filter(
        service_name='broadband'
    ).first()

    if not context_data or context_data.status == 'FAILED':
        return {
            'status': 'NO_DATA',
            'raw_score': None,
            'weighted_score': None,
            'message': 'Broadband data not available'
        }

    # Normal scoring...
```

**Result:**
- Criterion skipped (not counted in aggregation)
- Overall rating calculated from available criteria only
- UI shows: "Rated using 4/5 criteria (Broadband data unavailable)"

---

### Celery Task Failure

**Scenario:** Rating calculation task crashes (bug, database error, etc.).

**Handling:**
```python
@shared_task(bind=True, max_retries=3)
def calculate_rating_task(self, property_id):
    try:
        property = Property.objects.get(pk=property_id)
        # ... rating logic ...
        property.complete_stage3()
        property.save()

    except Exception as exc:
        logger.error(f"Rating calculation failed for property {property_id}: {exc}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

**If all retries fail:**
- Property remains in `STAGE3_IN_PROGRESS` state
- Frontend shows error: "Rating calculation failed. Please try again."
- User can click "Calculate Rating" again to retry

---

## Performance Considerations

### Bulk Rating Optimization

For large property lists (100+ properties), consider batching:

```python
from celery import group

def bulk_calculate_ratings(property_list_id):
    properties = Property.objects.filter(
        property_list_id=property_list_id,
        state__in=['STAGE2_COMPLETE', 'STAGE3_COMPLETE']
    )

    # Process in batches of 10 to avoid overwhelming Celery
    batch_size = 10
    for i in range(0, len(properties), batch_size):
        batch = properties[i:i+batch_size]

        job = group(
            calculate_rating_task.s(prop.id)
            for prop in batch
        )
        job.apply_async()

        # Small delay between batches
        time.sleep(1)
```

### Caching Criterion Configurations

Rating criteria are read-heavy (same criteria used for all properties in list):

```python
from django.core.cache import cache

def get_rating_criteria(property_list_id):
    cache_key = f"rating_criteria:{property_list_id}"
    criteria = cache.get(cache_key)

    if criteria is None:
        criteria = RatingCriteria.objects.get(
            propertylist__id=property_list_id
        )
        # Cache for 1 hour
        cache.set(cache_key, criteria, timeout=3600)

    return criteria

# Invalidate cache when criteria updated
@receiver(post_save, sender=RatingCriteria)
def invalidate_criteria_cache(sender, instance, **kwargs):
    for prop_list in instance.propertylist_set.all():
        cache_key = f"rating_criteria:{prop_list.id}"
        cache.delete(cache_key)
```

---

## UI Components

### Rating Display - Property Card

```
┌─────────────────────────────────────┐
│ 123 Main Street, London             │
│                                     │
│ £350,000 • 3 bed • 2 bath           │
│                                     │
│ Status: Stage 3 Complete            │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │  Rating: 87.5                   │ │
│ │  ★★★★☆                          │ │
│ │  [View Breakdown]               │ │
│ └─────────────────────────────────┘ │
│                                     │
│ [View Details]  [Edit]              │
└─────────────────────────────────────┘
```

### Rating Breakdown Modal

```
┌─────────────────────────────────────────────────┐
│ Rating Breakdown - 123 Main Street              │
├─────────────────────────────────────────────────┤
│                                                 │
│ Overall Rating: 87.5 / 100                      │
│ ████████████████████████████████████░░░░ 87.5%  │
│                                                 │
│ ─────────────────────────────────────────────── │
│                                                 │
│ System Criteria:                                │
│                                                 │
│ ✓ Price (Very Important, 1.5x)                  │
│   Score: 80 / 100 → Weighted: 120               │
│   £350,000 (Budget: £200k-£400k)                │
│                                                 │
│ ✓ Bedrooms (Important, 1.0x)                    │
│   Score: 100 / 100 → Weighted: 100              │
│   3 bedrooms (Perfect match)                    │
│                                                 │
│ ✓ Crime Rating (Important, 1.0x)                │
│   Score: 60 / 100 → Weighted: 60                │
│   Medium crime area                             │
│                                                 │
│ ─────────────────────────────────────────────── │
│                                                 │
│ User Criteria:                                  │
│                                                 │
│ ✓ Garden (Nice to Have, 0.5x)                   │
│   Score: 100 / 100 → Weighted: 50               │
│   Has garden ✓                                  │
│                                                 │
│ ✓ School Rating (Very Important, 1.5x)          │
│   Score: 90 / 100 → Weighted: 135               │
│   2 Outstanding schools nearby                  │
│                                                 │
│ ✗ Broadband Speed (Not scored)                  │
│   Data unavailable (service failed)             │
│                                                 │
│ ─────────────────────────────────────────────── │
│                                                 │
│ Total: 465 / 5 criteria = 93                    │
│                                                 │
│ [Recalculate Rating]  [Close]                   │
└─────────────────────────────────────────────────┘
```

### Disqualified Property Display

```
┌─────────────────────────────────────┐
│ 456 Oak Avenue, Manchester           │
│                                     │
│ £500,000 • 4 bed • 3 bath           │
│                                     │
│ Status: Stage 3 Complete            │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │  ⚠ DISQUALIFIED                 │ │
│ │                                 │ │
│ │  Reason: Price exceeds budget   │ │
│ │  (Threshold: £450,000)          │ │
│ │                                 │ │
│ │  [View Details]                 │ │
│ └─────────────────────────────────┘ │
│                                     │
│ [Edit] [Remove from List]           │
└─────────────────────────────────────┘
```

---

## Summary

**Stage 3 Rating Workflow:**
1. User triggers (individual or bulk)
2. Backend validates eligibility
3. Celery task processes each property
4. For each criterion:
   - Fetch configuration
   - Retrieve data
   - Apply scoring strategy
   - Check dealbreaker
   - Calculate weighted score
5. Aggregate scores
6. Store results
7. Update state to STAGE3_COMPLETE
8. Send WebSocket update
9. Frontend displays rating

**Key Features:**
- Flexible scoring strategies
- Dealbreaker early-exit logic
- Weighted importance
- Graceful handling of missing data
- Bulk operations for efficiency
- Real-time progress updates

This workflow is now ready for implementation and draw.io visualization.
