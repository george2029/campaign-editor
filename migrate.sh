#!/bin/sh
# Apply all database migrations. Creates app.db if it doesn't exist yet.
.venv/bin/alembic upgrade head
