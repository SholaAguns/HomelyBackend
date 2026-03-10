## Implementation Roadmap

Based on all documentation, here's a suggested implementation sequence:

* Important change to initial plan made, property and property list no longer a fk relationship, now a ManyToManyField as one property can be in multiple lists

### Phase 1: Accounts & Authentication (Weeks 1-2)
**Priority:** Critical foundation

**Tasks:**
1. Set up Django accounts app - done
2. Configure Django AllAuth (email/password authentication) - done
3. Integrate social login providers (Google) - done
4. Implement JWT token authentication (djangorestframework-simplejwt) - done
5. Create user registration and login endpoints - done
6. Set up password reset and email verification flows - done
7. Configure CORS and security settings - done
8. Create user profile model and endpoints - done
9. Write authentication tests - done

**Deliverable:** Fully functional authentication system with social login and JWT tokens.

---

### Phase 2: Foundation (Weeks 3-5)
**Priority:** Critical infrastructure

**Tasks:**
1. Set up Django models: - done
   - Property, PropertyList, ContextOptions, RatingCriteria, ContextData, CriterionScore
   - Add state fields to Property and PropertyList
   - Add unique_together constraints for PropertyList (owner+title) and RatingCriteria (owner+name)
2. Integrate django-fsm for state machines - done
3. Set up Django Channels for WebSocket support - done
4. Configure Redis for caching and Celery - done
5. Set up Celery workers and task infrastructure - done
6. Create basic API endpoints (Property CRUD, PropertyList CRUD)

**Deliverable:** Working backend with state management and async infrastructure.

---

### Phase 3: Stage 1 - Property Creation (Weeks 6-8)
**Priority:** Core functionality

**Tasks:**
1. Implement Property List creation UI
2. Implement Property creation UI (three methods: manual form, URL extraction, text extraction)
3. Build deduplication logic
4. Implement Context Options configuration UI
5. Implement Rating Criteria configuration UI (with reference-with-copy-on-write)
6. Basic property detail page

**Deliverable:** Users can create lists and add properties.

---

### Phase 4: Stage 2 - Context Retrieval (Weeks 9-12)
**Priority:** High value feature

**Tasks:**
1. Implement IContextService interface and factory - done
2. Build concrete service implementations:
   - CrimeService (UK Police API) - done
   - SchoolRatingService (GIAS CSV + Postcodes.io) - done (52,275 schools, 96.7% coords, Ofsted on-demand for Stage 3)
   - BroadbandService (Ofcom)
   - MobileCoverageService (Ofcom)
   - PlacesOfInterestService (Google Maps API)
3. Implement service orchestration (Celery tasks) - done
4. Implement completion aggregation (post_save signals + WebSocket) - done
5. Build progress indicators on frontend
6. Implement smart caching (Redis) - done
7. Add manual trigger buttons (individual + bulk) - done (backend API endpoints)
8. Implement error handling and retry mechanism - done

**Deliverable:** Users can retrieve context data for properties.

---

### Phase 5: Stage 3 - Rating System (Weeks 13-15)
**Priority:** Differentiating feature

**Tasks:**
1. Implement RatingCriteria configuration UI (all 21 criteria, weights, dealbreakers)
2. Build criterion scoring strategies:
   - MinMaxNormalization
   - InvertedNormalization
   - OrdinalMapping
   - BooleanScoring
   - ThresholdBased
3. Implement dealbreaker evaluation
4. Build rating aggregation logic
5. Create rating calculation Celery task
6. Build rating display UI (badges, breakdown modal)
7. Add manual trigger (individual + bulk)

**Deliverable:** Users can rate and compare properties.

---

### Phase 6: Automatic Rerun Logic (Weeks 16-17)
**Priority:** Polish and UX

**Tasks:**
1. Implement field dependency matrix
2. Build field change detection
3. Add confirmation dialogs
4. Implement cache invalidation on field change
5. Build automatic service rerun triggering
6. Build automatic rating recalculation
7. Handle context options modification (add/remove services)

**Deliverable:** System automatically maintains data consistency.

---

### Phase 7: Collaboration & Advanced Features (Weeks 18-20)
**Priority:** Nice-to-have

**Tasks:**
1. User permissions (viewers, contributors)
2. Real-time collaboration (WebSocket for multi-user edits)
3. Comments and tags
4. Saved locations
5. Export functionality
6. Advanced search and filtering

**Deliverable:** Full collaborative experience.

---

## Reference Guide: When to Use Each Document

| Task | Document to Reference |
|------|----------------------|
| Deciding on architectural approach | `architecture_decisions_20260106.md` |
| Implementing state transitions | `state_machine_diagrams_20260106.md` |
| Building rating calculation | `stage3_rating_workflow_20260106.md` |
| Handling field changes | `automatic_rerun_workflows_20260106.md` |
| Implementing error handling | `service_error_retry_flow_20260106.md` |
| Understanding original diagram issues | `workflow_diagrams_evaluation_20260106.md` |
| Making implementation decisions | `clarification_questions_20260106.md` (your answers) |

---

## Key Architectural Highlights

These decisions are critical to the project's success:

### 1. **State Machines are Mandatory**
Use django-fsm for both Property and PropertyList. This ensures:
- Invalid state transitions are prevented
- Audit trail is automatic
- Business logic is enforced
- Testing is simplified

