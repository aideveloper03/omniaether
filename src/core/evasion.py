"""Adversarial Evasion & Stealth System for AETHER-MINE.

Implements 2025-standard bot detection evasion:
- Tier 1 (Stealth): curl-cffi for Chrome 130+ JA3/TLS fingerprints
- Tier 2 (Adversarial): Behavioral noise - fake navigations, scrolling, clicking
- Tier 3 (Cascading Fallbacks): Shadow API -> Headless -> Wayback -> Human-in-loop
"""

import asyncio
import random
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Callable
from urllib.parse import urlparse, urljoin

import structlog
from curl_cffi import requests as curl_requests
from curl_cffi.requests import AsyncSession

from src.core.config import get_settings
from src.core.models import (
    DeviceFingerprint,
    ProxyHealth,
    ProxyStatus,
    FallbackTier,
)
from src.core.telemetry import get_telemetry, create_trace_id


logger = structlog.get_logger(__name__)


# Chrome 130+ browser profiles for curl-cffi
BROWSER_PROFILES = [
    "chrome120",
    "chrome119", 
    "chrome116",
    "chrome110",
    "safari17_2_ios",
    "safari17_0",
    "safari15_5",
]

# Screen resolutions for fingerprint diversity
SCREEN_RESOLUTIONS = [
    (1920, 1080),
    (2560, 1440),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (1680, 1050),
    (3840, 2160),
    (2560, 1080),
]

# GPU vendors and renderers
GPU_PROFILES = [
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA GeForce RTX 4090 Direct3D11)"),
    ("Google Inc. (NVIDIA)", "ANGLE (NVIDIA GeForce RTX 3080 Direct3D11)"),
    ("Google Inc. (AMD)", "ANGLE (AMD Radeon RX 7900 XTX Direct3D11)"),
    ("Google Inc. (Intel)", "ANGLE (Intel UHD Graphics 770 Direct3D11)"),
    ("Apple Inc.", "Apple M3 Pro"),
    ("Apple Inc.", "Apple M2 Max"),
]

# Timezones
TIMEZONES = [
    "America/New_York",
    "America/Los_Angeles",
    "America/Chicago",
    "Europe/London",
    "Europe/Paris",
    "Asia/Tokyo",
    "Asia/Singapore",
]

# Languages
LANGUAGES = [
    "en-US",
    "en-GB",
    "en-CA",
    "de-DE",
    "fr-FR",
    "es-ES",
    "ja-JP",
]


@dataclass
class BezierPoint:
    """Point for Bézier curve mouse movement."""
    x: float
    y: float
    timestamp: float = 0.0


def generate_bezier_curve(
    start: tuple[float, float],
    end: tuple[float, float],
    num_points: int = 50,
) -> list[BezierPoint]:
    """Generate human-like mouse movement using Bézier curves."""
    # Add control points for natural movement
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    # Random control points for curve variation
    ctrl1 = (
        start[0] + dx * random.uniform(0.2, 0.4) + random.uniform(-50, 50),
        start[1] + dy * random.uniform(0.1, 0.3) + random.uniform(-50, 50),
    )
    ctrl2 = (
        start[0] + dx * random.uniform(0.6, 0.8) + random.uniform(-50, 50),
        start[1] + dy * random.uniform(0.7, 0.9) + random.uniform(-50, 50),
    )
    
    points = []
    total_time = random.uniform(0.3, 0.8)  # Total movement time
    
    for i in range(num_points):
        t = i / (num_points - 1)
        
        # Cubic Bézier formula
        x = (
            (1 - t) ** 3 * start[0]
            + 3 * (1 - t) ** 2 * t * ctrl1[0]
            + 3 * (1 - t) * t ** 2 * ctrl2[0]
            + t ** 3 * end[0]
        )
        y = (
            (1 - t) ** 3 * start[1]
            + 3 * (1 - t) ** 2 * t * ctrl1[1]
            + 3 * (1 - t) * t ** 2 * ctrl2[1]
            + t ** 3 * end[1]
        )
        
        # Add slight jitter for realism
        x += random.uniform(-2, 2)
        y += random.uniform(-2, 2)
        
        # Non-linear time progression (slower at start/end)
        time_factor = 0.5 - 0.5 * math.cos(math.pi * t)
        timestamp = total_time * time_factor
        
        points.append(BezierPoint(x=x, y=y, timestamp=timestamp))
    
    return points


