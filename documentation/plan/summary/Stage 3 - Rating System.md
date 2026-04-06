# Stage 3: Rating System

Stage 3 evaluates properties based on weighted criteria and assigns numerical scores. Properties are assessed against both dealbreaker gates and scoring criteria to provide comparative ratings across the property list.

---

## Overview

**Purpose:** Calculate property ratings based on user-defined weighted criteria

**Triggering:** Manual (user clicks button) - NOT automatic

**Scoring Strategies:** 5 types (min-max, inverted, ordinal, boolean, threshold)

**Weight System:** Very Important (1.5), Important (1), Nice to Have (0.5), Not Important (0)

**Dealbreakers:** Early-exit gates that disqualify properties before scoring

---

## Rating Criteria Types

### System Criteria (7)
Built-in criteria based on core property fields:

| Criterion        | Source Field              | Data Type | Scoring Strategy                        |
| ---------------- | ------------------------- | --------- | --------------------------------------- |
| Price            | property.price            | Decimal   | Inverted min-max (lower better)         |
| Bedrooms         | property.bedrooms         | Integer   | Min-max (higher better)                 |
| Bathrooms        | property.bathrooms        | Integer   | Min-max (higher better)                 |
| Council Tax Band | property.council_tax_band | Character | Ordinal mapping (A=100, B=90...)        |
| Crime Rating     | context_data['crime']     | String    | Ordinal mapping (Low=100, Medium=50...) |
| EPC Rating       | property.epc_rating       | Character | Ordinal mapping (A=100, B=90...)        |
| Square Area      | property.square_area      | Decimal   | Min-max (higher better)                 |

### User Criteria (14)
Configurable criteria based on context data and preferences:

| Criterion | Source | Data Type | Scoring Strategy |
|-----------|--------|-----------|------------------|
| Distance to POI | context_data['poi'] | Decimal (meters) | Inverted min-max (closer better) |
| Amount of POI nearby | context_data['poi'] | Integer | Min-max (more better) |
| Garden | property.garden | Boolean | Boolean (Yes=100) |
| Furnished Status | property.furnished_status | String | Boolean (Furnished=100) |
| Child Suitability | property.child_suitable | Boolean | Boolean (Yes=100) |
| Broadband Speed | context_data['broadband'] | Decimal (Mbps) | Min-max (higher better) |
| Mobile Coverage | context_data['mobile'] | String | Ordinal mapping (Excellent=100...) |
| School Rating | context_data['schools'] | String | Ordinal mapping (Outstanding=100...) |
| Parking | property.parking | Boolean | Boolean (Yes=100) |
| Distance to Saved Location | Calculated from coordinates | Decimal (meters) | Inverted min-max (closer better) |
| Energy Efficiency | property.epc_rating | Integer | Min-max (higher better) |
| Lease Length | property.lease_length | Integer (years) | Min-max (longer better) |
| Completion Date | property.completion_date | Date | Threshold (sooner=100) |
| Floor Level | property.floor_level | Integer | User-defined (higher/lower better) |

---

## Stage 3 Workflow

### 1. User Clicks "Calculate Rating" Button

**Entry Points:**
- **Individual Property:** Property detail page → "Calculate Rating" button (enabled when `state = Stage2Complete` or `Stage3Complete`)
- **Bulk Operation:** Property List page → "Calculate Ratings for All" button (only for properties in `Stage2Complete` or `Stage3Complete`)

**Pre-Condition Checks:**
- Property must be in `Stage2Complete` or `Stage3Complete` state
- Rating criteria must be configured for the property list

### 2. Backend Initiates Rating Calculation

**State Transition:** `Property.state: Stage2Complete → Stage3InProgress`

**Process:**
```python
@transition(field=state, source=['Stage2Complete', 'Stage3Complete'], target='Stage3InProgress')
def run_stage3(self):
    """User triggers Stage 3 via button click"""
    calculate_rating_task.delay(self.id)  # Celery task
```

