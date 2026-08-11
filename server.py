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
from dotenv import load_dotenv

load_dotenv()

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

def capture_win32_gdi() -> Image.Image:
    """Fallback Win32 GDI screen capture for Windows."""
    import ctypes
    import ctypes.wintypes
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    hdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    gdi32.BitBlt(mdc, 0, 0, w, h, hdc, 0, 0, 0x00CC0020)
    
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32), ('biWidth', ctypes.c_int32), ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16), ('biBitCount', ctypes.c_uint16), ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32), ('biXPelsPerMeter', ctypes.c_int32), ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32), ('biClrImportant', ctypes.c_uint32)
        ]
    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight, bmi.biPlanes, bmi.biBitCount, bmi.biCompression = w, -h, 1, 32, 0
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bmi), 0)
    img = Image.frombuffer('RGBA', (w, h), buf, 'raw', 'BGRA')
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(0, hdc)
    return img.convert('RGB')


def capture_screen() -> tuple[bytes, Image.Image]:
    """Capture the primary monitor and return (png_bytes, pil_image)."""
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            screenshot = sct.grab(monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
    except Exception as e1:
        if platform.system() == "Windows":
            logger.warning(f"mss failed to capture screen: {e1}. Trying Win32 GDI...")
            try:
                img = capture_win32_gdi()
            except Exception as e2:
                logger.warning(f"Win32 GDI capture failed: {e2}. Falling back to PIL ImageGrab.")
                from PIL import ImageGrab
                img = ImageGrab.grab()
        else:
            logger.warning(f"Headless server screen capture fallback: {e1}")
            img = Image.new("RGB", (1920, 1080), color=(30, 30, 40))
        
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
        "api_key": os.getenv("GEMINI_API_KEY"),
        "model": "gemini-3.6-flash",
        "temperature": 0.7,
        "client": None,
    }
    
    # Initialize client immediately if env var is present
    if state["api_key"]:
        state["client"] = genai.Client(api_key=state["api_key"])

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            # ---- configure ---------------------------------------------------
            if msg_type == "configure":
                # API key is now loaded from .env, but we still allow updating model/temp
                state["model"] = data.get("model", state["model"])
                state["temperature"] = float(data.get("temperature", state["temperature"]))
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

                # Build current user message parts (including attachments)
                current_parts = []
                if user_msg:
                    current_parts.append(types.Part.from_text(text=user_msg))

                attachments = data.get("attachments", [])
                for att in attachments:
                    att_type = att.get("type", "text")
                    att_name = att.get("name", "attachment")
                    att_data = att.get("data", "")
                    if att_type == "image":
                        try:
                            b64_str = att_data.split(",", 1)[1] if "," in att_data else att_data
                            img_bytes = base64.b64decode(b64_str)
                            mime = "image/png"
                            if att_name.lower().endswith((".jpg", ".jpeg")):
                                mime = "image/jpeg"
                            elif att_name.lower().endswith(".webp"):
                                mime = "image/webp"
                            current_parts.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
                        except Exception as e:
                            logger.error(f"Failed to decode image attachment {att_name}: {e}")
                    else:
                        text_content = f"--- Attached File: {att_name} ---\n{att_data}\n--- End of File ---"
                        current_parts.append(types.Part.from_text(text=text_content))

                if not current_parts:
                    current_parts.append(types.Part.from_text(text="[Empty Message]"))

                contents.append(
                    types.Content(
                        role="user",
                        parts=current_parts,
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
                    error_msg = str(exc)
                    if "404" in error_msg or "not found" in error_msg.lower():
                        try:
                            client = state["client"]
                            models = []
                            for m in client.models.list():
                                if "generateContent" in m.supported_actions:
                                    models.append(m.name)
                            error_msg += f"\n\nAvailable models for your API key: {', '.join(models)}"
                        except Exception as e2:
                            error_msg += f"\n(Failed to list models: {e2})"
                    await ws.send_json({"type": "error", "message": error_msg})

            # ---- analyze_screen_image (from browser) --------------------------
            elif msg_type == "analyze_screen_image":
                if not state["client"]:
                    await ws.send_json({"type": "error", "message": "API key not set."})
                    continue

                prompt = data.get("prompt", "Describe everything you see on this screen in detail. Identify applications, windows, text, and any notable content.")
                image_data = data.get("image", "")

                try:
                    if "," in image_data:
                        b64_str = image_data.split(",", 1)[1]
                    else:
                        b64_str = image_data

                    png_bytes = base64.b64decode(b64_str)

                    # Create content object with text and image parts
                    text_part = types.Part.from_text(text=prompt)
                    image_part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")
                    contents = [
                        types.Content(
                            role="user",
                            parts=[text_part, image_part],
                        )
                    ]

                    client = state["client"]
                    response = await asyncio.to_thread(
                        lambda: client.models.generate_content_stream(
                            model=state["model"],
                            contents=contents,
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
                    logger.error("Screen image analysis error: %s", exc)
                    await ws.send_json({"type": "error", "message": str(exc)})

            # ---- analyze_screen (server-side capture) ------------------------
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

                    # Create content object with text and image parts
                    text_part = types.Part.from_text(text=prompt)
                    image_part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")
                    contents = [
                        types.Content(
                            role="user",
                            parts=[text_part, image_part],
                        )
                    ]

                    client = state["client"]
                    response = await asyncio.to_thread(
                        lambda: client.models.generate_content_stream(
                            model=state["model"],
                            contents=contents,
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
    import socket

    def is_port_in_use(p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', p)) == 0

    desired_port = int(os.getenv("PORT", 8000))
    if "PORT" not in os.environ and is_port_in_use(desired_port):
        for p in range(8000, 8050):
            if not is_port_in_use(p):
                desired_port = p
                break

    print("\n" + "=" * 60)
    print("  [HanumanAI] Intelligent Agent Platform")
    print(f"  [Web]     Open http://localhost:{desired_port} in your browser")
    print("=" * 60 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=desired_port, log_level="info")
