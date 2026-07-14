# Architecture

Internal architecture of `rvtdocs-mcp-py`, organized into five layers.

## Layer Diagram

```mermaid
graph TB
    subgraph "AI Agent (Cursor / Claude)"
        A[Tool Call<br/>rvtdocs_fetch / scan / batch / debug]
    end

    subgraph "Layer 1 — Routing"
        B1[canonicalize_query]
        B2[resolve_query]
        B3[NamespaceIndex<br/>2448 classes]
        B4[EXACT_CLASS_NAMESPACE_HINTS<br/>85 overrides]
        B5[normalize_year]
    end

    subgraph "Layer 2 — Fetch"
        C1[PageFetcher<br/>sync / urllib]
        C2[AsyncPageFetcher<br/>async / httpx]
        C3[SharedCache<br/>SQLite / LRU 500]
        C4[Retry + Negative Cache]
    end

    subgraph "Layer 3 — Extraction"
        D1[parse_rvtdocs_page<br/>selectolax HTML]
        D2[build_structured_snippet]
        D3[_detect_deprecation]
        D4[Confidence Scoring<br/>configurable weights]
    end

    subgraph "Layer 4 — Output Shaping"
        E1[Trust Gate<br/>pass / warn / fail]
        E2[Suggestions Engine]
        E3[Output Truncation<br/>15K / 50K limit]
        E4[Year Warning]
    end

    subgraph "Layer 5 — Observability"
        F1[TelemetryLogger<br/>JSONL + rotation]
        F2[CalibrationLogger]
        F3[SessionStore]
    end

    A --> B1 --> B2
    B2 --> B3
    B2 --> B4
    B2 --> B5
    B2 --> C1
    B2 --> C2
    C1 --> C3
    C2 --> C3
    C1 --> C4
    C2 --> C4
    C3 --> D1
    D1 --> D2
    D1 --> D3
    D1 --> D4
    D4 --> E1
    E1 --> E2
    E1 --> E3
    E1 --> E4
    E1 --> F1
    E1 --> F2
```

## Layer Details

### Layer 1 — Routing (`routing/`)

Transforms a free-text query into a rvtdocs.com URL path.

```mermaid
flowchart LR
    Q["Wall.Create"] --> CQ[canonicalize_query]
    CQ --> RQ[resolve_query]
    RQ --> H{Exact Hint?}
    H -- Yes --> URL1["/2025/Autodesk.Revit.DB.Wall/Create"]
    H -- No --> NI{NamespaceIndex?}
    NI -- Yes --> URL2["Resolved via index"]
    NI -- No --> CC{CamelCase heuristic}
    CC --> URL3["Best-guess path"]
```

| Component | File | Role |
|-----------|------|------|
| `canonicalize_query()` | `routing/__init__.py` | Strip whitespace, normalize casing, expand aliases |
| `resolve_query()` | `routing/resolver.py` | Match query to URL using priority chain |
| `NamespaceIndex` | `routing/namespace_index.py` | Lazy-loaded JSON index of 2,448 class-to-namespace mappings per year |
| `EXACT_CLASS_NAMESPACE_HINTS` | `routing/constants.py` | 85 hand-curated overrides for commonly misrouted classes |
| `normalize_year()` | `routing/resolver.py` | Validate year, clamp to supported range, emit warnings |
| `build_suggestions()` | `routing/suggestions.py` | Generate actionable suggestions for failed queries |

**Resolution priority chain:**
1. Exact namespace hint override (highest priority)
2. NamespaceIndex data-driven lookup (2,448 classes)
3. Method context namespace hints
4. CamelCase heuristic (lowest priority, fallback)

### Layer 2 — Fetch (`fetcher.py`, `async_fetcher.py`, `cache_store.py`)

HTTP retrieval with caching and retry logic.

| Component | Transport | Use Case |
|-----------|-----------|----------|
| `PageFetcher` | `urllib` (sync) | Single-query tools: `rvtdocs_fetch`, `rvtdocs_scan`, `rvtdocs_debug` |
| `AsyncPageFetcher` | `httpx` (async) | Batch tool: `rvtdocs_batch` (concurrent) |
| `SharedCache` | SQLite (WAL mode) | Shared by both fetchers, thread-safe via `threading.Lock` |

**Cache behavior:**

