# Frontend Technical Specification - Project Refactor (Angular)

**Date:** 2026-03-31
**Status:** Planning
**Related:** backend_technical_spec.md

---

## Table of Contents
1. [Overview](#overview)
2. [Component Architecture](#component-architecture)
3. [Models & Interfaces](#models--interfaces)
4. [Services](#services)
5. [Stores (Signal Store)](#stores-signal-store)
6. [Routing Updates](#routing-updates)
7. [Implementation Details](#implementation-details)
8. [Testing Strategy](#testing-strategy)
9. [Implementation Sequence](#implementation-sequence)

---

## Overview

### Key Changes from Current Frontend
- **Project-first workflow**: Users create Project before PropertyLists
- **3-step Project creation wizard** with context options and collaboration setup
- **Auto-scraping on PropertyList creation** with loading states and existing WebSocket polling
- **Inline ContextOptions setup modal** when missing during Stage 2 trigger
- **Project-level stats dashboard** with aggregated data
- **Area validation feedback** with suggestions on invalid input
- **Project-scoped navigation** between lists and tasks

### Technology Stack (Existing)
- Angular 18+ (standalone components)
- @ngrx/signals for state management
- RxJS for reactive programming
- TailwindCSS for styling (assumed based on config)
- Existing WebSocket service for real-time updates

---

## Component Architecture

### New Feature Module: Projects

```
src/app/features/projects/
├── components/
│   ├── project-list/
│   │   ├── project-list.component.ts
│   │   ├── project-list.component.html
│   │   └── project-list.component.css
│   ├── project-card/
│   │   ├── project-card.component.ts
│   │   ├── project-card.component.html
│   │   └── project-card.component.css
│   ├── project-create/
│   │   ├── project-create.component.ts         # Wizard container
│   │   ├── project-create.component.html
│   │   ├── project-create.component.css
│   │   ├── steps/
│   │   │   ├── step1-basic-info.component.ts
│   │   │   ├── step2-context-options.component.ts
│   │   │   └── step3-collaboration.component.ts
│   ├── project-detail/
│   │   ├── project-detail.component.ts
│   │   ├── project-detail.component.html
│   │   └── project-detail.component.css
│   ├── project-stats-panel/
│   │   ├── project-stats-panel.component.ts
│   │   ├── project-stats-panel.component.html
│   │   └── project-stats-panel.component.css
│   ├── project-dashboard/
│   │   ├── project-dashboard.component.ts
│   │   ├── project-dashboard.component.html
│   │   └── project-dashboard.component.css
│   ├── project-settings-dropdown/
│   │   └── project-settings-dropdown.component.ts
│   └── project-list-grid/
│       ├── project-list-grid.component.ts
│       ├── project-list-grid.component.html
│       └── project-list-grid.component.css
├── store/
│   └── project.store.ts
├── models/
│   └── project.models.ts
└── projects.routes.ts
```

### New Feature Module: Tasks

```
src/app/features/tasks/
├── components/
│   ├── task-list-view/
│   │   ├── task-list-view.component.ts
│   │   ├── task-list-view.component.html
│   │   └── task-list-view.component.css
│   ├── task-card/
│   │   ├── task-card.component.ts
│   │   ├── task-card.component.html
│   │   └── task-card.component.css
│   ├── task-create-modal/
│   │   └── task-create-modal.component.ts
│   └── task-edit-modal/
│       └── task-edit-modal.component.ts
├── store/
│   └── task.store.ts
├── models/
│   └── task.models.ts
└── tasks.routes.ts
```

### Updated Existing Components

#### property-lists/components/
- **property-list-list.component** → Update to show within project context
- **property-list-create.component** → Add area validation, remove collaboration fields
- **property-list-detail.component** → Update Stage 2/3 logic to check project-level context options
- **context-options-form.component** → Reuse for project-level setup + inline modal

#### shared/components/
- **Add:** `area-validation-input.component.ts` - Search input with validation
- **Add:** `inline-modal.component.ts` - Reusable modal for context options
- **Add:** `progress-indicator.component.ts` - Wizard step indicator

---

## Models & Interfaces

### New Models (src/app/shared/models/project-models.ts)

```typescript
export interface Project {
  uuid: string;
  owner: string;
  title: string;
  description: string;
  viewers: string[];
  contributors: string[];
  rating_criteria: string | null;
  rating_criteria_source: string | null;
  context_options: ContextOptions | null;
  property_lists_count: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  property_lists: PropertyList[];
}

export interface ProjectStats {
  total_properties: number;
  avg_price: number | null;
  min_price: number | null;
  max_price: number | null;
  property_lists_count: number;
  by_area: AreaBreakdown[];
  price_distribution: any; // Chart data
  property_types: any; // Chart data
}

export interface AreaBreakdown {
  name: string;
  list_count: number;
  property_count: number;
  avg_price: number;
}

export interface CreateProjectDto {
  title: string;
  description?: string;
  viewers?: string[];
  contributors?: string[];
}

export interface UpdateProjectDto {
  title?: string;
  description?: string;
  viewers?: string[];
  contributors?: string[];
  rating_criteria?: string | null;
}

export interface ContextOptions {
  uuid: string;
  project: string; // project UUID
  crime_service_enabled: boolean;
  schools_service_enabled: boolean;
  transport_service_enabled: boolean;
  poi_service_enabled: boolean;
  flood_service_enabled: boolean;
  broadband_service_enabled: boolean;
  demographics_service_enabled: boolean;
  council_tax_service_enabled?: boolean;
  saved_locations_service_enabled?: boolean;
}

export interface CreateContextOptionsDto {
  crime_service_enabled: boolean;
  schools_service_enabled: boolean;
  transport_service_enabled: boolean;
  poi_service_enabled: boolean;
  flood_service_enabled: boolean;
  broadband_service_enabled: boolean;
  demographics_service_enabled: boolean;
  council_tax_service_enabled?: boolean;
  saved_locations_service_enabled?: boolean;
}
```

### New Models (src/app/shared/models/task-models.ts)

```typescript
export type TaskStatus = 'TODO' | 'IN_PROGRESS' | 'DONE';
export type TaskPriority = 'LOW' | 'MEDIUM' | 'HIGH';

export interface TaskList {
  uuid: string;
  project: string; // project UUID
  title: string;
  description: string;
  tasks_count: number;
  created_at: string;
  updated_at: string;
}

export interface Task {
  uuid: string;
  task_list: string; // task_list UUID
  title: string;
  description: string;
  status: TaskStatus;
  status_display: string;
  priority: TaskPriority;
  priority_display: string;
  assigned_to: string | null;
  due_date: string | null;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface CreateTaskListDto {
  project: string;
  title: string;
  description?: string;
}

export interface CreateTaskDto {
  task_list: string;
  title: string;
  description?: string;
  status?: TaskStatus;
  priority?: TaskPriority;
  assigned_to?: string | null;
  due_date?: string | null;
  order?: number;
}
```

### Updated Models (src/app/shared/models/property-list-models.ts)

```typescript
// UPDATE existing PropertyList interface:
export interface PropertyList {
  uuid: string;
  owner: string;
  project: string; // NEW: project UUID
  project_title?: string; // NEW: for display
  title: string;
  state: PropertyListState; // REMOVE after backend removes it
  rating_criteria: string | null; // REMOVE - moved to Project
  rating_criteria_source: string | null; // REMOVE - moved to Project
  search_criteria: SearchCriteria | null;
  viewers: string[]; // REMOVE - moved to Project
  contributors: string[]; // REMOVE - moved to Project
  properties_count: number;
  status_summary: PropertyListStatusSummary;
  average_price?: number | null; // NEW
  highest_price?: number | null; // NEW
  lowest_price?: number | null; // NEW
  created_at: string;
  updated_at: string;
}

// UPDATE CreatePropertyListDto:
export interface CreatePropertyListDto {
  project: string; // NEW: required
  search_criteria: SearchCriteria; // NEW: required for auto-scraping
  title?: string; // OPTIONAL - backend auto-generates from area
}

// UPDATE UpdatePropertyListDto:
export interface UpdatePropertyListDto {
  title?: string;
  search_criteria?: SearchCriteria;
  // REMOVE: rating_criteria, viewers, contributors
}
```

### New Models (src/app/shared/models/validation-models.ts)

```typescript
export interface AreaValidationResponse {
  valid: boolean;
  message?: string;
  suggestions?: string[];
}
```

---

## Services

### New Service: ProjectService

**File:** `src/app/core/services/project-service/project.service.ts`

```typescript
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../api-service/api.service';
import {
  Project,
  ProjectDetail,
  ProjectStats,
  CreateProjectDto,
  UpdateProjectDto,
  CreateContextOptionsDto,
  ContextOptions
} from '../../../shared/models/project-models';

@Injectable({
  providedIn: 'root',
})
export class ProjectService {
  private api = inject(ApiService);
  private readonly endpoint = 'property/projects/';

  getAll(): Observable<Project[]> {
    return this.api.get<Project[]>(this.endpoint);
  }

  getByUuid(uuid: string): Observable<ProjectDetail> {
    return this.api.get<ProjectDetail>(`${this.endpoint}${uuid}/`);
  }

  create(data: CreateProjectDto): Observable<Project> {
    return this.api.post<Project>(this.endpoint, data);
  }

  update(uuid: string, data: UpdateProjectDto): Observable<Project> {
    return this.api.patch<Project>(`${this.endpoint}${uuid}/`, data);
  }

  delete(uuid: string): Observable<void> {
    return this.api.delete<void>(`${this.endpoint}${uuid}/`);
  }

  getStats(uuid: string): Observable<ProjectStats> {
    return this.api.get<ProjectStats>(`${this.endpoint}${uuid}/stats/`);
  }

  getContextOptions(uuid: string): Observable<ContextOptions> {
    return this.api.get<ContextOptions>(`${this.endpoint}${uuid}/context-options/`);
  }

  setContextOptions(uuid: string, data: CreateContextOptionsDto): Observable<ContextOptions> {
    return this.api.post<ContextOptions>(`${this.endpoint}${uuid}/context-options/`, data);
  }
}
```

### New Service: TaskService

**File:** `src/app/core/services/task-service/task.service.ts`

```typescript
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../api-service/api.service';
import {
  TaskList,
  Task,
  CreateTaskListDto,
  CreateTaskDto
} from '../../../shared/models/task-models';

@Injectable({
  providedIn: 'root',
})
export class TaskService {
  private api = inject(ApiService);
  private readonly taskListEndpoint = 'property/task-lists/';
  private readonly taskEndpoint = 'property/tasks/';

  // TaskList methods
  getAllTaskLists(projectUuid?: string): Observable<TaskList[]> {
    const params = projectUuid ? { project: projectUuid } : {};
    return this.api.get<TaskList[]>(this.taskListEndpoint, params);
  }

  getTaskList(uuid: string): Observable<TaskList> {
    return this.api.get<TaskList>(`${this.taskListEndpoint}${uuid}/`);
  }

  createTaskList(data: CreateTaskListDto): Observable<TaskList> {
    return this.api.post<TaskList>(this.taskListEndpoint, data);
  }

  updateTaskList(uuid: string, data: Partial<CreateTaskListDto>): Observable<TaskList> {
    return this.api.patch<TaskList>(`${this.taskListEndpoint}${uuid}/`, data);
  }

  deleteTaskList(uuid: string): Observable<void> {
    return this.api.delete<void>(`${this.taskListEndpoint}${uuid}/`);
  }

  // Task methods
  getAllTasks(taskListUuid?: string): Observable<Task[]> {
    const params = taskListUuid ? { task_list: taskListUuid } : {};
    return this.api.get<Task[]>(this.taskEndpoint, params);
  }

  getTask(uuid: string): Observable<Task> {
    return this.api.get<Task>(`${this.taskEndpoint}${uuid}/`);
  }

  createTask(data: CreateTaskDto): Observable<Task> {
    return this.api.post<Task>(this.taskEndpoint, data);
  }

  updateTask(uuid: string, data: Partial<CreateTaskDto>): Observable<Task> {
    return this.api.patch<Task>(`${this.taskEndpoint}${uuid}/`, data);
  }

  deleteTask(uuid: string): Observable<void> {
    return this.api.delete<void>(`${this.taskEndpoint}${uuid}/`);
  }
}
```

### New Service: ValidationService

**File:** `src/app/core/services/validation-service/validation.service.ts`

```typescript
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../api-service/api.service';
import { AreaValidationResponse } from '../../../shared/models/validation-models';

@Injectable({
  providedIn: 'root',
})
export class ValidationService {
  private api = inject(ApiService);
  private readonly endpoint = 'property/rightmove/validate-area/';

  validateArea(area: string): Observable<AreaValidationResponse> {
    return this.api.get<AreaValidationResponse>(this.endpoint, { area });
  }
}
```

### Updated Service: ContextOptionsService

**File:** `src/app/core/services/context-options-service/context-options.service.ts`

```typescript
// UPDATE: Remove methods that are now on ProjectService
// Keep methods for updating if needed, but primary CRUD moves to ProjectService
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../api-service/api.service';
import { ContextOptions, CreateContextOptionsDto } from '../../../shared/models/project-models';

@Injectable({
  providedIn: 'root',
})
export class ContextOptionsService {
  private api = inject(ApiService);
  private readonly endpoint = 'property/context-options/';

  // Keep for backward compatibility or direct access
  getByUuid(uuid: string): Observable<ContextOptions> {
    return this.api.get<ContextOptions>(`${this.endpoint}${uuid}/`);
  }

  update(uuid: string, data: CreateContextOptionsDto): Observable<ContextOptions> {
    return this.api.patch<ContextOptions>(`${this.endpoint}${uuid}/`, data);
  }

  delete(uuid: string): Observable<void> {
    return this.api.delete<void>(`${this.endpoint}${uuid}/`);
  }
}
```

### Updated Service: PropertyListService

**File:** `src/app/core/services/property-list-service/property-list.service.ts`

```typescript
// UPDATE: Remove activate() method (state field removed)
// UPDATE create() to accept new CreatePropertyListDto with project + search_criteria

import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ApiService } from '../api-service/api.service';
import {
  PropertyList,
  PropertyListDetail,
  CreatePropertyListDto,
  UpdatePropertyListDto,
} from '../../../shared/models/property-list-models';

@Injectable({
  providedIn: 'root',
})
export class PropertyListService {
  private api = inject(ApiService);
  private readonly endpoint = 'property/property-lists/';

  getAll(projectUuid?: string): Observable<PropertyList[]> {
    const params = projectUuid ? { project: projectUuid } : {};
    return this.api.get<PropertyList[]>(this.endpoint, params);
  }

  getByUuid(uuid: string): Observable<PropertyListDetail> {
    return this.api.get<PropertyListDetail>(`${this.endpoint}${uuid}/`);
  }

  create(data: CreatePropertyListDto): Observable<PropertyList> {
    return this.api.post<PropertyList>(this.endpoint, data);
  }

  update(uuid: string, data: UpdatePropertyListDto): Observable<PropertyList> {
    return this.api.patch<PropertyList>(`${this.endpoint}${uuid}/`, data);
  }

  delete(uuid: string): Observable<void> {
    return this.api.delete<void>(`${this.endpoint}${uuid}/`);
  }

  // REMOVED: activate() - state field removed from backend
}
```

---

## Stores (Signal Store)

### New Store: ProjectStore

**File:** `src/app/features/projects/store/project.store.ts`

```typescript
import { computed, inject } from '@angular/core';
import {
  patchState,
  signalStore,
  withComputed,
  withMethods,
  withState,
} from '@ngrx/signals';
import { rxMethod } from '@ngrx/signals/rxjs-interop';
import { pipe, switchMap, tap, exhaustMap, catchError, EMPTY } from 'rxjs';
import { ProjectService } from '../../../core/services/project-service/project.service';
import {
  Project,
  ProjectDetail,
  CreateProjectDto,
  UpdateProjectDto,
  ProjectStats,
} from '../../../shared/models/project-models';

type ProjectState = {
  entities: Record<string, Project>;
  detailEntities: Record<string, ProjectDetail>;
  statsEntities: Record<string, ProjectStats>;
  ids: string[];
  selectedId: string | null;
  loading: boolean;
  error: string | null;
};

const initialState: ProjectState = {
  entities: {},
  detailEntities: {},
  statsEntities: {},
  ids: [],
  selectedId: null,
  loading: false,
  error: null,
};

export const ProjectStore = signalStore(
  { providedIn: 'root' },
  withState(initialState),
  withComputed(({ entities, detailEntities, statsEntities, ids, selectedId }) => ({
    all: computed(() => ids().map((id) => entities()[id])),
    selected: computed(() => {
      const id = selectedId();
      return id ? entities()[id] : null;
    }),
    selectedDetail: computed(() => {
      const id = selectedId();
      return id ? detailEntities()[id] : null;
    }),
    selectedStats: computed(() => {
      const id = selectedId();
      return id ? statsEntities()[id] : null;
    }),
    count: computed(() => ids().length),
  })),
  withMethods((store, service = inject(ProjectService)) => ({
    load: rxMethod<void>(
      pipe(
        tap(() => patchState(store, { loading: true, error: null })),
        switchMap(() =>
          service.getAll().pipe(
            tap((projects) => {
              const entities: Record<string, Project> = {};
              const ids: string[] = [];
              projects.forEach((project) => {
                entities[project.uuid] = project;
                ids.push(project.uuid);
              });
              patchState(store, { entities, ids, loading: false });
            }),
            catchError((error) => {
              patchState(store, { error: error.message, loading: false });
              return EMPTY;
            })
          )
        )
      )
    ),

    loadDetail: rxMethod<string>(
      pipe(
        tap(() => patchState(store, { loading: true, error: null })),
        switchMap((uuid) =>
          service.getByUuid(uuid).pipe(
            tap((project) => {
              patchState(store, {
                detailEntities: {
                  ...store.detailEntities(),
                  [uuid]: project,
                },
                entities: {
                  ...store.entities(),
                  [uuid]: project,
                },
                selectedId: uuid,
                loading: false,
              });
            }),
            catchError((error) => {
              patchState(store, { error: error.message, loading: false });
              return EMPTY;
            })
          )
        )
      )
    ),

    loadStats: rxMethod<string>(
      pipe(
        switchMap((uuid) =>
          service.getStats(uuid).pipe(
            tap((stats) => {
              patchState(store, {
                statsEntities: {
                  ...store.statsEntities(),
                  [uuid]: stats,
                },
              });
            }),
            catchError(() => EMPTY)
          )
        )
      )
    ),

    create: rxMethod<CreateProjectDto>(
      pipe(
        tap(() => patchState(store, { loading: true, error: null })),
        exhaustMap((dto) =>
          service.create(dto).pipe(
            tap((project) => {
              patchState(store, {
                entities: {
                  ...store.entities(),
                  [project.uuid]: project,
                },
                ids: [...store.ids(), project.uuid],
                loading: false,
              });
            }),
            catchError((error) => {
              patchState(store, { error: error.message, loading: false });
              return EMPTY;
            })
          )
        )
      )
    ),

    update: rxMethod<{ uuid: string; data: UpdateProjectDto }>(
      pipe(
        tap(() => patchState(store, { loading: true, error: null })),
        exhaustMap(({ uuid, data }) =>
          service.update(uuid, data).pipe(
            tap((project) => {
              patchState(store, {
                entities: {
                  ...store.entities(),
                  [uuid]: project,
                },
                loading: false,
              });
            }),
            catchError((error) => {
              patchState(store, { error: error.message, loading: false });
              return EMPTY;
            })
          )
        )
      )
    ),

    delete: rxMethod<string>(
      pipe(
        tap(() => patchState(store, { loading: true, error: null })),
        exhaustMap((uuid) =>
          service.delete(uuid).pipe(
            tap(() => {
              const entities = { ...store.entities() };
              const detailEntities = { ...store.detailEntities() };
              delete entities[uuid];
              delete detailEntities[uuid];
              patchState(store, {
                entities,
                detailEntities,
                ids: store.ids().filter((id) => id !== uuid),
                loading: false,
              });
            }),
            catchError((error) => {
              patchState(store, { error: error.message, loading: false });
              return EMPTY;
            })
          )
        )
      )
    ),

    setSelected: (uuid: string | null) => patchState(store, { selectedId: uuid }),
  }))
);
```

### New Store: TaskStore

**File:** `src/app/features/tasks/store/task.store.ts`

```typescript
// Similar pattern to ProjectStore, managing TaskList and Task entities
// Omitted for brevity - follow same pattern as PropertyListStore
```

### Updated Store: PropertyListStore

**File:** `src/app/features/property-lists/store/property-list.store.ts`

```typescript
// UPDATE: Remove activate() method
// UPDATE: Filter by project UUID in load method

withMethods((store, service = inject(PropertyListService)) => ({
  load: rxMethod<string | void>( // Accept optional projectUuid
    pipe(
      tap(() => patchState(store, { loading: true, error: null })),
      switchMap((projectUuid) =>
        service.getAll(projectUuid).pipe(
          tap((lists) => {
            // ... existing logic
          }),
          catchError((error) => {
            patchState(store, { error: error.message, loading: false });
            return EMPTY;
          })
        )
      )
    )
  ),

  // REMOVE: activate() method

  // ... rest of methods
}))
```

---

## Routing Updates

### Main Routes (app.routes.ts)

```typescript
export const routes: Routes = [
  {
    path: '',
    redirectTo: 'projects', // CHANGE from 'lists'
    pathMatch: 'full',
  },
  // ... auth routes unchanged

  // NEW: Projects routes
  {
    path: 'projects',
    canActivate: [authGuard],
    loadChildren: () =>
      import('./features/projects/projects.routes').then((m) => m.PROJECT_ROUTES),
  },

  // UPDATE: PropertyLists now nested under projects
  {
    path: 'projects/:projectUuid/lists',
    canActivate: [authGuard],
    loadChildren: () =>
      import('./features/property-lists/property-lists.routes').then((m) => m.PROPERTY_LIST_ROUTES),
  },

  // KEEP: Direct property access
  {
    path: 'properties/:uuid',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/property/components/property-detail/property-detail.component').then(
        (m) => m.PropertyDetailComponent
      ),
  },

  // NEW: Tasks routes
  {
    path: 'projects/:projectUuid/tasks',
    canActivate: [authGuard],
    loadChildren: () =>
      import('./features/tasks/tasks.routes').then((m) => m.TASK_ROUTES),
  },

  // ... rest unchanged
];
```

### Project Routes

**File:** `src/app/features/projects/projects.routes.ts`

```typescript
import { Routes } from '@angular/router';

export const PROJECT_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/project-list/project-list.component').then(
        (m) => m.ProjectListComponent
      ),
  },
  {
    path: 'new',
    loadComponent: () =>
      import('./components/project-create/project-create.component').then(
        (m) => m.ProjectCreateComponent
      ),
  },
  {
    path: ':uuid',
    loadComponent: () =>
      import('./components/project-detail/project-detail.component').then(
        (m) => m.ProjectDetailComponent
      ),
  },
  {
    path: ':uuid/dashboard',
    loadComponent: () =>
      import('./components/project-dashboard/project-dashboard.component').then(
        (m) => m.ProjectDashboardComponent
      ),
  },
];
```

### Updated PropertyList Routes

**File:** `src/app/features/property-lists/property-lists.routes.ts`

```typescript
// UPDATE: Paths now relative to /projects/:projectUuid/lists
export const PROPERTY_LIST_ROUTES: Routes = [
  {
    path: '',
    loadComponent: () =>
      import('./components/property-list-list/property-list-list.component').then(
        (m) => m.PropertyListListComponent
      ),
  },
  {
    path: 'new',
    loadComponent: () =>
      import('./components/property-list-create/property-list-create.component').then(
        (m) => m.PropertyListCreateComponent
      ),
  },
  {
    path: ':uuid',
    loadComponent: () =>
      import('./components/property-list-detail/property-list-detail.component').then(
        (m) => m.PropertyListDetailComponent
      ),
  },
  // REMOVE: context-options route (moved to project level)
  {
    path: ':uuid/properties/new',
    // ... existing property creation routes
  },
];
```

---

## Implementation Details

### 1. Area Validation Input Component

**File:** `src/app/shared/components/area-validation-input/area-validation-input.component.ts`

```typescript
import { Component, Input, Output, EventEmitter, OnInit, signal, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { debounceTime, Subject } from 'rxjs';
import { ValidationService } from '../../../core/services/validation-service/validation.service';
import { AreaValidationResponse } from '../../models/validation-models';

@Component({
  selector: 'app-area-validation-input',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="area-validation-input">
      <label class="block text-sm font-medium mb-1">
        Area
        <span *ngIf="required" class="text-red-500">*</span>
      </label>

      <div class="relative">
        <input
          type="text"
          [(ngModel)]="areaValue"
          (ngModelChange)="onInputChange($event)"
          [class.border-red-500]="error()"
          [class.border-green-500]="isValid()"
          class="w-full px-3 py-2 border rounded-lg focus:outline-none focus:ring-2"
          placeholder="e.g., Manchester, London, SW1A 1AA"
        />
        <div class="absolute right-3 top-2.5">
          <span *ngIf="validating()" class="loading-spinner"></span>
          <span *ngIf="isValid()" class="text-green-500">✓</span>
        </div>
      </div>

      <div *ngIf="error()" class="mt-2">
        <p class="text-red-500 text-sm">{{ error() }}</p>
        <div *ngIf="suggestions().length > 0" class="mt-2">
          <p class="text-sm text-gray-600">Did you mean:</p>
          <ul class="mt-1 space-y-1">
            <li
              *ngFor="let suggestion of suggestions()"
              (click)="selectSuggestion(suggestion)"
              class="text-sm text-blue-600 hover:underline cursor-pointer"
            >
              {{ suggestion }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  `,
})
export class AreaValidationInputComponent implements OnInit {
  @Input() value = '';
  @Input() required = false;
  @Output() valueChange = new EventEmitter<string>();
  @Output() validationChange = new EventEmitter<boolean>();

  areaValue = '';
  validating = signal(false);
  error = signal<string | null>(null);
  suggestions = signal<string[]>([]);
  isValid = signal(false);

  private inputSubject = new Subject<string>();

  constructor(private validationService: ValidationService) {
    // Debounce input
    this.inputSubject.pipe(debounceTime(500)).subscribe((value) => {
      this.validateArea(value);
    });
  }

  ngOnInit() {
    this.areaValue = this.value;
  }

  onInputChange(value: string) {
    this.valueChange.emit(value);
    this.error.set(null);
    this.suggestions.set([]);
    this.isValid.set(false);

    if (!value) {
      this.validationChange.emit(false);
      return;
    }

    this.validating.set(true);
    this.inputSubject.next(value);
  }

  validateArea(area: string) {
    this.validationService.validateArea(area).subscribe({
      next: (response: AreaValidationResponse) => {
        this.validating.set(false);
        if (response.valid) {
          this.isValid.set(true);
          this.validationChange.emit(true);
        } else {
          this.error.set(response.message || 'Invalid area');
          this.suggestions.set(response.suggestions || []);
          this.validationChange.emit(false);
        }
      },
      error: () => {
        this.validating.set(false);
        this.error.set('Unable to validate area');
        this.validationChange.emit(false);
      },
    });
  }

  selectSuggestion(suggestion: string) {
    this.areaValue = suggestion;
    this.onInputChange(suggestion);
  }
}
```

### 2. Project Create Wizard

**File:** `src/app/features/projects/components/project-create/project-create.component.ts`

```typescript
import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { ProjectStore } from '../../store/project.store';
import { Step1BasicInfoComponent } from './steps/step1-basic-info.component';
import { Step2ContextOptionsComponent } from './steps/step2-context-options.component';
import { Step3CollaborationComponent } from './steps/step3-collaboration.component';
import { ProgressIndicatorComponent } from '../../../../shared/components/progress-indicator/progress-indicator.component';
import { CreateProjectDto, CreateContextOptionsDto } from '../../../../shared/models/project-models';
import { ProjectService } from '../../../../core/services/project-service/project.service';

@Component({
  selector: 'app-project-create',
  standalone: true,
  imports: [
    CommonModule,
    ProgressIndicatorComponent,
    Step1BasicInfoComponent,
    Step2ContextOptionsComponent,
    Step3CollaborationComponent,
  ],
  template: `
    <div class="max-w-3xl mx-auto p-6">
      <h1 class="text-3xl font-bold mb-6">Create New Project</h1>

      <app-progress-indicator
        [currentStep]="currentStep()"
        [totalSteps]="3"
      ></app-progress-indicator>

      <div class="mt-8">
        <app-step1-basic-info
          *ngIf="currentStep() === 1"
          [formData]="formData()"
          [errors]="errors()"
          (next)="handleStep1Next($event)"
        ></app-step1-basic-info>

        <app-step2-context-options
          *ngIf="currentStep() === 2"
          [contextOptions]="formData().contextOptions"
          (next)="handleStep2Next($event)"
          (back)="goBack()"
          (skip)="handleSkipContextOptions()"
        ></app-step2-context-options>

        <app-step3-collaboration
          *ngIf="currentStep() === 3"
          [formData]="formData()"
          [submitting]="submitting()"
          [errors]="errors()"
          (submit)="handleSubmit($event)"
          (back)="goBack()"
        ></app-step3-collaboration>
      </div>
    </div>
  `,
})
export class ProjectCreateComponent {
  private router = inject(Router);
  private projectService = inject(ProjectService);

  currentStep = signal(1);
  formData = signal({
    title: '',
    description: '',
    contextOptions: null as CreateContextOptionsDto | null,
    viewers: [] as string[],
    contributors: [] as string[],
  });
  errors = signal<Record<string, string>>({});
  submitting = signal(false);

  handleStep1Next(data: { title: string; description: string }) {
    this.formData.update((prev) => ({ ...prev, ...data }));
    this.currentStep.set(2);
  }

  handleStep2Next(contextOptions: CreateContextOptionsDto) {
    this.formData.update((prev) => ({ ...prev, contextOptions }));
    this.currentStep.set(3);
  }

  handleSkipContextOptions() {
    this.formData.update((prev) => ({ ...prev, contextOptions: null }));
    this.currentStep.set(3);
  }

  goBack() {
    this.currentStep.update((step) => step - 1);
  }

  handleSubmit(data: { viewers: string[]; contributors: string[] }) {
    this.formData.update((prev) => ({ ...prev, ...data }));
    this.submitting.set(true);

    const projectDto: CreateProjectDto = {
      title: this.formData().title,
      description: this.formData().description,
      viewers: this.formData().viewers,
      contributors: this.formData().contributors,
    };

    this.projectService.create(projectDto).subscribe({
      next: (project) => {
        // If context options provided, set them
        if (this.formData().contextOptions) {
          this.projectService
            .setContextOptions(project.uuid, this.formData().contextOptions!)
            .subscribe({
              next: () => {
                this.router.navigate(['/projects', project.uuid]);
              },
              error: (err) => {
                console.error('Failed to set context options:', err);
                // Still navigate even if context options fail
                this.router.navigate(['/projects', project.uuid]);
              },
            });
        } else {
          this.router.navigate(['/projects', project.uuid]);
        }
      },
      error: (err) => {
        this.submitting.set(false);
        this.errors.set({ submit: err.error?.detail || 'Failed to create project' });
      },
    });
  }
}
```

### 3. PropertyList Create with Area Validation

**File:** `src/app/features/property-lists/components/property-list-create/property-list-create.component.ts`

```typescript
// UPDATE existing component

import { Component, signal, inject, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { PropertyListService } from '../../../../core/services/property-list-service/property-list.service';
import { AreaValidationInputComponent } from '../../../../shared/components/area-validation-input/area-validation-input.component';
import { SearchCriteria } from '../../../../shared/models/property-models';

@Component({
  selector: 'app-property-list-create',
  standalone: true,
  imports: [CommonModule, FormsModule, AreaValidationInputComponent],
  templateUrl: './property-list-create.component.html',
})
export class PropertyListCreateComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private propertyListService = inject(PropertyListService);

  projectUuid = '';
  areaValid = signal(false);
  submitting = signal(false);
  error = signal<string | null>(null);

  searchCriteria = signal<SearchCriteria>({
    area: '',
    radius: 5,
    property_type: 'any',
    min_price: null,
    max_price: null,
    min_bedrooms: null,
    max_bedrooms: null,
    include_sold_stc: false,
  });

  ngOnInit() {
    // Get project UUID from route
    this.projectUuid = this.route.parent?.snapshot.paramMap.get('projectUuid') || '';
  }

  onAreaChange(value: string) {
    this.searchCriteria.update((criteria) => ({ ...criteria, area: value }));
  }

  onAreaValidationChange(isValid: boolean) {
    this.areaValid.set(isValid);
  }

  onSubmit() {
    if (!this.areaValid() || this.submitting()) return;

    this.submitting.set(true);
    this.error.set(null);

    this.propertyListService
      .create({
        project: this.projectUuid,
        search_criteria: this.searchCriteria(),
        // title is auto-generated from area
      })
      .subscribe({
        next: (list) => {
          // Redirect to list detail page with loading state
          this.router.navigate(['/projects', this.projectUuid, 'lists', list.uuid]);
        },
        error: (err) => {
          this.submitting.set(false);
          this.error.set(err.error?.detail || 'Failed to create property list');
        },
      });
  }
}
```

### 4. Stage 2 Trigger with Inline Modal

**File:** `src/app/features/property-lists/components/property-list-detail/property-list-detail.component.ts`

```typescript
// UPDATE existing component to add inline modal logic

showContextOptionsModal = signal(false);

triggerStage2ForList() {
  const listData = this.list();
  if (!listData) return;

  // Check if project has context options via ProjectService
  this.projectService.getByUuid(listData.project).subscribe({
    next: (project) => {
      if (!project.context_options) {
        // Show inline modal
        this.showContextOptionsModal.set(true);
      } else {
        // Proceed with Stage 2
        this.executeStage2();
      }
    },
  });
}

executeStage2() {
  // Existing Stage 2 logic using context data service
  // ...
}

onContextOptionsSaved(contextOptions: ContextOptions) {
  this.showContextOptionsModal.set(false);
  // Reload project to get updated context options
  // Then execute Stage 2
  this.executeStage2();
}
```

---

## Testing Strategy

### Unit Tests

**Component Tests (Jasmine + Karma)**

```typescript
// area-validation-input.component.spec.ts
describe('AreaValidationInputComponent', () => {
  let component: AreaValidationInputComponent;
  let fixture: ComponentFixture<AreaValidationInputComponent>;
  let validationService: jasmine.SpyObj<ValidationService>;

  beforeEach(() => {
    const validationServiceSpy = jasmine.createSpyObj('ValidationService', ['validateArea']);

    TestBed.configureTestingModule({
      imports: [AreaValidationInputComponent],
      providers: [{ provide: ValidationService, useValue: validationServiceSpy }],
    });

    fixture = TestBed.createComponent(AreaValidationInputComponent);
    component = fixture.componentInstance;
    validationService = TestBed.inject(ValidationService) as jasmine.SpyObj<ValidationService>;
  });

  it('should validate area on input change', fakeAsync(() => {
    validationService.validateArea.and.returnValue(of({ valid: true }));

    component.onInputChange('Manchester');
    tick(500); // Debounce time

    expect(validationService.validateArea).toHaveBeenCalledWith('Manchester');
    expect(component.isValid()).toBeTrue();
  }));

  it('should show suggestions when area is invalid', fakeAsync(() => {
    validationService.validateArea.and.returnValue(
      of({
        valid: false,
        message: 'Area not found',
        suggestions: ['Manchester', 'Manchester City Centre'],
      })
    );

    component.onInputChange('Manchster');
    tick(500);

    expect(component.error()).toBe('Area not found');
    expect(component.suggestions()).toEqual(['Manchester', 'Manchester City Centre']);
  }));
});
```

**Service Tests**

```typescript
// project.service.spec.ts
describe('ProjectService', () => {
  let service: ProjectService;
  let httpMock: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [ProjectService, ApiService],
    });

    service = TestBed.inject(ProjectService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  it('should fetch all projects', () => {
    const mockProjects: Project[] = [
      { uuid: '123', title: 'Test Project', /* ... */ },
    ];

    service.getAll().subscribe((projects) => {
      expect(projects).toEqual(mockProjects);
    });

    const req = httpMock.expectOne('/api/property/projects/');
    expect(req.request.method).toBe('GET');
    req.flush(mockProjects);
  });

  it('should create project', () => {
    const createDto: CreateProjectDto = { title: 'New Project', description: '' };
    const mockProject: Project = { uuid: '456', ...createDto, /* ... */ };

    service.create(createDto).subscribe((project) => {
      expect(project.uuid).toBe('456');
    });

    const req = httpMock.expectOne('/api/property/projects/');
    expect(req.request.method).toBe('POST');
    req.flush(mockProject);
  });
});
```

### Integration Tests (E2E with Cypress/Playwright)

```typescript
// project-creation.e2e.spec.ts
describe('Project Creation Flow', () => {
  it('should create project with all steps', () => {
    cy.visit('/projects/new');

    // Step 1
    cy.get('input[name="title"]').type('House Hunting 2026');
    cy.get('textarea[name="description"]').type('Looking for family home');
    cy.contains('Next').click();

    // Step 2 - skip
    cy.contains('Skip').click();

    // Step 3
    cy.get('[data-testid="viewers-select"]').click();
    cy.contains('john@example.com').click();
    cy.contains('Create Project').click();

    // Should redirect
    cy.url().should('include', '/projects/');
    cy.contains('House Hunting 2026');
  });
});
```

---

## Implementation Sequence

### Week 1: Models, Services, Stores

**Day 1: Models & Services**
- [ ] Create project-models.ts, task-models.ts, validation-models.ts
- [ ] Update property-list-models.ts
- [ ] Create ProjectService, TaskService, ValidationService
- [ ] Update PropertyListService (remove activate, add project filter)
- [ ] Write service unit tests

**Day 2: Stores**
- [ ] Create ProjectStore
- [ ] Create TaskStore (optional, lower priority)
- [ ] Update PropertyListStore (remove activate)
- [ ] Write store tests

**Day 3: Routing**
- [ ] Update app.routes.ts
- [ ] Create projects.routes.ts
- [ ] Create tasks.routes.ts (optional)
- [ ] Update property-lists.routes.ts (make relative to project)

---

### Week 2: Core Project Components

**Day 4: Project List & Card**
- [ ] Create ProjectListComponent
- [ ] Create ProjectCardComponent
- [ ] Wire up ProjectStore
- [ ] Test navigation

**Day 5: Project Create Wizard**
- [ ] Create ProjectCreateComponent
- [ ] Create Step1BasicInfoComponent
- [ ] Create Step2ContextOptionsComponent
- [ ] Create Step3CollaborationComponent
- [ ] Create ProgressIndicatorComponent
- [ ] Test wizard flow

**Day 6: Project Detail**
- [ ] Create ProjectDetailComponent
- [ ] Create ProjectStatsPanelComponent
- [ ] Create ProjectListGridComponent
- [ ] Test data fetching and display

---

### Week 3: PropertyList Updates

**Day 7: Area Validation**
- [ ] Create AreaValidationInputComponent
- [ ] Wire up ValidationService
- [ ] Test validation flow

**Day 8: PropertyList Create Update**
- [ ] Update PropertyListCreateComponent with area validation
- [ ] Update to use projectUuid from route
- [ ] Remove collaboration fields
- [ ] Test creation flow

**Day 9: PropertyList Detail Update**
- [ ] Update PropertyListDetailComponent
- [ ] Add inline context options modal trigger
- [ ] Update Stage 2/3 logic to check project-level config
- [ ] Test Stage 2/3 triggers

---

### Week 4: Dashboard & Polish

**Day 10: Project Dashboard**
- [ ] Create ProjectDashboardComponent
- [ ] Implement stats display
- [ ] Add charts (basic - defer complex charts if needed)
- [ ] Test stats API integration

**Day 11: Context Options Modal**
- [ ] Create InlineModalComponent
- [ ] Wire up context options form for inline use
- [ ] Test modal flow

**Day 12: Testing & Bug Fixes**
- [ ] Write unit tests for all new components
- [ ] Write E2E tests for key flows
- [ ] Fix bugs
- [ ] Cross-browser test
- [ ] Performance check

---

## Checklist Summary

### Pre-Implementation
- [ ] Backend API endpoints ready
- [ ] Models defined and exported
- [ ] Services created
- [ ] Stores created

### During Implementation
- [ ] All components standalone
- [ ] Signals used for reactive state
- [ ] TypeScript strict mode compliance
- [ ] TailwindCSS classes used consistently
- [ ] Error boundaries/handling implemented
- [ ] Loading states handled

### Post-Implementation
- [ ] Unit test coverage > 80%
- [ ] E2E tests for critical flows passing
- [ ] No console errors
- [ ] Responsive design verified
- [ ] Accessibility checked
- [ ] Documentation updated

---

## Success Criteria

### Functional
- ✅ Create projects with 3-step wizard
- ✅ Context options at project level
- ✅ PropertyList creation with area validation and auto-scraping
- ✅ Inline modals for missing config
- ✅ Project dashboard with stats
- ✅ Project-scoped navigation

### Non-Functional
- ✅ Page load < 3s
- ✅ Forms validate before submit
- ✅ Clear error messages
- ✅ Responsive design
- ✅ Accessible (keyboard, screen readers)

---

**END OF SPEC**
