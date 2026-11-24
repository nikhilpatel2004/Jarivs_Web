
import asyncio
import logging
import os
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

from ddgs import DDGS
from livekit.agents import function_tool, RunContext


class _DesktopUnavailable:
    """Placeholder so this module imports on headless/cloud hosts."""

    FAILSAFE = False
    PAUSE = 0

    def __getattr__(self, name):
        raise RuntimeError("Desktop control is not available on this host.")


try:
    import pyautogui
except Exception:  # no DISPLAY on headless/cloud hosts
    pyautogui = _DesktopUnavailable()

try:
    import pygetwindow as gw
except Exception:  # no DISPLAY on headless/cloud hosts
    gw = _DesktopUnavailable()

logger = logging.getLogger("jarvis-tools")

# ---------------- SAFETY CONFIGURATION ----------------

# Moving mouse to the top-left corner aborts PyAutoGUI actions.
pyautogui.FAILSAFE = True

# Small delay between automation actions.
pyautogui.PAUSE = 0.3

SCREENSHOT_DIR = Path.home() / "Pictures" / "JarvisScreenshots"

# ---------------- WEB SEARCH ----------------

@function_tool
async def search_web(context: RunContext, query: str) -> str:
    """Search the internet for information, news and facts."""
    logger.info("SEARCH_WEB: %s", query)

    try:
        results = await asyncio.to_thread(
            lambda: DDGS().text(query, max_results=5)
        )

        if not results:
            return "No search results found."

        output = []

        for item in results:
            output.append(
                f"Title: {item.get('title', '')}\n"
                f"Info: {item.get('body', '')}\n"
                f"URL: {item.get('href', '')}"
            )

        return "\n\n".join(output)

    except Exception:
        logger.exception("Web search failed")
        return "Web search failed. Please try again."


# ---------------- BROWSER OPEN ----------------

@function_tool
async def open_browser(context: RunContext, query: str) -> str:
    """Open a website or search query in the default browser."""

    query = query.strip()

    if not query:
        return "Please provide a website or search query."

    if query.startswith(("https://", "http://")):
        url = query

    elif query.lower() in ["google", "open google"]:
        url = "https://www.google.com"

    elif query.lower() in ["youtube", "open youtube"]:
        url = "https://www.youtube.com"

    elif query.lower() in ["duckduckgo", "open duckduckgo"]:
        url = "https://duckduckgo.com"

    else:
        url = "https://www.google.com/search?q=" + quote_plus(query)

    try:
        success = await asyncio.to_thread(webbrowser.open, url, 2)

        if success:
            return f"Browser opened: {url}"

        return "Could not open the browser."

    except Exception:
        logger.exception("Browser opening failed")
        return "Browser opening failed."


# ---------------- SCROLL CONTROL ----------------

@function_tool
async def scroll_screen(context: RunContext, direction: str, amount: int = 5) -> str:
    """
    Scroll the active window up or down.

    direction: up or down.
    amount: scroll intensity between 1 and 20.
    """

    direction = direction.lower().strip()

    if direction not in ("up", "down"):
        return "Direction must be up or down."

    amount = max(1, min(int(amount), 20))

    scroll_value = amount if direction == "up" else -amount

    try:
        await asyncio.to_thread(pyautogui.scroll, scroll_value)
        return f"Scrolled {direction}."

    except Exception:
        logger.exception("Scroll failed")
        return "Scroll failed."


# ---------------- MOUSE MOVEMENT ----------------

@function_tool
async def move_mouse(context: RunContext, direction: str, distance: int = 300) -> str:
    """Move the mouse up, down, left or right."""

    direction = direction.lower().strip()
    distance = max(1, min(int(distance), 1000))

    movements = {
        "up": (0, -distance),
        "down": (0, distance),
        "left": (-distance, 0),
        "right": (distance, 0),
    }

    if direction not in movements:
        return "Direction must be up, down, left or right."

    dx, dy = movements[direction]

    try:
        await asyncio.to_thread(pyautogui.moveRel, dx, dy, 0.3)
        return f"Mouse moved {direction}."

    except Exception:
        logger.exception("Mouse movement failed")
        return "Mouse movement failed."


# ---------------- MOUSE CLICK ----------------