### 2. **WebSocket Real-time Updates are Essential**
Don't rely on polling. Django Channels + WebSocket provides:
- Instant progress updates (e.g., "3/5 services complete")
- Better UX (feels fast and responsive)
- Lower server load
- Collaborative editing support

### 3. **Partial Success is User-Friendly**
Properties should complete Stage 2 even if some services fail:
- Users aren't blocked by one API failure
- Failed services can be retried independently
- Rating can proceed with available data
- Critical for time-sensitive house hunting

### 4. **Caching is Critical for Cost Control**
External API calls are expensive (financially and performance-wise):
- Smart service-specific caching (Crime: 30 days, Broadband: 7 days)
- Cache invalidation on field changes
- Reduces redundant API calls
- Improves response times

### 5. **Confirmation Dialogs Prevent Accidents**
Field changes that trigger expensive operations need confirmation:
- Postcode change → 5 service reruns
- Show user what will happen
- Prevent accidental costly operations
- "Don't ask again" option for power users

---

## Testing Strategy

### Unit Tests
- State machine transitions (valid and invalid)
- Criterion scoring strategies
- Field dependency detection
- Error classification
- Cache key generation

### Integration Tests
- Full property lifecycle (creation → Stage 2 → Stage 3)
- Service orchestration (parallel execution)
- WebSocket message delivery
- Bulk operations
- Automatic rerun triggering

### E2E Tests
- User completes full workflow (create list → add property → retrieve reports → rate)
- Collaborative editing
- Error recovery (service fails → manual retry)
- Field edit → automatic rerun

---

## Performance Benchmarks (Target)

| Operation | Target Performance |
|-----------|-------------------|
| Property creation | < 500ms |
| Stage 2 triggering (5 services) | < 1s (queue Celery tasks) |
| Individual service execution | < 10s (external API dependent) |
| Stage 3 rating calculation | < 2s |
| WebSocket message delivery | < 100ms |
| Page load (property list with 20 properties) | < 2s |
| Bulk rating (100 properties) | < 30s (parallel Celery) |

---

## Monitoring and Observability

### Key Metrics to Track

**Service Health:**
- Service success rate by service name
- Average service execution time
- Error rate by error type
- Cache hit rate

**User Experience:**
- Time from property creation to Stage2Complete
- Rating calculation time
- WebSocket message latency
- Failed service retry success rate

**System Health:**
- Celery queue length
- Redis memory usage
- Database query performance
- WebSocket connection count

### Logging

Use structured logging (structlog) for:
- State transitions
- Service execution (start, complete, fail)
- API calls to external services
- User actions (create, edit, delete)
- Errors and exceptions

---

## Security Considerations

### API Keys
- Store external API keys in environment variables (never in code)
- Use different keys for development/staging/production
- Rotate keys periodically
- Monitor usage to detect abuse

### User Data
- Encrypt sensitive fields (not applicable for public property data, but consider future features)
- Implement proper authentication (Django AllAuth + JWT)
- Authorization checks on all API endpoints (user can only edit their own lists)

### Rate Limiting
- Implement API rate limiting to prevent abuse
- Per-user limits for expensive operations (Stage 2 triggering)
- Global limits for external API calls (respect third-party rate limits)

---

## Cost Estimation

### External API Costs (Monthly, assuming 100 active users)

| Service | Cost Model | Estimated Usage | Monthly Cost |
|---------|------------|-----------------|--------------|
| Google Maps (POI) | $200 free/month, then $0.017/request | 2000 properties × 13 POI types = 26,000 requests | ~$442 |
| Ideal Postcodes | £9/200 lookups | 200 properties = 200 lookups | £9 |
| UK Police API | FREE | Unlimited | £0 |
| Ofcom (Broadband/Mobile) | FREE (likely) | Unlimited | £0 |
| Department for Education | FREE | Unlimited | £0 |

**Total: ~£450/month** (dominated by Google Maps)

### Optimization Strategies:
1. **Cache aggressively** (POI data doesn't change often)
2. **Batch POI requests** (one request for multiple POI types)
3. **Consider alternative POI providers** (OpenStreetMap, cheaper options)
4. **User quotas** (limit properties per list for free tier)

---

## Final Checklist Before Implementation

- [ ] All clarification questions answered ✓
- [ ] Architecture decisions documented ✓
- [ ] State machines designed ✓
- [ ] Workflows documented ✓
- [ ] Original diagrams updated (TO DO)
- [ ] ERD created (OPTIONAL)
- [ ] Sequence diagrams created (OPTIONAL)
- [ ] Development environment set up
- [ ] External API keys obtained
- [ ] Django project initialized
- [ ] CI/CD pipeline configured
- [ ] Monitoring and logging infrastructure ready

---

## Conclusion

Your Homely project has a **solid architectural foundation** and **well-defined workflows**. The three-stage approach (Creation → Context → Rating) provides clear separation of concerns and a logical user experience.

**Strengths:**
- Comprehensive feature set addressing real house-hunting pain points
- Smart use of external APIs for automated data gathering
- Flexible configuration (context options, rating criteria)
- Progressive loading for good UX
- Collaborative features add significant value

**Recommendations:**
- Start with Phase 1 authentication (Django AllAuth + JWT)
- Build Phase 2 foundation (state machines, WebSockets, Celery)
- Implement Stages 1-3 sequentially (don't build everything at once)
- Get user feedback early (after Stage 1 and Stage 2)
- Monitor external API costs closely
- Invest in error handling and retry logic (external APIs will fail)

