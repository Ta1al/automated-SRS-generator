# Data Flow Diagrams

## DFD Level 0 - System Context

```mermaid
graph LR
    User((User)) -->|Upload Docs & Query| System["Automated SRS Generator"]
    System -->|Returns SRS Document| User
    User -->|View/Manage| Frontend["Web Frontend"]
    Frontend -->|API Requests| System
```

## DFD Level 1 - Main Processes

```mermaid
graph TD
    User((User))
    DB[(Database)]
    VectorDB[(Vector Store)]
    
    User -->|Documents & Query| Input["1.0 Document Input"]
    Input -->|Processed Docs| Processing["2.0 Processing & Extraction"]
    Processing -->|Embeddings| VectorDB
    Processing -->|Extracted Data| Graph["3.0 Graph Processing"]
    Graph -->|Requirements| Validation["4.0 Validation"]
    Validation -->|Valid Data| Generation["5.0 SRS Generation"]
    Generation -->|Chat History| DB
    Generation -->|SRS Document| Output["6.0 Output Delivery"]
    Output -->|Return SRS| User
```

## DFD Level 2 - Detailed Processing

```mermaid
graph TD
    subgraph Frontend
        UI["User Interface<br/>Chat Workspace"]
    end
    
    subgraph Backend["Backend API"]
        Auth["Authentication<br/>Service"]
        Chat["Chat<br/>Service"]
    end
    
    subgraph RAG["RAG Pipeline"]
        Vectorize["Vectorization<br/>with Embeddings"]
        Search["Similarity<br/>Search"]
    end
    
    subgraph Graph["Graph Execution"]
        Nodes["Graph Nodes<br/>Processing"]
        LLM["LLM<br/>Integration"]
    end
    
    subgraph Validation["Validation"]
        Mermaid["Mermaid<br/>Validator"]
        DataCheck["Data<br/>Validation"]
    end
    
    subgraph Storage
        UserDB[(User DB)]
        ChatDB[(Chat DB)]
        VectorDB[(Vector Store)]
    end
    
    UI -->|Authenticate| Auth
    UI -->|Create Chat| Chat
    Chat -->|Store| ChatDB
    Chat -->|Send Query| Vectorize
    Vectorize -->|Store Embeddings| VectorDB
    Vectorize -->|Search| Search
    Search -->|Retrieved Docs| Nodes
    Nodes -->|Process| LLM
    LLM -->|Generated Content| Mermaid
    Mermaid -->|Validate| DataCheck
    DataCheck -->|Store Results| ChatDB
    DataCheck -->|Return SRS| UI
```
