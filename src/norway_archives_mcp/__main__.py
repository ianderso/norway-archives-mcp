"""Entry point: ``python -m norway_archives_mcp`` / the ``norway-archives-mcp`` script."""

from __future__ import annotations

from .server import run


def main() -> None:
    run()


if __name__ == "__main__":
    main()
