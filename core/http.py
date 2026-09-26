# core/http.py
import httpx
import random
import asyncio
from typing import Optional

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0",
]


class HTTPPool:
    def __init__(self, proxies: list[str] | None = None):
        self.proxies = proxies or []
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._lock = asyncio.Lock()

    def _ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _proxy(self) -> Optional[str]:
        if not self.proxies:
            return None
        raw = random.choice(self.proxies)
        return self._parse_proxy(raw)

    @staticmethod
    def _parse_proxy(raw: str) -> str:
        raw = raw.strip()
        if not raw:
            return raw
        if "://" in raw:
            return raw
        if "##" in raw:
            parts = raw.split("##")
            if len(parts) == 3:
                host_port, user, pw = parts
                return f"http://{user}:{pw}@{host_port}"
        if "@" in raw:
            left, right = raw.split("@", 1)
            lp = left.split(":")
            rp = right.split(":")
            if len(lp) == 2 and len(rp) == 2:
                if lp[1].isdigit():
                    return f"http://{right}@{left}"
                return f"http://{left}@{right}"
        parts = raw.split(":")
        if len(parts) == 4:
            a, b, c, d = parts
            if b.isdigit():
                return f"http://{c}:{d}@{a}:{b}"
        if len(parts) == 2:
            return f"http://{raw}"
        return raw

    async def client(self, proxy: Optional[str] = None) -> httpx.AsyncClient:
        key = proxy or "__direct__"
        async with self._lock:
            if key not in self._clients:
                kwargs = {
                    "http2": True,
                    "timeout": 40.0,
                    "follow_redirects": True,
                    "verify": False,
                }
                if proxy:
                    kwargs["proxy"] = proxy
                self._clients[key] = httpx.AsyncClient(**kwargs)
            return self._clients[key]

    async def get(self, url: str, **kwargs) -> httpx.Response:
        proxy = self._proxy()
        client = await self.client(proxy)
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self._ua())
        return await client.get(url, headers=headers, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        proxy = self._proxy()
        client = await self.client(proxy)
        headers = kwargs.pop("headers", {})
        headers.setdefault("User-Agent", self._ua())
        return await client.post(url, headers=headers, **kwargs)

    async def close(self):
        for c in self._clients.values():
            await c.aclose()
        self._clients.clear()
