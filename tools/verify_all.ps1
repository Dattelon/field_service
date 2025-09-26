$ErrorActionPreference = "Stop"
python -m venv .venv
if (Test-Path ".venv/Scripts/pip.exe") { .venv/Scripts/pip.exe install -U pip wheel } else { .venv/bin/pip install -U pip wheel }
if (Test-Path ".venv/Scripts/pip.exe") { .venv/Scripts/pip.exe install -r requirements.txt } else { .venv/bin/pip install -r requirements.txt }
if (Test-Path ".venv/Scripts/ruff.exe") { .venv/Scripts/ruff.exe check --fix . } else { .venv/bin/ruff check --fix . }
if (Test-Path ".venv/Scripts/black.exe") { .venv/Scripts/black.exe . } else { .venv/bin/black . }
if (Test-Path ".venv/Scripts/mypy.exe") { .venv/Scripts/mypy.exe . } else { .venv/bin/mypy . }
if (Test-Path ".venv/Scripts/alembic.exe") { .venv/Scripts/alembic.exe upgrade head } else { .venv/bin/alembic upgrade head }
pytest -q
Write-Host "✅ OK"
