# RVTDocs MCP

Python MCP server for deterministic RVTDocs querying with low-retry behavior.

## Overview

- Python 3.14 project managed with `uv`
- MCP server entrypoint: `rvtdocs-mcp`
- Runtime source lives under `src/`
- Internal docs live under `src/docs/`

## Tools

- `rvtdocs_fetch(query, year=2026, max_chars=12000, mode="trust")`
- `rvtdocs_scan(query, year=2026, max_chars=12000)`
- `rvtdocs_debug(query, year=2026, max_chars=12000)`

## Run local

```powershell
uv run --python 3.14 rvtdocs-mcp
```

Module form while editing source:

```powershell
uv run --python 3.14 python -m src.server
```

## Run via GitHub

```powershell
uvx --from "git+https://github.com/trgiangv/rvtdocs-mcp.git" --python 3.14 rvtdocs-mcp
```

## MCP config

From local checkout:

```json
{
	"mcpServers": {
		"rvtdocs": {
			"type": "stdio",
			"command": "uv",
			"args": ["run", "--python", "3.14", "rvtdocs-mcp"]
		}
	}
}
```

From GitHub:

```json
{
	"mcpServers": {
		"rvtdocs": {
			"type": "stdio",
			"command": "uvx",
			"args": [
				"--from",
				"git+https://github.com/trgiangv/rvtdocs-mcp.git",
				"--python",
				"3.14",
				"rvtdocs-mcp"
			]
		}
	}
}
```

## More docs

- Setup and MCP wiring: `src/docs/setup.md`
- Internal architecture: `src/docs/architecture.md`
- Tool reference: `src/docs/tools/`
- Agent-oriented commands and repo notes: `AGENTS.md`