class FingerprintGenerator:
    """Generates diverse device fingerprints."""
    
    def __init__(self, rotation_threshold: int = 50) -> None:
        self._rotation_threshold = rotation_threshold
        self._current_fingerprint: DeviceFingerprint | None = None
        self._requests_with_current = 0
    
    def generate(self) -> DeviceFingerprint:
        """Generate a new device fingerprint."""
        resolution = random.choice(SCREEN_RESOLUTIONS)
        gpu = random.choice(GPU_PROFILES)
        
        # Generate canvas/webgl hashes
        canvas_hash = f"{random.getrandbits(128):032x}"
        webgl_hash = f"{random.getrandbits(128):032x}"
        audio_hash = f"{random.getrandbits(64):016x}"
        
        # Common fonts
        fonts = random.sample([
            "Arial", "Helvetica", "Times New Roman", "Georgia",
            "Verdana", "Courier New", "Trebuchet MS", "Lucida Console",
            "Segoe UI", "Tahoma", "Impact", "Comic Sans MS",
        ], k=random.randint(6, 12))
        
        # Common plugins (modern browsers have few)
        plugins = random.sample([
            "Chrome PDF Plugin",
            "Chrome PDF Viewer",
            "Native Client",
        ], k=random.randint(0, 3))
        
        # Generate user agent
        browser_profile = random.choice(BROWSER_PROFILES)
        chrome_version = random.randint(119, 130)
        
        if "safari" in browser_profile:
            user_agent = (
                f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                f"AppleWebKit/605.1.15 (KHTML, like Gecko) "
                f"Version/17.{random.randint(0, 5)} Safari/605.1.15"
            )
        else:
            user_agent = (
                f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) "
                f"Chrome/{chrome_version}.0.{random.randint(0, 9999)}.{random.randint(0, 999)} "
                f"Safari/537.36"
            )
        
        fingerprint = DeviceFingerprint(
            screen_width=resolution[0],
            screen_height=resolution[1],
            color_depth=random.choice([24, 32]),
            pixel_ratio=random.choice([1.0, 1.25, 1.5, 2.0]),
            platform=random.choice(["Win32", "MacIntel", "Linux x86_64"]),
            gpu_vendor=gpu[0],
            gpu_renderer=gpu[1],
            timezone=random.choice(TIMEZONES),
            language=random.choice(LANGUAGES),
            webgl_hash=webgl_hash,
            canvas_hash=canvas_hash,
            audio_hash=audio_hash,
            fonts=fonts,
            plugins=plugins,
            user_agent=user_agent,
        )
        
        self._current_fingerprint = fingerprint
        self._requests_with_current = 0
        
        logger.debug(
            "fingerprint_generated",
            fingerprint_id=fingerprint.fingerprint_id,
            resolution=f"{resolution[0]}x{resolution[1]}",
        )
        
        return fingerprint
    
    def get_current(self) -> DeviceFingerprint:
        """Get current fingerprint, rotating if needed."""
        if (
            self._current_fingerprint is None
            or self._requests_with_current >= self._rotation_threshold
        ):
            return self.generate()
        
        self._requests_with_current += 1
        return self._current_fingerprint