**Celery Task Launch:**
- Single Celery task per property
- Task executes rating pipeline (see below)
- Task updates property state on completion

### 3. Rating Calculation Pipeline

**5-Step Process:**

#### Step 1: Dealbreaker Gate Evaluation

**Purpose:** Early-exit gate to disqualify properties before scoring

**Logic:**
```python
def evaluate_dealbreakers(property, rating_criteria):
    """Check all dealbreaker criteria first"""
    dealbreaker_criteria = rating_criteria.criteria.filter(is_dealbreaker=True)

    for criterion in dealbreaker_criteria:
        raw_value = extract_raw_value(property, criterion)

        if not meets_dealbreaker_threshold(raw_value, criterion):
            # Disqualify and exit early
            property.disqualified = True
            property.disqualification_reason = f"Failed dealbreaker: {criterion.name}"
            property.overall_rating = 0
            property.save()
            return False  # Stop processing

    return True  # Passed all dealbreakers, continue to scoring
```

**Example Dealbreakers:**
- Price must be ≤ £500,000
- Minimum 3 bedrooms required
- Crime rating must not be "High"
- Must have parking

**If Failed:**
- Property marked as `disqualified = True`
- Overall rating set to 0
- No scoring performed
- Property transitions to `Stage3Complete`

#### Step 2: Raw Value Extraction

**Purpose:** Retrieve criterion values from property data or context data

**Logic:**
```python
def extract_raw_value(property, criterion):
    """Extract raw value based on criterion source"""
    if criterion.source == 'property':
        return getattr(property, criterion.field_name)
    elif criterion.source == 'context':
        context_data = property.context_data.get(service_name=criterion.service_name)
        return context_data.data[criterion.data_path]
    elif criterion.source == 'calculated':
        # e.g., distance to saved location
        return calculate_distance(property, criterion.target_location)
```

**Example Extractions:**
- Price: `property.price` → 350000.00
- Crime rating: `context_data['crime'].data['rating']` → "Low"
- Distance to work: `calculate_distance(property, user.saved_locations.get(name='Work'))` → 5000.0 (meters)

#### Step 3: Scoring (Normalization)

**Purpose:** Convert raw values to 0-100 normalized scores

**5 Scoring Strategies:**

##### Strategy 1: Min-Max Normalization (Higher is Better)
```python
def score_min_max(value, criterion, all_properties):
    """Higher values get higher scores"""
    values = [extract_raw_value(p, criterion) for p in all_properties]
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return 100  # All properties equal

    normalized = (value - min_val) / (max_val - min_val) * 100
    return normalized

# Example: Bedrooms (3 bedrooms)
# All properties: 2, 3, 3, 4, 5 bedrooms
# min=2, max=5
# score = (3 - 2) / (5 - 2) * 100 = 33.33
```

##### Strategy 2: Inverted Min-Max (Lower is Better)
```python
def score_inverted_min_max(value, criterion, all_properties):
    """Lower values get higher scores"""
    values = [extract_raw_value(p, criterion) for p in all_properties]
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        return 100

    normalized = (max_val - value) / (max_val - min_val) * 100
    return normalized

# Example: Price (£350,000)
# All properties: £300k, £350k, £400k, £450k
# min=300k, max=450k
# score = (450k - 350k) / (450k - 300k) * 100 = 66.67
```

##### Strategy 3: Ordinal Mapping
```python
def score_ordinal(value, criterion):
    """Map categorical values to predefined scores"""
    mapping = criterion.ordinal_mapping  # Stored in database

    return mapping.get(value, 0)

# Example: Council Tax Band ('B')
# Mapping: {'A': 100, 'B': 90, 'C': 80, 'D': 70, 'E': 60, 'F': 50, 'G': 40, 'H': 30}
# score = 90

# Example: Crime Rating ('Low')
# Mapping: {'Low': 100, 'Medium': 50, 'High': 0}
# score = 100
```

