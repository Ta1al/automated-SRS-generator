# Sequence Diagram

Sequence diagram of the Functional Requirement 4 (FR4) process.

```mermaid
sequenceDiagram
    title FR-4: SRS Document Generation (with FR-5 & FR-5a)

    actor User
    participant UI as WebApp / UI
    participant SRS as SRS Generator Service
    participant Analyzer as Requirement Analyzer\n(FR-5)
    participant Diagrams as Diagram Generator\n(FR-5a)
    participant Template as Template Engine\n(IEEE 830 Composer)
    participant Storage as Document Storage

    %% Request SRS generation
    User->>UI: Provide project info & raw requirements
    User->>UI: Click "Generate SRS"
    UI->>SRS: submitSRSRequest(projectData, rawRequirements)
    activate SRS

    %% Extract & categorize requirements (FR-5)
    SRS->>Analyzer: analyzeRequirements(rawRequirements)
    activate Analyzer
    Analyzer-->>Analyzer: NLP parsing & extraction
    Analyzer-->>Analyzer: Classify FR vs NFR\n+ group NFRs (performance, security, etc.)
    Analyzer-->>SRS: categorizedRequirements
    deactivate Analyzer

    %% Generate diagrams (FR-5a)
    SRS->>Diagrams: generateSystemDiagrams(categorizedRequirements, systemContext)
    activate Diagrams
    Diagrams-->>Diagrams: Derive system structure\n(use cases, flows, context)
    Diagrams-->>SRS: diagramDefinitions\n(PlantUML/Mermaid.js)
    deactivate Diagrams

    %% Assemble IEEE 830-compliant SRS (FR-4)
    SRS->>Template: buildSRS(projectData,\n categorizedRequirements,\n diagramDefinitions)
    activate Template
    Template-->>Template: Populate IEEE 830 sections:\nIntroduction, System Description,\nInterfaces, FRs, NFRs,\nDiagrams, Wireframes, References
    Template-->>SRS: srsDocument
    deactivate Template

    %% Store and deliver document
    SRS->>Storage: saveSRS(srsDocument)
    Storage-->>SRS: storageLocation / documentId

    SRS-->>UI: SRSGenerationResult(linkToSRS, status=success)
    deactivate SRS

    UI-->>User: Show success & SRS download/view link
```