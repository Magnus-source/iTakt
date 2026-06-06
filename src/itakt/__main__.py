"""Entry point — python -m itakt"""
import asyncio
from .repl import run_repl


def main() -> None:
    asyncio.run(run_repl())


if __name__ == "__main__":
    main()
