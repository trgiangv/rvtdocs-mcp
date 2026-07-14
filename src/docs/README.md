# rvtdocs-mcp

MCP server for Revit API documentation retrieval, optimized for agentic workflows with trust-gated output shaping and token-efficient extraction.

## Quick Links

| Document | Description |
|----------|-------------|
| [Setup Guide](./setup.md) | Installation, configuration, and running |
| [Architecture](./architecture.md) | Internal layers, data flow, caching, and component diagram |
| [Tools Reference](./tools/) | Per-tool docs with parameters, output schemas, and examples |
| [Workflows](./workflows.md) | Multi-tool agent workflows with Mermaid sequence diagrams |
| [Token Efficiency](./token-efficiency.md) | Quantitative comparison vs WebSearch, LLM pretrained, raw fetch |

## What It Does

```
┌──────────────────────────────────────────────────────────────┐
│                   AI Agent (Cursor / Claude)                  │
│                                                              │
│  "Look up Wall.Create for Revit 2025"                        │
└──────────────────────┬───────────────────────────────────────┘
                       │ MCP (stdio)
                       ▼
┌──────────────────────────────────────────────────────────────┐
│                      rvtdocs-mcp                              │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  ┌────────────┐  │
│  │ Routing  │→ │ Fetching │→ │Extraction │→ │  Output    │  │
│  │          │  │          │  │           │  │  Shaping   │  │
│  │ resolve  │  │ urllib/  │  │ selectolax│  │ trust-gate │  │
│  │ query →  │  │ httpx +  │  │ HTML →    │  │ scan/trust │  │
│  │ URL path │  │ SQLite   │  │ structured│  │ /full/diag │  │
│  │          │  │ cache    │  │ markdown  │  │            │  │
│  └──────────┘  └──────────┘  └───────────┘  └────────────┘  │
│                                                              │
│  Data source: rvtdocs.com (Revit 2022-2027)                  │
└──────────────────────────────────────────────────────────────┘
```

## Tools (9)

| Category | Tools | Purpose |
|----------|-------|---------|
| **Core Fetch** | `rvtdocs_fetch`, `rvtdocs_scan`, `rvtdocs_debug`, `rvtdocs_batch` | Retrieve API docs with configurable detail level |
| **Observability** | `rvtdocs_stats`, `rvtdocs_version_info` | Usage metrics and version metadata |
| **Introspection** | `rvtdocs_schema` | Self-describe tool schemas for validation |
| **Session** | `rvtdocs_session_set`, `rvtdocs_session_get` | Cross-tool ephemeral key-value store |

## Key Metrics

| Metric | Value |
|--------|-------|
| Namespace index coverage | 2,448 classes across 6 Revit versions |
| SQLite cache capacity | 500 entries, LRU eviction, WAL mode |
| Batch concurrency | Up to 10 queries per call via httpx async |
| Output budget | 15,000 chars (single) / 50,000 chars (batch) |
| Supported Revit versions | 2022, 2023, 2024, 2025, 2026, 2027 |
| Cache TTL | 7 days (class/method), 30 days (namespace), 30s (negative) |
| Retry policy | 2 retries with 1s/3s exponential backoff |

## Token Efficiency at a Glance

| Approach | 4-Query Lookup | Tool Calls | Accuracy |
|----------|---------------|------------|----------|
| WebSearch | ~16,000 tokens | 4 | ~60% |
| LLM Pretrained | 0 tokens | 0 | ~50% (risky) |
| **rvtdocs_batch (trust)** | **~4,000 tokens** | **1** | **~95%** |

See [Token Efficiency](./token-efficiency.md) for detailed analysis.
