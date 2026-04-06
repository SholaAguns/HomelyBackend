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
