"""Migration guards for environment-specific control."""

from __future__ import annotations

import os


def is_dev_environment() -> bool:
    """Check if running in development environment.
    
    Returns True if:
    - APP_ENV == "development" or "dev"
    - ALLOW_DEV_SEEDS == "1" or "true"
    - Running in pytest (TEST environment)
    """
    app_env = os.getenv("APP_ENV", "").lower()
    allow_dev = os.getenv("ALLOW_DEV_SEEDS", "").lower()
    is_test = os.getenv("PYTEST_CURRENT_TEST") is not None
    
    return (
        app_env in ("development", "dev")
        or allow_dev in ("1", "true", "yes")
        or is_test
    )


def is_ci_environment() -> bool:
    """Check if running in CI/testing environment.
    
    Returns True if:
    - CI == "1" or "true"
    - PYTEST_CURRENT_TEST is set
    """
    ci_env = os.getenv("CI", "").lower()
    is_test = os.getenv("PYTEST_CURRENT_TEST") is not None
    
    return ci_env in ("1", "true", "yes") or is_test


def skip_unless_dev(op, reason: str = "dev-only seed") -> bool:
    """Skip migration unless in dev environment.
    
    Usage in migration:
        if skip_unless_dev(op, "demo data"):
            return
    
    Returns True if should skip (not dev), False if should proceed (is dev).
    """
    if not is_dev_environment():
        print(f"⏭️  Skipping {reason} (not in development environment)")
        return True
    return False


def ensure_ci_environment(op, reason: str = "CI-only migration") -> None:
    """Ensure migration runs only in CI/test environment.
    
    Usage in migration:
        ensure_ci_environment(op, "test fixtures")
        # migration code...
    
    Raises RuntimeError if not in CI environment.
    """
    if not is_ci_environment():
        raise RuntimeError(
            f"Migration '{reason}' should only run in CI/test environment. "
            "Set CI=1 or PYTEST_CURRENT_TEST to proceed."
        )
