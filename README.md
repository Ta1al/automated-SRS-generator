# AI-Powered Automated SRS Generator

![Status](https://img.shields.io/badge/Status-Under%20Development-yellow)

## Abstract

Many software projects fail due to vague or incomplete requirements given by non-technical clients. Writing a Software Requirement Specification (SRS) requires expertise, which many clients and small teams lack.

Our proposed solution is an **AI-powered Automated SRS Generator**. Through a chat interface, clients can describe their project idea in plain English. The system uses NLP and AI to:

- Ask clarifying questions
- Suggest missing requirements
- Generate a complete **IEEE 830-compliant SRS**
- Produce **UML diagrams** (use-case, class, sequence)
- Provide basic **wireframes** of the system

This will save time, reduce miscommunication, and make requirement engineering accessible to non-technical stakeholders.

## Justification

Traditionally, System Analysts or Requirements Engineers gather client requirements and write the SRS with supporting diagrams. However, this is time-consuming, costly, and prone to human error.

Recent tools like Almware, Reqi's "Rex," and Blueprint.AI show early attempts to automate requirement documentation, but they lack interactive clarification, missing requirement suggestions, and visual model generation. Our project combines all these aspects into one assistant.

This project bridges the gap between clients and developers by acting like a junior Requirements Engineer. It adds academic value (NLP, AI, automation) and industrial value (time and cost savings in requirement engineering).

## Objectives

- Develop a **chat-based interface** where clients describe requirements
- Implement **AI-driven clarification** (chatbot asks follow-up questions)
- Add a **knowledge base/ML model** to suggest missing requirements
- Generate **IEEE 830-compliant SRS** documents
- Automatically create **UML diagrams** (use-case, class, sequence)
- Optionally generate basic **UI wireframes**
- Ensure usability, scalability, and security of the platform

## Project Scope

### In Scope
- Interactive AI-based requirement gathering
- Automated SRS generation (IEEE 830)
- UML diagrams (use-case, class, sequence)
- Wireframe prototypes
- Exportable reports (PDF/DOCX)

### Out of Scope
- Full system implementation for client projects
- Advanced UI/UX prototyping beyond basic wireframes
- Domain-specific deep knowledge bases (initially general best practices only)

## Tools and Technologies

- **Frontend:** React + Tailwind CSS (chat interface, diagram display)
- **Backend:** Python (Flask/FastAPI)
- **AI/NLP:** Hugging Face Transformers, spaCy, OpenAI API or open-source model
- **Database:** MongoDB Atlas
- **Diagram Generation:** PlantUML / Mermaid.js
- **Wireframes:** Mermaid wireframes
- **Deployment:** Docker + Cloud (AWS/Heroku/Vercel)
- **Collaboration:** GitHub, CI/CD pipelines

## Potential Impact

- **Academic:** Demonstrates AI + NLP in requirements engineering, publishable research
- **Industrial:** Saves time, reduces cost of hiring analysts, improves project success rate
- **Social:** Makes software development accessible for non-technical founders/startups

## Documentation

For detailed project specifications, please refer to the files in the `documentation/` folder:
- [FYP Proposal](documentation/FYP%20Proposal.pdf)
- [Software Requirements Specifications](documentation/Software%20Requirements%20Specifications.pdf)

## License

This project is part of a Final Year Project.

---

**Submission Date:** October 2025
