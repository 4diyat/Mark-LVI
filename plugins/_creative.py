"""Non-Qt helpers for the interactive editor and image canvas."""
from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from pathlib import Path

MAX_CODE_BYTES = 1_000_000
MAX_IMAGE_BYTES = 20_000_000
MAX_OUTPUT_BYTES = 64_000
RUN_TIMEOUT = 15


def read_code(path: str) -> str:
    p = Path(path)
    if p.stat().st_size > MAX_CODE_BYTES:
        raise ValueError("File is larger than 1 MB.")
    data = p.read_bytes()
    if len(data) > MAX_CODE_BYTES:
        raise ValueError("File is larger than 1 MB.")
    return data.decode("utf-8")


def write_code(path: str, text: str) -> None:
    data = text.encode("utf-8")
    if len(data) > MAX_CODE_BYTES:
        raise ValueError("File is larger than 1 MB.")
    Path(path).write_bytes(data)


def run_code(path: str, timeout: float = RUN_TIMEOUT) -> tuple[int | None, str]:
    """Run the exact file selected and approved by the person, not a sandbox.

    Captured output is bounded in memory while both pipes continue draining.
    Timeout stops the direct process, but cannot guarantee termination of its
    children. Code has the user's normal privileges and inherits the environment.
    """
    p = Path(path).resolve(strict=True)
    if p.suffix.lower() == ".py":
        argv = [sys.executable, str(p)]
    elif p.suffix.lower() in (".js", ".mjs", ".cjs"):
        node = shutil.which("node")
        if not node:
            raise ValueError("Node.js is not installed or not on PATH.")
        argv = [node, str(p)]
    else:
        raise ValueError("Only Python and JavaScript files can be run.")
    proc = subprocess.Popen(argv, cwd=str(p.parent), stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = bytearray()
    truncated = [False]

    def drain():
        while True:
            chunk = proc.stdout.read(8192)
            if not chunk:
                break
            remaining = max(0, MAX_OUTPUT_BYTES - len(output))
            output.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated[0] = True

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
    reader.join(timeout=1)
    text = bytes(output).decode("utf-8", errors="replace")
    if truncated[0]:
        text += "\n[Output truncated]"
    if timed_out:
        text += "\n[Timed out; child processes may still be running]"
        return None, text
    return proc.returncode, text


def generate_image(prompt: str, api_key: str, client_factory=None) -> tuple[bytes, str]:
    """Ask Gemini for one image. Returns verified-size bytes and MIME type."""
    prompt = (prompt or "").strip()
    if not prompt or len(prompt) > 5000:
        raise ValueError("Enter an image prompt of at most 5000 characters.")
    if not (api_key or "").strip():
        raise ValueError("A Gemini API key is required.")
    if client_factory is None:
        from google import genai
        client_factory = genai.Client
    client = client_factory(api_key=api_key, http_options={"timeout": 60000})
    response = client.models.generate_content(
        model="gemini-2.5-flash-image", contents=prompt,
        config={"response_modalities": ["TEXT", "IMAGE"]})
    for candidate in getattr(response, "candidates", None) or []:
        for part in getattr(getattr(candidate, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            mime = str(getattr(inline, "mime_type", "") or "").lower()
            if isinstance(data, (bytes, bytearray)) and mime in {"image/png", "image/jpeg", "image/webp"}:
                if not data or len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("The generated image is empty or too large.")
                return bytes(data), mime
    raise ValueError("The image service did not return an image; try another prompt or check model access.")
