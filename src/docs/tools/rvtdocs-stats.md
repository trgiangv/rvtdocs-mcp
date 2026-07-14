# rvtdocs_stats

Query usage statistics for the rvtdocs MCP server over a specified time period.

## Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `hours` | int | No | `24` | Time window in hours to aggregate stats |

## Output Schema (~500 tokens)

```json
{
  "period": "24h",
  "totalCalls": 150,
  "byTool": {
    "rvtdocs_fetch": 80,
    "rvtdocs_scan": 50,
    "rvtdocs_batch": 20
  },
  "successRate": 0.87,
  "avgConfidence": 0.76,
  "avgLatencyMs": 1200,
  "cacheHitRate": 0.65,
  "topQueries": ["Wall", "FilteredElementCollector", "Document"],
  "topFailures": [
    { "query": "Schema.EraseSchemaAndAllEntities", "reasonCode": "api_not_found", "count": 3 }
  ]
}
```

## When to Use

1. **Self-optimization** — agent checks `cacheHitRate` to determine if queries are repeating (use session store)
2. **Failure patterns** — `topFailures` reveals systematic routing issues
3. **Performance monitoring** — `avgLatencyMs` indicates cache warm-up status
4. **Usage audit** — understand which tools and queries are most used

## Advantages

- Low token cost (~500 tokens)
- Enables agent self-correction based on failure patterns
- No side effects — read-only telemetry

## Disadvantages

- Requires `RVTDOCS_MCP_TELEMETRY=1` (default on)
- Stats are session-scoped — reset when server restarts