##### Strategy 4: Boolean
```python
def score_boolean(value, criterion):
    """Convert boolean to 0 or 100"""
    if criterion.boolean_true_is_better:
        return 100 if value else 0
    else:
        return 0 if value else 100

# Example: Has Garden (True)
# true_is_better = True
# score = 100
```

##### Strategy 5: Threshold-Based
```python
def score_threshold(value, criterion):
    """Score based on threshold ranges"""
    thresholds = criterion.thresholds  # List of (threshold, score) tuples

    for threshold, score in sorted(thresholds, reverse=True):
        if value >= threshold:
            return score

    return 0

# Example: Distance to Station (300 meters)
# Thresholds: [(0, 100), (500, 75), (1000, 50), (2000, 25)]
# value=300 is ≥0, so score = 100
```

#### Step 4: Weight Application

**Purpose:** Apply importance weights to normalized scores

**Weight Values:**
- **Very Important:** 1.5
- **Important:** 1.0
- **Nice to Have:** 0.5
- **Not Important:** 0.0 (criterion skipped)

**Logic:**
```python
def apply_weight(normalized_score, weight):
    """Multiply normalized score by weight"""
    return normalized_score * weight

# Example: Price criterion
# normalized_score = 66.67
# weight = 1.5 (Very Important)
# weighted_score = 66.67 * 1.5 = 100.00
```

#### Step 5: Overall Rating Aggregation

**Purpose:** Calculate final property rating

**Formula:**
```python
def calculate_overall_rating(property, rating_criteria):
    """Calculate final rating from all criterion scores"""
    weighted_scores = []
    weights = []

    for criterion in rating_criteria.criteria.filter(weight__gt=0):
        raw_value = extract_raw_value(property, criterion)
        normalized_score = score_criterion(raw_value, criterion, all_properties)
        weighted_score = normalized_score * criterion.weight

        weighted_scores.append(weighted_score)
        weights.append(criterion.weight)

        # Save individual criterion score
        CriterionScore.objects.update_or_create(
            property=property,
            criterion=criterion,
            defaults={
                'raw_value': raw_value,
                'normalized_score': normalized_score,
                'weighted_score': weighted_score
            }
        )

    # Overall rating = sum of weighted scores / sum of weights
    overall_rating = sum(weighted_scores) / sum(weights) if weights else 0

    return overall_rating

# Example Calculation:
# Criterion 1: Price (score=66.67, weight=1.5) → weighted=100.00
# Criterion 2: Bedrooms (score=33.33, weight=1.5) → weighted=50.00
# Criterion 3: Garden (score=100, weight=0.5) → weighted=50.00
#
# overall_rating = (100 + 50 + 50) / (1.5 + 1.5 + 0.5) = 200 / 3.5 = 57.14
```

### 4. Rating Persistence

**Database Updates:**
```python
# Save overall rating
property.overall_rating = overall_rating
property.rating_breakdown = {
    'total_criteria': len(weighted_scores),
    'scored_criteria': len(weighted_scores),
    'dealbreakers_passed': True
}
property.save()

# Individual criterion scores already saved in Step 5
```

### 5. Stage 3 Completion

**State Transition:** `Property.state: Stage3InProgress → Stage3Complete`

**WebSocket Event:**
```javascript
{
  type: 'rating_complete',
  property_id: 123,
  property_state: 'Stage3Complete',
  overall_rating: 57.14,
  rating_breakdown: {
    'Price': { normalized: 66.67, weighted: 100.00 },
    'Bedrooms': { normalized: 33.33, weighted: 50.00 },
    'Garden': { normalized: 100, weighted: 50.00 }
  }
}
```

**UI Updates:**
- Display overall rating score
- Show star rating visualization
- Display criterion breakdown table
- Enable "Compare Properties" button

---

## Rating Criteria Management

### Creating Rating Criteria ✅ BACKEND API IMPLEMENTED / ⏳ FRONTEND UI TODO

**Two Options:**

