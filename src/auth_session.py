from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4


@dataclass
class OemSession:
    session_id: str
    oem_base_url: str
    username: str
    password: str
    token: Optional[str]
    expires_at: datetime

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) >= self.expires_at


class SessionCache:
    def __init__(self, ttl_minutes: int = 30):
        self._ttl_minutes = ttl_minutes
        self._sessions: dict[str, OemSession] = {}

    def create(
        self,
        oem_base_url: str,
        username: str,
        password: str,
        token: Optional[str],
    ) -> OemSession:
        session = OemSession(
            session_id=str(uuid4()),
            oem_base_url=oem_base_url.rstrip("/"),
            username=username,
            password=password,
            token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=self._ttl_minutes),
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> Optional[OemSession]:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.is_expired():
            self._sessions.pop(session_id, None)
            return None
        return session

