from __future__ import annotations

import os
import shutil
from pathlib import Path


def _existing(path: str | os.PathLike[str] | None) -> str | None:
    if not path:
        return None
    candidate = Path(path).expanduser()
    return str(candidate) if candidate.is_file() else None


def find_ffmpeg() -> str | None:
    """Return a usable ffmpeg executable, preferring system ffmpeg."""
    system = shutil.which("ffmpeg")
    if system:
        return system

    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).is_file():
            return bundled
    except Exception:
        pass
    return None


def find_js_runtime() -> tuple[str | None, str | None]:
    """Return (runtime_name, executable_path) for a yt-dlp supported JS runtime."""
    candidates: list[tuple[str, str | None]] = [
        ("deno", shutil.which("deno")),
        ("node", shutil.which("node")),
        ("quickjs", shutil.which("qjs") or shutil.which("quickjs")),
        ("bun", shutil.which("bun")),
    ]

    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", user_profile / "AppData" / "Local"))
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))

    candidates.extend(
        [
            ("deno", _existing(user_profile / ".deno" / "bin" / "deno.exe")),
            ("node", _existing(program_files / "nodejs" / "node.exe")),
            ("bun", _existing(user_profile / ".bun" / "bin" / "bun.exe")),
            ("deno", _existing(local_app_data / "deno" / "deno.exe")),
            ("deno", _existing(local_app_data / "Microsoft" / "WinGet" / "Links" / "deno.exe")),
            ("node", _existing(local_app_data / "Microsoft" / "WinGet" / "Links" / "node.exe")),
        ]
    )

    seen: set[tuple[str, str]] = set()
    for name, path in candidates:
        if not path:
            continue
        key = (name, str(path).lower())
        if key in seen:
            continue
        seen.add(key)
        if Path(path).is_file():
            return name, str(path)
    return None, None


def yt_dlp_runtime_options() -> dict:
    opts: dict = {}

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        opts["ffmpeg_location"] = ffmpeg

    runtime_name, runtime_path = find_js_runtime()
    if runtime_name and runtime_path:
        opts["js_runtimes"] = {runtime_name: {"path": runtime_path}}

    return opts


def engine_summary() -> str:
    ffmpeg = find_ffmpeg()
    runtime_name, _ = find_js_runtime()
    ffmpeg_text = "FFmpeg ready" if ffmpeg else "FFmpeg missing"
    js_text = f"JS: {runtime_name.title()}" if runtime_name else "JS runtime missing"
    return f"{ffmpeg_text}  •  {js_text}"


def find_ffplay() -> str | None:
    """Return ffplay when available, including common Windows package locations."""
    system = shutil.which("ffplay")
    if system:
        return system

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        candidate = Path(ffmpeg).with_name("ffplay.exe" if os.name == "nt" else "ffplay")
        if candidate.is_file():
            return str(candidate)

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        direct_candidates = [
            local / "Microsoft" / "WinGet" / "Links" / "ffplay.exe",
            program_files / "ffmpeg" / "bin" / "ffplay.exe",
            program_files / "FFmpeg" / "bin" / "ffplay.exe",
            program_files_x86 / "ffmpeg" / "bin" / "ffplay.exe",
            Path(r"C:\ffmpeg\bin\ffplay.exe"),
            Path(r"C:\ProgramData\chocolatey\bin\ffplay.exe"),
        ]
        for candidate in direct_candidates:
            if candidate.is_file():
                return str(candidate)

        # Winget's Gyan.FFmpeg package is often installed under Packages and
        # may not be visible to a process that started before PATH refreshed.
        packages = local / "Microsoft" / "WinGet" / "Packages"
        if packages.is_dir():
            try:
                for candidate in packages.glob("Gyan.FFmpeg*/*/bin/ffplay.exe"):
                    if candidate.is_file():
                        return str(candidate)
                for candidate in packages.glob("Gyan.FFmpeg*/**/ffplay.exe"):
                    if candidate.is_file():
                        return str(candidate)
            except OSError:
                pass
    return None


def find_aria2c() -> str | None:
    """Optional high-speed progressive downloader."""
    candidates = [
        shutil.which("aria2c"),
        _existing(Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Microsoft" / "WinGet" / "Links" / "aria2c.exe"),
        _existing(Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "aria2" / "aria2c.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None
