"""Test environment isolation.

The app loads backend/.env via pydantic-settings. Tests must not inherit
production-ish values (notably ADMIN_TOKEN), otherwise admin-gated routes
return 403 before reaching the behaviour under test.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DEMO_MODE", "true")
os.environ["ADMIN_TOKEN"] = ""
os.environ["ADMIN_EMAILS"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()
