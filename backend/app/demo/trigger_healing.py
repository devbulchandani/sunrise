"""python -m app.demo.trigger_healing <source_slug>"""

import asyncio
import sys

from app.demo import trigger_healing

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m app.demo.trigger_healing <source_slug|id>")
        sys.exit(1)
    asyncio.run(trigger_healing(sys.argv[1]))
