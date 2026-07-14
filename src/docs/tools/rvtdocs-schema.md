# rvtdocs_schema

Returns JSON schemas for all 9 rvtdocs tools. Useful for external tool validators, auto-discovery, and testing.

## Parameters

None.

## Output Schema (~2,000 tokens)

```json
{
  "tools": {
    "rvtdocs_fetch": {
      "parameters": {
        "query": { "type": "string", "required": true },
        "year": { "type": "string", "default": "2026" },
        "max_chars": { "type": "integer", "default": 12000 },
        "mode": { "type": "string", "default": "trust", "enum": ["trust", "full", "diagnostics"] }
      }
    },
    "rvtdocs_scan": { "..." },
    "rvtdocs_batch": { "..." },
    "rvtdocs_debug": { "..." },
    "rvtdocs_stats": { "..." },
    "rvtdocs_version_info": { "..." },
    "rvtdocs_schema": { "..." },
    "rvtdocs_session_set": { "..." },
    "rvtdocs_session_get": { "..." }
  }
}
```

## When to Use

1. **Tool validation** — verify correct parameters before calling
2. **Auto-discovery** — programmatic access to tool schemas
3. **Testing** — assert schema compatibility in CI

## Advantages

- Self-describing — no need to read source code or docs
- Enables automated tool chain composition

## Disadvantages

- High token cost (~2,000 tokens) for metadata that rarely changes
- Should be called once per session at most