#### Option 1: Create New Criteria
User builds custom rating criteria from scratch:
1. Navigate to Property List → "Add Rating Criteria" → "Create New"
2. Configure criteria:
   - Select criteria to include (from system + user criteria lists)
   - Set importance weight for each (Very Important, Important, Nice to Have, Not Important)
   - Mark dealbreakers (optional)
   - Configure ordinal mappings/thresholds if needed
3. Save criteria with a name (e.g., "Family-Friendly Criteria")

#### Option 2: Select Existing Criteria
User reuses previously created criteria:
1. Navigate to Property List → "Add Rating Criteria" → "Select Existing"
2. Browse list of:
   - User's own criteria
   - Platform-provided templates (optional)
3. Select criteria to use
4. Property list references criteria via FK (no duplication)

### Reference-with-Copy-on-Write (Decision #1) ✅ BACKEND SUPPORT / ⏳ FRONTEND WORKFLOW TODO

**Sharing Behavior:**
- Rating criteria are referenced (not duplicated initially)
- Multiple property lists can share the same rating criteria
- Tracks provenance with `rating_criteria_source` field

**Copy-on-Write Trigger:**
When user edits a shared criteria:
```python
def edit_rating_criteria(property_list, new_criteria_data):
    """Edit criteria with copy-on-write logic"""
    current_criteria = property_list.rating_criteria

    # Check if criteria is shared with other lists
    if current_criteria.propertylist_set.count() > 1:
        # Fork: Create new criteria instance
        new_criteria = RatingCriteria.objects.create(
            name=f"{current_criteria.name} (Modified)",
            owner=property_list.owner,
            **new_criteria_data
        )

        # Track original source
        property_list.rating_criteria_source = current_criteria
        property_list.rating_criteria = new_criteria
        property_list.save()

        # Trigger automatic re-rating for all properties
        for property in property_list.properties.filter(state='Stage3Complete'):
            property.run_stage3()
    else:
        # Not shared, edit directly
        for key, value in new_criteria_data.items():
            setattr(current_criteria, key, value)
        current_criteria.save()

        # Trigger automatic re-rating
        for property in property_list.properties.filter(state='Stage3Complete'):
            property.run_stage3()
```

**Benefits:**
- Prevents unintended changes to other lists using the same criteria
- Maintains flexibility to reuse common criteria configurations
- Tracks criteria evolution history

---

## Automatic Re-Rating ⏳ TODO

**Triggers (Automatic, No User Action Required):**

### 1. Property Field Changes ⏳ TODO
When property data changes that affect rating criteria:
```python
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
}

# On property save
def save(self, *args, **kwargs):
    changed_fields = self.get_changed_fields()
    super().save(*args, **kwargs)

    # Check if any rating-dependent fields changed
    if any(field in FIELD_RATING_DEPENDENCIES for field in changed_fields):
        if self.state == 'Stage3Complete':
            # Automatic re-rating (no confirmation needed)
            self.run_stage3()
```

### 2. Context Data Updates ⏳ TODO
When context services rerun and update data:
```python
# After context service completes
def on_context_data_complete(property, service_name):
    # Check if any rating criteria use this service
    rating_criteria = property.property_list.rating_criteria
    if rating_criteria and rating_criteria.uses_service(service_name):
        if property.state == 'Stage3Complete':
            # Automatic re-rating
            property.run_stage3()
```

### 3. Rating Criteria Modifications ⏳ TODO
When criteria configuration changes:
```python
# After rating criteria edit
def save(self, *args, **kwargs):
    super().save(*args, **kwargs)

    # Trigger re-rating for all properties using this criteria
    for property_list in self.propertylist_set.all():
        for property in property_list.properties.filter(state='Stage3Complete'):
            property.run_stage3()
```

**Note:** Automatic re-rating does NOT show confirmation dialogs (unlike service reruns), as rating calculations are:
- Fast (no external API calls)
- Free (no cost)
- Expected behavior (users want up-to-date ratings)

---

## UI Components ⏳ TODO (Frontend)

### Property Detail Page - Stage 3 Complete ⏳ TODO

