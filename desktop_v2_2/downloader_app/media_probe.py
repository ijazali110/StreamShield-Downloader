from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
import yt_dlp

from .models import MediaVariant, VideoItem
from .runtime import yt_dlp_runtime_options
from .workers import _browser_options


class ProbeSignals(QObject):
    ready = Signal(str, object, object, object)  # key, variants, subtitles, metadata
    error = Signal(str, str)


def _label_for_format(fmt: dict) -> str:
    height = fmt.get("height")
    fps = fmt.get("fps")
    ext = str(fmt.get("ext") or "")
    acodec = str(fmt.get("acodec") or "")
    vcodec = str(fmt.get("vcodec") or "")
    if vcodec == "none" and acodec != "none":
        abr = fmt.get("abr") or fmt.get("tbr")
        language = str(fmt.get("language") or "").strip()
        base = f"Audio {int(abr)}k" if abr else "Audio"
        return f"{base} • {language}" if language else base
    if height:
        suffix = f" {int(fps)}fps" if fps and fps >= 50 else ""
        return f"{int(height)}p{suffix}"
    if ext:
        return ext.upper()
    return str(fmt.get("format_note") or fmt.get("format_id") or "Best")


class FormatProbeWorker(QRunnable):
    """Resolve available formats/qualities for a detected media URL.

    This does not bypass access controls. It uses the same authorized headers or
    optional browser session the item already has.
    """

    def __init__(self, item: VideoItem, browser: str | None = None):
        super().__init__()
        self.item = item
        self.browser = browser
        self.signals = ProbeSignals()

    @Slot()
    def run(self):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            "socket_timeout": 20,
            "retries": 2,
            **yt_dlp_runtime_options(),
            **_browser_options(self.browser),
        }
        if self.item.http_headers:
            opts["http_headers"] = dict(self.item.http_headers)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(self.item.active_url(), download=False)
            if not isinstance(info, dict):
                raise RuntimeError("No media information returned")
            variants: list[MediaVariant] = []
            seen: set[tuple] = set()
            for fmt in info.get("formats") or []:
                if not isinstance(fmt, dict):
                    continue
                url = str(fmt.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                vcodec = str(fmt.get("vcodec") or "")
                acodec = str(fmt.get("acodec") or "")
                kind = "audio" if vcodec == "none" and acodec != "none" else "video"
                label = _label_for_format(fmt)
                key = (label, kind, int(fmt.get("height") or 0), str(fmt.get("format_id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                variants.append(
                    MediaVariant(
                        label=label,
                        url=url,
                        kind=kind,
                        height=fmt.get("height"),
                        width=fmt.get("width"),
                        bitrate=fmt.get("tbr") or fmt.get("abr"),
                        fps=fmt.get("fps"),
                        codec=vcodec,
                        audio_codec=acodec,
                        language=str(fmt.get("language") or ""),
                        format_id=str(fmt.get("format_id") or ""),
                        ext=str(fmt.get("ext") or ""),
                        http_headers=dict(self.item.http_headers),
                        verified=self.item.verified,
                    )
                )

            # For simple direct URLs yt-dlp may expose no formats. Keep the
            # captured URL as one selectable stream instead of hiding the item.
            if not variants:
                variants.append(
                    MediaVariant(
                        label="Best",
                        url=self.item.active_url(),
                        kind=self.item.media_kind or "video",
                        http_headers=dict(self.item.http_headers),
                        verified=self.item.verified,
                    )
                )

            subtitle_rows: list[dict] = []
            for language, entries in (info.get("subtitles") or {}).items():
                for entry in entries or []:
                    if isinstance(entry, dict) and entry.get("url"):
                        subtitle_rows.append({"language": language, "url": entry.get("url"), "ext": entry.get("ext") or ""})
            for language, entries in (info.get("automatic_captions") or {}).items():
                for entry in entries or []:
                    if isinstance(entry, dict) and entry.get("url"):
                        subtitle_rows.append({"language": language, "url": entry.get("url"), "ext": entry.get("ext") or "", "auto": True})

            metadata = {
                "title": str(info.get("title") or ""),
                "duration": info.get("duration"),
                "thumbnail": str(info.get("thumbnail") or ""),
            }
            self.signals.ready.emit(self.item.key, variants, subtitle_rows, metadata)
        except Exception as exc:
            self.signals.error.emit(self.item.key, str(exc))
