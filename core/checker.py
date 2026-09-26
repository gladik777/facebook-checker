# core/checker.py
import asyncio
from dataclasses import dataclass, field


@dataclass
class Credential:
    email: str
    password: str


@dataclass
class CheckResult:
    cred: Credential
    status: str
    modules: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)
    proxy: str = ""

    def __str__(self):
        return f"{self.status} | {self.cred.email}:{self.cred.password}"


class Checker:
    def __init__(self, modules: list, proxies: list[str], concurrency: int = 3, proxy_uses: int = 20):
        self.modules = modules
        self.proxies = proxies
        self.sem = asyncio.Semaphore(concurrency)
        self.proxy_uses = proxy_uses
        self.proxy_index = 0
        self.proxy_counter = 0
        self._lock = asyncio.Lock()

    async def _next_proxy(self) -> str | None:
        if not self.proxies:
            return None
        async with self._lock:
            if self.proxy_counter >= self.proxy_uses:
                self.proxy_counter = 0
                self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
            self.proxy_counter += 1
            return self.proxies[self.proxy_index]

    async def check_one(self, cred: Credential) -> CheckResult:
        async with self.sem:
            proxy = await self._next_proxy()
            mod = self.modules[0]
            try:
                result_data = await mod.run(cred, proxy=proxy)
            except Exception as e:
                return CheckResult(
                    cred=cred,
                    status="ERROR",
                    raw={"error": type(e).__name__, "detail": str(e)[:300]},
                    proxy=proxy or "",
                )

            status = result_data.get("status", "ERROR")
            return CheckResult(
                cred=cred,
                status=status,
                modules={mod.name: result_data},
                raw=result_data,
                proxy=proxy or "",
            )

    async def run(self, creds: list[Credential]):
        tasks = [self.check_one(c) for c in creds]
        for coro in asyncio.as_completed(tasks):
            yield await coro
