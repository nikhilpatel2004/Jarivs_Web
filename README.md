# Jarvis — AI Voice Assistant

**Jarvis** is a voice AI assistant built with [LiveKit Agents for Python](https://github.com/livekit/agents). It runs a real-time voice pipeline — speech recognition, agent reasoning, and expressive speech synthesis — and extends the agent with desktop control and browser automation tools.

## Project name

**Jarvis** — an AI voice assistant.

## Description

Jarvis holds a real-time voice conversation using LiveKit: it listens with AssemblyAI, reasons with an OpenAI-compatible LLM served through an OMNIROUTE gateway, and speaks back with Fish Audio TTS. In addition to the voice loop, the agent can control the user's desktop (scroll, mouse, keyboard, screenshots, screen context) and drive a browser through Playwright.

## Features

Features present in the current codebase (`src/agent.py`, `src/tools.py`, `src/browser_manager.py`, `src/playwright_tools.py`):

- Real-time voice pipeline:
  - STT: AssemblyAI (`assemblyai-stt-3-7-realtime-agent`).
  - LLM: OpenAI-compatible endpoint provided via the OMNIROUTE gateway.
  - TTS: Fish Audio S2.1 Pro via LiveKit inference.
  - Turn detection via LiveKit inference, preemptive generation, expressive TTS, adaptive interruption handling, AI acoustics noise cancellation, and keyterm detection.
- Desktop control tools:
  - Scroll, mouse move/click, keyboard press/type, screenshot capture, screen info, active-window info.
- Browser automation tools (Playwright): start/navigate, accessibility snapshot, text/HTML extraction, element queries, screenshot/PDF, JavaScript evaluation, close.
- Web search tools backed by DuckDuckGo/DDGS.

## Tech stack

- Python agent: LiveKit Agents for Python (`livekit-agents[images]~=1.8`), LiveKit plugins (AssemblyAI, OpenAI, AI acoustics), LiveKit Inference, Fish Audio TTS, OpenAI-compatible LLM via OMNIROUTE.
- Desktop/browser tooling: Playwright, pyautogui, pygetwindow, Pillow.
- Frontend: Flutter app in `livekit_flutter_starter/` (LiveKit Flutter SDK components/client, chat bubbles, etc.).
- Deployment: Docker (uv-based) → Render (worker).

## Project structure

- `src/agent.py` — main agent server and session (Assistant agent, tools, environment gate).
- `src/tools.py` — desktop and web tools.
- `src/browser_manager.py` — browser management (engine, headless, artifacts, profile dirs).
- `src/playwright_tools.py` — Playwright browser tools.
- `src/__init__.py`
- `tests/` — evaluation tests (currently commented out; behavior covered by simulations).
- `pyproject.toml`, `uv.lock`, `Dockerfile`, `.dockerignore`, `.env.example`, `render.yaml`, `taskfile.yaml`, `scenarios.yaml`.
- `livekit_flutter_starter/` — Flutter voice assistant frontend.

## Prerequisites

- Python 3.10–3.14 and `uv`.
- LiveKit Cloud account/project and credentials (LiveKit URL/API key/API secret), or self-hosted LiveKit server.
- OMNIROUTE gateway credentials (API key, base URL, model).
- AssemblyAI API key.
- For desktop/browser features: a desktop environment with Playwright Chromium available.

## Installation and setup

1. Install `uv` and the LiveKit CLI; sign in to LiveKit Cloud (`lk cloud auth`).
2. Run `uv sync` to install Python dependencies.
3. Create `.env.local` from `.env.example` with the required variables (never commit real values).
4. Review and adjust agent instructions/tools as needed.

## Environment variables

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `OMNIROUTE_API_KEY`
- `OMNIROUTE_BASE_URL`
- `OMNIROUTE_MODEL`
- `ASSEMBLYAI_API_KEY`
- Optional: `JARVIS_BROWSER_ENGINE`, `JARVIS_BROWSER_HEADLESS`, `JARVIS_BROWSER_ARTIFACTS_DIR`, `JARVIS_BROWSER_USER_DATA_DIR`

All `OMNIROUTE_*` variable names above are used consistently across the agent code, `render.yaml`, and `.env.example`.

## Run locally

- `uv run src/agent.py dev` (or `lk agent dev`).
- Console: `lk agent console`.
- Production start: `uv run src/agent.py start`.

## Run the Flutter app

- `cd livekit_flutter_starter`
- `flutter pub get`
- `flutter run`

## Deploy on Render

- Render worker using the Dockerfile; `render.yaml` configures `type: worker`, `runtime: docker`, `branch: main`, `plan: 1c-2g`, `maxShutdownDelaySeconds: 300`, and environment variables.

## Troubleshooting

- Missing environment variables cause the agent session to raise a `RuntimeError` listing required variables.
- Browser automation requires Playwright Chromium (installed in the Docker image).
- TODO: verify Flutter Android Gradle/AGP version mismatch fix steps locally.

## Author

- nikhilpatel2004