| Feature | Value |
|---------|-------|
| Backend | SQLite with WAL journal mode |
| Capacity | 500 entries, LRU eviction (batch of 100) |
| TTL — class/method | 7 days |
| TTL — namespace | 30 days |
| TTL — negative (failed fetch) | 30 seconds |
| Thread safety | `threading.Lock` around all DB operations |
| Migration | Auto-migrates legacy `cache.json` to SQLite on first access |

**Retry policy:**

```
Attempt 1 → fail → wait 1.0s → Attempt 2 → fail → wait 3.0s → Attempt 3 → give up
```

Returns `FetchResult` with `attempts_used`, `retries_used`, and `error_detail` for transparency.

### Layer 3 — Extraction (`extractor.py`, `html_parser.py`)

Transforms raw HTML into structured API documentation.

```mermaid
flowchart LR
    HTML["Raw HTML"] --> SP[parse_rvtdocs_page<br/>selectolax]
    SP --> APS[ApiPageStructure]
    APS --> BSS[build_structured_snippet]
    BSS --> MD["Structured Markdown"]
    HTML --> DD[_detect_deprecation]
    DD --> DEP["Deprecation Info"]
    MD --> CS[Confidence Scoring]
    DEP --> CS
    CS --> EX["Extracted Payload"]
```

**Structured extraction output** (vs raw text):

| Aspect | Raw (trafilatura) | Structured (html_parser) |
|--------|-------------------|--------------------------|
| Format | Flat text dump | Section-aware markdown |
| Noise | Inherited members, nav, ads | Stripped to declared members only |
| Size | ~3,000 chars for a class page | ~2,000 chars (33% smaller) |
| Parseable | Agent must interpret | Ready-to-use sections |

**Confidence scoring** uses configurable weights (`confidence_config.py`) with signals:
- Title token match
- Class token match
- Method token match
- Structured parameters found
- Namespace match
- Deprecation detection

### Layer 4 — Output Shaping (`server.py`)

Controls what the agent receives, minimizing tokens while preserving actionable information.

**Trust-gate modes:**

```mermaid
graph LR
    subgraph "Output Size"
        SCAN["scan<br/>~300 tokens"]
        TRUST["trust<br/>~800 tokens"]
        FULL["full<br/>~2,500 tokens"]
        DIAG["diagnostics<br/>~4,000 tokens"]
    end
    SCAN --> TRUST --> FULL --> DIAG
```

| Mode | Snippet | Diagnostics | Evidence | TokenStats | Use Case |
|------|---------|-------------|----------|------------|----------|
| `scan` | No | No | No | No | Quick existence check |
| `trust` | No | No | No | No | Code generation with metadata only |
| `full` | Yes | No | Yes | Yes | Read API documentation in detail |
| `diagnostics` | Yes | Yes | Yes | Yes | Debug routing and extraction issues |

**Output truncation** enforces hard limits:

| Scope | Limit |
|-------|-------|
| Single tool | 15,000 chars |
| Batch tool | 50,000 chars |
| Truncation order | snippet → diagnostics → suggestions → error |

### Layer 5 — Observability (`telemetry.py`, `calibration.py`, `session_store.py`)

Fail-safe logging and session management.

| Component | Storage | Rotation | Purpose |
|-----------|---------|----------|---------|
| `TelemetryLogger` | JSONL file | 10 MB | Tool usage events (query, latency, cache hit, source) |
| `CalibrationLogger` | JSONL file | None | Confidence calibration data for tuning weights |
| `SessionStore` | In-memory dict | None (ephemeral) | Cross-tool key-value store for agent context |

## Data Flow — Single Fetch

```mermaid
sequenceDiagram
    participant Agent
    participant Server as server.py
    participant Router as routing/
    participant Fetcher as fetcher.py
    participant Cache as SharedCache
    participant Extractor as extractor.py
    participant Output as Output Shaping

    Agent->>Server: rvtdocs_fetch(query, year, mode)
    Server->>Router: canonicalize + resolve
    Router-->>Server: QueryResolution (kind, path, class, method)
    Server->>Cache: lookup(url)
    alt Cache hit
        Cache-->>Server: cached HTML
    else Cache miss
        Server->>Fetcher: fetch(url)
        Fetcher-->>Server: FetchResult (html, status, attempts)
        Server->>Cache: store(url, html, ttl)
    end
    Server->>Extractor: extract_for_resolution(html, resolution)
    Extractor-->>Server: extracted (snippet, confidence, deprecation)
    Server->>Output: shape by mode (trust/full/diagnostics)
    Output-->>Agent: FetchPayload JSON
```
