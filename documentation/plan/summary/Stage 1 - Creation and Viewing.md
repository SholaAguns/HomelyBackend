# Stage 1: Creation and Viewing

Stage 1 focuses on creating property lists and adding properties through multiple methods, with support for collaboration and organization.

---

## Property List Workflow

### 1. Create Property List
**User Action:** Fill in creation form
- **Fields:** Title only
- **State:** `Draft` → `Active` (when context options OR first property added)

### 2. Configure Context Options (Optional, Can Be Done Anytime)
**User Action:** Click "Add Context Options" button
- Select which services to enable (Crime, Schools, Broadband, Mobile, POI types)
- Can be modified later (triggers automatic reruns for existing properties)
- If no context options configured, "Retrieve Context Reports" button redirects to this form

**Architectural Note:** Context options are **modifiable anytime**. When new services are added, they automatically run for all existing properties beyond `New` state.

### 3. Configure Rating Criteria (Optional, Can Be Done Anytime)
**User Action:** Click "Add Rating Criteria" button

**Two Options:**
- **Create New:** Build custom rating criteria from scratch
- **Select Existing:** Use previously created criteria (creates FK reference)

**Copy-on-Write Behavior:**
- Rating criteria are referenced (not duplicated initially)
- When editing a shared criteria → system creates a copy automatically
- Tracks original source with `rating_criteria_source` field
- Prevents unintended changes to other lists using the same criteria

**Architectural Note:** Rating criteria are **optional**. Properties can exist and complete Stage 2 without rating criteria configured.

### 4. Add Properties to List
See Property Workflow below.

### 5. Collaboration Features
**Viewers:** Read-only access (no edits)
**Contributors:** Full edit access except list deletion

**Actions:**
- Comments on list or properties
- Tag properties and other subscribers
- Real-time updates via WebSocket when others make changes

### 6. Saved Locations (User Profile Level)
**Purpose:** Store frequently referenced addresses for POI distance calculations

**Workflow:**
1. Navigate to Profile Settings → Saved Locations
2. Create new location with:
   - Name
   - Address (manual entry or postcode lookup via Ideal Postcodes API)
3. Use in rating criteria for "Distance from [Saved Location]" calculations

---

## Property Workflow

### 1. Add Property Button Click
**Entry Point:** Property List detail page → "Add Property" button

### 2. Select Creation Method
**Three Options:**

#### Option A: Manual Form
- User fills in standard property fields
- Title, address, postcode, price, bedrooms, bathrooms, etc.
- Direct form submission

#### Option B: Text Extraction
- User pastes property description text
- Backend parses and extracts fields using NLP/regex
- User reviews and edits extracted data before saving

#### Option C: URL Extraction
- User provides Rightmove/Zoopla property URL
- Backend scrapes page and extracts property details
- User reviews and edits before saving

### 3. Deduplication Check
**Process:**
- Backend normalizes address (lowercase, remove punctuation, standardize spacing)
- Check for existing properties with:
  - Same normalized address OR
  - Same external ID (Rightmove/Zoopla listing ID)
- **If match found:** Show warning with link to existing property
- **If no match:** Proceed with creation

### 4. Property Created
**State:** `New`
**API Response:** Returns property ID and detail view URL

### 5. Property Detail Page Displayed
**UI Shows:**
- Property details
- State badge: "New"
- **"Retrieve Context Reports" button** (manual trigger)
  - If context options not configured → Button redirects to context options form
  - If context options configured → Button is enabled