class ProxyManager:
    """Manages proxy pool with circuit breaker logic."""
    
    def __init__(
        self,
        proxies: list[str] | None = None,
        max_failures: int = 3,
        burn_timeout_hours: int = 24,
    ) -> None:
        settings = get_settings()
        self._max_failures = max_failures or settings.proxy_max_failures
        self._burn_timeout = burn_timeout_hours or settings.proxy_burn_timeout_hours
        
        self._proxies: dict[str, ProxyHealth] = {}
        
        if proxies:
            for i, proxy_url in enumerate(proxies):
                proxy_id = f"proxy_{i}"
                self._proxies[proxy_id] = ProxyHealth(
                    proxy_id=proxy_id,
                    proxy_url=proxy_url,
                )
        
        logger.info(
            "proxy_manager_initialized",
            proxy_count=len(self._proxies),
        )
    
    def add_proxy(self, proxy_url: str) -> str:
        """Add a proxy to the pool."""
        proxy_id = f"proxy_{len(self._proxies)}"
        self._proxies[proxy_id] = ProxyHealth(
            proxy_id=proxy_id,
            proxy_url=proxy_url,
        )
        return proxy_id
    
    def get_active_proxy(self) -> tuple[str, str] | None:
        """Get an active proxy from the pool.
        
        Returns (proxy_id, proxy_url) or None if no active proxies.
        """
        now = datetime.now(timezone.utc)
        
        # Check for cooled-down proxies
        for proxy_id, health in self._proxies.items():
            if health.status == ProxyStatus.BURNED:
                if health.cooldown_until and now > health.cooldown_until:
                    health.status = ProxyStatus.ACTIVE
                    health.consecutive_failures = 0
                    logger.info("proxy_recovered", proxy_id=proxy_id)
        
        # Get active proxies sorted by success rate
        active = [
            (pid, h) for pid, h in self._proxies.items()
            if h.status == ProxyStatus.ACTIVE
        ]
        
        if not active:
            return None
        
        # Sort by success rate (descending) and latency (ascending)
        active.sort(key=lambda x: (-x[1].success_rate, x[1].avg_latency_ms))
        
        proxy_id, health = active[0]
        return proxy_id, health.proxy_url
    
    def record_success(self, proxy_id: str, latency_ms: float) -> None:
        """Record a successful request for a proxy."""
        if proxy_id in self._proxies:
            self._proxies[proxy_id].record_success(latency_ms)
    
    def record_failure(self, proxy_id: str) -> None:
        """Record a failed request for a proxy."""
        if proxy_id in self._proxies:
            self._proxies[proxy_id].record_failure(
                self._max_failures,
                self._burn_timeout,
            )
            
            if self._proxies[proxy_id].status == ProxyStatus.BURNED:
                logger.warning(
                    "proxy_burned",
                    proxy_id=proxy_id,
                    failures=self._proxies[proxy_id].consecutive_failures,
                )
    
    def get_stats(self) -> dict[str, Any]:
        """Get proxy pool statistics."""
        total = len(self._proxies)
        active = sum(1 for h in self._proxies.values() if h.status == ProxyStatus.ACTIVE)
        burned = sum(1 for h in self._proxies.values() if h.status == ProxyStatus.BURNED)
        
        return {
            "total_proxies": total,
            "active_proxies": active,
            "burned_proxies": burned,
            "avg_success_rate": sum(h.success_rate for h in self._proxies.values()) / total if total else 0,
        }


