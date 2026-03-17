# Activity Diagram

This diagram shows the main activity flow of the automated SRS generator system.

```mermaid
flowchart TD
    Start([User Initiates SRS Generation]) --> UploadDocs[Upload Documents]
    UploadDocs --> ProcessDocs[Process Documents]
    ProcessDocs --> VectorStore[Store in Vector Database]
    VectorStore --> ExtractInfo[Extract Information]
    ExtractInfo --> GenerateReqs[Generate Requirements]
    GenerateReqs --> ValidateMermaid[Validate with Mermaid]
    ValidateMermaid --> Decision{Validation Passed?}
    Decision -->|No| Refine[Refine Requirements]
    Refine --> GenerateReqs
    Decision -->|Yes| GenerateSRS[Generate SRS Document]
    GenerateSRS --> ReturnSRS[Return SRS to User]
    ReturnSRS --> End([Process Complete])
```

## Process Description

1. **User Initiates SRS Generation** - User starts the process through the frontend
2. **Upload Documents** - User uploads seed documents (GDPR, HIPAA, etc.)
3. **Process Documents** - Backend processes uploaded documents
4. **Store in Vector Database** - Documents are embedded and stored in vector store
5. **Extract Information** - Graph nodes extract relevant information
6. **Generate Requirements** - Requirements are generated based on extracted info
7. **Validate with Mermaid** - Generated requirements are validated
8. **Validation Check** - If validation fails, refine requirements; otherwise continue
9. **Generate SRS Document** - Final SRS document is assembled
10. **Return SRS to User** - Document is returned to the user
