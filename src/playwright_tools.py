import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from livekit.agents import RunContext, function_tool

from browser_manager import (
    MAX_ELEMENTS,
    MAX_HTML_CHARS,
    MAX_TEXT_CHARS,
    MAX_EVAL_RESULT_CHARS,
    format_error,
    get_browser_manager,
    shutdown_browser_manager,
    truncate,
    _artifacts_dir,
    _safe_filename,
)

logger = logging.getLogger("jarvis-playwright-tools")


async def _page(context: RunContext, page_id: str | None = None):
    manager = await get_browser_manager(context)
    return manager, *(await manager.get_page(page_id))


def _ok(message: str) -> str:
    return message


# ---------------- LIFECYCLE / NAVIGATION ----------------


@function_tool
async def browser_start(context: RunContext, headless: bool = False) -> str:
    """Start the Playwright browser session if it is not already running."""
    try:
        manager = await get_browser_manager(context)
        if manager.started:
            pid, page = await manager.get_page()
            return _ok(f"Browser already running. Active page: {await manager.page_summary(page, pid)}")
        if headless:
            os.environ["JARVIS_BROWSER_HEADLESS"] = "true"
        await manager.ensure_started()
        pid, page = await manager.get_page()
        return _ok(f"Browser started ({manager.engine}, headless={manager.headless}). Active: {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_start failed")
        return format_error("Browser start", e)


@function_tool
async def browser_close(context: RunContext) -> str:
    """Close the Playwright browser session and release all resources."""
    try:
        await shutdown_browser_manager(context)
        return _ok("Browser closed.")
    except Exception as e:
        logger.exception("browser_close failed")
        return format_error("Browser close", e)


@function_tool
async def browser_status(context: RunContext) -> str:
    """Get Playwright browser status, active page, and open tab count."""
    try:
        manager = await get_browser_manager(context)
        if not manager.started:
            return _ok("Browser is not running.")
        pages = await manager.list_pages()
        active = next((p for p in pages if p["active"]), None)
        active_desc = (
            f"{active['page_id']}: {active.get('title') or 'Untitled'} ({active.get('url') or 'about:blank'})"
            if active
            else "none"
        )
        return _ok(
            f"Browser running: engine={manager.engine}, headless={manager.headless}, "
            f"tabs={len(pages)}, active={active_desc}."
        )
    except Exception as e:
        logger.exception("browser_status failed")
        return format_error("Browser status", e)


@function_tool
async def browser_navigate(
    context: RunContext,
    url: str,
    wait_until: str = "domcontentloaded",
    page_id: str | None = None,
) -> str:
    """Navigate the active browser page to a URL. wait_until can be load, domcontentloaded, networkidle, or commit."""
    try:
        manager, pid, page = await _page(context, page_id)
        if wait_until not in {"load", "domcontentloaded", "networkidle", "commit"}:
            return "wait_until must be load, domcontentloaded, networkidle, or commit."
        await page.goto(url, wait_until=wait_until)
        return _ok(f"Navigated. {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_navigate failed")
        return format_error("Navigation", e)


@function_tool
async def browser_reload(context: RunContext, page_id: str | None = None) -> str:
    """Reload the current browser page."""
    try:
        manager, pid, page = await _page(context, page_id)
        await page.reload(wait_until="domcontentloaded")
        return _ok(f"Reloaded. {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_reload failed")
        return format_error("Reload", e)


@function_tool
async def browser_go_back(context: RunContext, page_id: str | None = None) -> str:
    """Go back in browser history."""
    try:
        manager, pid, page = await _page(context, page_id)
        resp = await page.go_back(wait_until="domcontentloaded")
        if resp is None:
            return _ok("No previous page in history.")
        return _ok(f"Went back. {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_go_back failed")
        return format_error("Go back", e)


