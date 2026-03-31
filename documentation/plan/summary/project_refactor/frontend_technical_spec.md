# Frontend Technical Specification - Project Refactor

**Date:** 2026-03-30
**Status:** Planning
**Related:** backend_technical_spec.md

---

## Table of Contents
1. [Overview](#overview)
2. [Component Architecture](#component-architecture)
3. [Page Structure](#page-structure)
4. [State Management](#state-management)
5. [API Integration](#api-integration)
6. [Routing](#routing)
7. [Implementation Details](#implementation-details)
8. [Testing Strategy](#testing-strategy)
9. [Implementation Sequence](#implementation-sequence)

---

## Overview

### Key Changes from Current Frontend
- **Project-first workflow**: Users create Project before PropertyLists
- **3-step Project creation wizard** with context options and collaboration setup
- **Auto-scraping on PropertyList creation** with loading states and polling
- **Inline ContextOptions setup** when missing during Stage 2 trigger
- **Project-level stats dashboard** with aggregated data
- **Area validation feedback** with suggestions on invalid input
- **Project-scoped navigation** between lists and tasks

### Technology Stack
- React (assumed based on existing codebase)
- React Router for navigation
- Axios/Fetch for API calls
- WebSocket for real-time updates (existing)
- Form validation library (to be determined)

---

## Component Architecture

### New Components

#### 1. Project Components
```
src/components/project/
├── ProjectCreateWizard.jsx          # 3-step creation form
├── ProjectCreateStep1.jsx           # Name + description
├── ProjectCreateStep2.jsx           # Context options (optional)
├── ProjectCreateStep3.jsx           # Collaboration (optional)
├── ProjectDetailPage.jsx            # Main project view
├── ProjectStatsPanel.jsx            # Top stats display
├── ProjectSettingsDropdown.jsx      # More settings menu
├── ProjectListGrid.jsx              # Paginated PropertyList cards
└── ProjectDashboard.jsx             # Analytics/charts view
```

#### 2. PropertyList Components (Updated)
```
src/components/propertylist/
├── PropertyListCreateForm.jsx       # Search criteria form (updated)
├── PropertyListDetailPage.jsx       # List view with loading states
├── PropertyListLoadingSpinner.jsx   # Scraping progress indicator
└── PropertyListCard.jsx             # Preview card (updated)
```

#### 3. Context Options Components
```
src/components/context/
├── ContextOptionsForm.jsx           # Service toggles form
├── ContextOptionsInlineModal.jsx    # Stage 2 missing config modal
└── ContextOptionsEditModal.jsx      # Project-level edit
```

#### 4. Rating Criteria Components
```
src/components/rating/
├── RatingCriteriaSelector.jsx       # Existing criteria dropdown
├── RatingCriteriaCreateForm.jsx     # New criteria form
└── RatingCriteriaEditModal.jsx      # Project-level edit
```

#### 5. Task Components (New)
```
src/components/tasks/
├── TaskListView.jsx                 # Task list display
├── TaskCard.jsx                     # Individual task
├── TaskCreateForm.jsx               # New task modal
└── TaskEditForm.jsx                 # Edit task modal
```

#### 6. Shared Components
```
src/components/shared/
├── AreaValidationInput.jsx          # Search input with validation
├── BulkOperationConfirmModal.jsx    # Stage 2/3 confirmation (removed)
└── ErrorBoundary.jsx                # Error handling
```

---

## Page Structure

### 1. Project Create Wizard (`/projects/new`)

**Step 1: Basic Info**
```jsx
<ProjectCreateStep1>
  <TextField name="title" required maxLength={255} />
  <TextArea name="description" optional />
  <Button onClick={nextStep}>Next</Button>
</ProjectCreateStep1>
```

**Step 2: Context Options (Optional)**
```jsx
<ProjectCreateStep2>
  <p>Configure which context data services to use (optional, can skip)</p>
  <ContextOptionsForm
    onSave={attachToProject}
    allowSkip={true}
  />
  <Button onClick={skip}>Skip</Button>
  <Button onClick={nextStep}>Next</Button>
</ProjectCreateStep2>
```

**Step 3: Collaboration (Optional)**
```jsx
<ProjectCreateStep3>
  <UserMultiSelect
    label="Viewers"
    field="viewers"
  />
  <UserMultiSelect
    label="Contributors"
    field="contributors"
  />
  <ShareableLink projectUuid={tempUuid} />
  <Button onClick={submit}>Create Project</Button>
</ProjectCreateStep3>
```

**Behavior:**
- Progressive disclosure: show step indicators
- Allow back navigation between steps
- Validation only on current step
- On submit: POST `/api/property/projects/` → redirect to `/projects/{uuid}`

---

### 2. Project Detail Page (`/projects/{uuid}`)

**Layout:**
```jsx
<ProjectDetailPage>
  <Header>
    <Breadcrumb>Projects / {project.title}</Breadcrumb>
    <EditButton />
  </Header>

  <ProjectStatsPanel>
    <Stat label="Property Lists" value={property_lists_count} />
    <Stat label="Total Properties" value={total_properties} />
    <Stat label="Areas Covered" value={unique_areas.length} />
    <Link to={`/projects/${uuid}/dashboard`}>View Dashboard</Link>
  </ProjectStatsPanel>

  <ActionsPanel>
    <Button onClick={openContextOptionsModal}>
      Edit Context Options
    </Button>
    <Button onClick={openRatingCriteriaModal}>
      Add/Edit Rating Criteria
    </Button>
    <ProjectSettingsDropdown>
      <MenuItem to={`/projects/${uuid}/tasks`}>Task Lists</MenuItem>
      <MenuItem to={`/projects/${uuid}/applications`}>Applications</MenuItem>
    </ProjectSettingsDropdown>
  </ActionsPanel>

  <PropertyListGrid>
    <CreateNewCard onClick={() => navigate(`/projects/${uuid}/lists/new`)} />
    {propertyLists.map(list =>
      <PropertyListCard key={list.uuid} {...list} />
    )}
    <Pagination
      page={page}
      totalPages={totalPages}
      onPageChange={setPage}
    />
  </PropertyListGrid>
</ProjectDetailPage>
```

**Data Fetching:**
- GET `/api/property/projects/{uuid}/` for project details
- GET `/api/property/projects/{uuid}/stats/` for aggregated stats
- GET `/api/property/property-lists/?project={uuid}&page={n}` for lists

---

### 3. PropertyList Create Form (`/projects/{uuid}/lists/new`)

**Layout:**
```jsx
<PropertyListCreateForm projectUuid={uuid}>
  <h2>Create New Property List</h2>

  <AreaValidationInput
    name="area"
    label="Area"
    required
    onValidate={async (value) => {
      const result = await validateArea(value);
      if (!result.valid) {
        return {
          error: result.message,
          suggestions: result.suggestions
        };
      }
      return { valid: true };
    }}
    renderSuggestions={(suggestions) =>
      <ul>
        {suggestions.map(s =>
          <li key={s} onClick={() => setArea(s)}>{s}</li>
        )}
      </ul>
    }
  />

  <SearchCriteriaFields>
    {/* existing fields: radius, property_type, min_price, etc */}
  </SearchCriteriaFields>

  <Button
    type="submit"
    disabled={!areaValid || submitting}
  >
    Create & Scrape Properties
  </Button>
</PropertyListCreateForm>
```

**Behavior:**
1. On area input blur: validate via GET `/api/property/rightmove/validate-area/?area={value}`
2. Show suggestions if invalid
3. On submit:
   - POST `/api/property/property-lists/` with search_criteria
   - Backend creates list, auto-generates title, starts scraping
   - Redirect to `/projects/{uuid}/lists/{list_uuid}` with loading state

---

### 4. PropertyList Detail Page (`/projects/{uuid}/lists/{list_uuid}`)

**Loading State (during scraping):**
```jsx
<PropertyListDetailPage>
  <Header>
    <Breadcrumb>
      Projects / {project.title} / {list.title}
    </Breadcrumb>
  </Header>

  <PropertyListLoadingSpinner>
    <Spinner />
    <p>Scraping properties from Rightmove...</p>
    <ProgressBar current={scrapedCount} total={estimatedTotal} />
  </PropertyListLoadingSpinner>

  {/* Poll every 2s for updated property count */}
</PropertyListDetailPage>
```

**Loaded State:**
```jsx
<PropertyListDetailPage>
  <Header>
    <EditTitleButton currentTitle={list.title} />
    <SearchCriteriaSummary criteria={list.search_criteria} />
  </Header>

  <ActionsPanel>
    <Button
      onClick={triggerStage2ForList}
      disabled={!project.context_options}
    >
      Run Stage 2 (Context Data)
    </Button>
    <Button
      onClick={triggerStage3ForList}
      disabled={!hasContextData || !project.rating_criteria}
    >
      Run Stage 3 (Rating)
    </Button>
  </ActionsPanel>

  <PropertyGrid>
    {properties.map(property =>
      <PropertyCard
        key={property.uuid}
        {...property}
        onStage2Click={() => triggerStage2ForProperty(property.uuid)}
        onStage3Click={() => triggerStage3ForProperty(property.uuid)}
      />
    )}
  </PropertyGrid>
</PropertyListDetailPage>
```

**Polling Logic:**
```javascript
const pollProperties = async () => {
  if (isScrapingComplete) return;

  const response = await fetch(`/api/property/property-lists/${listUuid}/`);
  const data = await response.json();

  setProperties(data.properties);
  setScrapedCount(data.properties.length);

  if (data.scraping_status === 'complete') {
    setIsScrapingComplete(true);
  } else {
    setTimeout(pollProperties, 2000);
  }
};

useEffect(() => {
  pollProperties();
}, []);
```

---

### 5. Context Options Inline Modal

**Trigger:** User clicks "Run Stage 2" but `project.context_options` is null

**Modal Content:**
```jsx
<ContextOptionsInlineModal
  projectUuid={project.uuid}
  onSave={async (options) => {
    await fetch(`/api/property/projects/${project.uuid}/context-options/`, {
      method: 'POST',
      body: JSON.stringify(options)
    });
    // Refresh project data
    await fetchProject();
    // Now trigger Stage 2
    triggerStage2();
  }}
  onCancel={closeModal}
>
  <h3>Configure Context Options</h3>
  <p>You need to set up context options before running Stage 2</p>

  <ContextOptionsForm
    onSubmit={handleSave}
    services={[
      { name: 'crime', label: 'Crime Data', enabled: false },
      { name: 'schools', label: 'Schools', enabled: false },
      { name: 'transport', label: 'Transport', enabled: false },
      { name: 'poi', label: 'Points of Interest', enabled: false },
      { name: 'flood', label: 'Flood Risk', enabled: false },
      { name: 'broadband', label: 'Broadband', enabled: false },
      { name: 'demographics', label: 'Demographics', enabled: false }
    ]}
  />

  <Button onClick={onCancel}>Cancel</Button>
  <Button onClick={onSave}>Save & Continue</Button>
</ContextOptionsInlineModal>
```

---

### 6. Rating Criteria Selection Modal

**Trigger:** User clicks "Run Stage 3" but `project.rating_criteria` is null

**Modal Content:**
```jsx
<RatingCriteriaSelectionModal
  projectUuid={project.uuid}
  onSelect={async (criteriaUuid) => {
    await fetch(`/api/property/projects/${project.uuid}/`, {
      method: 'PATCH',
      body: JSON.stringify({ rating_criteria: criteriaUuid })
    });
    await fetchProject();
    triggerStage3();
  }}
  onCreate={async (newCriteria) => {
    const response = await fetch(`/api/property/rating-criteria/`, {
      method: 'POST',
      body: JSON.stringify(newCriteria)
    });
    const created = await response.json();
    onSelect(created.uuid);
  }}
>
  <h3>Select Rating Criteria</h3>

  <Tabs>
    <Tab label="Existing Criteria">
      <RatingCriteriaSelector
        currentUserId={user.id}
        onSelect={onSelect}
      />
    </Tab>
    <Tab label="Create New">
      <RatingCriteriaCreateForm onSubmit={onCreate} />
    </Tab>
  </Tabs>
</RatingCriteriaSelectionModal>
```

---

### 7. Project Dashboard (`/projects/{uuid}/dashboard`)

**Layout:**
```jsx
<ProjectDashboard>
  <Header>
    <h1>{project.title} - Dashboard</h1>
  </Header>

  <StatsGrid>
    <Card title="Total Properties" value={stats.total_properties} />
    <Card title="Average Price" value={formatCurrency(stats.avg_price)} />
    <Card title="Price Range"
          value={`${formatCurrency(stats.min_price)} - ${formatCurrency(stats.max_price)}`} />
  </StatsGrid>

  <ChartsRow>
    <PriceDistributionChart data={stats.price_distribution} />
    <PropertyTypeChart data={stats.property_types} />
  </ChartsRow>

  <AreaBreakdown>
    <h2>Areas Covered</h2>
    <Table>
      <thead>
        <tr>
          <th>Area</th>
          <th>List Count</th>
          <th>Property Count</th>
          <th>Avg Price</th>
        </tr>
      </thead>
      <tbody>
        {stats.by_area.map(area =>
          <tr key={area.name}>
            <td>{area.name}</td>
            <td>{area.list_count}</td>
            <td>{area.property_count}</td>
            <td>{formatCurrency(area.avg_price)}</td>
          </tr>
        )}
      </tbody>
    </Table>
  </AreaBreakdown>
</ProjectDashboard>
```

**Data Source:**
- GET `/api/property/projects/{uuid}/stats/` returns:
```json
{
  "total_properties": 250,
  "avg_price": 425000,
  "min_price": 200000,
  "max_price": 850000,
  "property_lists_count": 5,
  "by_area": [
    {"name": "Manchester", "list_count": 2, "property_count": 120, "avg_price": 380000},
    {"name": "London", "list_count": 3, "property_count": 130, "avg_price": 465000}
  ],
  "price_distribution": [...],
  "property_types": {...}
}
```

---

## State Management

### Global State (Context/Redux)
```javascript
// ProjectContext.jsx
const ProjectContext = createContext();

export const ProjectProvider = ({ children }) => {
  const [currentProject, setCurrentProject] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchProjects = async () => {
    setLoading(true);
    const response = await fetch('/api/property/projects/');
    const data = await response.json();
    setProjects(data.results);
    setLoading(false);
  };

  const selectProject = async (uuid) => {
    setLoading(true);
    const response = await fetch(`/api/property/projects/${uuid}/`);
    const data = await response.json();
    setCurrentProject(data);
    setLoading(false);
  };

  return (
    <ProjectContext.Provider value={{
      currentProject,
      projects,
      loading,
      fetchProjects,
      selectProject
    }}>
      {children}
    </ProjectContext.Provider>
  );
};
```

### Local Component State
- **Form state**: Use controlled components with validation
- **Loading states**: Track per-operation (scraping, stage 2, stage 3)
- **Error states**: Display validation errors, API errors
- **Modal states**: Open/closed state for inline modals

---

## API Integration

### API Client Setup
```javascript
// api/client.js
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/property',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Request interceptor for auth token
apiClient.interceptors.request.use(config => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for error handling
apiClient.interceptors.response.use(
  response => response,
  error => {
    if (error.response?.status === 401) {
      // Redirect to login
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export default apiClient;
```

### API Service Functions
```javascript
// api/projectService.js
import apiClient from './client';

export const projectService = {
  list: (params) => apiClient.get('/projects/', { params }),

  get: (uuid) => apiClient.get(`/projects/${uuid}/`),

  create: (data) => apiClient.post('/projects/', data),

  update: (uuid, data) => apiClient.patch(`/projects/${uuid}/`, data),

  delete: (uuid) => apiClient.delete(`/projects/${uuid}/`),

  getStats: (uuid) => apiClient.get(`/projects/${uuid}/stats/`),

  setContextOptions: (uuid, options) =>
    apiClient.post(`/projects/${uuid}/context-options/`, options),

  getContextOptions: (uuid) =>
    apiClient.get(`/projects/${uuid}/context-options/`)
};

// api/propertyListService.js
export const propertyListService = {
  list: (params) => apiClient.get('/property-lists/', { params }),

  get: (uuid) => apiClient.get(`/property-lists/${uuid}/`),

  create: (data) => apiClient.post('/property-lists/', data),

  update: (uuid, data) => apiClient.patch(`/property-lists/${uuid}/`, data),

  delete: (uuid) => apiClient.delete(`/property-lists/${uuid}/`),

  triggerStage2: (uuid) =>
    apiClient.post(`/property-lists/${uuid}/retrieve_context_data/`),

  triggerStage3: (uuid) =>
    apiClient.post(`/property-lists/${uuid}/calculate_ratings/`)
};

// api/validationService.js
export const validationService = {
  validateArea: (area) =>
    apiClient.get('/rightmove/validate-area/', { params: { area } })
};
```

---

## Routing

### Route Structure
```javascript
// App.jsx or routes.jsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

<BrowserRouter>
  <Routes>
    {/* Project routes */}
    <Route path="/projects" element={<ProjectListPage />} />
    <Route path="/projects/new" element={<ProjectCreateWizard />} />
    <Route path="/projects/:projectUuid" element={<ProjectDetailPage />} />
    <Route path="/projects/:projectUuid/dashboard" element={<ProjectDashboard />} />

    {/* PropertyList routes */}
    <Route path="/projects/:projectUuid/lists/new" element={<PropertyListCreateForm />} />
    <Route path="/projects/:projectUuid/lists/:listUuid" element={<PropertyListDetailPage />} />

    {/* Task routes */}
    <Route path="/projects/:projectUuid/tasks" element={<TaskListsPage />} />

    {/* Legacy routes - redirect to projects */}
    <Route path="/property-lists" element={<Navigate to="/projects" replace />} />
    <Route path="/property-lists/:listUuid"
           element={<LegacyPropertyListRedirect />} />
  </Routes>
</BrowserRouter>
```

### Legacy Redirect Handler
```javascript
// For old bookmarks/links to property lists
const LegacyPropertyListRedirect = () => {
  const { listUuid } = useParams();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const response = await fetch(`/api/property/property-lists/${listUuid}/`);
      const list = await response.json();
      navigate(`/projects/${list.project_uuid}/lists/${listUuid}`, { replace: true });
    })();
  }, [listUuid]);

  if (loading) return <Spinner />;
  return null;
};
```

---

## Implementation Details

### 1. Area Validation Input Component

```jsx
// components/shared/AreaValidationInput.jsx
import { useState, useEffect } from 'react';
import { validationService } from '../../api/validationService';
import debounce from 'lodash/debounce';

export const AreaValidationInput = ({
  value,
  onChange,
  onValidationChange,
  required = false
}) => {
  const [validating, setValidating] = useState(false);
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [isValid, setIsValid] = useState(false);

  const validateArea = debounce(async (areaValue) => {
    if (!areaValue) {
      setError(null);
      setSuggestions([]);
      setIsValid(false);
      onValidationChange?.(false);
      return;
    }

    setValidating(true);
    try {
      const response = await validationService.validateArea(areaValue);

      if (response.data.valid) {
        setError(null);
        setSuggestions([]);
        setIsValid(true);
        onValidationChange?.(true);
      } else {
        setError(response.data.message);
        setSuggestions(response.data.suggestions || []);
        setIsValid(false);
        onValidationChange?.(false);
      }
    } catch (err) {
      setError('Unable to validate area. Please try again.');
      setIsValid(false);
      onValidationChange?.(false);
    } finally {
      setValidating(false);
    }
  }, 500);

  useEffect(() => {
    validateArea(value);
  }, [value]);

  return (
    <div className="area-validation-input">
      <label>
        Area {required && <span className="required">*</span>}
      </label>

      <div className="input-wrapper">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className={error ? 'error' : isValid ? 'valid' : ''}
          placeholder="e.g., Manchester, London, SW1A 1AA"
        />
        {validating && <Spinner size="small" />}
        {isValid && <CheckIcon className="valid-icon" />}
      </div>

      {error && (
        <div className="error-message">
          <p>{error}</p>
          {suggestions.length > 0 && (
            <div className="suggestions">
              <p>Did you mean:</p>
              <ul>
                {suggestions.map(suggestion => (
                  <li
                    key={suggestion}
                    onClick={() => {
                      onChange(suggestion);
                      setError(null);
                      setSuggestions([]);
                    }}
                  >
                    {suggestion}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
```

### 2. Project Create Wizard State Management

```javascript
// pages/ProjectCreateWizard.jsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { projectService } from '../api/projectService';

export const ProjectCreateWizard = () => {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    context_options: null,
    viewers: [],
    contributors: []
  });
  const [errors, setErrors] = useState({});
  const [submitting, setSubmitting] = useState(false);

  const updateField = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    // Clear error for this field
    if (errors[field]) {
      setErrors(prev => {
        const newErrors = { ...prev };
        delete newErrors[field];
        return newErrors;
      });
    }
  };

  const validateStep1 = () => {
    const newErrors = {};
    if (!formData.title.trim()) {
      newErrors.title = 'Title is required';
    }
    if (formData.title.length > 255) {
      newErrors.title = 'Title must be 255 characters or less';
    }
    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = () => {
    if (step === 1 && !validateStep1()) return;
    setStep(prev => prev + 1);
  };

  const handleBack = () => {
    setStep(prev => prev - 1);
  };

  const handleSkipContextOptions = () => {
    updateField('context_options', null);
    setStep(3);
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    try {
      const response = await projectService.create({
        title: formData.title,
        description: formData.description,
        viewers: formData.viewers,
        contributors: formData.contributors
      });

      // If context options provided, set them
      if (formData.context_options) {
        await projectService.setContextOptions(
          response.data.uuid,
          formData.context_options
        );
      }

      navigate(`/projects/${response.data.uuid}`);
    } catch (error) {
      setErrors({ submit: error.response?.data?.detail || 'Failed to create project' });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="project-create-wizard">
      <ProgressIndicator currentStep={step} totalSteps={3} />

      {step === 1 && (
        <ProjectCreateStep1
          title={formData.title}
          description={formData.description}
          errors={errors}
          onTitleChange={(value) => updateField('title', value)}
          onDescriptionChange={(value) => updateField('description', value)}
          onNext={handleNext}
        />
      )}

      {step === 2 && (
        <ProjectCreateStep2
          contextOptions={formData.context_options}
          onContextOptionsChange={(value) => updateField('context_options', value)}
          onBack={handleBack}
          onNext={handleNext}
          onSkip={handleSkipContextOptions}
        />
      )}

      {step === 3 && (
        <ProjectCreateStep3
          viewers={formData.viewers}
          contributors={formData.contributors}
          onViewersChange={(value) => updateField('viewers', value)}
          onContributorsChange={(value) => updateField('contributors', value)}
          onBack={handleBack}
          onSubmit={handleSubmit}
          submitting={submitting}
          errors={errors}
        />
      )}
    </div>
  );
};
```

### 3. Stage 2 Trigger with Inline Modal

```javascript
// hooks/useStage2Trigger.js
import { useState } from 'react';
import { propertyListService, projectService } from '../api';

export const useStage2Trigger = (propertyList, project) => {
  const [showContextOptionsModal, setShowContextOptionsModal] = useState(false);
  const [triggering, setTriggering] = useState(false);

  const triggerStage2 = async () => {
    // Check if project has context options
    if (!project.context_options) {
      setShowContextOptionsModal(true);
      return;
    }

    // Trigger Stage 2
    setTriggering(true);
    try {
      await propertyListService.triggerStage2(propertyList.uuid);
      // WebSocket will handle real-time updates
    } catch (error) {
      console.error('Failed to trigger Stage 2:', error);
      alert('Failed to start context data retrieval');
    } finally {
      setTriggering(false);
    }
  };

  const handleContextOptionsSaved = async () => {
    setShowContextOptionsModal(false);
    // Now trigger Stage 2
    await triggerStage2();
  };

  return {
    triggerStage2,
    triggering,
    showContextOptionsModal,
    setShowContextOptionsModal,
    handleContextOptionsSaved
  };
};

// Usage in component:
const PropertyListDetailPage = () => {
  const { propertyList, project } = usePropertyListContext();
  const {
    triggerStage2,
    triggering,
    showContextOptionsModal,
    setShowContextOptionsModal,
    handleContextOptionsSaved
  } = useStage2Trigger(propertyList, project);

  return (
    <>
      <Button
        onClick={triggerStage2}
        disabled={triggering}
      >
        {triggering ? 'Starting...' : 'Run Stage 2'}
      </Button>

      {showContextOptionsModal && (
        <ContextOptionsInlineModal
          projectUuid={project.uuid}
          onSave={handleContextOptionsSaved}
          onCancel={() => setShowContextOptionsModal(false)}
        />
      )}
    </>
  );
};
```

---

## Testing Strategy

### Unit Tests

**Component Tests** (React Testing Library)
```javascript
// __tests__/AreaValidationInput.test.jsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AreaValidationInput } from '../components/shared/AreaValidationInput';
import { validationService } from '../api/validationService';

jest.mock('../api/validationService');

describe('AreaValidationInput', () => {
  it('validates area on input change', async () => {
    validationService.validateArea.mockResolvedValue({
      data: { valid: true }
    });

    const onValidationChange = jest.fn();
    render(
      <AreaValidationInput
        value=""
        onChange={() => {}}
        onValidationChange={onValidationChange}
      />
    );

    const input = screen.getByPlaceholderText(/e.g., Manchester/i);
    await userEvent.type(input, 'Manchester');

    await waitFor(() => {
      expect(validationService.validateArea).toHaveBeenCalledWith('Manchester');
      expect(onValidationChange).toHaveBeenCalledWith(true);
    });
  });

  it('shows suggestions when area is invalid', async () => {
    validationService.validateArea.mockResolvedValue({
      data: {
        valid: false,
        message: 'Area not found',
        suggestions: ['Manchester', 'Manchester City Centre']
      }
    });

    render(<AreaValidationInput value="Manchster" onChange={() => {}} />);

    await waitFor(() => {
      expect(screen.getByText(/Area not found/i)).toBeInTheDocument();
      expect(screen.getByText('Manchester')).toBeInTheDocument();
      expect(screen.getByText('Manchester City Centre')).toBeInTheDocument();
    });
  });
});
```

**Hook Tests**
```javascript
// __tests__/useStage2Trigger.test.js
import { renderHook, act } from '@testing-library/react-hooks';
import { useStage2Trigger } from '../hooks/useStage2Trigger';
import { propertyListService } from '../api';

jest.mock('../api');

describe('useStage2Trigger', () => {
  it('shows modal when context options missing', async () => {
    const propertyList = { uuid: 'list-123' };
    const project = { uuid: 'proj-456', context_options: null };

    const { result } = renderHook(() => useStage2Trigger(propertyList, project));

    await act(async () => {
      result.current.triggerStage2();
    });

    expect(result.current.showContextOptionsModal).toBe(true);
    expect(propertyListService.triggerStage2).not.toHaveBeenCalled();
  });

  it('triggers Stage 2 when context options exist', async () => {
    const propertyList = { uuid: 'list-123' };
    const project = {
      uuid: 'proj-456',
      context_options: { crime: true, schools: true }
    };

    propertyListService.triggerStage2.mockResolvedValue({});

    const { result } = renderHook(() => useStage2Trigger(propertyList, project));

    await act(async () => {
      await result.current.triggerStage2();
    });

    expect(propertyListService.triggerStage2).toHaveBeenCalledWith('list-123');
    expect(result.current.showContextOptionsModal).toBe(false);
  });
});
```

### Integration Tests

**User Flow Tests** (Cypress/Playwright)
```javascript
// e2e/projectCreation.spec.js
describe('Project Creation Flow', () => {
  it('creates project with all steps', () => {
    cy.visit('/projects/new');

    // Step 1
    cy.get('input[name="title"]').type('House Hunting 2026');
    cy.get('textarea[name="description"]').type('Looking for family home');
    cy.contains('Next').click();

    // Step 2 - skip context options
    cy.contains('Skip').click();

    // Step 3
    cy.get('[data-testid="viewers-select"]').click();
    cy.contains('john@example.com').click();
    cy.contains('Create Project').click();

    // Should redirect to project detail page
    cy.url().should('include', '/projects/');
    cy.contains('House Hunting 2026');
  });
});

// e2e/propertyListScraping.spec.js
describe('PropertyList Auto-Scraping', () => {
  it('validates area and scrapes properties', () => {
    cy.visit('/projects/some-uuid/lists/new');

    // Enter invalid area
    cy.get('input[name="area"]').type('Manchstr');
    cy.contains('Area not found').should('be.visible');
    cy.contains('Manchester').click(); // Click suggestion

    // Fill rest of form
    cy.get('select[name="radius"]').select('5');
    cy.get('input[name="min_price"]').type('200000');
    cy.get('input[name="max_price"]').type('500000');

    cy.contains('Create & Scrape Properties').click();

    // Should show loading state
    cy.contains('Scraping properties from Rightmove');

    // Wait for completion (mock WebSocket)
    cy.wait(3000);
    cy.get('[data-testid="property-card"]').should('have.length.greaterThan', 0);
  });
});
```

---

## Implementation Sequence

### Week 1: Core Project Infrastructure

**Day 1: Project Components & Routing**
- [ ] Set up routing structure
- [ ] Create ProjectListPage (basic list view)
- [ ] Create ProjectDetailPage skeleton
- [ ] Create ProjectCreateWizard with step 1 only
- [ ] Test navigation between pages

**Day 2: Project Creation Wizard**
- [ ] Implement Step 1 (basic info) with validation
- [ ] Implement Step 2 (context options form)
- [ ] Implement Step 3 (collaboration)
- [ ] Wire up wizard state management
- [ ] Test full creation flow

**Day 3: Project Detail Page**
- [ ] Build ProjectStatsPanel
- [ ] Build ProjectSettingsDropdown
- [ ] Implement PropertyListGrid with pagination
- [ ] Add edit/delete project actions
- [ ] Test data fetching and display

---

### Week 2: PropertyList Auto-Scraping

**Day 4: Area Validation**
- [ ] Create AreaValidationInput component
- [ ] Implement debounced validation
- [ ] Add suggestion selection UI
- [ ] Write unit tests for validation
- [ ] Integrate into PropertyList create form

**Day 5: PropertyList Creation & Loading**
- [ ] Update PropertyListCreateForm with area validation
- [ ] Build PropertyListLoadingSpinner
- [ ] Implement polling logic for scraping progress
- [ ] Add error handling for scraping failures
- [ ] Test creation → loading → loaded flow

**Day 6: PropertyList Detail Updates**
- [ ] Update PropertyListDetailPage layout
- [ ] Add Stage 2/3 trigger buttons
- [ ] Implement button disable logic based on prerequisites
- [ ] Test property display with new project context

---

### Week 3: Context & Rating Setup

**Day 7: Context Options Management**
- [ ] Create ContextOptionsForm component
- [ ] Create ContextOptionsInlineModal
- [ ] Create ContextOptionsEditModal
- [ ] Implement save/update logic
- [ ] Test inline modal trigger on Stage 2 click

**Day 8: Rating Criteria Management**
- [ ] Create RatingCriteriaSelector component
- [ ] Create RatingCriteriaCreateForm
- [ ] Create RatingCriteriaSelectionModal
- [ ] Implement modal trigger on Stage 3 click
- [ ] Test criteria selection and creation

**Day 9: Stage 2/3 Triggers**
- [ ] Create useStage2Trigger hook
- [ ] Create useStage3Trigger hook
- [ ] Wire up property-level triggers
- [ ] Wire up list-level triggers
- [ ] Test prerequisite checks and modal flows

---

### Week 4: Dashboard & Polish

**Day 10: Project Dashboard**
- [ ] Create ProjectDashboard page
- [ ] Build StatsGrid component
- [ ] Implement charts (price distribution, property types)
- [ ] Build area breakdown table
- [ ] Test stats API integration

**Day 11: Task Management (Optional)**
- [ ] Create TaskListsPage
- [ ] Create TaskCard component
- [ ] Implement task CRUD operations
- [ ] Add task ordering/drag-drop
- [ ] Test task management flow

**Day 12: Testing & Bug Fixes**
- [ ] Write unit tests for all new components
- [ ] Write integration tests for key flows
- [ ] Fix bugs discovered in testing
- [ ] Cross-browser testing
- [ ] Performance optimization

---

## Checklist Summary

### Pre-Implementation
- [ ] Backend API endpoints ready (from backend spec)
- [ ] API documentation/OpenAPI spec available
- [ ] Design mockups/wireframes reviewed
- [ ] Component library/styling approach decided

### During Implementation
- [ ] All components follow naming conventions
- [ ] PropTypes/TypeScript types defined
- [ ] Error boundaries implemented
- [ ] Loading states handled
- [ ] Empty states designed
- [ ] Responsive design tested
- [ ] Accessibility (a11y) checked

### Post-Implementation
- [ ] Unit test coverage > 80%
- [ ] Integration tests for critical flows passing
- [ ] No console errors/warnings
- [ ] Performance metrics acceptable (< 3s page load)
- [ ] Cross-browser compatibility verified
- [ ] User acceptance testing completed
- [ ] Documentation updated

---

## Success Criteria

### Functional Requirements Met
- ✅ Users can create projects with 3-step wizard
- ✅ Context options configurable at project level
- ✅ PropertyList creation auto-scrapes with area validation
- ✅ Area suggestions shown for invalid inputs
- ✅ Loading states shown during scraping
- ✅ Inline modals prompt for missing config before Stage 2/3
- ✅ Project dashboard shows aggregated stats
- ✅ Navigation flows logically (project → lists → properties)

### Non-Functional Requirements Met
- ✅ Page load times < 3 seconds
- ✅ Forms validate before submission
- ✅ Error messages clear and actionable
- ✅ Responsive on mobile/tablet/desktop
- ✅ Accessible (keyboard navigation, screen readers)
- ✅ No memory leaks (cleanup on unmount)

---

## Notes

### Assumptions
- React is the frontend framework (adjust if different)
- Existing WebSocket implementation can be reused for real-time updates
- Existing auth system provides user context
- API returns paginated results in standard format

### Deferred/Out of Scope
- Bulk operations at project level (removed from scope per user decision)
- Advanced analytics/charts (basic stats only)
- Mobile app (web-only)
- Offline support
- Real-time collaboration (beyond what WebSocket provides)

### Dependencies on Backend
- Backend must be deployed first (endpoints ready)
- Area validation endpoint operational
- Auto-scraping on list creation working
- Stats endpoint returning correct aggregations
- Context options/rating criteria properly scoped to project

---

**END OF SPEC**
