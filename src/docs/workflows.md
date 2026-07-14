# Agent Workflows

How the 9 rvtdocs-mcp-py tools compose into multi-step agent workflows for Revit API development.

## Workflow 1 — Code Generation (Most Common)

Agent looks up related APIs before writing Revit code.

**Tools used:** `rvtdocs_batch` → (agent writes code) → `rvtdocs_fetch` (if error)

```mermaid
sequenceDiagram
    participant User
    participant Agent
    participant RVTDocs as rvtdocs-mcp-py

    User->>Agent: "Implement ExtensibleStorage for rooms"

    Note over Agent: Step 1 — Batch lookup related APIs
    Agent->>RVTDocs: rvtdocs_batch(["ExtensibleStorage",<br/>"SchemaBuilder", "Entity", "FilteredElementCollector"],<br/>year="2025", mode="trust")
    RVTDocs-->>Agent: 4 results, ~4,000 tokens, ~2s

    Note over Agent: Step 2 — Agent writes code using API metadata
    Agent->>Agent: Generate C# code based on<br/>confidence, sectionsFound, deprecation

    alt Needs more detail on a specific API
        Note over Agent: Step 3 — Targeted full fetch
        Agent->>RVTDocs: rvtdocs_fetch("SchemaBuilder",<br/>year="2025", mode="full")
        RVTDocs-->>Agent: Full API docs with params,<br/>~2,500 tokens
    end

    Agent->>User: "Here's the implementation..."
```

**Token budget:**

| Step | Tool | Tokens (output) |
|------|------|-----------------|
| 1 | `rvtdocs_batch` (4 queries, trust) | ~4,000 |
| 2 | Agent reasoning | 0 |
| 3 | `rvtdocs_fetch` (full, if needed) | ~2,500 |
| **Total (trust only)** | | **~4,000** |
| **Total (with 1 full fetch)** | | **~6,500** |

---

## Workflow 2 — Validate-First (Most Token-Efficient)

Agent validates API existence before committing to code. Best for uncertain or complex tasks.

**Tools used:** `rvtdocs_scan` (multiple) → `rvtdocs_fetch` (selective)

```mermaid
sequenceDiagram
    participant Agent
    participant RVTDocs as rvtdocs-mcp-py

    Note over Agent: Step 1 — Scan 10 APIs (~300 tok each)
    Agent->>RVTDocs: rvtdocs_scan("Schema.Lookup")
    Agent->>RVTDocs: rvtdocs_scan("Entity.Get")
    Agent->>RVTDocs: rvtdocs_scan("Wall.Create")
    Agent->>RVTDocs: rvtdocs_scan("... 7 more")
    RVTDocs-->>Agent: 7 pass, 2 warn, 1 fail

    Note over Agent: Step 2 — Full fetch only for warnings
    Agent->>RVTDocs: rvtdocs_fetch(warn_api_1, mode="full")
    Agent->>RVTDocs: rvtdocs_fetch(warn_api_2, mode="full")
    RVTDocs-->>Agent: Detailed API docs

    Note over Agent: Step 3 — Use suggestions to fix failed query
    Agent->>Agent: Read suggestions from scan failure<br/>→ Fix query
    Agent->>RVTDocs: rvtdocs_scan(fixed_query)
    RVTDocs-->>Agent: pass ✓

    Note over Agent: Step 4 — Write code with confidence
    Agent->>Agent: Generate code for all 10 APIs
```

**Token budget:**

| Step | Tool | Tokens |
|------|------|--------|
| 1 | 10x `rvtdocs_scan` | ~3,000 |
| 2 | 2x `rvtdocs_fetch` (full) | ~5,000 |
| 3 | 1x `rvtdocs_scan` (retry) | ~300 |
| **Total** | | **~8,300** |
| **vs 10x full fetch** | | ~25,000 |
| **Savings** | | **67%** |

---

## Workflow 3 — API Migration (Cross-Version)

Agent compares API surfaces across Revit versions to detect breaking changes.

**Tools used:** `rvtdocs_batch` (year A) → `rvtdocs_batch` (year B) → diff

```mermaid
sequenceDiagram
    participant Agent
    participant RVTDocs as rvtdocs-mcp-py

    Note over Agent: Step 1 — Fetch APIs for source version
    Agent->>RVTDocs: rvtdocs_batch(<br/>["Wall.Create", "Floor.Create",<br/>"View3D.CreateIsometric", "Document.SaveAs"],<br/>year="2022", mode="full")
    RVTDocs-->>Agent: 4 results with signatures

    Note over Agent: Step 2 — Fetch APIs for target version
    Agent->>RVTDocs: rvtdocs_batch(<br/>["Wall.Create", "Floor.Create",<br/>"View3D.CreateIsometric", "Document.SaveAs"],<br/>year="2025", mode="full")
    RVTDocs-->>Agent: 4 results + deprecation warnings

    Note over Agent: Step 3 — Compare
    Agent->>Agent: Diff signatures,<br/>check deprecation flags,<br/>identify namespace changes

    Agent->>Agent: "Wall.Create — params changed,<br/>Floor.Create — deprecated → use Floor.Create(Document, ...)"
```

**Token budget:**

