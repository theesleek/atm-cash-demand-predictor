from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.operations import RateLimitState


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


@dataclass
class _AttemptWindow:
    failures: int = 0
    window_started: float = 0.0
    blocked_until: float = 0.0


class LoginRateLimiter:
    def __init__(self, attempts: int, window_seconds: int, block_seconds: int):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self.block_seconds = block_seconds
        self._windows: dict[str, _AttemptWindow] = {}
        self._lock = threading.Lock()

    def retry_after(self, key: str) -> int:
        now = time.monotonic()
        with self._lock:
            window = self._windows.get(key)
            if window is None or window.blocked_until <= now:
                return 0
            return max(1, int(window.blocked_until - now))

    def record_failure(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            window = self._windows.setdefault(key, _AttemptWindow(window_started=now))
            if now - window.window_started >= self.window_seconds:
                window.failures = 0
                window.window_started = now
            window.failures += 1
            if window.failures >= self.attempts:
                window.blocked_until = now + self.block_seconds

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


_limiter: LoginRateLimiter | None = None


def get_login_rate_limiter(attempts: int, window_seconds: int, block_seconds: int) -> LoginRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = LoginRateLimiter(attempts, window_seconds, block_seconds)
    return _limiter


def distributed_retry_after(session: Session, key: str) -> int:
    state = session.get(RateLimitState, key)
    if state is None or state.blocked_until is None:
        return 0
    remaining = int((_aware(state.blocked_until) - datetime.now(timezone.utc)).total_seconds())
    if remaining <= 0:
        state.blocked_until = None
        state.failures = 0
        session.commit()
        return 0
    return max(1, remaining)


def distributed_record_failure(
    session: Session,
    key: str,
    attempts: int,
    window_seconds: int,
    block_seconds: int,
) -> None:
    now = datetime.now(timezone.utc)
    state = session.query(RateLimitState).filter(RateLimitState.key == key).with_for_update().first()
    if state is None:
        state = RateLimitState(key=key, failures=0, window_started_at=now)
        session.add(state)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            state = session.get(RateLimitState, key)
    if state is None:
        return
    if now - _aware(state.window_started_at) > timedelta(seconds=window_seconds):
        state.failures = 0
        state.window_started_at = now
    state.failures += 1
    if state.failures >= attempts:
        state.blocked_until = now + timedelta(seconds=block_seconds)
    session.commit()


def distributed_reset(session: Session, key: str) -> None:
    state = session.get(RateLimitState, key)
    if state is not None:
        session.delete(state)
        session.commit()
