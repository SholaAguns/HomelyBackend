# Project Model Refactor Plan

**Status:** Planning
**Date:** 2026-03-31

## Overview
Further changes required to models and logic. System not in production yet - all existing data is test data that can be deleted.

## Model Changes Required
- Move `PropertyList.rating_criteria` field to `Project`
- Attach `ContextOptions` to `Project` instead of `PropertyList` (change from OneToOne to ForeignKey)

---

# New User Flow
-  User creates a Project
- Creation form:
	- Page 1: Fill in name and description
	- Page 2: Attach context options (optional and skippable)
	- Page 3)  Add viewers/contributors or copy shareable link (optional) -> Submit
- Redirected to Project detail page;
	- Panel with top level stats:
		- Count of lists, areas included,
		- Link to dashboard page,
		- Edit context options,
		- Add/edit rating criteria button,
		- More settings dropdown (
			- link to Tasklists,
			- link to Applications,
			- run stage 2 on all button (if applicable)
			- run stage 3 on all button(if applicable)
	- Paginated preview cards of property lists and create new button
- User clicks create new property list
- PropertyList creation:
	- Frontend:
		- Use Search criteria form
		- Submit.
	- Backend:
		- Set title as the area field of entered for search criteria (If same name already exists in this project append number).  WE don't have to keep SearchCriteria.area and the list name coupled after this, both can be edited/updated independently
		- Save project list and search criteria
		- Automatically use RightmoveService.scrape_properties_by_search to populate properties in list
	- Frontend:
		- After submit button clicked redirect to PropertyList detail page and show loading spinner for properties population
		- Poll backend for properties data to show preview cards (similar to how it works now)
- User runs stage 2:
	- Similar to how it is currently implemented except context options is saved and retrieved at Project level
	- When creating a property if the same property exists in another list in the SAME project, no need to recreate, just update the details.
	- But if  the same property exists in another list in ANOTHER project then create a duplicate,
	- This way we will always have one source of truth for context options at the project level even if properties happen to be in multiple lists within it.
	- Stage 2 can be triggered at the Property, List or Project level
- User runs stage 3:
	- Similar to initial plan, once stage 2 has ran, stage 3 button can appear
	- Can be ran at Property, List or Project level
	- When button is clicked if there is no rating criteria attached to the project then redirect to rating criteria selection/creation page
	- Submit
	- Rating kicked off, not yet implemented See Stage 3 - Rating System.md

---

# Backend Implementation Plan

See complete backend plan in separate document.

---

# Frontend Implementation Plan

See complete frontend plan in separate document.

---

# Clarifying Questions & Analysis

## 🔴 CRITICAL - Must Answer Before Implementation

### 1. ContextOptions Migration Conflicts ⚠️
**Issue:** Different PropertyLists in same Project may have DIFFERENT ContextOptions

**Example:**
```
Project "House Hunting 2026"
├─ List "London": Crime=ON, Schools=ON, POI=OFF
└─ List "Manchester": Crime=ON, Schools=OFF, POI=ON
```

**Migration Options:**
- **A) Use first list** (simple but arbitrary)
- **B) Union of all enabled services** (safer, enables more)
- **C) Most common config** (complex)
- **D) Require manual reconciliation** (safest)

**❓ DECISION NEEDED:** Which option? ContextOptions should now be a project level field not propertylist level, if this concern is about existing data, we can delete all existing data before proceeding

---

### 2. RatingCriteria Migration Strategy ⚠️
**Issue:** PropertyLists in same Project may use different rating_criteria

**Example:**
```
Project "House Hunting 2026"
├─ List "London": uses "City Living Criteria"
└─ List "Manchester": uses "Suburban Family Criteria"
```

**Migration Options:**
- **A) Most frequently used** (current plan)
- **B) First list's criteria** (arbitrary)
- **C) Leave empty, require user selection** (safest)

**Edge Case:** What if there's a tie (2 lists with different criteria)?

