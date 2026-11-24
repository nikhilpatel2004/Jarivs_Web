
import logging
import os
import textwrap

from dotenv import load_dotenv

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    STTContextOptions,
    TurnHandlingOptions,
    cli,
    inference,
    room_io,
)

from livekit.plugins import ai_coustics, openai, assemblyai

from browser_manager import shutdown_browser_manager
from playwright_tools import PLAYWRIGHT_TOOLS
from tools import (
    search_web,
    open_browser,
    scroll_screen,
    move_mouse,
    click_mouse,
    press_key,
    type_text,
    get_screen_info,
    take_screenshot,
    get_active_window,
)

load_dotenv(".env.local")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent")


class Assistant(Agent):
    def __init__(self):
        super().__init__(
            tools=[
                search_web,
                open_browser,
                scroll_screen,
                move_mouse,
                click_mouse,
                press_key,
                type_text,
                get_screen_info,
                take_screenshot,
                get_active_window,
                *PLAYWRIGHT_TOOLS,
            ],
            instructions=textwrap.dedent("""
                You are Jarvis, a Windows desktop voice assistant.

                Speak naturally, confidently and concisely.
                Always respond in the language the user is speaking.

                DESKTOP CONTROL:

                1. Scroll:
                   Use scroll_screen for scrolling.
                   Directions are up or down.
                   Amount must be between 1 and 20.
                   Use smaller amounts for slow scrolling.

                2. Mouse:
                   Use move_mouse for moving the cursor.
                   Use click_mouse for clicking at the current cursor position.
                   Never claim you clicked something unless the tool succeeds.

                3. Keyboard:
                   Use press_key for supported keys and shortcuts.
                   Use type_text to type text into the currently focused window.
                   Before typing, make sure the user has selected the intended window.

                4. Screenshots:
                   Use take_screenshot when the user asks to capture the screen.
                   Screenshots are saved locally.
                   Do not claim to visually inspect a screenshot unless an image-reading
                   capability is actually available.

                5. Screen information:
                   Use get_screen_info for screen size and mouse position.
                   Use get_active_window to identify the active application.

                6. Browser:
                   Use open_browser to open websites or perform browser searches.
                   Use search_web for researching information.

                7. Browser control (Playwright):
                   Use browser_* tools for full interactive browser control.
                   Start with browser_start or browser_navigate when needed.
                   Use browser_snapshot_accessibility or browser_get_text before browser_get_html.
                   Use browser_query_elements to find clickable/fillable elements.
                   For interactions, prefer clear selectors; selector_type supports css, text, label, placeholder, testid, role.
                   After navigation or major actions, report the page title/URL briefly.
                   Use browser_screenshot/browser_pdf for captures; report saved path.
                   Use browser_evaluate_js only when no dedicated tool covers the need.
                   Close the browser with browser_close when the user is done.

                SAFETY:

                - Never pretend an action succeeded if the tool failed.
                - Do not perform financial transactions, purchases, password entry,
                  account deletion, or other sensitive browser actions without explicit user confirmation.
                - Do not execute destructive actions.
                - If the target of an action is unclear, ask the user.
                - Before filling sensitive fields or submitting important forms, confirm intent.
                - Keep action responses short and voice-friendly.
            """),
        )


server = AgentServer()


@server.rtc_session(agent_name="my-agent")
async def my_agent(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    logger.info("Jarvis session starting")

    required_vars = [
        "OMNIROUTE_API_KEY",
        "OMNIROUTE_BASE_URL",
        "OMNIROUTE_MODEL",
    ]

    missing_vars = [
        name for name in required_vars if not os.getenv(name)
    ]

    if missing_vars:
        raise RuntimeError(
            f"Missing environment variables: {', '.join(missing_vars)}"
        )

    session = AgentSession(
        stt=assemblyai.STT(
            model="assemblyai-stt-3-7-realtime-agent",
        ),

        llm=openai.LLM(
            model=os.getenv("OMNIROUTE_MODEL"),
            base_url=os.getenv("OMNIROUTE_BASE_URL"),
            api_key=os.getenv("OMNIROUTE_API_KEY"),
        ),

        tts="fishaudio/s2.1-pro:fa4c9eb3dccc4806b382b40d61c6b10a",

        stt_context_options=STTContextOptions(
            keyterms=["LiveKit", "Jarvis"],
            keyterm_detection={"enabled": True},
        ),

        turn_handling=TurnHandlingOptions(
            turn_detection=inference.TurnDetector(),
            preemptive_generation={"enabled": True},
        ),

        expressive=True,
    )

    async def _cleanup_browser() -> None:
        await shutdown_browser_manager(session)

    ctx.add_shutdown_callback(_cleanup_browser)

    await session.start(
        agent=Assistant(),
        room=ctx.room,

        room_options=room_io.RoomOptions(
            video_input=True,

            audio_input=room_io.AudioInputOptions(
                noise_cancellation=ai_coustics.audio_enhancement(
                    model=ai_coustics.EnhancerModel.QUAIL_VF_S
                ),
            ),
        ),
    )

    logger.info("AgentSession started")

    await ctx.connect()

    logger.info("Jarvis connected")

    await session.generate_reply(
        instructions="Greet the user as Jarvis and offer your assistance."
    )


if __name__ == "__main__":
    cli.run_app(server)

