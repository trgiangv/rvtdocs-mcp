# AGENTS.md

## Repo layout

- Runtime package code lives under `src/`.
- Benchmarks write generated artifacts into `benchmarks/reports/`.
- Internal user-facing docs live under `src/docs/`.
- Keep top-level `README.md` short and user-facing; move agent workflow detail here or into `src/docs/`.

## Validated commands

- Local server: `uv run --python 3.14 rvtdocs-mcp`
- Local module entry: `uv run --python 3.14 python -m src.server`
- Local `uvx` source run: `uvx --from <absolute-path-to-repo> --python 3.14 rvtdocs-mcp`
- GitHub `uvx` run: `uvx --from git+https://github.com/trgiangv/rvtdocs-mcp.git --python 3.14 rvtdocs-mcp`
- Benchmark runner: `uv run --python 3.14 python -m src.benchmarking.runner --mode trust`
- Rare matrix: `uv run --python 3.14 python -m src.benchmarking.rare_matrix --years 2022,2023,2024,2025,2026,2027 --mode trust`
- Smoke check: `uv run --python 3.14 python -m compileall src`

## Agent usage notes

- Prefer `rvtdocs_scan` first when you only need existence or trust signals.
- Use `rvtdocs_fetch(..., mode="full")` when content evidence is required.
- Use `rvtdocs_debug` only for routing or extraction triage.
- Current output quality signals include `http.reasonCode`, `extracted.confidence`, `extracted.reasonCode`, `extracted.evidence`, and `extracted.tokenStats`.

## Benchmark and validation

- Seed file: `benchmarks/query-seeds.v1.json`
- Benchmark spec: `benchmarks/benchmark-spec.v1.md`
- Reports are written to `benchmarks/reports/`
- No dedicated automated test suite exists yet; rely on smoke checks and benchmark help commands.

## Environment

- Optional cache env: `RVTDOCS_MCP_CACHE_FILE`
- Optional parser mode env: `RVTDOCS_MCP_PARSER_MODE=auto|trafilatura|readability|selectolax|builtin`
- Telemetry envs are documented in `src/docs/setup.md`

## Notes for agents

- Do not reintroduce `rvtdocs_mcp` import paths unless the package layout is actually changed.
- Keep README and `src/docs/setup.md` in sync when changing run commands or packaging.
- The repo currently has no dedicated automated test suite; use smoke checks unless tests are added.
- Support only local source and GitHub-based `uvx` documentation; do not add PyPI install docs unless publishing is actually adopted.
- GitHub source docs should use `git+https://github.com/trgiangv/rvtdocs-mcp.git`.