**❓ DECISION NEEDED:** Strategy + tie-breaking rule? Same answer as above RatingCriteria should now be a project level field not propertylist level, if this concern is about existing data, we can delete all existing data before proceeding

---

### 3. Property Deduplication Key 🔑
**Issue:** What uniquely identifies a property?

**Current:** `postcode + address_line_1`

**Problems:**
- Address formatting varies ("123 Main St" vs "123 Main Street")
- Rightmove might relist same property with different ID
- Price changes shouldn't create duplicates

**Options:**
- **A) Rightmove `external_id`** (reliable if available)
- **B) `postcode + normalized_address`** (current)
- **C) UPRN** (UK Property Reference Number - authoritative)
- **D) Hybrid:** Try external_id, fallback to postcode+address

**❓ DECISION NEEDED:** Which key? Normalize addresses? UPRN if available, then external id if available, then lastly fallback to `postcode + normalized_address

---

### 4. Auto-Scraping Error Handling ❌
**Issue:** What happens when scraping fails?

**Failure Scenarios:**
- Invalid area (typo, doesn't exist)
- Rightmove API timeout
- Zero properties found
- Rate limit hit

**Options:**
- **A) Create empty list** - show error, allow retry (current plan)
- **B) Validate area first** - reject before creating list
- **C) Rollback on failure** - delete list if scraping fails

**❓ DECISION NEEDED:** Error strategy? Validate areas upfront? - Validate area first

---

### 5. Bulk Operations - Cost Protection 💰
**Issue:** Running Stage 2/3 on entire project = thousands of API calls

**Example:**
```
10 lists × 100 properties = 1,000 properties
Stage 2: 1,000 × 7 services = 7,000 API calls
Estimated cost: £200+ in external APIs
```

**Safeguards Needed:**
- **A) Confirmation dialog** showing count + estimated API calls
- **B) Batch size limits** (max 100 at once)
- **C) "New Properties Only" option** (skip existing context data)
- **D) Cost estimate** in £ (if API pricing known)

**❓ DECISION NEEDED:** Which safeguards? All of them? - Okay let's limit running stage 2/3 to property/list level only for now while we revisit viability of running at project level

---

## 🟡 MEDIUM PRIORITY

### 6. Title Auto-Generation Rules 📝
**Question:** Should editing SearchCriteria.area update PropertyList.title?

**Scenario:**
1. Create list: area="Manchester" → title="Manchester" ✅
2. User edits title to "Manchester City Center" ✏️
3. User edits search: area="Manchester Suburbs"
4. Should title become "Manchester Suburbs"? ❓

**Options:**
- **A) Never update** after creation (current assumption)
- **B) Track if user edited**, only update if auto-generated
- **C) Ask user** on area change

**❓ DECISION NEEDED:** Confirm decoupling behavior? - Option A is correct, user can manually update title if they want after creation

---

### 7. SearchCriteria Sharing vs Duplication 🔄
**Question:** Should multiple lists share same SearchCriteria instance?

**Current:** Each list duplicates SearchCriteria

**Alternative:** Share with copy-on-write

**Pros:** Easier re-use, saves DB space
**Cons:** Editing affects multiple lists, adds complexity

**❓ DECISION NEEDED:** Keep duplicated or implement sharing? - Keep duplicated

---

### 8. Missing ContextOptions Default 🔧
**Question:** User runs Stage 2 but Project has no ContextOptions

**Options:**
- **A) Show error:** "Configure first" (current assumption)
- **B) Auto-create default** (all disabled = useless)
- **C) Inline setup modal** (best UX)

**❓ DECISION NEEDED:** Which option? - Inline setup

---

### 9. Manual Property Creation Features ✋
**Question:** Original plan had 3 creation methods. Still implementing?

**Original Plan:**
- Manual form entry
- Paste Rightmove URL to extract
- Paste text description to extract

**Current Refactor:** Only auto-scraping mentioned

**❓ DECISION NEEDED:**
- Still implementing manual methods?
- Lower priority?
- Or dropped entirely?
- Answer: low priority user can still manually use those options if they wish, code already exists

---

## 🟢 LOW PRIORITY / CLARIFICATIONS

### 10. Multi-List Property Behavior ✅
**Clarification:** Property in multiple lists within same Project shares Stage 2 data

**Example:**
```
Property X in List A and List B (same project)
Run Stage 2 on List A → Property X gets context data
List B automatically benefits (same property)
```

**Assumption:** This is intended (saves API calls) ✅ Correct

---

### 11. Title Uniqueness Scope Change 🔄
**Question:** Change uniqueness from (owner, title) to (project, title)?

**Current:** User can't have two "Manchester" lists across ALL projects
**Proposed:** User can have "Manchester" in Project A and B, but not duplicate in same project

**❓ CONFIRMATION NEEDED:** Is this change intended? - Correct, project  + title uniqueness required now

---

### 12. Future: ContextOptions Override/Inheritance 🔮
**Future Consideration:** If we add list-level overrides later, how do they merge?

**Example:**
```
Project: Crime=ON, Schools=ON, POI=OFF
List override: POI=ON
Result: Crime=ON, Schools=ON, POI=ON (for this list only)
```

**Not urgent - just noting for architecture planning** - ContextOptions only at Project level not at list level

---

# Comparison to Original Plan

## What's Different from Initial Design?

### ✅ Aligned with Original
- Stage 2/3 workflow (context → rating)
- WebSocket real-time updates
- Celery async task execution
- Caching strategy
- State machines (Property only now)

### 🔄 Significant Changes
| Original | Refactored |
|----------|------------|
| PropertyList has ContextOptions | **Project** has ContextOptions |
| PropertyList has RatingCriteria | **Project** has RatingCriteria |
| Manual property creation primary | **Auto-scraping** primary |
| PropertyList state machine | Removed (simplified) |
| 3 creation methods | Currently only auto-scrape |

### ❓ Unclear / Needs Confirmation
1. Manual/URL/text property creation - still implementing?
2. Copy-on-write for RatingCriteria - still applicable?
3. Per-list ContextOptions overrides - future feature?

---

# Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Data loss in ContextOptions migration | High | High | Need conflict resolution strategy |
| Data loss in RatingCriteria migration | High | High | Need conflict resolution strategy |
| Duplicate property detection fails | Medium | Medium | Use Rightmove external_id + address |
| Accidental bulk API calls (cost) | High | Critical | Add confirmation + cost estimates |
| Auto-scraping failures confuse users | Medium | Medium | Clear error messages + retry UX |
| Title conflicts after auto-generation | Low | Low | Numbering scheme handles it |

---

# Implementation Readiness Checklist

## Before Starting Backend:
- [ ] Answer Question #1 (ContextOptions migration)
- [ ] Answer Question #2 (RatingCriteria migration)
- [ ] Answer Question #3 (Deduplication key)
- [ ] Answer Question #4 (Auto-scraping errors)
- [ ] Answer Question #5 (Bulk operation safeguards)
- [ ] Confirm manual property creation scope (#9)

## Before Starting Frontend:
- [ ] Confirm title generation rules (#6)
- [ ] Confirm missing ContextOptions behavior (#8)
- [ ] Design confirmation modals for bulk operations
- [ ] Design error states for auto-scraping

## Before Database Migrations:
- [ ] Backup production DB (wait, it's test data - OK to delete)
- [ ] Write migration conflict resolution scripts
- [ ] Test migrations on copy of test data
- [ ] Document what data transformations will occur

---

# Next Steps

1. **User reviews this document**
2. **User answers all 🔴 Critical questions**
3. **User confirms/denies 🟡 Medium priority assumptions**
4. **Begin implementation:**
   - Phase 1: Models + Migrations
   - Phase 2: Backend API
   - Phase 3: Frontend