class StealthClient:
    """Stealth HTTP client using curl-cffi with TLS fingerprint impersonation."""
    
    def __init__(
        self,
        proxy_manager: ProxyManager | None = None,
        fingerprint_generator: FingerprintGenerator | None = None,
        impersonate: str = "chrome120",
    ) -> None:
        self._proxy_manager = proxy_manager
        self._fingerprint_gen = fingerprint_generator or FingerprintGenerator()
        self._impersonate = impersonate
        self._telemetry = get_telemetry()
        
        logger.info(
            "stealth_client_initialized",
            impersonate=impersonate,
        )
    
    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> curl_requests.Response:
        """Make a stealth GET request."""
        return await self._request("GET", url, headers=headers, timeout=timeout)
    
    async def post(
        self,
        url: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> curl_requests.Response:
        """Make a stealth POST request."""
        return await self._request(
            "POST", url, data=data, json=json, headers=headers, timeout=timeout
        )
    
    async def _request(
        self,
        method: str,
        url: str,
        data: Any = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> curl_requests.Response:
        """Make a stealth request with fingerprint impersonation."""
        trace_id = create_trace_id()
        fingerprint = self._fingerprint_gen.get_current()
        
        # Build headers
        request_headers = {
            "User-Agent": fingerprint.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": f"{fingerprint.language},en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Sec-CH-UA": f'"Chromium";v="130", "Google Chrome";v="130"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": f'"{fingerprint.platform}"',
        }
        
        if headers:
            request_headers.update(headers)
        
        # Get proxy if available
        proxy = None
        proxy_id = None
        if self._proxy_manager:
            proxy_result = self._proxy_manager.get_active_proxy()
            if proxy_result:
                proxy_id, proxy = proxy_result
        
        start_time = time.perf_counter()
        
        try:
            async with AsyncSession(impersonate=self._impersonate) as session:
                response = await session.request(
                    method,
                    url,
                    data=data,
                    json=json,
                    headers=request_headers,
                    timeout=timeout,
                    proxy=proxy,
                    allow_redirects=True,
                )
            
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if proxy_id and self._proxy_manager:
                self._proxy_manager.record_success(proxy_id, latency_ms)
            
            logger.debug(
                "stealth_request_success",
                trace_id=trace_id,
                url=url,
                status=response.status_code,
                latency_ms=latency_ms,
            )
            
            return response
            
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            
            if proxy_id and self._proxy_manager:
                self._proxy_manager.record_failure(proxy_id)
            
            logger.error(
                "stealth_request_failed",
                trace_id=trace_id,
                url=url,
                error=str(e),
                latency_ms=latency_ms,
            )
            raise


class BehavioralNoise:
    """Generates human-like behavioral noise to pollute bot detection telemetry."""
    
    def __init__(self, page: Any) -> None:  # page is Playwright Page
        self._page = page
        settings = get_settings()
        self._min_delay = settings.human_delay_min_ms
        self._max_delay = settings.human_delay_max_ms
    
    async def human_delay(self) -> None:
        """Add human-like delay between actions."""
        delay = random.uniform(self._min_delay, self._max_delay) / 1000
        await asyncio.sleep(delay)
    
    async def random_scroll(self) -> None:
        """Perform random scrolling."""
        viewport = await self._page.viewport_size()
        if not viewport:
            return
        
        # Random scroll amount
        scroll_y = random.randint(100, viewport["height"])
        
        # Smooth scroll with Bézier-like motion
        steps = random.randint(3, 8)
        for _ in range(steps):
            step_y = scroll_y // steps + random.randint(-20, 20)
            await self._page.mouse.wheel(0, step_y)
            await asyncio.sleep(random.uniform(0.05, 0.15))
        
        await self.human_delay()
    
    async def random_mouse_movement(self) -> None:
        """Perform random mouse movement using Bézier curves."""
        viewport = await self._page.viewport_size()
        if not viewport:
            return
        
        # Random start and end points
        start = (
            random.randint(0, viewport["width"]),
            random.randint(0, viewport["height"]),
        )
        end = (
            random.randint(0, viewport["width"]),
            random.randint(0, viewport["height"]),
        )
        
        # Generate Bézier curve
        points = generate_bezier_curve(start, end)
        
        # Move mouse along curve
        for point in points:
            await self._page.mouse.move(point.x, point.y)
            await asyncio.sleep(0.01)
    
    async def random_hover(self) -> None:
        """Hover over random elements."""
        try:
            # Find hoverable elements
            elements = await self._page.query_selector_all("a, button, input")
            
            if elements:
                element = random.choice(elements)
                box = await element.bounding_box()
                
                if box:
                    # Move to element center with Bézier curve
                    target = (
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    
                    viewport = await self._page.viewport_size()
                    if viewport:
                        start = (
                            random.randint(0, viewport["width"]),
                            random.randint(0, viewport["height"]),
                        )
                        
                        points = generate_bezier_curve(start, target)
                        for point in points:
                            await self._page.mouse.move(point.x, point.y)
                            await asyncio.sleep(0.01)
                    
                    # Hover duration
                    await asyncio.sleep(random.uniform(0.2, 0.8))
        
        except Exception:
            pass  # Ignore hover failures
    
    async def fake_navigation(self) -> None:
        """Perform fake navigation actions without actually clicking."""
        await self.random_mouse_movement()
        await self.random_scroll()
        await self.random_hover()
        await self.human_delay()
    
    async def inject_noise(self, intensity: int = 3) -> None:
        """Inject behavioral noise with specified intensity (1-5)."""
        actions = [
            self.random_scroll,
            self.random_mouse_movement,
            self.random_hover,
            self.human_delay,
        ]
        
        # Number of actions based on intensity
        num_actions = intensity * 2
        
        for _ in range(num_actions):
            action = random.choice(actions)
            await action()


class CascadingFallback:
    """Implements cascading fallback retrieval system."""
    
    def __init__(
        self,
        stealth_client: StealthClient | None = None,
        shadow_api_interceptor: Any = None,  # ShadowAPIInterceptor
    ) -> None:
        self._stealth_client = stealth_client or StealthClient()
        self._shadow_api = shadow_api_interceptor
        self._telemetry = get_telemetry()
        
        logger.info("cascading_fallback_initialized")
    
    async def retrieve(
        self,
        url: str,
        on_human_required: Callable[[str], None] | None = None,
    ) -> tuple[bytes | None, FallbackTier]:
        """Attempt to retrieve content with cascading fallbacks.
        
        Fallback order:
        1. Direct Shadow API Fetch
        2. Stealth Headless Browser
        3. Wayback Machine
        4. Google Cache
        5. Human-in-the-loop notification
        """
        trace_id = create_trace_id()
        
        # Tier 1: Direct Shadow API
        logger.info("fallback_tier_1", trace_id=trace_id, url=url, tier="shadow_api")
        try:
            response = await self._stealth_client.get(url, timeout=15.0)
            if response.status_code == 200:
                return response.content, FallbackTier.SHADOW_API
        except Exception as e:
            logger.debug("tier_1_failed", error=str(e))
        
        # Tier 2: Headless Browser (if available)
        if self._shadow_api:
            logger.info("fallback_tier_2", trace_id=trace_id, url=url, tier="headless")
            try:
                await self._shadow_api.start()
                apis = await self._shadow_api.navigate_and_intercept(url)
                if apis:
                    # Try to get content from discovered APIs
                    for api in apis:
                        try:
                            resp = await self._shadow_api.clone_to_httpx(api)
                            if resp.status_code == 200:
                                await self._shadow_api.stop()
                                return resp.content, FallbackTier.HEADLESS_BROWSER
                        except Exception:
                            continue
                await self._shadow_api.stop()
            except Exception as e:
                logger.debug("tier_2_failed", error=str(e))
        
        # Tier 3: Wayback Machine
        logger.info("fallback_tier_3", trace_id=trace_id, url=url, tier="wayback")
        try:
            wayback_url = f"https://web.archive.org/web/2/{url}"
            response = await self._stealth_client.get(wayback_url, timeout=20.0)
            if response.status_code == 200:
                return response.content, FallbackTier.WAYBACK_MACHINE
        except Exception as e:
            logger.debug("tier_3_failed", error=str(e))
        
        # Tier 4: Google Cache
        logger.info("fallback_tier_4", trace_id=trace_id, url=url, tier="google_cache")
        try:
            cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
            response = await self._stealth_client.get(cache_url, timeout=20.0)
            if response.status_code == 200:
                return response.content, FallbackTier.GOOGLE_CACHE
        except Exception as e:
            logger.debug("tier_4_failed", error=str(e))
        
        # Tier 5: Human-in-the-loop
        logger.warning("fallback_tier_5", trace_id=trace_id, url=url, tier="human")
        if on_human_required:
            on_human_required(url)
        
        return None, FallbackTier.HUMAN_IN_LOOP
