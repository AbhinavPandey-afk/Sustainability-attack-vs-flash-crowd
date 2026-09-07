"""In-memory session/conversion simulation.

A minimal, single-process session tracker used only to populate
app_active_sessions. The session identifier is a random opaque token
stored in a cookie — it is never used as a Prometheus label (that would be
an unbounded label, which CLAUDE.md section 7 explicitly warns against).

No Redis/external store is introduced: this is a research prototype and a
single FastAPI process is sufficient (CLAUDE.md section 4).
"""
import time
import uuid
from threading import Lock

from .metrics import APP_ACTIVE_SESSIONS, APP_SESSION_DURATION_SECONDS


class SessionTracker:
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        # session_id -> (created_at, expires_at), both time.monotonic() values.
        self._sessions: dict[str, tuple[float, float]] = {}
        self._lock = Lock()

    def touch(self, session_id: str | None) -> str:
        """Register activity for a session, creating one if needed/expired.

        Returns the (possibly new) session id and refreshes the active
        session gauge. Expired sessions have their lifetime (now - created)
        recorded into app_session_duration_seconds before being dropped —
        this is what feature engineering later reads to compute the
        session_duration behaviour feature (CLAUDE.md section 14.4).
        """
        now = time.monotonic()
        with self._lock:
            self._purge_expired(now)
            if session_id and session_id in self._sessions:
                created_at, _ = self._sessions[session_id]
            else:
                session_id = uuid.uuid4().hex
                created_at = now
            self._sessions[session_id] = (created_at, now + self.ttl_seconds)
            APP_ACTIVE_SESSIONS.set(len(self._sessions))
        return session_id

    def _purge_expired(self, now: float) -> None:
        expired = [sid for sid, (_, expires_at) in self._sessions.items() if expires_at <= now]
        for sid in expired:
            created_at, _ = self._sessions.pop(sid)
            APP_SESSION_DURATION_SECONDS.observe(now - created_at)
