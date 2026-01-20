from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Dict, Iterable, Optional


@dataclass
class ProxyState:
    failures: int
    burned_until: Optional[float]


class ProxyCircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 86400) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._states: Dict[str, ProxyState] = {}

    def record_success(self, proxy_id: str) -> None:
        self._states[proxy_id] = ProxyState(failures=0, burned_until=None)

    def record_failure(self, proxy_id: str) -> None:
        state = self._states.get(proxy_id, ProxyState(failures=0, burned_until=None))
        state.failures += 1
        if state.failures >= self.failure_threshold:
            state.burned_until = time.time() + self.cooldown_seconds
            state.failures = 0
        self._states[proxy_id] = state

    def is_available(self, proxy_id: str) -> bool:
        state = self._states.get(proxy_id)
        if not state or state.burned_until is None:
            return True
        if time.time() >= state.burned_until:
            self._states[proxy_id] = ProxyState(failures=0, burned_until=None)
            return True
        return False

    def next_available(self, proxy_ids: Iterable[str]) -> Optional[str]:
        for proxy_id in proxy_ids:
            if self.is_available(proxy_id):
                return proxy_id
        return None

    def burned_proxies(self) -> Dict[str, float]:
        burned: Dict[str, float] = {}
        now = time.time()
        for proxy_id, state in self._states.items():
            if state.burned_until and state.burned_until > now:
                burned[proxy_id] = state.burned_until
        return burned