| Step | Tool | Tokens |
|------|------|--------|
| 1 | `rvtdocs_batch` (4 queries, full, 2022) | ~10,000 |
| 2 | `rvtdocs_batch` (4 queries, full, 2025) | ~10,000 |
| 3 | Agent reasoning | 0 |
| **Total** | | **~20,000** |

---

## Workflow 4 — Debug & Diagnostics

Agent encounters unexpected behavior. Uses debug tools to investigate routing and extraction.

**Tools used:** `rvtdocs_debug` → `rvtdocs_stats` → `rvtdocs_fetch` (corrected)

```mermaid
sequenceDiagram
    participant Agent
    participant RVTDocs as rvtdocs-mcp-py

    Note over Agent: API query returned wrong result
    Agent->>RVTDocs: rvtdocs_debug("View3D.CreateIsometric", year="2025")
    RVTDocs-->>Agent: Full diagnostic trace:<br/>- inputQuery, canonicalQuery<br/>- resolution (kind, className, path)<br/>- semantic (confidence, evidence)<br/>- snippet content

    Note over Agent: Analyze diagnostic output
    Agent->>Agent: "Resolution used DB namespace ✓<br/>Confidence 0.85 ✓<br/>Issue is in extraction, not routing"

    Note over Agent: Check overall server health
    Agent->>RVTDocs: rvtdocs_stats(hours=24)
    RVTDocs-->>Agent: {successRate: 0.87,<br/>cacheHitRate: 0.65,<br/>topFailures: [...]}

    Note over Agent: Retry with fully qualified name
    Agent->>RVTDocs: rvtdocs_fetch(<br/>"Autodesk.Revit.DB.View3D.CreateIsometric",<br/>mode="full")
    RVTDocs-->>Agent: Correct result with full snippet
```

---

## Workflow 5 — Session Memory (Long Multi-Step Tasks)

Agent uses session store to remember earlier lookups across a multi-step task.

**Tools used:** `rvtdocs_fetch` → `rvtdocs_session_set` → (other work) → `rvtdocs_session_get`

```mermaid
sequenceDiagram
    participant Agent
    participant RVTDocs as rvtdocs-mcp-py

    Note over Agent: Step 1 — Look up SchemaBuilder
    Agent->>RVTDocs: rvtdocs_fetch("SchemaBuilder",<br/>year="2025", mode="full")
    RVTDocs-->>Agent: Full docs (~2,500 tokens)

    Note over Agent: Step 2 — Save key findings
    Agent->>RVTDocs: rvtdocs_session_set("schema_api",<br/>"SchemaBuilder: needs Guid, AccessLevel,<br/>SchemaName. Use Field for each property.")
    RVTDocs-->>Agent: { stored: true }

    Note over Agent: Steps 3-7 — Agent works on other parts...

    Note over Agent: Step 8 — Recall without re-fetching
    Agent->>RVTDocs: rvtdocs_session_get("schema_api")
    RVTDocs-->>Agent: { value: "SchemaBuilder: needs Guid..." }<br/>~100 tokens (vs re-fetch ~2,500)
```

**Token savings:** Session recall costs ~100 tokens vs re-fetch at ~2,500 tokens = **96% savings**.

---

## Workflow Selection Guide

```mermaid
flowchart TD
    START["Agent needs Revit API info"] --> Q1{How many APIs?}

    Q1 -- "1 API" --> Q2{Need docs content?}
    Q1 -- "2-10 APIs" --> BATCH["rvtdocs_batch<br/>1 call, ~2s"]
    Q1 -- "Just validate" --> SCAN["rvtdocs_scan<br/>~300 tokens"]

    Q2 -- "No, just check existence" --> SCAN
    Q2 -- "Yes, confident in query" --> TRUST["rvtdocs_fetch(mode='trust')<br/>~800 tokens"]
    Q2 -- "Yes, need full docs" --> FULL["rvtdocs_fetch(mode='full')<br/>~2,500 tokens"]
    Q2 -- "Debug routing issue" --> DEBUG["rvtdocs_debug<br/>~4,000 tokens"]

    BATCH --> MODE{Mode?}
    MODE -- "Validate only" --> BT["batch(mode='trust')<br/>~4K tokens / 4 queries"]
    MODE -- "Read full docs" --> BF["batch(mode='full')<br/>~10K tokens / 4 queries"]

    SCAN --> RESULT{Result?}
    RESULT -- "pass" --> CODE["Write code directly"]
    RESULT -- "warn" --> FULL
    RESULT -- "fail" --> SUGGEST["Read suggestions → fix query"]
    SUGGEST --> SCAN2["rvtdocs_scan(fixed)"]
```

## Token Budget Summary

| Workflow | Total Tokens | Tool Calls | Best For |
|----------|-------------|------------|----------|
| Code Generation (batch trust) | ~4,000 | 1 | Known APIs, code writing |
| Code Generation (with full fetch) | ~6,500 | 2 | Need param details |
| Validate-First (10 APIs) | ~8,300 | 13 | Uncertain APIs, complex tasks |
| API Migration (4 APIs × 2 years) | ~20,000 | 2 | Cross-version comparison |
| Session Memory | ~100 recall | 1 | Multi-step, avoid re-fetch |
| Debug Routing | ~4,000 | 1 | Wrong namespace / low confidence |
