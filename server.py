"""
NexusAI - Intelligent Agent Platform (Backend)
FastAPI server with WebSocket, screen capture, system control, and Gemini API integration.
Uses the new google.genai SDK.
"""

import asyncio
import base64
import io
import json
import logging
import os
import platform
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from google import genai
from google.genai import types
import mss
import mss.tools
from PIL import Image

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hanumanai")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(title="HanumanAI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Resolve directory where this script lives (serves static files from there)
BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# System prompts per agent mode
# ---------------------------------------------------------------------------
SYSTEM_PROMPTS = {
    "chat": (
        "You are HanumanAI, a friendly, intelligent, and helpful AI assistant. "
        "You have the ability to see the user's screen and execute system commands when asked. "
        "Be conversational, helpful, and proactive. Use markdown formatting in your responses."
    ),
    "task": (
        "You are HanumanAI Task Agent. You specialize in productivity tasks: summarizing text, "
        "translating languages, extracting data, generating structured outputs (JSON, CSV, tables), "
        "and analyzing content. Be efficient and precise. Always format output clearly using markdown."
    ),
    "code": (
        "You are HanumanAI Code Agent. You are an expert programmer. You write clean, efficient, "
        "well-documented code. You can debug issues, explain code, generate unit tests, refactor, "
        "and suggest improvements. Always use proper code blocks with language specifiers. "
        "When the user shares their screen, analyze any code you see."
    ),
    "knowledge": (
        "You are HanumanAI Knowledge Agent. You provide well-researched, comprehensive answers. "
        "Explain complex topics clearly, compare concepts, provide pros/cons analysis, and "
        "generate step-by-step tutorials. Use structured markdown with headers, lists, and tables."
    ),
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def capture_screen() -> tuple[bytes, Image.Image]:
    """Capture the primary monitor and return (png_bytes, pil_image)."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        # Resize if very large to save bandwidth / API tokens
        if img.width > 1920:
            ratio = 1920 / img.width
            img = img.resize((1920, int(img.height * ratio)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        buf.seek(0)
        return buf.getvalue(), img


def get_system_info() -> dict:
    """Gather basic system information."""
    import shutil
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "python": platform.python_version(),
        "hostname": platform.node(),
    }
    try:
        total, used, free = shutil.disk_usage("/")
        info["disk_total_gb"] = round(total / (1024 ** 3), 2)
        info["disk_used_gb"] = round(used / (1024 ** 3), 2)
        info["disk_free_gb"] = round(free / (1024 ** 3), 2)
    except Exception:
        pass
    return info


# ---------------------------------------------------------------------------
# WebSocket handler
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    logger.info("WebSocket client connected")

    # Per-connection state
    state = {
        "api_key": None,
        "model": "gemini-2.0-flash",
        "temperature": 0.7,
        "client": None,
    }

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            # ---- configure ---------------------------------------------------
            if msg_type == "configure":
                state["api_key"] = data.get("apiKey", state["api_key"])
                state["model"] = data.get("model", state["model"])
                state["temperature"] = float(data.get("temperature", state["temperature"]))
                if state["api_key"]:
                    state["client"] = genai.Client(api_key=state["api_key"])
                await ws.send_json({"type": "configured", "success": True})

            # ---- chat --------------------------------------------------------
            elif msg_type == "chat":
                if not state["client"]:
                    await ws.send_json({"type": "error", "message": "API key not set. Please configure your Gemini API key in Settings."})
                    continue

                mode = data.get("mode", "chat")
                user_msg = data.get("message", "")
                history = data.get("history", [])

                system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["chat"])

                # Build contents list for Gemini
                contents = []
                for entry in history:
                    role = entry.get("role", "user")
                    parts_data = entry.get("parts", [])
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=p) for p in parts_data],
                        )
                    )

                # Append current user message
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=user_msg)],
                    )
                )

                try:
                    client = state["client"]
                    response = await asyncio.to_thread(
                        lambda: client.models.generate_content_stream(
                            model=state["model"],
                            contents=contents,
                            config=types.GenerateContentConfig(
                                system_instruction=system_prompt,
                                temperature=state["temperature"],
                            ),
                        )
                    )
                    # Iterate through the stream
                    for chunk in response:
                        if chunk.text:
                            await ws.send_json({"type": "chunk", "content": chunk.text})
                    await ws.send_json({"type": "done"})

                except Exception as exc:
                    logger.error("Chat error: %s", exc)
                    await ws.send_json({"type": "error", "message": str(exc)})

            # ---- analyze_screen ----------------------------------------------
            elif msg_type == "analyze_screen":
                if not state["client"]:
                    await ws.send_json({"type": "error", "message": "API key not set."})
                    continue

                prompt = data.get("prompt", "Describe everything you see on this screen in detail. Identify applications, windows, text, and any notable content.")

                try:
                    png_bytes, pil_img = await asyncio.to_thread(capture_screen)
                    b64 = base64.b64encode(png_bytes).decode("utf-8")
                    await ws.send_json({
                        "type": "screen_captured",
                        "image": f"data:image/png;base64,{b64}",
                    })

                    # Create image part for the API
                    image_part = types.Part.from_image(image=pil_img)
                    text_part = types.Part.from_text(text=prompt)

                    client = state["client"]
                    response = await asyncio.to_thread(
                        lambda: client.models.generate_content_stream(
                            model=state["model"],
                            contents=[text_part, image_part],
                            config=types.GenerateContentConfig(
                                system_instruction="You are HanumanAI with screen-reading capability. Analyze the screenshot the user shares and respond helpfully.",
                                temperature=state["temperature"],
                            ),
                        )
                    )
                    for chunk in response:
                        if chunk.text:
                            await ws.send_json({"type": "chunk", "content": chunk.text})
                    await ws.send_json({"type": "done"})

                except Exception as exc:
                    logger.error("Screen capture error: %s", exc)
                    await ws.send_json({"type": "error", "message": str(exc)})

            # ---- execute_command ---------------------------------------------
            elif msg_type == "execute_command":
                command = data.get("command", "")
                if not command:
                    await ws.send_json({"type": "error", "message": "No command provided."})
                    continue

                try:
                    result = await asyncio.to_thread(
                        lambda: subprocess.run(
                            command,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=30,
                            cwd=os.path.expanduser("~"),
                        )
                    )
                    output = result.stdout
                    if result.stderr:
                        output += "\n" + result.stderr
                    await ws.send_json({
                        "type": "command_result",
                        "output": output.strip(),
                        "exitCode": result.returncode,
                    })
                except subprocess.TimeoutExpired:
                    await ws.send_json({"type": "command_result", "output": "Command timed out after 30 seconds.", "exitCode": -1})
                except Exception as exc:
                    logger.error("Command error: %s", exc)
                    await ws.send_json({"type": "error", "message": str(exc)})

            # ---- system_info -------------------------------------------------
            elif msg_type == "system_info":
                info = await asyncio.to_thread(get_system_info)
                await ws.send_json({"type": "system_info_result", "info": info})

            else:
                await ws.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/{filename:path}")
async def static_files(filename: str):
    filepath = BASE_DIR / filename
    if filepath.is_file():
        return FileResponse(filepath)
    return FileResponse(BASE_DIR / "index.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 60)
    print("  [HanumanAI] Intelligent Agent Platform")
    print("  [Web]     Open http://localhost:8000 in your browser")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