@function_tool
async def click_mouse(
    context: RunContext,
    click_type: str = "single"
) -> str:
    """Click or double click at the current mouse position."""

    click_type = click_type.lower().strip()

    if click_type not in ("single", "double", "right"):
        return "Use single, double or right."

    try:
        action = {
            "single": pyautogui.click,
            "double": pyautogui.doubleClick,
            "right": pyautogui.rightClick,
        }[click_type]
        await asyncio.to_thread(action)
        return f"{click_type} click completed."

    except Exception:
        logger.exception("Mouse click failed")
        return "Mouse click failed."


# ---------------- KEYBOARD CONTROL ----------------

@function_tool
async def press_key(context: RunContext, key: str):
    """
    Press keyboard keys or keyboard shortcuts.
    Examples: enter, escape, ctrl+c, ctrl+v, alt+tab, ctrl+shift+t
    """
    key = key.strip().lower().replace(" ", "")

    allowed_keys = {
        "enter", "escape", "esc", "tab", "space",
        "backspace", "delete", "insert",
        "up", "down", "left", "right",
        "home", "end", "pageup", "pagedown",
        "capslock", "numlock", "scrolllock",

        *[f"f{i}" for i in range(1, 13)],

        "ctrl", "shift", "alt", "win",

        "ctrl+c", "ctrl+v", "ctrl+x", "ctrl+a",
        "ctrl+z", "ctrl+y", "ctrl+s", "ctrl+f",
        "ctrl+p", "ctrl+w", "ctrl+t",
        "ctrl+shift+t", "ctrl+shift+w",

        "alt+tab", "alt+f4",
        "win+d", "win+e", "win+r",

        "ctrl+tab", "ctrl+shift+tab",
        "ctrl+1", "ctrl+2", "ctrl+3",
        "ctrl+4", "ctrl+5", "ctrl+6",
        "ctrl+7", "ctrl+8", "ctrl+9",
    }

    if key not in allowed_keys:
        return f"Key or shortcut not allowed: {key}"

    try:
        if "+" in key:
            keys = key.split("+")
            await asyncio.to_thread(pyautogui.hotkey, *keys)
        else:
            await asyncio.to_thread(pyautogui.press, key)

        return f"Successfully pressed {key}"

    except Exception as e:
        logger.exception("Keyboard action failed")
        return f"Keyboard error: {e}"

# ---------------- TYPE TEXT ----------------

@function_tool
async def type_text(context: RunContext, text: str) -> str:
    """Type text into the currently active window."""

    if len(text) > 2000:
        return "Text is too long. Maximum length is 2000 characters."

    try:
        await asyncio.to_thread(pyautogui.write, text, interval=0.02)
        return "Text typed."

    except Exception:
        logger.exception("Typing failed")
        return "Typing failed."


# ---------------- SCREEN INFORMATION ----------------

@function_tool
async def get_screen_info(context: RunContext) -> str:
    """Return screen dimensions and current mouse position."""

    try:
        width, height = pyautogui.size()
        x, y = pyautogui.position()

        return (
            f"Screen size: {width}x{height}. "
            f"Mouse position: x={x}, y={y}."
        )

    except Exception:
        logger.exception("Screen information failed")
        return "Could not read screen information."


# ---------------- SCREENSHOT ----------------

@function_tool
async def take_screenshot(context: RunContext) -> str:
    """Capture the desktop and save a screenshot locally."""

    try:
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

        filename = datetime.now().strftime(
            "jarvis_%Y%m%d_%H%M%S.png"
        )

        path = SCREENSHOT_DIR / filename

        await asyncio.to_thread(
            lambda: pyautogui.screenshot().save(path)
        )

        return f"Screenshot saved locally: {path}"

    except Exception:
        logger.exception("Screenshot failed")
        return "Screenshot failed."


# ---------------- ACTIVE WINDOW ----------------

@function_tool
async def get_active_window(context: RunContext) -> str:
    """Get the currently active Windows application title."""

    try:
        window = await asyncio.to_thread(gw.getActiveWindow)

        if window:
            return f"Active window: {window.title}"

        return "Could not detect an active window."

    except Exception:
        logger.exception("Active window detection failed")
        return "Active window detection failed."
