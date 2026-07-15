from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from .tools import register_all

app = FastMCP("rvtdocs-mcp-py")

register_all(app)


def main() -> None:
    app.run()


if __name__ == "__main__":
    main()