```
┌─────────────────────────────────────────────────┐
│ 123 Main Street, London SW1A 1AA                │
│ £350,000 • 3 bed • 2 bath                       │
│                                                 │
│ Status: Stage 3 Complete                        │
│                                                 │
│ Overall Rating: 87.5 ★★★★☆                      │
│                                                 │
│ [Recalculate Rating]  [Compare Properties]      │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Rating Breakdown:                               │
│                                                 │
│ Price (Very Important)                          │
│ ━━━━━━━━━━━━━━━━━━━━░░░░░░░░ 66.7/100          │
│                                                 │
│ Bedrooms (Very Important)                       │
│ ━━━━━━━━━━░░░░░░░░░░░░░░░░░░ 33.3/100          │
│                                                 │
│ Crime Rating (Important)                        │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100/100           │
│                                                 │
│ Garden (Nice to Have)                           │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100/100           │
│                                                 │
│ Distance to Work (Important)                    │
│ ━━━━━━━━━━━━━━━━░░░░░░░░░░░░ 50/100            │
│                                                 │
│ [View All Criteria (8)]                         │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Property Detail Page - Disqualified ⏳ TODO

```
┌─────────────────────────────────────────────────┐
│ 456 Oak Avenue, Manchester                      │
│ £550,000 • 2 bed • 1 bath                       │
│                                                 │
│ Status: Disqualified                            │
│                                                 │
│ ⚠️ This property did not meet dealbreaker       │
│    requirements:                                │
│                                                 │
│ • Price exceeds maximum (£500,000)              │
│                                                 │
│ [Edit Rating Criteria]                          │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Property List Page - Comparison View ⏳ TODO

```
┌─────────────────────────────────────────────────┐
│ My House Hunt - Property Comparison             │
│                                                 │
│ Sort by: Rating (High to Low) ▼                 │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 1. 789 Elm St, Birmingham               │     │
│ │ Rating: 92.3 ★★★★★                      │     │
│ │ £380,000 • 4 bed • 2 bath               │     │
│ │ [View Details]                          │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 2. 123 Main St, London                  │     │
│ │ Rating: 87.5 ★★★★☆                      │     │
│ │ £350,000 • 3 bed • 2 bath               │     │
│ │ [View Details]                          │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 3. 456 Oak Ave, Manchester              │     │
│ │ ⚠️ Disqualified (Price too high)        │     │
│ │ £550,000 • 2 bed • 1 bath               │     │
│ │ [View Details]                          │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Rating Criteria Configuration Form ⏳ TODO

```
┌─────────────────────────────────────────────────┐
│ Configure Rating Criteria                       │
│                                                 │
│ Criteria Name: Family-Friendly Criteria         │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ System Criteria:                                │
│                                                 │
│ ☑ Price                                         │
│   Importance: ◉ Very Important                  │
│   □ Dealbreaker (Max: £500,000)                 │
│                                                 │
│ ☑ Bedrooms                                      │
│   Importance: ◉ Very Important                  │
│   ☑ Dealbreaker (Min: 3)                        │
│                                                 │
│ ☑ Crime Rating                                  │
│   Importance: ◉ Important                       │
│   ☑ Dealbreaker (Not "High")                    │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ User Criteria:                                  │
│                                                 │
│ ☑ Garden                                        │
│   Importance: ◉ Nice to Have                    │
│                                                 │
│ ☑ Distance to Work (Saved Location)             │
│   Importance: ◉ Important                       │
│   Location: Home Office                         │
│                                                 │
│ ☑ School Rating                                 │
│   Importance: ◉ Very Important                  │
│                                                 │
│ [Save Criteria]  [Cancel]                       │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## API Endpoints

### Stage 3 Triggering ✅ IMPLEMENTED
```
POST   /api/properties/{uuid}/run-stage3/              # ✅ Trigger Stage 3 for property
POST   /api/projects/{uuid}/run-stage3-bulk/           # ✅ Trigger Stage 3 for all properties in project
```

