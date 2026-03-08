# AFG Estimate Analyser Architecture

This document describes the end-to-end architecture of the **AFG Estimate Analyser** system, detailing how components interact from UI upload down to the sandboxed agent validation.

## End-to-End Workflow Diagram

```mermaid
graph TD
    %% Define Styles
    classDef frontend fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef backend fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef worker fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff;
    classDef db fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;
    classDef storage fill:#64748b,stroke:#334155,stroke-width:2px,color:#fff;
    classDef ai fill:#ec4899,stroke:#be185d,stroke-width:2px,color:#fff;

    %% Client Layer
    subgraph Client ["Client Layer"]
        UI["Frontend UI (React/Node)"]:::frontend
    end

    %% API Layer
    subgraph API ["API & Orchestration Layer"]
        FastAPI["Backend API (FastAPI) <br> Port 2357"]:::backend
        RedisBroker[("Redis Broker & Result Backend <br> Port 6379")]:::db
    end

    %% Extraction Layer
    subgraph Extraction ["Extraction Service Layer"]
        ExtractorAPI["Extraction Service (FastAPI) <br> Port 1204"]:::worker
        AsposeEngine["Aspose.Cells Engine <br> (HTML Conversion)"]:::worker
        FileSys[("File System <br> Isolated /fl_task_id/")]:::storage
        Parser["HTML Parsers & ROI Engine <br> (BeautifulSoup)"]:::worker
    end

    %% Agent Layer
    subgraph MSAF ["Microsoft Agent Framework (MSAF)"]
        CeleryWorker["Celery Worker <br> (Task Orchestrator)"]:::worker
        AgentOrchestrator["Agent Orchestrator <br> (LLM Prompting)"]:::ai
        AzureOpenAI(("Azure OpenAI <br> (LLM Engine)")):::ai
        ToolRegistry["Tool Registry <br> (get_available_rules, run_rule_validation)"]:::worker
        Sandbox["Sandbox Executor <br> (Subprocess Validation Environment)"]:::worker
    end

    %% Database Layer
    subgraph Database ["SQL Server Database"]
        MainDB[("SQL Server")]:::db
        ConfigView["vr.vw_consolidated_validation_config <br> (Rule Settings)"]:::db
        ExtSchema["Dynamic Schema <br> [ext_task_id].[tables]"]:::db
    end

    %% Relationships & Flow
    UI -- "1. Uploads TCO Excel" --> FastAPI
    UI -- "9. Listens (SSE) to Traceability Log" --> RedisBroker
    
    FastAPI -- "2. Routes Task & File Paths" --> RedisBroker
    RedisBroker -- "3. Picks up job" --> CeleryWorker
    
    CeleryWorker -- "4. Triggers Extraction" --> ExtractorAPI
    ExtractorAPI -- "Loads Workbook" --> AsposeEngine
    AsposeEngine -- "Saves HTML" --> FileSys
    ExtractorAPI -- "Extracts Tables" --> Parser
    Parser -- "Creates Schema & Tables" --> ExtSchema
    
    CeleryWorker -- "5. Init Super Agent" --> AgentOrchestrator
    AgentOrchestrator -- "6. Request Rules by Mode" --> ToolRegistry
    ToolRegistry -- "Queries matching rules" --> ConfigView
    ToolRegistry -- "Returns Rules JSON" --> AgentOrchestrator
    
    AgentOrchestrator -- "7. Determines which rules to run" --> AzureOpenAI
    AzureOpenAI -- "Executes run_rule_validation" --> ToolRegistry
    ToolRegistry -- "8. Injects Schema & Spawns" --> Sandbox
    Sandbox -- "Reads injected DataFrame" --> ExtSchema
    
    Sandbox -- "Returns Pass/Fail & Output" --> ToolRegistry
    ToolRegistry -- "Summarizes Results" --> AgentOrchestrator
    AgentOrchestrator -- "10. Final Report" --> CeleryWorker
    CeleryWorker -- "Posts Result" --> RedisBroker
    FastAPI -- "Fetches Final Result" --> RedisBroker
```

## Component Breakdown

1. **Frontend UI**: User interface to upload TCO Excel sheets and monitor real-time server-side events (SSE).
2. **Backend API**: The primary entry gateway that intercepts uploads, saves them temporarily, and delegates work to the asynchronous Celery queue.
3. **Redis Broker**: Acts as the message broker for Celery queues (`get_task_queue`), the state backend for results (`result_queue`), and the PubSub engine for real-time frontend logs (`tracebility_queue`).
4. **Extraction Service**: Dedicated process utilizing `Aspose.Cells` to map Excel sheets to precise HTML representations. It enforces strict isolation:
   - **File System**: `data/html_out/fl_<task_id>`
   - **Database**: `[ext_<task_id>]` Schema
5. **MSAF Celery Worker**: Handles asynchronous task loads. Initiates extraction, then spins up the Azure OpenAI Agent.
6. **Agent Orchestrator**: Uses Azure OpenAI (`gpt-4.1`). It leverages tools to actively fetch rules based on the detected layout (Waterfall/Agile) and loop through them sequentially.
7. **Sandbox Executor**: For extreme security and stability, the Agent does not run rule functions in its own thread. Instead, it spawns an isolated python `subprocess`. This sandbox contains SQL-intercept engines to ensure legacy raw SQL strings automatically bind to the correct isolated `[ext_<task_id>]` schema before utilizing the `pandas` analytic library. 
8. **SQL Server Database**: The central truth that holds configuration data (`vw_consolidated_validation_config`) and all dynamic extracted task grid states.