@function_tool
async def browser_go_forward(context: RunContext, page_id: str | None = None) -> str:
    """Go forward in browser history."""
    try:
        manager, pid, page = await _page(context, page_id)
        resp = await page.go_forward(wait_until="domcontentloaded")
        if resp is None:
            return _ok("No forward page in history.")
        return _ok(f"Went forward. {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_go_forward failed")
        return format_error("Go forward", e)


# ---------------- TABS ----------------


@function_tool
async def browser_new_tab(context: RunContext, url: str | None = None) -> str:
    """Open a new browser tab, optionally navigating to a URL."""
    try:
        manager = await get_browser_manager(context)
        pid, page = await manager.new_page(url)
        return _ok(f"Opened new tab. {await manager.page_summary(page, pid)}")
    except Exception as e:
        logger.exception("browser_new_tab failed")
        return format_error("New tab", e)


@function_tool
async def browser_list_tabs(context: RunContext) -> str:
    """List open browser tabs with page IDs, titles, and URLs."""
    try:
        manager = await get_browser_manager(context)
        if not manager.started:
            return _ok("Browser is not running.")
        pages = await manager.list_pages()
        if not pages:
            return _ok("No open tabs.")
        lines = []
        for p in pages:
            marker = "*" if p["active"] else "-"
            title = (p.get("title") or "Untitled")[:60]
            url = (p.get("url") or "about:blank")[:80]
            lines.append(f"{marker} {p['page_id']}: {title} | {url}")
        return _ok("Tabs:\n" + "\n".join(lines))
    except Exception as e:
        logger.exception("browser_list_tabs failed")
        return format_error("List tabs", e)


@function_tool
async def browser_switch_tab(context: RunContext, page_id: str) -> str:
    """Switch the active browser tab by page_id."""
    try:
        manager = await get_browser_manager(context)
        page = await manager.switch_page(page_id)
        return _ok(f"Switched tab. {await manager.page_summary(page, page_id)}")
    except Exception as e:
        logger.exception("browser_switch_tab failed")
        return format_error("Switch tab", e)


@function_tool
async def browser_close_tab(context: RunContext, page_id: str | None = None) -> str:
    """Close a browser tab. Defaults to the active tab."""
    try:
        manager = await get_browser_manager(context)
        pid = await manager.close_page(page_id)
        active = manager.active_page_id or "none"
        return _ok(f"Closed {pid}. Active tab: {active}.")
    except Exception as e:
        logger.exception("browser_close_tab failed")
        return format_error("Close tab", e)


# ---------------- INTERACTION ----------------


@function_tool
async def browser_click(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    button: str = "left",
    double: bool = False,
    page_id: str | None = None,
) -> str:
    """Click an element. selector_type: css, text, label, placeholder, testid, or role (role:Name)."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        if button not in {"left", "right", "middle"}:
            return "button must be left, right, or middle."
        if double:
            await locator.dblclick(button=button)
        else:
            await locator.click(button=button)
        return _ok(f"Clicked {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_click failed")
        return format_error("Click", e)


@function_tool
async def browser_fill(
    context: RunContext,
    target: str,
    value: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Fill an input field with text, replacing existing content."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.fill(value)
        return _ok(f"Filled {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_fill failed")
        return format_error("Fill", e)


@function_tool
async def browser_type_text(
    context: RunContext,
    target: str,
    text: str,
    selector_type: str = "css",
    delay_ms: int = 20,
    page_id: str | None = None,
) -> str:
    """Type text into an element character by character. Useful when fill is not enough."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.click()
        await locator.type(text, delay=max(0, min(delay_ms, 500)))
        return _ok(f"Typed into {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_type_text failed")
        return format_error("Type text", e)


