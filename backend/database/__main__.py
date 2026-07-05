"""Allow `python -m backend.database` to create/upgrade the SQLite schema.

SETUP.md documents this command; without a __main__ module,
`python -m backend.database` errors ("package cannot be directly executed").
"""
from backend import config
from backend.database import init_db

init_db()
print(f"OK - initialised {config.DB_PATH}")