**Note:** Project-level bulk (not property-list level) due to rating criteria being at project scope.

### Rating Criteria Management ✅ IMPLEMENTED
```
GET    /api/rating-criteria/                      # ✅ List all user's criteria
POST   /api/rating-criteria/                      # ✅ Create new criteria
GET    /api/rating-criteria/{uuid}/               # ✅ Get criteria details
PUT    /api/rating-criteria/{uuid}/               # ✅ Update criteria
PATCH  /api/rating-criteria/{uuid}/               # ✅ Partial update criteria
DELETE /api/rating-criteria/{uuid}/               # ✅ Delete criteria
POST   /api/rating-criteria/{uuid}/copy/          # ✅ Copy criteria (copy-on-write support)
```

### Rating Results ✅ IMPLEMENTED
```
GET    /api/properties/{uuid}/rating/                  # ✅ Get overall rating and breakdown
GET    /api/properties/{uuid}/criterion-scores/       # ✅ Get individual criterion scores
GET    /api/projects/{uuid}/property-comparison/      # ✅ Get sorted comparison (project-level)
       ?min_rating=80                                  # ✅ Filter by minimum rating
       &exclude_disqualified=true                      # ✅ Exclude disqualified properties
```

**Note:** Comparison at project level (not property-list level) to support cross-list comparison.

### WebSocket Endpoint ✅ IMPLEMENTED
```
ws://host/ws/property/{property_uuid}/            # ✅ Real-time rating updates (property channel)
ws://host/ws/property-list/{list_uuid}/           # ✅ Real-time rating updates (list channel)
```

**Events:**
- `rating_progress` - Rating calculation in progress
- `rating_complete` - Rating calculation finished
- `rating_failed` - Rating calculation failed

---

## Data Models ✅ IMPLEMENTED

```python
class RatingCriteria(models.Model):  # ✅ Implemented in property/models/stage3_models.py
    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, related_name='rating_criteria')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def uses_service(self, service_name):
        """Check if any criteria use this context service"""
        return self.criteria.filter(source='context', service_name=service_name).exists()

class Criterion(models.Model):  # ✅ Implemented in property/models/stage3_models.py
    rating_criteria = models.ForeignKey(RatingCriteria, related_name='criteria')
    name = models.CharField(max_length=255)

    # Source configuration
    source = models.CharField(max_length=20)  # 'property', 'context', 'calculated'
    field_name = models.CharField(max_length=100, null=True)  # For 'property' source
    service_name = models.CharField(max_length=50, null=True)  # For 'context' source
    data_path = models.CharField(max_length=255, null=True)  # JSON path for context data

    # Scoring configuration
    scoring_strategy = models.CharField(max_length=50)  # 'min_max', 'inverted', 'ordinal', 'boolean', 'threshold'
    ordinal_mapping = models.JSONField(null=True)  # {'A': 100, 'B': 90, ...}
    thresholds = models.JSONField(null=True)  # [(0, 100), (500, 75), ...]
    boolean_true_is_better = models.BooleanField(default=True)

    # Weight and dealbreaker
    weight = models.DecimalField(max_digits=3, decimal_places=1)  # 0, 0.5, 1, 1.5
    is_dealbreaker = models.BooleanField(default=False)
    dealbreaker_threshold = models.JSONField(null=True)  # {'operator': '>=', 'value': 3}

class Project(models.Model):  # ✅ CHANGE: Rating criteria moved to Project level
    # ... other fields

    # ✅ Rating criteria (moved from PropertyList)
    rating_criteria = models.ForeignKey(RatingCriteria, null=True, blank=True, on_delete=models.SET_NULL, related_name='projects')
    rating_criteria_source = models.ForeignKey(
        RatingCriteria,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derived_projects',
        help_text='Source criteria if this was created via copy-on-write'
    )

class PropertyList(models.Model):
    # ... other fields
    # ⚠️ NOTE: rating_criteria removed - now at Project level

class Property(models.Model):  # ✅ Implemented in property/models/stage1_models.py
    # ... other fields

    # ✅ Stage 3 results
    overall_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rating_breakdown = models.JSONField(null=True, blank=True)
    disqualified = models.BooleanField(default=False)
    disqualification_reason = models.TextField(blank=True)

class CriterionScore(models.Model):  # ✅ Implemented in property/models/stage3_models.py
    property = models.ForeignKey(Property, related_name='criterion_scores', on_delete=models.CASCADE)
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='scores')

    raw_value = models.JSONField()  # Original value (price, boolean, etc.)
    normalized_score = models.DecimalField(max_digits=5, decimal_places=2)  # 0-100
    weighted_score = models.DecimalField(max_digits=5, decimal_places=2)  # normalized * weight

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('property', 'criterion')
```

