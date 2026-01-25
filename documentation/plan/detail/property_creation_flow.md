
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
