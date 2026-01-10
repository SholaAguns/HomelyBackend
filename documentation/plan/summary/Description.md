# Homely - Property List Web Application

A property list web application designed to aid the house hunting process through intelligent property evaluation and comparison.

---

## Overview

Homely helps users create curated property lists and systematically evaluate properties based on contextual information and personalized criteria. The application operates through **three distinct stages**, each building upon the previous.

---

## Three-Stage Architecture

### Stage 1: Creation and Viewing
Users create property lists and add properties via three methods:
- **Manual form entry** - Standard property details form
- **Text extraction** - Parse property descriptions from copied text
- **URL extraction** - Extract from Rightmove/Zoopla property pages

**Key Features:**
- **Deduplication** - Prevents duplicate entries using normalized addresses and external IDs
- **Collaborative sharing** - Add viewers (read-only) or contributors (full edit except deletion)
- **Comments and tags** - Collaborate with other platform users
- **Saved locations** - Store frequently referenced addresses for POI distance calculations

### Stage 2: Context Retrieval
Asynchronously gathers contextual information about each property from external APIs.

**Available Services:**
- Crime statistics (UK Police API)
- Broadband speed (Ofcom)
- Mobile coverage (Ofcom)
- School ratings (Department for Education API)
- Places of Interest (Google Maps) - 13 types including schools, hospitals, parks, supermarkets, etc.

**Key Features:**
- **Manual triggering** - User clicks "Retrieve Context Reports" button (individual or bulk)
- **Progressive loading** - Frontend displays completed data as services finish (no waiting for all)
- **Service state tracking** - Complete, InProgress, or Failed with retry mechanism
- **Automatic reruns** - Changes to related fields (e.g., postcode) trigger dependent service reruns with user confirmation
- **Partial success** - Properties complete Stage 2 even if some services fail (failed services can be retried independently)

### Stage 3: Rating System
Evaluates properties based on weighted criteria and assigns scores.

**Criteria Types:**
- **System Criteria (7):** Price, bedrooms, bathrooms, council tax band, crime rating, EPC rating, square area
- **User Criteria (14):** Distance to POI, amount of POI nearby, garden, furnished status, child suitability, broadband speed, mobile coverage, school rating, parking, and more

**Key Features:**
- **Manual triggering** - User clicks "Calculate Rating" button (individual or bulk)
- **Dealbreaker gates** - Properties can be disqualified early if they fail critical thresholds
- **Intelligent scoring** - Min-max normalization, inverted scoring, ordinal mapping, boolean, and threshold-based strategies
- **Weighted calculations** - Criteria receive importance weights (Very Important: 1.5, Important: 1, Nice to Have: 0.5, Not Important: 0)
- **Score persistence** - Both individual criterion scores and overall ratings are stored
- **Automatic re-rating** - Changes to property data or rating criteria trigger automatic recalculation
- **Reference-with-copy-on-write** - Rating criteria can be reused across lists; editing creates an independent copy

---

## State Management

### Property States
Properties progress through stages with explicit state tracking:
- **New** - Initial state after creation
- **Stage2InProgress** - Context services running
- **Stage2Complete** - All context services complete/failed
- **Stage3InProgress** - Rating calculation running
- **Stage3Complete** - Rating calculated

### PropertyList States
- **Draft** - Initial state after creation
- **Active** - Has context options and/or properties

All state transitions are managed by `django-fsm` and logged for audit trail.

---

## Tech Stack

### Core Stack
- **Frontend:** Angular
- **Backend:** Django 5+ with Django REST Framework
- **Database:** PostgreSQL
- **State Management:** Django ORM + django-fsm
- **Real-time:** Django Channels (WebSockets)
- **Background Jobs:** Celery with Redis
- **Caching:** Redis (service-specific TTL)
- **Hosting:** Render

### Actor Model Implementation
Each Property List has a state machine tracking its children. Each Property has its own state machine managing its lifecycle through three stages.

