
```mermaid
flowchart TD
    Start([Start]) --> CreatePropertyComponent_CreationOptions["CreatePropertyComponent<br/>(Creation Options Page)"]

    CreatePropertyComponent_CreationOptions --> CreationDecision{Creation option?}

    CreationDecision -->|Manual| PropertyCreationFormComponent["PropertyCreationFormComponent"]
    PropertyCreationFormComponent --> CreatePropertyEndpoint["create_property_endpoint"]

    CreationDecision -->|From URL or Text| CreatePropertyComponent_LoadInputField["CreatePropertyComponent<br/>(Load URL or Text Input Field)"]
    CreatePropertyComponent_LoadInputField --> CreateFromInputEndpoint["create_from_input_endpoint"]

    CreateFromInputEndpoint --> PropertyCreationServiceFactory["property_creation_service_factory"]
    PropertyCreationServiceFactory --> RightmoveService["rightmove_service"]

    RightmoveService --> PropertyCreationRequest["PropertyCreationRequest"]
    PropertyCreationRequest --> PropertyCreationFormComponent

CreateFromInputEndpoint -.-> NoteCreateFromInputEndpoint["2 endpoints create_from_url and create_from_text"]
    PropertyCreationServiceFactory -.-> NoteFactory["Discerns which IPropertyCreationService to use<br/>(RightMoveService, HTMLParserService, etc.)"]
    RightmoveService -.-> NoteRightmove["For this example using Rightmove service to create from url input Scrapes webpage and creates PropertyCreationRequest"]


```

## Implementation Roadmap

### Phase 1: Core Backend Infrastructure
- [x] Property model updates (ensure external_url field exists)
- [x] PropertyCreationRequest schema (unsaved Property model structure)
- [x] create_property_endpoint (manual creation, should already exist)
- [x] Error handling patterns
- [x] Validation layer

### Phase 2: Service Layer
- [x] IPropertyCreationService interface
- [x] property_creation_service_factory
- [x] RightmoveService implementation
  - [x] URL scraping logic
  - [x] Data extraction to PropertyCreationRequest
- [ ] HTMLParserService (future)
- [x] Service selection logic in factory

### Phase 3: Input Endpoints
- [x] create_from_input_endpoint (single endpoint with parameter)
  - [x] URL input handling
  - [x] Text input handling
- [x] Service factory integration
- [x] Response structure (unsaved Property model)

### Phase 4: Frontend Components
- [ ] CreatePropertyComponent (creation options page)
- [ ] PropertyCreationFormComponent
- [ ] URL/Text input field UI
- [ ] Form population from PropertyCreationRequest
- [ ] Submit flow

### Phase 5: Integration & Testing
- [ ] End-to-end flow testing
- [ ] Error handling paths
- [ ] Auth/authorization integration
- [ ] Unit tests for services
- [ ] API endpoint tests
