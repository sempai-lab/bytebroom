"""The list of caches ByteBroom knows about.

Adding a cache = adding one ``Cache(...)`` entry to ``CACHES`` below.

    key            unique id (letters/underscores)
    name           what the user sees
    paths          folders/files; glob patterns allowed. For a folder its CONTENTS are
                   deleted and the folder itself is kept. Build them with ``P(base, ...)``
                   so the base path is escaped and only the parts can hold wildcards.
    safe           True  = pre-ticked; it just re-downloads / rebuilds when needed
                   False = shown as CAUTION and not pre-ticked (the user loses something)
    note           one short sentence: what happens when it is cleared
    command        official clean command, tried first if the tool is installed;
                   if it fails or is missing, the files are deleted directly
    command_only   never delete files directly - only run the command (e.g. Docker)
    min_age_hours  only delete files older than this (e.g. Temp)
    close_first    app name to remind the user to close (its files are locked while open)

Only entries whose paths exist on the machine are shown.
"""
from __future__ import annotations

import glob
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

# ----------------------------------------------------------------------------- locations
HOME = str(Path.home())
LOCAL = os.environ.get("LOCALAPPDATA") or os.path.join(HOME, "AppData", "Local")
ROAMING = os.environ.get("APPDATA") or os.path.join(HOME, "AppData", "Roaming")
TEMP = tempfile.gettempdir()

CHROME = os.path.join(LOCAL, "Google", "Chrome", "User Data")
CHROME_BETA = os.path.join(LOCAL, "Google", "Chrome Beta", "User Data")
EDGE = os.path.join(LOCAL, "Microsoft", "Edge", "User Data")
HF_HOME = os.environ.get("HF_HOME") or os.path.join(HOME, ".cache", "huggingface")
UV_CACHE = os.environ.get("UV_CACHE_DIR") or os.path.join(LOCAL, "uv", "cache")
PIP_CACHE = os.environ.get("PIP_CACHE_DIR") or os.path.join(LOCAL, "pip", "cache")


def P(base: str, *parts: str) -> str:
    """Glob pattern: ``base`` is escaped, ``parts`` may contain wildcards."""
    return os.path.join(glob.escape(base), *parts)


@dataclass(frozen=True)
class Cache:
    key: str
    name: str
    paths: tuple[str, ...]
    safe: bool
    note: str
    command: tuple[str, ...] | None = None
    command_only: bool = False
    min_age_hours: float = 0
    close_first: str = ""


def browser_cache(key: str, name: str, user_data: str, app: str) -> Cache:
    """Chromium-style browser: only cache folders, never the profile itself."""
    per_profile = ("Cache", "Code Cache", "GPUCache", "DawnGraphiteCache", "DawnWebGPUCache")
    shared = ("GrShaderCache", "ShaderCache", "GraphiteDawnCache", "component_crx_cache")
    return Cache(
        key, name,
        tuple(P(user_data, "*", d) for d in per_profile) + tuple(P(user_data, d) for d in shared),
        True, "Web cache only. Logins, bookmarks and history stay.",
        close_first=app,
    )


# ----------------------------------------------------------------------------- the list
CACHES: tuple[Cache, ...] = (
    # ---- SAFE: re-downloaded / rebuilt when needed -------------------------------------
    Cache("uv", "uv packages", (P(UV_CACHE),), True,
          "Python packages downloaded by uv. Re-downloaded on next `uv sync` / install.",
          command=("uv", "cache", "clean")),
    Cache("pip", "pip packages", (P(PIP_CACHE),), True,
          "Python packages downloaded by pip. Re-downloaded on next install."),
    Cache("npm", "npm packages", (P(LOCAL, "npm-cache"),), True,
          "Node packages cache. Re-downloaded on next `npm install`."),
    Cache("yarn", "Yarn packages", (P(LOCAL, "Yarn", "Cache"),), True,
          "Yarn packages cache. Re-downloaded on next install."),
    Cache("temp", "Windows Temp", (P(TEMP),), True,
          "Temp files older than 1 day. Files in use are skipped.", min_age_hours=24),
    Cache("arduino", "Arduino downloads", (P(LOCAL, "Arduino15", "staging"),), True,
          "Downloaded board/library zips. Installed boards stay."),
    Cache("ollama", "Ollama installers",
          (P(LOCAL, "Ollama", "updates_v2"), P(LOCAL, "Ollama", "OllamaSetup.exe")), True,
          "Leftover update installers. Your models stay."),
    Cache("nuitka", "Nuitka build cache", (P(LOCAL, "Nuitka", "Nuitka"),), True,
          "Compiler downloads and build cache. Rebuilt on next compile."),
    browser_cache("chrome", "Chrome cache", CHROME, "Chrome"),
    browser_cache("chrome_beta", "Chrome Beta cache", CHROME_BETA, "Chrome Beta"),
    browser_cache("edge", "Edge cache", EDGE, "Edge"),
    Cache("discord", "Discord cache",
          tuple(P(ROAMING, "discord", d) for d in ("Cache", "Code Cache", "GPUCache")), True,
          "Image/media cache. Logins stay.", close_first="Discord"),
    Cache("gpu", "GPU shader cache",
          (P(LOCAL, "NVIDIA", "DXCache"), P(LOCAL, "NVIDIA", "GLCache"),
           P(LOCAL, "D3DSCache"), P(LOCAL, "AMD", "DxCache")), True,
          "Rebuilt automatically (games may load a bit slower once)."),
    Cache("crash", "Crash dumps", (P(LOCAL, "CrashDumps"),), True,
          "Old crash reports from apps."),
    Cache("selenium", "Selenium drivers", (P(HOME, ".cache", "selenium"),), True,
          "Browser drivers. Selenium downloads them again when needed."),

    # ---- CAUTION: the user loses something (big re-download, re-setup) ----------------
    Cache("omnivoice", "OmniVoice models", (P(LOCAL, "OmniVoice", "hf_cache"),), False,
          "Its AI voice models. OmniVoice re-downloads them (~11 GB) on next start.",
          close_first="OmniVoice"),
    Cache("chrome_ai", "Chrome AI model",
          (P(CHROME, "OptGuideOnDeviceModel"), P(CHROME_BETA, "OptGuideOnDeviceModel")), False,
          "Gemini Nano on-device model (~4 GB each). Chrome may download it again.",
          close_first="Chrome"),
    Cache("hf", "Hugging Face models", (P(HF_HOME, "hub"),), False,
          "AI models used by Python scripts. Re-downloaded when a script needs them."),
    Cache("whisper", "Whisper models", (P(HOME, ".cache", "whisper"),), False,
          "Speech-to-text models. Re-downloaded when a script needs them."),
    Cache("torch", "PyTorch hub", (P(HOME, ".cache", "torch"),), False,
          "PyTorch model downloads. Re-downloaded when needed."),
    Cache("playwright", "Playwright browsers", (P(LOCAL, "ms-playwright"),), False,
          "Test browsers. Get them back with `playwright install`."),
    Cache("pub", "Flutter/Dart packages", (P(LOCAL, "Pub", "Cache"),), False,
          "Run `flutter pub get` in your projects afterwards."),
    Cache("gradle", "Gradle caches", (P(HOME, ".gradle", "caches"),), False,
          "Android build dependencies. The first build afterwards is slow."),
    Cache("docker", "Docker unused data", (P(LOCAL, "Docker", "wsl"),), False,
          "Runs `docker system prune` (unused containers, images, build cache). "
          "Docker must be running. Size shown = Docker's whole disk.",
          command=("docker", "system", "prune", "-f"), command_only=True),
)
