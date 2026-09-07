"""Medium endpoint class: simulated search with configurable CPU workload
and an in-memory cache to simulate cache hits/misses.
"""
from fastapi import APIRouter

from ..config import settings
from ..metrics import APP_CACHE_HITS_TOTAL, APP_CACHE_MISSES_TOTAL, endpoint_class
from ..models import SearchResponse, SearchResult

router = APIRouter()

_ENDPOINT_CLASS = "medium"

# Small fixed synthetic corpus — no external calls, fully local.
_CORPUS = [f"Document {i}: sample content about topic {i % 17}" for i in range(200)]

# Bounded, FIFO-evicted cache. Query strings are cache keys only — never
# used as Prometheus label values (would be unbounded cardinality).
_cache: dict[str, list[SearchResult]] = {}
_cache_order: list[str] = []


def _simulate_search(query: str) -> list[SearchResult]:
    """Deterministic CPU-bound workload: the same query always yields the
    same results. Cost is proportional to SEARCH_WORKLOAD_ITERATIONS.
    """
    matches: list[SearchResult] = []
    needle = query.lower()
    for _ in range(max(settings.SEARCH_WORKLOAD_ITERATIONS, 1)):
        matches = [
            SearchResult(id=i, title=doc.split(":")[0], snippet=doc)
            for i, doc in enumerate(_CORPUS)
            if needle in doc.lower()
        ]
    return matches[:10]


@router.get("/api/search", response_model=SearchResponse)
@endpoint_class(_ENDPOINT_CLASS)
async def search(q: str) -> SearchResponse:
    cached = q in _cache
    if cached:
        APP_CACHE_HITS_TOTAL.labels(endpoint_class=_ENDPOINT_CLASS).inc()
        results = _cache[q]
    else:
        APP_CACHE_MISSES_TOTAL.labels(endpoint_class=_ENDPOINT_CLASS).inc()
        results = _simulate_search(q)
        _cache[q] = results
        _cache_order.append(q)
        if len(_cache_order) > settings.SEARCH_CACHE_SIZE:
            oldest = _cache_order.pop(0)
            _cache.pop(oldest, None)

    return SearchResponse(query=q, results=results, cached=cached)