---

## State Transitions ✅ IMPLEMENTED

**Property State Machine (Stage 3 Portion):**
```
Stage2Complete ──────────> Stage3InProgress  # ✅ run_stage3() transition
                              │
                              │ (rating calculation complete)
                              │
                              ▼
Stage3Complete <───────── Stage3InProgress  # ✅ complete_stage3() transition
       │                      ▲
       │                      │
       │ (field/criteria      │ (automatic re-rating) ⏳ TODO
       │  change)             │
       │                      │
       └──────────────────────┘
```

**Transitions:**
- ✅ `Stage2Complete → Stage3InProgress` - User clicks "Calculate Rating" via `run_stage3()`
- ✅ `Stage3Complete → Stage3InProgress` - Re-rating via `run_stage3()`
- ✅ `Stage3InProgress → Stage3Complete` - Rating calculation finished via `complete_stage3()`
- ⏳ `Stage3Complete → Stage3InProgress` - Automatic re-rating on field/criteria changes (TODO)

---

## Implementation Status

**Last Updated:** 2026-04-06

### ✅ Completed

#### Core Rating Logic (Phase 1)
- ✅ `RatingService` class with full calculation pipeline
- ✅ 5 scoring strategies:
  - ✅ Min-Max Normalization (higher is better)
  - ✅ Inverted Min-Max (lower is better)
  - ✅ Ordinal Mapping (categorical values)
  - ✅ Boolean Scoring (true/false)
  - ✅ Threshold-Based (range brackets)
- ✅ Dealbreaker evaluation (8 operators: >=, >, <=, <, ==, !=, in, not_in)
- ✅ Raw value extraction (property/context/calculated sources)
- ✅ Overall rating aggregation (weighted average)
- ✅ Rating persistence (Property fields + CriterionScore records)
- ✅ 23 unit tests (all passing)

#### Celery Task Integration (Phase 2)
- ✅ `calculate_property_rating(property_id)` - Individual property rating
- ✅ `bulk_calculate_ratings(property_ids)` - Bulk rating with state filtering
- ✅ `bulk_calculate_project_ratings(project_id)` - Project-level bulk rating
- ✅ WebSocket notifications (`_send_rating_complete`, `_send_rating_failed`)
- ✅ Error handling with retry logic (exponential backoff)
- ✅ State machine integration (STAGE3_IN_PROGRESS → STAGE3_COMPLETE)
- ✅ 10 task tests (all passing)

#### API Endpoints & Serializers (Phase 3)
- ✅ **Serializers:**
  - ✅ `CriterionSerializer` - Individual criterion with validation
  - ✅ `RatingCriteriaSerializer` - Read-only criteria view
  - ✅ `RatingCriteriaCreateSerializer` - Create/update with nested criteria
  - ✅ `CriterionScoreSerializer` - Score results
  - ✅ `PropertyRatingSerializer` - Complete rating view
  - ✅ `PropertyComparisonSerializer` - Compact comparison view
- ✅ **ViewSets:**
  - ✅ `RatingCriteriaViewSet` - Full CRUD operations
  - ✅ Copy endpoint: `POST /api/rating-criteria/{uuid}/copy/`
