"""Compatibility shim for legacy benchmark module path."""

from .benchmarking.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
