"""Phase 2 application configuration.

All values are overridable via environment variables so experiments can
tune endpoint workload without code changes. No cost model, HPA, or
Kubernetes-specific configuration lives here yet — those belong to later
phases.
"""
import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    # Session/conversion simulation
    SESSION_TTL_SECONDS: float = _float_env("CASCADE_SESSION_TTL_SECONDS", 300)

    # Medium endpoint (/api/search)
    SEARCH_CACHE_SIZE: int = _int_env("CASCADE_SEARCH_CACHE_SIZE", 256)
    SEARCH_WORKLOAD_ITERATIONS: int = _int_env("CASCADE_SEARCH_WORKLOAD_ITERATIONS", 20)

    # Expensive endpoint (/api/generate-report)
    REPORT_MIN_COMPLEXITY: int = _int_env("CASCADE_REPORT_MIN_COMPLEXITY", 1)
    REPORT_MAX_COMPLEXITY: int = _int_env("CASCADE_REPORT_MAX_COMPLEXITY", 100)
    REPORT_DEFAULT_COMPLEXITY: int = _int_env("CASCADE_REPORT_DEFAULT_COMPLEXITY", 10)
    REPORT_ITERATIONS_PER_COMPLEXITY: int = _int_env("CASCADE_REPORT_ITERATIONS_PER_COMPLEXITY", 2000)
    # Hard ceiling regardless of the above, so the endpoint always has a
    # bounded maximum execution time even if the other values change.
    REPORT_MAX_ITERATIONS: int = _int_env("CASCADE_REPORT_MAX_ITERATIONS", 200_000)


settings = Settings()