- ✅ **Property Actions:**
  - ✅ `POST /api/properties/{uuid}/run-stage3/` - Trigger rating
  - ✅ `GET /api/properties/{uuid}/rating/` - Get rating results
  - ✅ `GET /api/properties/{uuid}/criterion-scores/` - Get detailed scores
- ✅ **Project Actions:**
  - ✅ `POST /api/projects/{uuid}/run-stage3-bulk/` - Bulk rating
  - ✅ `GET /api/projects/{uuid}/property-comparison/` - Sorted comparison
- ✅ URL routing configured
- ✅ Query param filtering (min_rating, exclude_disqualified)

#### Data Models
- ✅ `RatingCriteria` model with owner, name, timestamps
- ✅ `Criterion` model with full configuration (source, strategy, weights, dealbreakers)
- ✅ `CriterionScore` model for storing individual scores
- ✅ Project-level rating criteria reference (moved from PropertyList)
- ✅ Property fields: `overall_rating`, `rating_breakdown`, `disqualified`, `disqualification_reason`

#### State Machine
- ✅ State transitions defined:
  - ✅ `run_stage3()`: STAGE2_COMPLETE/STAGE3_COMPLETE → STAGE3_IN_PROGRESS
  - ✅ `complete_stage3()`: STAGE3_IN_PROGRESS → STAGE3_COMPLETE
- ✅ State validation in API endpoints

### 🚧 In Progress / TODO

#### Automatic Re-Rating Hooks
- ⏳ Property field change detection
- ⏳ Context data update triggers
- ⏳ Rating criteria modification triggers
- ⏳ Signal handlers for automatic re-rating

#### Testing
- ⏳ API endpoint integration tests
- ⏳ Serializer validation tests
- ⏳ End-to-end workflow tests
- ⏳ Permission tests

#### Admin Interface
- ⏳ RatingCriteriaAdmin configuration
- ⏳ CriterionInline for nested editing
- ⏳ CriterionScoreAdmin for viewing results
- ⏳ Bulk operations support

#### UI Components (Frontend)
- ⏳ Rating Criteria configuration form
- ⏳ Property rating display (badges, breakdown modal)
- ⏳ Property comparison view
- ⏳ Dealbreaker indication
- ⏳ Re-rating triggers

#### Copy-on-Write Implementation
- ✅ Backend copy endpoint exists
- ⏳ Frontend workflow for editing shared criteria
- ⏳ Provenance tracking UI

#### Performance Optimization
- ⏳ Query optimization review
- ⏳ Caching strategies for ratings
- ⏳ Pagination for large comparison views
- ⏳ Bulk operations monitoring

### 📝 Notes

**Project-Level Changes:**
- Rating criteria now attached to `Project` (not `PropertyList`)
- All property lists in a project share the same rating criteria
- Comparison works across all lists in a project
- Automatic deduplication for properties in multiple lists

**Implementation Files:**
- Core Logic: `property/services/rating_service.py` (447 lines)
- Tasks: `property/tasks.py` (calculate_property_rating, bulk tasks)
- Serializers: `property/serializers.py` (6 new serializers, 174 lines)
- Views: `property/views.py` (RatingCriteriaViewSet + 4 actions)
- Tests: `property/tests/test_rating_service.py` (680 lines, 23 tests)
- Tests: `property/tests/test_stage3_tasks.py` (422 lines, 10 tests)

**Documentation:**
- Phase 1 Complete: `documentation/claude_responses/stage3_phase1_complete.md`
- Phase 2 Complete: `documentation/claude_responses/stage3_phase2_complete.md`
- Phase 3 Complete: `documentation/claude_responses/stage3_phase3_complete.md`

---

## For More Details

- **Rating calculation:** `documentation/plan/detail/stage3_rating_workflow_20260106.md`
- **Architecture decisions:** `documentation/plan/detail/architecture_decisions_20260106.md`
- **State machines:** `documentation/plan/detail/state_machine_diagrams_20260106.md`
- **Automatic reruns:** `documentation/plan/detail/automatic_rerun_workflows_20260106.md`