**Example (django-fsm):**
```python
from django_fsm import FSMField, transition
from celery import group

class Property(models.Model):
    state = FSMField(default='New', protected=True)

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

    @transition(field=state, source='Stage2InProgress', target='Stage2Complete')
    def complete_stage2(self):
        """Called automatically when all services complete/fail"""
        pass

    @transition(field=state, source=['Stage2Complete', 'Stage3Complete'], target='Stage3InProgress')
    def run_stage3(self):
        """User triggers Stage 3 via button click"""
        calculate_rating_task.delay(self.id)

    @transition(field=state, source='Stage3InProgress', target='Stage3Complete')
    def complete_stage3(self):
        """Called by rating task when complete"""
        pass

    @transition(field=state, source=['Stage2Complete', 'Stage3InProgress', 'Stage3Complete'], target='Stage2InProgress')
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

## Real-time Communication

**WebSocket Events (Django Channels):**
- Service progress updates: "Crime report ready" (3/5 complete)
- Rating calculation updates: "Rating updated: 87.5"
- Collaborative edit notifications: "User X edited property Y"

**Example WebSocket Message:**
```javascript
{
  type: 'service_update',
  service: 'crime',
  status: 'COMPLETE',
  property_id: 123,
  property_state: 'Stage2Complete',
  progress: {
    total: 5,
    complete: 3,
    failed: 1,
    in_progress: 1
  }
}
```

---

## External API Integrations

| Service | Purpose | Cost | Provider |
|---------|---------|------|----------|
| Ideal Postcodes | Address autocomplete, UPRN lookup | £9/200 lookups | UK |
| UK Police API | Crime statistics | FREE | Official government |
| Google Maps | POI search, distances, directions | $200 free/month | Google |
| Ofcom | Broadband/mobile coverage | Likely FREE | UK regulator |
| Department for Education | School ratings (Ofsted) | FREE | UK government |

---

## Key Architectural Patterns

### 1. Service Factory Pattern
Context services created based on configuration:
```python
class IContextService(ABC):
    @abstractmethod
    def fetch_data(self, property): pass

    @abstractmethod
    def get_cache_key(self, property): pass

    @abstractmethod
    def get_cache_ttl(self): pass

# Concrete implementations
class CrimeService(IContextService): ...
class BroadbandService(IContextService): ...
class SchoolRatingService(IContextService): ...
```

### 2. Smart Caching Strategy
Each service defines its own caching logic:
- Crime: Cached by postcode sector (30 days)
- Broadband: Cached by UPRN (7 days)
- Schools: Cached by postcode (90 days)
- POI: Cached by rounded coordinates (30 days)

### 3. Progressive Asynchronous Processing
- Stage 2 services run in parallel (separate Celery tasks per service)
- Frontend displays data incrementally via WebSocket updates
- Automatic state transitions when all async operations complete

### 4. Automatic Dependency Triggering
- Field changes automatically trigger dependent service reruns (with confirmation)
- Property field changes mapped to affected services (e.g., postcode → crime, schools, POI, broadband, mobile)
- Rating automatically recalculates when context data or criteria change

### 5. Error Handling with Retry
- Services classified by error type (transient vs. permanent)
- Automatic retries with exponential backoff (max 3 attempts)
- Manual retry option for failed services
- Partial success policy (properties complete even with failures)
- Detailed error logging for debugging

---

## Data Model Relationships

```
User (1) ─── (M) PropertyList
PropertyList (1) ─── (M) Property
PropertyList (1) ─── (1) ContextOptions
PropertyList (1) ─── (1) RatingCriteria
Property (1) ─── (M) ContextData (one per service)
Property (1) ─── (M) CriterionScore (one per criterion)
User (M) ─── (M) PropertyList (as viewer/contributor)
User (1) ─── (M) SavedLocation
```

---

## Development Phases

**Phase 1:** Foundation (Django models, state machines, WebSockets, Celery)
**Phase 2:** Stage 1 - Property Creation (CRUD, deduplication, collaboration)
**Phase 3:** Stage 2 - Context Retrieval (services, caching, error handling)
**Phase 4:** Stage 3 - Rating System (criteria, scoring, dealbreakers)
**Phase 5:** Automatic Reruns (field detection, confirmations)
**Phase 6:** Advanced Features (collaboration, export, search)

---

## Documentation Structure

**For high-level overview:** This file (Description.md)
**For stage workflows:** Stage 1/2/3 .md files
**For detailed architecture:** `documentation/plan/detail/architecture_decisions_20260106.md`
**For state management:** `documentation/plan/detail/state_machine_diagrams_20260106.md`
**For rating details:** `documentation/plan/detail/stage3_rating_workflow_20260106.md`
**For field changes:** `documentation/plan/detail/automatic_rerun_workflows_20260106.md`
**For error handling:** `documentation/plan/detail/service_error_retry_flow_20260106.md`
**For implementation roadmap:** `documentation/plan/implementation_roadmap.md`