@function_tool
async def browser_press_key(
    context: RunContext,
    key: str,
    target: str | None = None,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Press a keyboard key or shortcut, optionally targeting an element first."""
    try:
        manager, pid, page = await _page(context, page_id)
        if target:
            locator = manager.resolve_locator(page, target, selector_type).first
            await locator.press(key)
        else:
            await page.keyboard.press(key)
        return _ok(f"Pressed {key} on {pid}.")
    except Exception as e:
        logger.exception("browser_press_key failed")
        return format_error("Press key", e)


@function_tool
async def browser_select_option(
    context: RunContext,
    target: str,
    value: str | None = None,
    label: str | None = None,
    index: int | None = None,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Select an option in a dropdown by value, label, or index."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        if value is not None:
            await locator.select_option(value=value)
        elif label is not None:
            await locator.select_option(label=label)
        elif index is not None:
            await locator.select_option(index=index)
        else:
            return "Provide value, label, or index."
        return _ok(f"Selected option in {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_select_option failed")
        return format_error("Select option", e)


@function_tool
async def browser_check(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Check a checkbox or radio button."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.check()
        return _ok(f"Checked {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_check failed")
        return format_error("Check", e)


@function_tool
async def browser_uncheck(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Uncheck a checkbox."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.uncheck()
        return _ok(f"Unchecked {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_uncheck failed")
        return format_error("Uncheck", e)


@function_tool
async def browser_hover(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Hover over an element."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.hover()
        return _ok(f"Hovered {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_hover failed")
        return format_error("Hover", e)


@function_tool
async def browser_drag_and_drop(
    context: RunContext,
    source: str,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Drag a source element to a target element."""
    try:
        manager, pid, page = await _page(context, page_id)
        src = manager.resolve_locator(page, source, selector_type).first
        dst = manager.resolve_locator(page, target, selector_type).first
        await src.drag_to(dst)
        return _ok(f"Dragged {source} to {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_drag_and_drop failed")
        return format_error("Drag and drop", e)


@function_tool
async def browser_scroll(
    context: RunContext,
    direction: str = "down",
    amount: int = 500,
    page_id: str | None = None,
) -> str:
    """Scroll the page. direction: up, down, top, bottom."""
    try:
        manager, pid, page = await _page(context, page_id)
        direction = direction.lower().strip()
        amount = max(100, min(int(amount), 5000))
        if direction == "down":
            await page.mouse.wheel(0, amount)
        elif direction == "up":
            await page.mouse.wheel(0, -amount)
        elif direction == "top":
            await page.evaluate("() => window.scrollTo(0, 0)")
        elif direction == "bottom":
            await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        else:
            return "direction must be up, down, top, or bottom."
        return _ok(f"Scrolled {direction} on {pid}.")
    except Exception as e:
        logger.exception("browser_scroll failed")
        return format_error("Scroll", e)


@function_tool
async def browser_scroll_into_view(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Scroll an element into view."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.scroll_into_view_if_needed()
        return _ok(f"Scrolled {target} into view on {pid}.")
    except Exception as e:
        logger.exception("browser_scroll_into_view failed")
        return format_error("Scroll into view", e)


@function_tool
async def browser_upload_file(
    context: RunContext,
    target: str,
    file_path: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Upload a file to a file input element. file_path must be a local path."""
    try:
        manager, pid, page = await _page(context, page_id)
        path = Path(file_path).expanduser()
        if not path.exists():
            return f"File not found: {path}"
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.set_input_files(str(path))
        return _ok(f"Uploaded {path.name} to {target} on {pid}.")
    except Exception as e:
        logger.exception("browser_upload_file failed")
        return format_error("Upload file", e)

# ---------------- EXTRACTION / INSPECTION ----------------


@function_tool
async def browser_get_page_info(context: RunContext, page_id: str | None = None) -> str:
    """Get current page URL, title, and viewport size."""
    try:
        manager, pid, page = await _page(context, page_id)
        title = await page.title()
        url = page.url
        viewport = page.viewport_size or {}
        return _ok(
            f"{pid}: title='{title}', url='{url}', viewport={viewport.get('width')}x{viewport.get('height')}."
        )
    except Exception as e:
        logger.exception("browser_get_page_info failed")
        return format_error("Get page info", e)


@function_tool
async def browser_get_text(
    context: RunContext,
    target: str | None = None,
    selector_type: str = "css",
    max_chars: int = MAX_TEXT_CHARS,
    page_id: str | None = None,
) -> str:
    """Get visible text from the page or a specific element. Output is truncated for voice use."""
    try:
        manager, pid, page = await _page(context, page_id)
        max_chars = max(200, min(int(max_chars), 12000))
        if target:
            locator = manager.resolve_locator(page, target, selector_type).first
            text = await locator.inner_text()
        else:
            text = await page.inner_text("body")
        text = " ".join(text.split())
        return _ok(f"Text from {pid}:\n{truncate(text, max_chars)}")
    except Exception as e:
        logger.exception("browser_get_text failed")
        return format_error("Get text", e)


@function_tool
async def browser_get_html(
    context: RunContext,
    target: str | None = None,
    selector_type: str = "css",
    outer: bool = True,
    max_chars: int = MAX_HTML_CHARS,
    page_id: str | None = None,
) -> str:
    """Get HTML from the page or a specific element. Output is truncated."""
    try:
        manager, pid, page = await _page(context, page_id)
        max_chars = max(200, min(int(max_chars), 12000))
        if target:
            locator = manager.resolve_locator(page, target, selector_type).first
            html = await locator.evaluate("(el, outer) => outer ? el.outerHTML : el.innerHTML", outer)
        else:
            html = await page.content()
        html = " ".join(html.split())
        return _ok(f"HTML from {pid}:\n{truncate(html, max_chars)}")
    except Exception as e:
        logger.exception("browser_get_html failed")
        return format_error("Get HTML", e)


@function_tool
async def browser_get_attribute(
    context: RunContext,
    target: str,
    attribute: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Get an attribute value from an element."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        value = await locator.get_attribute(attribute)
        return _ok(f"{attribute} on {target} ({pid}): {value}")
    except Exception as e:
        logger.exception("browser_get_attribute failed")
        return format_error("Get attribute", e)


@function_tool
async def browser_get_value(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Get the current input value from an element."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type).first
        value = await locator.input_value()
        return _ok(f"Value of {target} ({pid}): {truncate(value, 1000)}")
    except Exception as e:
        logger.exception("browser_get_value failed")
        return format_error("Get value", e)


@function_tool
async def browser_query_elements(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    max_elements: int = MAX_ELEMENTS,
    page_id: str | None = None,
) -> str:
    """Query elements and return a compact summary (tag, text, key attributes)."""
    try:
        manager, pid, page = await _page(context, page_id)
        locator = manager.resolve_locator(page, target, selector_type)
        count = await locator.count()
        max_elements = max(1, min(int(max_elements), 50))
        limit = min(count, max_elements)
        items = []
        for i in range(limit):
            item = await locator.nth(i).evaluate(
                r"""el => {
                  const text = (el.innerText || el.textContent || '').replace(/\s+/g,' ').trim().slice(0,120);
                  return {
                    tag: el.tagName.toLowerCase(),
                    text,
                    id: el.id || null,
                    name: el.getAttribute('name'),
                    role: el.getAttribute('role'),
                    type: el.getAttribute('type'),
                    href: el.getAttribute('href'),
                    ariaLabel: el.getAttribute('aria-label')
                  };
                }"""
            )
            items.append(item)
        return _ok(f"Found {count} elements on {pid}; showing {limit}:\n{json.dumps(items, ensure_ascii=False)}")
    except Exception as e:
        logger.exception("browser_query_elements failed")
        return format_error("Query elements", e)


@function_tool
async def browser_snapshot_accessibility(context: RunContext, page_id: str | None = None) -> str:
    """Get an accessibility snapshot of the page for understanding structure and interactive elements."""
    try:
        manager, pid, page = await _page(context, page_id)
        snapshot = await page.accessibility.snapshot()
        text = json.dumps(snapshot, ensure_ascii=False)
        return _ok(f"Accessibility snapshot for {pid}:\n{truncate(text, 8000)}")
    except Exception as e:
        logger.exception("browser_snapshot_accessibility failed")
        return format_error("Accessibility snapshot", e)


# ---------------- WAITING ----------------


@function_tool
async def browser_wait_for_selector(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    state: str = "visible",
    timeout_ms: int = 10000,
    page_id: str | None = None,
) -> str:
    """Wait for an element to reach a state: attached, detached, visible, or hidden."""
    try:
        manager, pid, page = await _page(context, page_id)
        if state not in {"attached", "detached", "visible", "hidden"}:
            return "state must be attached, detached, visible, or hidden."
        locator = manager.resolve_locator(page, target, selector_type).first
        await locator.wait_for(state=state, timeout=max(0, min(int(timeout_ms), 60000)))
        return _ok(f"Element {target} is {state} on {pid}.")
    except Exception as e:
        logger.exception("browser_wait_for_selector failed")
        return format_error("Wait for selector", e)


@function_tool
async def browser_wait_for_text(
    context: RunContext,
    text: str,
    timeout_ms: int = 10000,
    page_id: str | None = None,
) -> str:
    """Wait for text to appear on the page."""
    try:
        manager, pid, page = await _page(context, page_id)
        await page.get_by_text(text).first.wait_for(state="visible", timeout=max(0, min(int(timeout_ms), 60000)))
        return _ok(f"Found text on {pid}.")
    except Exception as e:
        logger.exception("browser_wait_for_text failed")
        return format_error("Wait for text", e)


@function_tool
async def browser_wait_for_url(
    context: RunContext,
    url_or_pattern: str,
    timeout_ms: int = 10000,
    page_id: str | None = None,
) -> str:
    """Wait for the page URL to match a string or glob pattern."""
    try:
        manager, pid, page = await _page(context, page_id)
        await page.wait_for_url(url_or_pattern, timeout=max(0, min(int(timeout_ms), 60000)))
        return _ok(f"URL matched on {pid}: {page.url}")
    except Exception as e:
        logger.exception("browser_wait_for_url failed")
        return format_error("Wait for URL", e)


@function_tool
async def browser_wait_ms(context: RunContext, ms: int = 1000) -> str:
    """Wait for a short fixed time in milliseconds (max 10000)."""
    ms = max(0, min(int(ms), 10000))
    await asyncio.sleep(ms / 1000)
    return _ok(f"Waited {ms} ms.")


# ---------------- ARTIFACTS ----------------


@function_tool
async def browser_screenshot(
    context: RunContext,
    target: str | None = None,
    selector_type: str = "css",
    full_page: bool = False,
    page_id: str | None = None,
) -> str:
    """Take a screenshot of the page or a specific element and save it locally."""
    try:
        manager, pid, page = await _page(context, page_id)
        artifacts = _artifacts_dir()
        artifacts.mkdir(parents=True, exist_ok=True)
        path = artifacts / _safe_filename("browser", "png")
        if target:
            locator = manager.resolve_locator(page, target, selector_type).first
            await locator.screenshot(path=str(path))
        else:
            await page.screenshot(path=str(path), full_page=full_page)
        return _ok(f"Screenshot saved: {path} ({pid})")
    except Exception as e:
        logger.exception("browser_screenshot failed")
        return format_error("Screenshot", e)


@function_tool
async def browser_pdf(context: RunContext, page_id: str | None = None) -> str:
    """Save the current page as a PDF. Works best in headless Chromium."""
    try:
        manager, pid, page = await _page(context, page_id)
        artifacts = _artifacts_dir()
        artifacts.mkdir(parents=True, exist_ok=True)
        path = artifacts / _safe_filename("page", "pdf")
        await page.pdf(path=str(path))
        return _ok(f"PDF saved: {path} ({pid})")
    except Exception as e:
        logger.exception("browser_pdf failed")
        return format_error("PDF", e)


# ---------------- ADVANCED / FULL CONTROL ----------------


@function_tool
async def browser_evaluate_js(
    context: RunContext,
    expression: str,
    page_id: str | None = None,
) -> str:
    """Evaluate JavaScript in the page context and return the JSON-serializable result. Use for advanced control not covered by other tools."""
    try:
        manager, pid, page = await _page(context, page_id)
        result = await page.evaluate(expression)
        try:
            text = json.dumps(result, ensure_ascii=False)
        except Exception:
            text = str(result)
        return _ok(f"JS result on {pid}:\n{truncate(text, MAX_EVAL_RESULT_CHARS)}")
    except Exception as e:
        logger.exception("browser_evaluate_js failed")
        return format_error("Evaluate JS", e)


@function_tool
async def browser_handle_dialog(
    context: RunContext,
    action: str = "dismiss",
    prompt_text: str = "",
) -> str:
    """Configure how the next browser dialog is handled: accept or dismiss. Optionally provide prompt text for prompt dialogs."""
    try:
        manager = await get_browser_manager(context)
        action = action.lower().strip()
        if action not in {"accept", "dismiss"}:
            return "action must be accept or dismiss."
        manager.dialog_action = action
        manager.dialog_prompt_text = prompt_text
        last = manager.last_dialog
        last_desc = f" Last dialog: {last.kind} '{last.message}' ({last.handled})." if last else ""
        return _ok(f"Next dialog will be {action}.{last_desc}")
    except Exception as e:
        logger.exception("browser_handle_dialog failed")
        return format_error("Handle dialog", e)


@function_tool
async def browser_set_viewport(
    context: RunContext,
    width: int,
    height: int,
    page_id: str | None = None,
) -> str:
    """Set the browser viewport size."""
    try:
        manager, pid, page = await _page(context, page_id)
        width = max(320, min(int(width), 3840))
        height = max(240, min(int(height), 2160))
        await page.set_viewport_size({"width": width, "height": height})
        return _ok(f"Viewport set to {width}x{height} on {pid}.")
    except Exception as e:
        logger.exception("browser_set_viewport failed")
        return format_error("Set viewport", e)


@function_tool
async def browser_cookies_get(context: RunContext, page_id: str | None = None) -> str:
    """Get cookies for the current browser context."""
    try:
        manager, pid, page = await _page(context, page_id)
        cookies = await manager.context.cookies(page.url) if manager.context else []
        text = json.dumps(cookies, ensure_ascii=False)
        return _ok(f"Cookies for {pid}:\n{truncate(text, 6000)}")
    except Exception as e:
        logger.exception("browser_cookies_get failed")
        return format_error("Get cookies", e)


@function_tool
async def browser_cookies_clear(context: RunContext) -> str:
    """Clear all browser cookies in the current context."""
    try:
        manager = await get_browser_manager(context)
        await manager.ensure_started()
        if manager.context:
            await manager.context.clear_cookies()
        return _ok("Cookies cleared.")
    except Exception as e:
        logger.exception("browser_cookies_clear failed")
        return format_error("Clear cookies", e)


@function_tool
async def browser_storage_get(
    context: RunContext,
    kind: str = "local",
    page_id: str | None = None,
) -> str:
    """Get localStorage or sessionStorage from the current page. kind: local or session."""
    try:
        manager, pid, page = await _page(context, page_id)
        kind = kind.lower().strip()
        if kind not in {"local", "session"}:
            return "kind must be local or session."
        storage = "localStorage" if kind == "local" else "sessionStorage"
        data = await page.evaluate(f"() => Object.fromEntries(Object.entries({storage}))")
        return _ok(f"{kind}Storage on {pid}:\n{truncate(json.dumps(data, ensure_ascii=False), 6000)}")
    except Exception as e:
        logger.exception("browser_storage_get failed")
        return format_error("Get storage", e)


@function_tool
async def browser_storage_set(
    context: RunContext,
    key: str,
    value: str,
    kind: str = "local",
    page_id: str | None = None,
) -> str:
    """Set a localStorage or sessionStorage key. kind: local or session."""
    try:
        manager, pid, page = await _page(context, page_id)
        kind = kind.lower().strip()
        if kind not in {"local", "session"}:
            return "kind must be local or session."
        storage = "localStorage" if kind == "local" else "sessionStorage"
        await page.evaluate(f"([k,v]) => {storage}.setItem(k,v)", [key, value])
        return _ok(f"Set {kind}Storage key '{key}' on {pid}.")
    except Exception as e:
        logger.exception("browser_storage_set failed")
        return format_error("Set storage", e)


@function_tool
async def browser_storage_clear(
    context: RunContext,
    kind: str = "local",
    page_id: str | None = None,
) -> str:
    """Clear localStorage or sessionStorage on the current page. kind: local or session."""
    try:
        manager, pid, page = await _page(context, page_id)
        kind = kind.lower().strip()
        if kind not in {"local", "session"}:
            return "kind must be local or session."
        storage = "localStorage" if kind == "local" else "sessionStorage"
        await page.evaluate(f"() => {storage}.clear()")
        return _ok(f"Cleared {kind}Storage on {pid}.")
    except Exception as e:
        logger.exception("browser_storage_clear failed")
        return format_error("Clear storage", e)


@function_tool
async def browser_network_log(context: RunContext, limit: int = 20) -> str:
    """Get recent browser network request log entries."""
    try:
        manager = await get_browser_manager(context)
        if not manager.started:
            return _ok("Browser is not running.")
        limit = max(1, min(int(limit), 50))
        items = manager.network_log[-limit:]
        return _ok(f"Recent network entries ({len(items)}):\n{json.dumps(items, ensure_ascii=False)}")
    except Exception as e:
        logger.exception("browser_network_log failed")
        return format_error("Network log", e)


@function_tool
async def browser_download(
    context: RunContext,
    target: str,
    selector_type: str = "css",
    page_id: str | None = None,
) -> str:
    """Click an element and capture a resulting download, saving it to the artifacts directory."""
    try:
        manager, pid, page = await _page(context, page_id)
        artifacts = _artifacts_dir()
        artifacts.mkdir(parents=True, exist_ok=True)
        locator = manager.resolve_locator(page, target, selector_type).first
        async with page.expect_download() as dl_info:
            await locator.click()
        download = await dl_info.value
        suggested = download.suggested_filename or _safe_filename("download", "bin")
        path = artifacts / suggested
        await download.save_as(str(path))
        return _ok(f"Download saved: {path} ({pid})")
    except Exception as e:
        logger.exception("browser_download failed")
        return format_error("Download", e)


# Convenient list for agent registration
PLAYWRIGHT_TOOLS = [
    browser_start,
    browser_close,
    browser_status,
    browser_navigate,
    browser_reload,
    browser_go_back,
    browser_go_forward,
    browser_new_tab,
    browser_list_tabs,
    browser_switch_tab,
    browser_close_tab,
    browser_click,
    browser_fill,
    browser_type_text,
    browser_press_key,
    browser_select_option,
    browser_check,
    browser_uncheck,
    browser_hover,
    browser_drag_and_drop,
    browser_scroll,
    browser_scroll_into_view,
    browser_upload_file,
    browser_get_page_info,
    browser_get_text,
    browser_get_html,
    browser_get_attribute,
    browser_get_value,
    browser_query_elements,
    browser_snapshot_accessibility,
    browser_wait_for_selector,
    browser_wait_for_text,
    browser_wait_for_url,
    browser_wait_ms,
    browser_screenshot,
    browser_pdf,
    browser_evaluate_js,
    browser_handle_dialog,
    browser_set_viewport,
    browser_cookies_get,
    browser_cookies_clear,
    browser_storage_get,
    browser_storage_set,
    browser_storage_clear,
    browser_network_log,
    browser_download,
]
