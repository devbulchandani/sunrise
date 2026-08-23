"""python -m app.demo.break_scraper <source_slug>"""

import asyncio
import sys

from app.demo import _assert_demo_mode, break_scraper

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m app.demo.break_scraper <source_slug|id>")
        sys.exit(1)
    _assert_demo_mode()
    asyncio.run(break_scraper(sys.argv[1]))
