"""Unit tests for app/src/sessions.py — session tracking and the
app_session_duration_seconds histogram that feature engineering later
reads for the session_duration behaviour feature (CLAUDE.md section 14.4).
"""
import time

from app.src.metrics import APP_SESSION_DURATION_SECONDS
from app.src.sessions import SessionTracker


def test_touch_creates_new_session_when_none_given():
    tracker = SessionTracker(ttl_seconds=60)
    session_id = tracker.touch(None)
    assert session_id
    assert session_id in tracker._sessions


def test_touch_reuses_existing_unexpired_session():
    tracker = SessionTracker(ttl_seconds=60)
    first = tracker.touch(None)
    second = tracker.touch(first)
    assert first == second
    assert len(tracker._sessions) == 1


def test_touch_issues_new_session_for_unknown_id():
    tracker = SessionTracker(ttl_seconds=60)
    session_id = tracker.touch("not-a-real-session-id")
    assert session_id != "not-a-real-session-id"


def test_expired_session_is_purged_and_records_duration_observation():
    tracker = SessionTracker(ttl_seconds=0.01)
    session_id = tracker.touch(None)
    time.sleep(0.02)

    sample_count_before = _histogram_sample_count()
    tracker.touch(None)  # any call triggers _purge_expired, dropping the expired session
    sample_count_after = _histogram_sample_count()

    assert session_id not in tracker._sessions
    assert sample_count_after == sample_count_before + 1


def _histogram_sample_count():
    for metric in APP_SESSION_DURATION_SECONDS.collect():
        for sample in metric.samples:
            if sample.name.endswith("_count"):
                return sample.value
    return 0.0


def test_active_session_gauge_reflects_current_count():
    from app.src.metrics import APP_ACTIVE_SESSIONS

    tracker = SessionTracker(ttl_seconds=60)
    tracker.touch(None)
    tracker.touch(None)
    assert APP_ACTIVE_SESSIONS._value.get() == len(tracker._sessions)
