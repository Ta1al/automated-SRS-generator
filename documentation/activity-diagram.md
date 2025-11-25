# Activity Diagram

Activity diagram of the Functional Requirement 4 (FR4) process.

```mermaid
flowchart TD
    %% FR-4: SRS Document Generation - Activity Diagram

    A[Start] --> B[User provides project info and raw requirements]
    B --> C[User clicks 'Generate SRS']

    C --> D[Validate input project info and requirements]
    D --> E{Input valid?}

    E -- No --> F[Show validation errors to user]
    F --> G[End failure]

    E -- Yes --> H[Analyze requirements NLP extraction and parsing]
    H --> I[Categorize requirements FR vs NFR, group NFRs by performance/security/etc.]

    I --> J[Derive system structure context, use cases, flows]
    J --> K[Generate system diagrams PlantUML / Mermaid.js]
    K --> L{Diagrams generated?}

    L -- No --> M[Log diagram generation error]
    M --> N[Mark diagrams section as partial/empty in SRS]
    N --> O[Compose IEEE 830-compliant SRS all required sections]

    L -- Yes --> P[Attach generated diagrams to SRS content]
    P --> O[Compose IEEE 830-compliant SRS all required sections]

    O --> Q[Save SRS document to storage]
    Q --> R{Storage successful?}

    R -- No --> S[Show generation/storage error to user]
    S --> T[End failure]

    R -- Yes --> U[Return SRS download/view link to user]
    U --> V[User views/downloads SRS document]
    V --> W[End success]
```