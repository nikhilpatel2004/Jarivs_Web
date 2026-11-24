import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

logger = logging.getLogger("jarvis-browser")

DEFAULT_TIMEOUT_MS = 10_000
MAX_TEXT_CHARS = 4_000
MAX_HTML_CHARS = 6_000
MAX_ELEMENTS = 20
MAX_NETWORK_LOG = 50
MAX_EVAL_RESULT_CHARS = 4_000


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _artifacts_dir() -> Path:
    raw = os.getenv("JARVIS_BROWSER_ARTIFACTS_DIR")
    if raw:
        return Path(raw).expanduser()
    return Path.home() / "Pictures" / "JarvisBrowser"


def _safe_filename(prefix: str, suffix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"{prefix}_{ts}.{suffix.lstrip('.')}"


@dataclass
class DialogRecord:
    kind: str
    message: str
    default_value: str = ""
    handled: str = "pending"


@dataclass
class BrowserManager:
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: BrowserContext | None = None
    pages: dict[str, Page] = field(default_factory=dict)
    active_page_id: str | None = None
    page_counter: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    network_log: list[dict[str, Any]] = field(default_factory=list)
    last_dialog: DialogRecord | None = None
    dialog_action: str = "dismiss"  # dismiss | accept
    dialog_prompt_text: str = ""
    started: bool = False

    @property
    def engine(self) -> str:
        return os.getenv("JARVIS_BROWSER_ENGINE", "chromium").strip().lower()

    @property
    def headless(self) -> bool:
        return _env_bool("JARVIS_BROWSER_HEADLESS", False)

    @property
    def navigation_timeout_ms(self) -> int:
        return _env_int("JARVIS_BROWSER_NAVIGATION_TIMEOUT_MS", 30_000)

    @property
    def action_timeout_ms(self) -> int:
        return _env_int("JARVIS_BROWSER_ACTION_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)

    async def ensure_started(self) -> "BrowserManager":
        async with self.lock:
            if self.started and self.browser and self.context:
                return self
            self.playwright = await async_playwright().start()
            engine = self.engine
            launcher = {
                "chromium": self.playwright.chromium,
                "firefox": self.playwright.firefox,
                "webkit": self.playwright.webkit,
            }.get(engine)
            if launcher is None:
                raise ValueError(
                    f"Unsupported browser engine '{engine}'. Use chromium, firefox, or webkit."
                )

            launch_args: dict[str, Any] = {"headless": self.headless}
            user_data_dir = os.getenv("JARVIS_BROWSER_USER_DATA_DIR")
            if user_data_dir:
                user_data_dir = str(Path(user_data_dir).expanduser())
                Path(user_data_dir).mkdir(parents=True, exist_ok=True)
                self.context = await launcher.launch_persistent_context(
                    user_data_dir,
                    **launch_args,
                )
                self.browser = self.context.browser
            else:
                self.browser = await launcher.launch(**launch_args)
                self.context = await self.browser.new_context()

            self.context.set_default_timeout(self.action_timeout_ms)
            self.context.set_default_navigation_timeout(self.navigation_timeout_ms)
            self.context.on("page", self._on_page)
            self.context.on("requestfinished", self._on_request_finished)
            self.context.on("requestfailed", self._on_request_failed)

            existing = self.context.pages
            if existing:
                for page in existing:
                    self._register_page(page)
                self.active_page_id = next(iter(self.pages.keys()), None)
            else:
                page = await self.context.new_page()
                self._register_page(page)
                self.active_page_id = next(iter(self.pages.keys()), None)

            self.started = True
            logger.info("Browser started: engine=%s headless=%s", engine, self.headless)
            return self

    def _register_page(self, page: Page) -> str:
        for pid, existing in self.pages.items():
            if existing is page:
                return pid
        self.page_counter += 1
        page_id = f"page-{self.page_counter}"
        self.pages[page_id] = page
        page.on("dialog", lambda dialog: asyncio.create_task(self._handle_dialog(dialog)))
        page.on("close", lambda: self._on_page_close(page))
        return page_id

    def _on_page(self, page: Page) -> None:
        page_id = self._register_page(page)
        self.active_page_id = page_id
        logger.info("New browser page registered: %s", page_id)

    def _on_page_close(self, page: Page) -> None:
        for pid, existing in list(self.pages.items()):
            if existing is page:
                del self.pages[pid]
                if self.active_page_id == pid:
                    self.active_page_id = next(iter(self.pages.keys()), None)
                break

    async def _handle_dialog(self, dialog: Any) -> None:
        self.last_dialog = DialogRecord(
            kind=dialog.type,
            message=dialog.message,
            default_value=getattr(dialog, "default_value", "") or "",
        )
        try:
            if self.dialog_action == "accept":
                await dialog.accept(self.dialog_prompt_text)
                self.last_dialog.handled = "accepted"
            else:
                await dialog.dismiss()
                self.last_dialog.handled = "dismissed"
        except Exception:
            logger.exception("Failed to handle dialog")
            if self.last_dialog:
                self.last_dialog.handled = "error"

    def _on_request_finished(self, request: Any) -> None:
        self._append_network_log(request, status="finished")

    def _on_request_failed(self, request: Any) -> None:
        failure = ""
        try:
            failure = request.failure or ""
        except Exception:
            failure = ""
        self._append_network_log(request, status="failed", failure=str(failure))

    def _append_network_log(self, request: Any, status: str, failure: str = "") -> None:
        entry = {
            "status": status,
            "method": getattr(request, "method", ""),
            "url": getattr(request, "url", ""),
            "resource_type": getattr(request, "resource_type", ""),
        }
        if failure:
            entry["failure"] = failure
        self.network_log.append(entry)
        if len(self.network_log) > MAX_NETWORK_LOG:
            self.network_log = self.network_log[-MAX_NETWORK_LOG:]

    async def shutdown(self) -> None:
        async with self.lock:
            errors: list[str] = []
            try:
                if self.context:
                    await self.context.close()
            except Exception as e:
                errors.append(f"context: {e}")
            try:
                if self.browser and self.browser.is_connected():
                    await self.browser.close()
            except Exception as e:
                errors.append(f"browser: {e}")
            try:
                if self.playwright:
                    await self.playwright.stop()
            except Exception as e:
                errors.append(f"playwright: {e}")
            self.playwright = None
            self.browser = None
            self.context = None
            self.pages.clear()
            self.active_page_id = None
            self.started = False
            self.network_log.clear()
            if errors:
                logger.warning("Browser shutdown errors: %s", "; ".join(errors))

    def _resolve_page(self, page_id: str | None = None) -> tuple[str, Page]:
        if not self.started or not self.context:
            raise RuntimeError("Browser is not started. Call browser_start first.")
        if page_id:
            page = self.pages.get(page_id)
            if not page:
                raise ValueError(f"Unknown page_id '{page_id}'.")
            return page_id, page
        if self.active_page_id and self.active_page_id in self.pages:
            return self.active_page_id, self.pages[self.active_page_id]
        if self.pages:
            pid = next(iter(self.pages.keys()))
            self.active_page_id = pid
            return pid, self.pages[pid]
        raise RuntimeError("No browser page available.")

    async def get_page(self, page_id: str | None = None) -> tuple[str, Page]:
        await self.ensure_started()
        return self._resolve_page(page_id)

    async def new_page(self, url: str | None = None) -> tuple[str, Page]:
        await self.ensure_started()
        assert self.context is not None
        page = await self.context.new_page()
        page_id = self._register_page(page)
        self.active_page_id = page_id
        if url:
            await page.goto(url, wait_until="domcontentloaded")
        return page_id, page

    async def list_pages(self) -> list[dict[str, Any]]:
        await self.ensure_started()
        result = []
        for pid, page in self.pages.items():
            title = ""
            url = ""
            try:
                title = await page.title()
            except Exception:
                pass
            try:
                url = page.url
            except Exception:
                pass
            result.append(
                {
                    "page_id": pid,
                    "active": pid == self.active_page_id,
                    "title": title,
                    "url": url,
                }
            )
        return result

    async def close_page(self, page_id: str | None = None) -> str:
        await self.ensure_started()
        pid, page = self._resolve_page(page_id)
        await page.close()
        return pid

    async def switch_page(self, page_id: str) -> Page:
        await self.ensure_started()
        pid, page = self._resolve_page(page_id)
        self.active_page_id = pid
        await page.bring_to_front()
        return page

    def resolve_locator(self, page: Page, target: str, selector_type: str = "css") -> Any:
        selector_type = (selector_type or "css").strip().lower()
        target = target.strip()
        if not target:
            raise ValueError("Target selector is required.")
        if selector_type == "css":
            return page.locator(target)
        if selector_type == "text":
            return page.get_by_text(target, exact=False)
        if selector_type == "label":
            return page.get_by_label(target, exact=False)
        if selector_type == "placeholder":
            return page.get_by_placeholder(target, exact=False)
        if selector_type == "testid":
            return page.get_by_test_id(target)
        if selector_type == "role":
            # format: "button:Submit" or "button=Submit" or just "button"
            role = target
            name = None
            for sep in [":", "="]:
                if sep in target:
                    role, name = target.split(sep, 1)
                    role = role.strip()
                    name = name.strip()
                    break
            role = role.strip().lower().replace(" ", "-")
            if name:
                return page.get_by_role(role, name=name, exact=False)  # type: ignore[arg-type]
            return page.get_by_role(role)  # type: ignore[arg-type]
        raise ValueError(
            "selector_type must be one of: css, text, label, placeholder, testid, role."
        )

    async def page_summary(self, page: Page, page_id: str) -> str:
        title = ""
        url = ""
        try:
            title = await page.title()
        except Exception:
            pass
        try:
            url = page.url
        except Exception:
            pass
        return f"[{page_id}] {title or 'Untitled'} - {url}"


_managers: dict[int, BrowserManager] = {}
_managers_lock = asyncio.Lock()


def _manager_key(context_or_session: Any) -> int:
    # Tool RunContext has .session (AgentSession). Prefer it for stable keying.
    session = getattr(context_or_session, "session", None)
    if session is not None:
        return id(session)
    return id(context_or_session)


async def get_browser_manager(context: Any) -> BrowserManager:
    key = _manager_key(context)
    async with _managers_lock:
        manager = _managers.get(key)
        if manager is None:
            manager = BrowserManager()
            _managers[key] = manager
        return manager


async def shutdown_browser_manager(context_or_session: Any) -> None:
    key = _manager_key(context_or_session)
    async with _managers_lock:
        manager = _managers.pop(key, None)
    if manager:
        await manager.shutdown()


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated, {len(text)} chars total]"


def format_error(action: str, exc: Exception) -> str:
    if isinstance(exc, PlaywrightTimeoutError):
        return f"{action} timed out. Check selector/page state and try again."
    msg = str(exc).strip()
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > 300:
        msg = msg[:300] + "..."
    return f"{action} failed: {msg}"