**Architectural Note:** Stage 2 is **NOT automatic**. User must click button (Decision #2: Manual triggering with bulk option).

### 6. (Optional) User Edits Property
**Field Change Detection:**
- System detects which fields changed
- Checks field dependency matrix:
  ```
  postcode → [crime, schools, poi, broadband, mobile]
  price → [rating recalculation only]
  bedrooms → [rating recalculation only]
  ...
  ```

**Confirmation Dialog:**
- **If service dependencies exist:** Show confirmation dialog listing affected services and API cost warning
- User can enable "Don't ask again" preference
- **If only rating dependencies:** No confirmation, automatic recalculation

**Action:** Services/rating rerun after user confirms

---

## State Management

### PropertyList States
- **Draft** - Initial state, no context options or properties yet
- **Active** - Has context options and/or properties

**Transitions:**
```
Draft → Active (when context options added OR first property added)
```

### Property States (Stage 1)
- **New** - Initial state after creation

**Next Transitions (Stage 2):**
```
New → Stage2InProgress (when user clicks "Retrieve Context Reports")
```

**See:** `documentation/plan/detail/state_machine_diagrams_20260106.md` for complete state machine definitions.

---

## Key Architectural Decisions

### Decision #3: Property Addition Rules - Flexible
- Properties can be added **without context options configured**
- No blocking or disabled buttons
- "Retrieve Context Reports" button redirects to configuration if needed

### Decision #1: Rating Criteria - Reference-with-Copy-on-Write
- Rating criteria shared via FK reference
- Editing creates automatic fork (copy-on-write)
- Tracks original source for provenance
- **Implementation:** `PropertyList.rating_criteria_source` field

### Decision #15: Field Change Detection - Approved Matrix
```python
FIELD_SERVICE_DEPENDENCIES = {
    'postcode': ['crime', 'schools', 'poi', 'broadband', 'mobile'],
    'latitude': ['poi'],
    'longitude': ['poi'],
    # All other fields: []
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
}
```

### Decision #16: Field Change Confirmation - Required
- Confirmation dialog shown before rerunning services
- Lists affected services and warns about API costs
- "Don't ask again" option available
- **Rationale:** Prevents accidental expensive operations

---

## UI Components

### Property List Detail Page
```
┌─────────────────────────────────────────────────┐
│ My House Hunt                                   │
│ Created: Jan 5, 2026 • 5 properties             │
├─────────────────────────────────────────────────┤
│                                                 │
│ Context Options: Configured ✓                   │
│ [Edit Context Options]                          │
│                                                 │
│ Rating Criteria: Using "Family-friendly"        │
│ [Edit Rating Criteria]                          │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ [Add Property]  [Retrieve Reports for All (2)]  │
│                 [Rate All Properties (3)]       │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Property Cards:                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 123 Main Street, London                 │     │
│ │ £350,000 • 3 bed • 2 bath               │     │
│ │ Status: New                             │     │
│ │ [Retrieve Reports] [Edit] [Delete]      │     │
│ └─────────────────────────────────────────┘     │
│                                                 │
│ ┌─────────────────────────────────────────┐     │
│ │ 456 Oak Avenue, Manchester              │     │
│ │ £400,000 • 4 bed • 3 bath               │     │
│ │ Status: Stage2Complete                  │     │
│ │ Rating: 87.5 ★★★★☆                      │     │
│ │ [View Details] [Edit] [Compare]         │     │
│ └─────────────────────────────────────────┘     │
└─────────────────────────────────────────────────┘
```

### Property Detail Page
```
┌─────────────────────────────────────────────────┐
│ 123 Main Street, London SW1A 1AA                │
│ £350,000 • 3 bed • 2 bath • 1200 sq ft          │
│                                                 │
│ Status: New                                     │
│                                                 │
│ [Retrieve Context Reports]  [Edit Details]      │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Property Details:                               │
│ • Price: £350,000                               │
│ • Bedrooms: 3                                   │
│ • Bathrooms: 2                                  │
│ • Garden: Yes                                   │
│ • Parking: Off-street                           │
│ • EPC: C                                        │
│ • Council Tax: B                                │
│                                                 │
│ ───────────────────────────────────────────     │
│                                                 │
│ Comments (2):                                   │
│ • John: "Nice garden!"                          │
│ • Sarah: "Close to schools"                     │
│                                                 │
│ [Add Comment]                                   │
└─────────────────────────────────────────────────┘
```

### Field Edit Confirmation Dialog
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

## API Endpoints

### Property Lists
```
GET    /api/property-lists/              # List all lists for user
POST   /api/property-lists/              # Create new list
GET    /api/property-lists/{id}/         # Get list details
PUT    /api/property-lists/{id}/         # Update list
DELETE /api/property-lists/{id}/         # Delete list
```

### Properties
```
GET    /api/properties/                  # List all properties for user
POST   /api/properties/                  # Create property
GET    /api/properties/{id}/             # Get property details
PUT    /api/properties/{id}/             # Update property (triggers field change logic)
DELETE /api/properties/{id}/             # Delete property
```

### Context Options
```
GET    /api/context-options/{list_id}/   # Get context options for list
PUT    /api/context-options/{list_id}/   # Update context options
```

### Rating Criteria
```
GET    /api/rating-criteria/             # List all criteria (user's + templates)
POST   /api/rating-criteria/             # Create new criteria
GET    /api/rating-criteria/{id}/        # Get criteria details
PUT    /api/rating-criteria/{id}/        # Update criteria (triggers copy-on-write if shared)
DELETE /api/rating-criteria/{id}/        # Delete criteria
```

---

## Data Models (Simplified)

```python
class PropertyList(models.Model):
    owner = models.ForeignKey(User)
    title = models.CharField(max_length=255)
    state = FSMField(default='Draft')

    context_options = models.ForeignKey(ContextOptions, null=True, blank=True)
    rating_criteria = models.ForeignKey(RatingCriteria, null=True, blank=True)
    rating_criteria_source = models.ForeignKey(RatingCriteria, null=True, related_name='derived_lists')

    viewers = models.ManyToManyField(User, related_name='viewable_lists')
    contributors = models.ManyToManyField(User, related_name='editable_lists')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class Property(models.Model):
    property_list = models.ForeignKey(PropertyList)
    state = FSMField(default='New')

    # Property details
    title = models.CharField(max_length=255)
    address_line_1 = models.CharField(max_length=255)
    postcode = models.CharField(max_length=10)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    bedrooms = models.IntegerField()
    bathrooms = models.IntegerField()
    # ... more fields

    # Normalized for deduplication
    normalized_address = models.CharField(max_length=500)
    external_id = models.CharField(max_length=100, null=True, blank=True)  # Rightmove/Zoopla ID

    # Stage 3 results
    overall_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rating_breakdown = models.JSONField(null=True, blank=True)
    disqualified = models.BooleanField(default=False)
    disqualification_reason = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class SavedLocation(models.Model):
    user = models.ForeignKey(User)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
```

---

## For More Details

- **Architecture decisions:** `documentation/plan/detail/architecture_decisions_20260106.md`
- **State machines:** `documentation/plan/detail/state_machine_diagrams_20260106.md`
- **Automatic reruns:** `documentation/plan/detail/automatic_rerun_workflows_20260106.md`
- **Next stage:** Stage 2 - Context retrieval.md
