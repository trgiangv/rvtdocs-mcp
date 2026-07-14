# rvtdocs_debug

Diagnostic fetch that exposes the full routing and extraction pipeline internals. Equivalent to `rvtdocs_fetch(mode="diagnostics")`.

## Parameters

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | Yes | — | API query to diagnose |
| `year` | string | No | `"2026"` | Revit version year (2022-2027) |
| `max_chars` | int | No | `12000` | Maximum snippet character count |

## Output Schema (~4,000 tokens)

Returns the standard `FetchPayload` plus a `diagnostics` block:

```json
{
  "success": true,
  "resolved": { "kind": "method", "path": "/2025/Autodesk.Revit.DB.View3D/CreateIsometric" },
  "http": { "ok": true, "status": 200, "elapsedMs": 1100 },
  "trust": { "verdict": "pass", "confidence": 0.85 },
  "extracted": {
    "snippet": "## View3D.CreateIsometric\n...",
    "focus": "method",
    "matched": true,
    "confidence": 0.85,
    "evidence": ["method_token", "class_token", "structured_parameters"]
  },
  "diagnostics": {
    "mode": "diagnostics",
    "inputQuery": "View3D.CreateIsometric",
    "canonicalQuery": "View3D.CreateIsometric",
    "canonicalRewritten": false,
    "resolution": {
      "kind": "method",
      "className": "View3D",
      "methodName": "CreateIsometric",
      "path": "/2025/Autodesk.Revit.DB.View3D/CreateIsometric",
      "unverifiedNamespace": false
    },
    "semantic": {
      "focus": "method",
      "matched": true,
      "confidence": 0.85,
      "reasonCode": "single_fetch_success",
      "evidence": ["method_token", "class_token"]
    },
    "result": {
      "success": true,
      "reasonCode": "single_fetch_success",
      "snippetIncluded": true
    }
  }
}
```

## When to Use

1. **Wrong namespace** — query resolves to `Autodesk.Revit.DirectContext3D.View3D` instead of `Autodesk.Revit.DB.View3D`
2. **Low confidence** — fetch returns success but confidence is below threshold
3. **Unexpected failure** — query should match but returns `api_not_found`
4. **Investigating extraction quality** — checking what evidence the confidence scorer found

## Diagnostic Fields Explained

| Field | Purpose |
|-------|---------|
| `inputQuery` | Exact string the agent passed |
| `canonicalQuery` | After normalization (trim, case, alias expansion) |
| `canonicalRewritten` | Whether canonicalization changed the query |
| `resolution.kind` | Detected type: `class`, `method`, `namespace`, `ambiguous` |
| `resolution.className` | Extracted class name from the query |
| `resolution.methodName` | Extracted method name (if applicable) |
| `resolution.unverifiedNamespace` | `true` if namespace was guessed, not from index |
| `semantic.evidence` | List of signals that contributed to confidence |
| `semantic.reasonCode` | Detailed reason for the semantic match result |

## Advantages

- **Full transparency** — see exactly how the query was routed and why
- **Includes snippet** — see the actual extracted content
- **Evidence list** — understand which signals boosted or lowered confidence
- **Namespace verification** — know if the namespace was verified or guessed

## Disadvantages

- **High token cost** (~4,000 tokens) — 13x more than `rvtdocs_scan`
- **Should not be used routinely** — reserved for debugging specific issues
- **No batch variant** — only single-query
