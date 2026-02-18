# Data Flow Diagrams (DFD)

- Context Diagram (Level 0)
- Level 1 - high-level functional decomposition
- Level 2 - detailed decomposition of the "Create SRS" process

---

## Context Diagram (Level 0)

```mermaid
flowchart LR
	%% External entities
	User([User])
	LLM([External LLM Service])

	%% System boundary
	subgraph System [Automated SRS Generator]
		SystemCore((System))
		Database[(Project DB / Storage)]
	end

	%% Data flows
	User -->|create project / enter requirements| SystemCore
	SystemCore -->|store projects & reqs| Database
	SystemCore -->|send prompt / request generation| LLM
	LLM -->|generated content | SystemCore
	SystemCore -->|deliver SRS | User
```

---

## Level 1 - High-level processes

```mermaid
flowchart LR
	User([User])
	LLM([External LLM Service])
	DB[(Project DB)]

	subgraph System [Automated SRS Generator]
		P1["P1: Manage Projects & Requirements"]
		P2["P2: Create SRS"]
		P3["P3: Generate Diagrams"]
		P4["P4: Export & Deliver"]
		Store[(Intermediate storage: Drafts)]
	end

	User -->|create / update project| P1
	P1 -->|requirements| Store
	P1 -->|save| DB

	P2 -->|fetch reqs| Store
	P2 -->|prompt| LLM
	LLM -->|responses| P2
	P2 -->|draft SRS| Store

	P3 -->|diagram source| P2
	P3 -->|rendered diagrams| Store

	P4 -->|collect drafts| Store
	P4 -->|final files| User
	P4 -->|archive| DB

	%% Useful flows
	P2 -->|requests diagram| P3
	P3 -->|diagram artifacts| P2
```

---

## Level 2 - Decompose P2: Create SRS (detailed)

```mermaid
flowchart TD
	User([User])
	LLM([External LLM Service])
	DB[(Project DB / Archive)]

	subgraph P2 [P2: Create SRS]
		P2_1["P2.1: Collect Requirements & Metadata"]
		P2_2["P2.2: Interactive Conversation (LLM)"]
		P2_3["P2.3: Assemble & Format Document"]
		P2_4["P2.4: Review, Validate & Finalize"]
		Drafts[(Draft storage)]
	end

	User -->|submit/confirm reqs| P2_1
	P2_1 -->|requirements + context| P2_2

	P2_2 -->|prompts| LLM
	LLM -->|text responses| P2_2
	P2_2 -->|content fragments| Drafts

	P2_3 -->|pull fragments| Drafts
	P2_3 -->|assemble doc| Drafts
	P2_3 -->|request diagrams| P3["P3: Generate Diagrams"]
	P3 -->|diagrams| P2_3

	P2_4 -->|present draft to user| User
	User -->|feedback / edits| P2_2
	P2_4 -->|finalize| DB
	P2_4 -->|export| P4["P4: Export & Deliver"]
```


