from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from PySide6.QtCore import QObject, QRunnable, Signal, Slot
import yt_dlp

from .models import MediaVariant, VideoItem
from .runtime import find_aria2c, find_js_runtime, yt_dlp_runtime_options


URL_RE = re.compile(r"https?://[^\s<>\"']+")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
PLAYBACK_ONLY_QUERY_KEYS = {"t", "start", "time_continue", "si", "feature", "pp", "ab_channel"}
DIRECT_VIDEO_EXTENSIONS = {
    ".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi", ".wmv", ".flv", ".ts", ".m2ts",
}
DIRECT_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac"}
MANIFEST_EXTENSIONS = {".m3u8", ".mpd"}
DIRECT_FILE_EXTENSIONS = {".pdf", ".zip", ".rar", ".7z", ".exe", ".msi", ".apk", ".iso", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".doc", ".docx", ".xlsx", ".pptx"}


def normalize_url(url: str) -> str:
    """Normalize harmless YouTube share parameters; preserve all other sites exactly."""
    value = (url or "").strip().rstrip(".,);]}>")
    try:
        parsed = urlparse(value)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host not in YOUTUBE_HOSTS:
            return value
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k not in PLAYBACK_ONLY_QUERY_KEYS]
        return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, parsed.params, urlencode(query), ""))
    except Exception:
        return value


def extract_urls(text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for match in URL_RE.findall(text or ""):
        url = normalize_url(match)
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def site_label(url: str, fallback: str = "Website") -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return host or fallback
    except Exception:
        return fallback


def _youtube_video_id(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host == "youtu.be":
            return parsed.path.strip("/").split("/", 1)[0]
        if host in YOUTUBE_HOSTS:
            if parsed.path == "/watch":
                return dict(parse_qsl(parsed.query)).get("v", "")
            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed"}:
                return parts[1]
    except Exception:
        pass
    return ""


def _looks_like_playlist(url: str) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower().split(":", 1)[0]
        if host not in YOUTUBE_HOSTS:
            return False
        query = dict(parse_qsl(parsed.query))
        return parsed.path == "/playlist" and bool(query.get("list"))
    except Exception:
        return False


def _media_extension(url: str) -> str:
    try:
        path = unquote(urlparse(url).path).lower()
        return Path(path).suffix
    except Exception:
        return ""


def direct_media_kind(url: str) -> str:
    ext = _media_extension(url)
    if ext in DIRECT_VIDEO_EXTENSIONS:
        return "video"
    if ext in DIRECT_AUDIO_EXTENSIONS:
        return "audio"
    if ext == ".m3u8":
        return "hls"
    if ext == ".mpd":
        return "dash"
    if ext in DIRECT_FILE_EXTENSIONS:
        return "file"
    return ""


def is_direct_media_url(url: str) -> bool:
    return bool(direct_media_kind(url))


def _can_fallback(url: str) -> bool:
    return bool(_youtube_video_id(url)) or is_direct_media_url(url)


def _fallback_item(url: str) -> VideoItem:
    video_id = _youtube_video_id(url)
    media_kind = direct_media_kind(url)
    host = site_label(url)
    if video_id:
        title = f"YouTube video ({video_id})"
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        source = "youtube.com"
    else:
        try:
            basename = Path(unquote(urlparse(url).path)).name
        except Exception:
            basename = ""
        title = basename or f"Media from {host}"
        thumbnail = ""
        source = host
    return VideoItem(
        title=title,
        webpage_url=normalize_url(url),
        video_id=video_id,
        duration=None,
        thumbnail=thumbnail,
        source=source,
        extractor="direct",
        direct_media=bool(media_kind),
        media_kind=media_kind,
        variants=[MediaVariant(label="Original", url=normalize_url(url), kind=media_kind or "file")] if media_kind == "file" else [],
    )


def _video_url(entry: dict) -> str:
    webpage_url = entry.get("webpage_url") or entry.get("original_url")
    if webpage_url:
        return normalize_url(str(webpage_url))

    raw_url = entry.get("url")
    if raw_url and str(raw_url).startswith(("http://", "https://")):
        return normalize_url(str(raw_url))

    video_id = str(entry.get("id") or "")
    extractor = str(entry.get("extractor_key") or entry.get("extractor") or "").lower()
    if video_id and "youtube" in extractor:
        return f"https://www.youtube.com/watch?v={video_id}"
    return str(raw_url or video_id)


def _source_from_info(info: dict, url: str) -> str:
    webpage = str(info.get("webpage_url") or info.get("original_url") or url or "")
    host = site_label(webpage, "")
    if host:
        return host
    extractor = str(info.get("extractor_key") or info.get("extractor") or "Website")
    return extractor.replace("_", " ")


def _safe_headers(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, str] = {}
    for key, val in value.items():
        if key and val is not None:
            result[str(key)] = str(val)
    return result


def _browser_options(browser: str | None) -> dict:
    name = (browser or "").strip().lower()
    if not name:
        return {}
    # yt-dlp's Python API expects a tuple/list browser specification, not a string.
    return {"cookiesfrombrowser": (name,)}


class _CaptureLogger:
    def __init__(self):
        self.lines: list[str] = []

    def clear(self) -> None:
        self.lines.clear()

    def _add(self, message) -> None:
        text = str(message or "").strip()
        if text and text not in self.lines:
            self.lines.append(text)
            if len(self.lines) > 40:
                self.lines = self.lines[-40:]

    def debug(self, message):
        text = str(message or "")
        if text.startswith("[debug]"):
            return
        self._add(text)

    def info(self, message):
        self._add(message)

    def warning(self, message):
        self._add(message)

    def error(self, message):
        self._add(message)

    def tail(self, limit: int = 8) -> str:
        return "\n".join(self.lines[-limit:])


def _friendly_download_error(raw_message: str) -> str:
    text = (raw_message or "Download failed").strip()
    lower = text.lower()
    hints: list[str] = []

    if any(marker in lower for marker in ("drm", "widevine", "playready", "fairplay", "encrypted media")):
        hints.append("This stream appears to be DRM-protected. Shield Stream does not bypass DRM protection.")

    if "ffmpeg" in lower and ("not found" in lower or "install" in lower or "merge" in lower):
        hints.append("FFmpeg could not be used. Rerun run_windows.bat so the bundled dependency can be repaired.")

    runtime_name, _ = find_js_runtime()
    js_problem = any(
        marker in lower
        for marker in (
            "javascript runtime",
            "js runtime",
            "challenge solving failed",
            "n challenge",
            "no video formats found",
            "requested format is not available",
        )
    )
    if js_problem and not runtime_name:
        hints.append("A JavaScript runtime is required for this site. Run install_deno_windows.bat, then restart the app.")

    if "sign in" in lower or "login" in lower or "confirm you" in lower or "age" in lower or "cookies" in lower:
        hints.append("This page may require your signed-in browser session. Enable 'Use browser session when required' in Settings and retry.")

    if "unsupported url" in lower or "no suitable extractor" in lower:
        hints.append("This webpage is not supported by the current extractor. Direct MP4/WebM/HLS/DASH links can still be downloaded.")

    if "403" in lower or "forbidden" in lower or "cloudflare" in lower:
        hints.append("The website blocked the automated request. If you are authorized to access the media, try enabling your browser session in Settings, then retry.")

    if "404" in lower or "not found" in lower:
        hints.append("The captured media endpoint may have expired or may not be the real stream. Keep playback running, run the extension Power Scan again, and send a freshly verified stream.")

    if "security error" in lower or "text error instead of media" in lower:
        hints.append("The server returned a text/security response instead of video bytes. Re-scan while playback is active; signed stream URLs can expire quickly.")

    if hints:
        return text + "\n\n" + "\n".join(f"- {hint}" for hint in hints)
    return text


class AnalyzeSignals(QObject):
    item = Signal(object)
    status = Signal(str)
    warning = Signal(str)
    finished = Signal(int, int)
    error = Signal(str)


class AnalyzeWorker(QRunnable):
    """Analyze supported webpages, playlists, and direct media URLs without downloading."""

    def __init__(self, urls: Iterable[str], browser: str | None = None):
        super().__init__()
        self.urls = [normalize_url(url) for url in urls]
        self.browser = browser
        self.signals = AnalyzeSignals()

    def _emit_fallback(self, url: str, reason: str) -> int:
        if not _can_fallback(url) or _looks_like_playlist(url):
            return 0
        self.signals.item.emit(_fallback_item(url))
        first_line = (reason or "Metadata preview was unavailable").splitlines()[0]
        self.signals.warning.emit(
            "Preview metadata could not be loaded, but this direct media/video link was added anyway. "
            f"Details: {first_line}"
        )
        return 1

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        value = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(name or "download")).strip(" .")
        return value[:180] or "download"

    def _download_generic_file(self, source_url: str) -> str:
        """Resume a normal direct HTTP file without routing it through yt-dlp."""
        parsed = urlparse(source_url)
        name = Path(unquote(parsed.path)).name or "download"
        name = self._sanitize_filename(name)
        final_path = Path(self.output_dir) / name
        part_path = final_path.with_name(final_path.name + ".part")
        existing = part_path.stat().st_size if part_path.exists() else 0

        headers = dict(self.item.http_headers)
        headers.update(self.variant_headers)
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = urllib.request.Request(source_url, headers=headers, method="GET")
        try:
            response = urllib.request.urlopen(request, timeout=35)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and part_path.exists() and part_path.stat().st_size > 0:
                part_path.replace(final_path)
                return str(final_path)
            raise

        status = int(getattr(response, "status", 200) or 200)
        disposition = response.headers.get("Content-Disposition", "")
        match = re.search(r'filename\*?=(?:UTF-8\'\'|["\']?)([^"\';]+)', disposition, re.I)
        if match:
            try:
                detected = unquote(match.group(1).strip().strip('"\''))
                if detected:
                    name = self._sanitize_filename(detected)
                    final_path = Path(self.output_dir) / name
                    part_path = final_path.with_name(final_path.name + ".part")
                    existing = part_path.stat().st_size if part_path.exists() else 0
            except Exception:
                pass

        if status != 206 and existing:
            existing = 0
        content_length = int(response.headers.get("Content-Length") or 0)
        total = existing + content_length if content_length else 0
        mode = "ab" if status == 206 and existing else "wb"
        downloaded = existing
        started = time.monotonic()
        last_emit = started
        with open(part_path, mode) as handle:
            while True:
                if self.cancel_event.is_set():
                    raise yt_dlp.utils.DownloadError("Cancelled by user")
                chunk = response.read(1024 * 512)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if now - last_emit >= 0.25:
                    elapsed = max(0.001, now - started)
                    speed_bps = max(0.0, (downloaded - existing) / elapsed)
                    percent = (downloaded / total * 100.0) if total else 0.0
                    eta = ((total - downloaded) / speed_bps) if total and speed_bps > 0 else None
                    self.signals.progress.emit(
                        self.item.key,
                        percent,
                        self._human_speed(speed_bps),
                        self._human_eta(eta),
                        "Downloading",
                    )
                    last_emit = now
        response.close()
        part_path.replace(final_path)
        self._validate_downloaded_files([final_path])
        return str(final_path)

    @Slot()
    def run(self):
        added = 0
        failed = 0
        base_opts = {
            "quiet": True,
            "no_warnings": False,
            "skip_download": True,
            "extract_flat": "in_playlist",
            "ignoreerrors": False,
            "lazy_playlist": False,
            "socket_timeout": 25,
            "retries": 3,
            "extractor_retries": 3,
            **yt_dlp_runtime_options(),
            **_browser_options(self.browser),
        }

        for index, url in enumerate(self.urls, start=1):
            logger = _CaptureLogger()
            opts = dict(base_opts)
            opts["logger"] = logger
            self.signals.status.emit(f"Analyzing {index}/{len(self.urls)}")

            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as exc:
                detail = str(exc).strip() or "Unknown analysis error"
                tail = logger.tail()
                if tail and tail not in detail:
                    detail = f"{detail}\n{tail}"
                fallback_added = self._emit_fallback(url, detail)
                if fallback_added:
                    added += fallback_added
                else:
                    failed += 1
                    self.signals.error.emit(f"Could not analyze: {url}\n{detail}")
                continue

            if not info:
                detail = logger.tail() or "The extractor returned no media metadata for this page."
                fallback_added = self._emit_fallback(url, detail)
                if fallback_added:
                    added += fallback_added
                else:
                    failed += 1
                    self.signals.error.emit(f"Could not analyze: {url}\n{detail}")
                continue

            entries = info.get("entries") if isinstance(info, dict) else None
            if entries is not None:
                playlist_title = str(info.get("title") or "Playlist")
                playlist_added = 0
                for entry in entries:
                    if not entry:
                        continue
                    item_url = _video_url(entry)
                    if not item_url:
                        continue
                    item = VideoItem(
                        title=str(entry.get("title") or entry.get("id") or "Untitled video"),
                        webpage_url=item_url,
                        video_id=str(entry.get("id") or ""),
                        duration=entry.get("duration"),
                        thumbnail=str(entry.get("thumbnail") or ""),
                        source=_source_from_info(entry, item_url),
                        playlist_title=playlist_title,
                        extractor=str(entry.get("extractor_key") or entry.get("extractor") or ""),
                        direct_media=bool(entry.get("direct")) or is_direct_media_url(item_url),
                        media_kind=direct_media_kind(item_url),
                        http_headers=_safe_headers(entry.get("http_headers")),
                    )
                    self.signals.item.emit(item)
                    playlist_added += 1
                    added += 1
                if playlist_added == 0:
                    failed += 1
                    self.signals.error.emit(
                        f"A collection was found but no downloadable video entries were returned: {url}"
                    )
                continue

            item_url = _video_url(info) or url
            item = VideoItem(
                title=str(info.get("title") or info.get("id") or "Untitled video"),
                webpage_url=item_url,
                video_id=str(info.get("id") or ""),
                duration=info.get("duration"),
                thumbnail=str(info.get("thumbnail") or ""),
                source=_source_from_info(info, item_url),
                extractor=str(info.get("extractor_key") or info.get("extractor") or ""),
                direct_media=bool(info.get("direct")) or is_direct_media_url(item_url),
                media_kind=direct_media_kind(item_url),
                http_headers=_safe_headers(info.get("http_headers")),
            )
            if item.webpage_url:
                self.signals.item.emit(item)
                added += 1
            else:
                fallback_added = self._emit_fallback(url, "Metadata did not contain a usable media URL.")
                if fallback_added:
                    added += fallback_added
                else:
                    failed += 1
                    self.signals.error.emit(f"Could not build a usable media URL from metadata: {url}")

        self.signals.finished.emit(added, failed)


class DownloadSignals(QObject):
    progress = Signal(str, float, str, str, str)
    finished = Signal(str, str)
    error = Signal(str, str)


class DownloadWorker(QRunnable):
    """Reliable resumable downloader used by Shield Stream V2.

    yt-dlp handles site-specific extraction and video/audio merge. For normal
    non-DRM direct/HLS/DASH streams, V2 keeps .part files for resume, uses
    fragment concurrency, and optionally delegates progressive HTTP transfers
    to aria2c when the user chooses Maximum mode and aria2c is installed.
    """

    def __init__(
        self,
        item: VideoItem,
        output_dir: str,
        quality: str,
        concurrent_fragments: int = 8,
        browser: str | None = None,
        format_id: str = "",
        variant_url: str = "",
        variant_headers: dict[str, str] | None = None,
        speed_mode: str = "Fast",
        download_subtitles: bool = False,
        subtitle_langs: str = "en.*",
    ):
        super().__init__()
        self.item = item
        self.output_dir = str(Path(output_dir))
        self.quality = quality
        self.concurrent_fragments = max(1, int(concurrent_fragments))
        self.browser = browser
        self.format_id = str(format_id or "").strip()
        self.variant_url = str(variant_url or "").strip()
        self.variant_headers = dict(variant_headers or {})
        self.speed_mode = str(speed_mode or "Fast").title()
        self.download_subtitles = bool(download_subtitles)
        self.subtitle_langs = str(subtitle_langs or "en.*").strip() or "en.*"
        self.signals = DownloadSignals()
        self.cancel_event = threading.Event()
        self._last_filename = ""

    def cancel(self):
        self.cancel_event.set()

    def _format_selector(self) -> str:
        if self.format_id:
            # Exact format selection is used for probed manifests. If it is a
            # video-only representation yt-dlp can merge the best matching
            # audio stream when available.
            return f"{self.format_id}+bestaudio/{self.format_id}/best"
        quality = self.quality.lower()
        if quality in {"mp3", "audio"} or quality.startswith("audio"):
            return "bestaudio/best"
        if quality == "best":
            return "bestvideo*+bestaudio/best"
        height = "".join(ch for ch in quality if ch.isdigit())
        if height:
            return (
                f"bestvideo*[height<={height}]+bestaudio/"
                f"best[height<={height}]/bestvideo*+bestaudio/best"
            )
        return "bestvideo*+bestaudio/best"

    @staticmethod
    def _human_speed(value) -> str:
        if not value:
            return "--"
        speed = float(value)
        units = ["B/s", "KB/s", "MB/s", "GB/s"]
        unit = units[0]
        for unit in units:
            if speed < 1024 or unit == units[-1]:
                break
            speed /= 1024
        return f"{speed:.1f} {unit}"

    @staticmethod
    def _human_eta(value) -> str:
        if value is None:
            return "--"
        try:
            total = max(0, int(value))
        except (TypeError, ValueError):
            return "--"
        minutes, seconds = divmod(total, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:d}:{seconds:02d}"

    def _progress_hook(self, data: dict):
        if self.cancel_event.is_set():
            raise yt_dlp.utils.DownloadError("Cancelled by user")

        status = data.get("status")
        if status == "downloading":
            downloaded = float(data.get("downloaded_bytes") or 0)
            total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            percent = (downloaded / total * 100.0) if total > 0 else 0.0
            speed = self._human_speed(data.get("speed"))
            eta = self._human_eta(data.get("eta"))
            self.signals.progress.emit(self.item.key, percent, speed, eta, "Downloading")
        elif status == "finished":
            filename = str(data.get("filename") or "").strip()
            if filename:
                self._last_filename = filename
            self.signals.progress.emit(self.item.key, 100.0, "--", "--", "Processing")

    @staticmethod
    def _looks_like_text_error(path: Path) -> tuple[bool, str]:
        try:
            size = path.stat().st_size
            if size <= 0:
                return True, "The downloaded file is empty."
            if size > 128 * 1024:
                return False, ""
            data = path.read_bytes()[:8192]
        except Exception:
            return False, ""

        if not data:
            return True, "The downloaded file is empty."

        printable = sum(1 for b in data if b in b"\t\r\n" or 32 <= b < 127)
        is_text = printable / max(1, len(data)) > 0.92 and b"\x00" not in data
        if not is_text:
            return False, ""

        text = data.decode("utf-8", errors="replace").strip()
        lower = text.lower()
        error_markers = (
            "security error", "access denied", "forbidden", "not found",
            "unauthorized", "permission denied", "invalid token", "expired",
            "<!doctype html", "<html", "<head", "<body", "error 403", "error 404",
        )
        if any(marker in lower for marker in error_markers):
            preview = " ".join(text.split())[:220]
            return True, f"Server returned a text error instead of media: {preview}"

        if path.suffix.lower() in {".unknown_video", ".txt", ".html", ".htm"} and not lower.startswith("#extm3u"):
            preview = " ".join(text.split())[:220]
            return True, f"Server returned text instead of a playable media file: {preview}"
        return False, ""

    def _result_paths(self, result, ydl) -> list[Path]:
        values: list[str] = []
        if self._last_filename:
            values.append(self._last_filename)
        if isinstance(result, dict):
            for key in ("filepath", "_filename"):
                value = result.get(key)
                if value:
                    values.append(str(value))
            for download in result.get("requested_downloads") or []:
                if isinstance(download, dict):
                    for key in ("filepath", "filename"):
                        value = download.get(key)
                        if value:
                            values.append(str(value))
            try:
                prepared = ydl.prepare_filename(result)
                if prepared:
                    values.append(str(prepared))
            except Exception:
                pass

        unique: list[Path] = []
        seen: set[str] = set()
        for value in values:
            try:
                path = Path(value)
                key = str(path.resolve()) if path.exists() else str(path)
            except Exception:
                path = Path(value)
                key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.exists() and path.is_file():
                unique.append(path)
        return unique

    def _validate_downloaded_files(self, paths: list[Path]) -> None:
        for path in paths:
            bad, reason = self._looks_like_text_error(path)
            if not bad:
                continue
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            raise yt_dlp.utils.DownloadError(reason)

    def _build_opts(self, logger: _CaptureLogger, exact_format: bool = True) -> dict:
        fragments = self.concurrent_fragments
        if self.speed_mode == "Normal":
            fragments = min(fragments, 4)
        elif self.speed_mode == "Maximum":
            fragments = max(fragments, 16)

        opts = {
            "format": self._format_selector() if exact_format else "bestvideo*+bestaudio/best",
            "outtmpl": str(Path(self.output_dir) / "%(title).180B [%(id)s].%(ext)s"),
            "noplaylist": True,
            "quiet": True,
            "no_warnings": False,
            "windowsfilenames": True,
            "concurrent_fragment_downloads": fragments,
            "retries": 12,
            "fragment_retries": 12,
            "extractor_retries": 4,
            "file_access_retries": 5,
            "socket_timeout": 30,
            "merge_output_format": "mp4",
            "progress_hooks": [self._progress_hook],
            "logger": logger,
            "continuedl": True,
            "nopart": False,
            "overwrites": False,
            "part": True,
            **yt_dlp_runtime_options(),
            **_browser_options(self.browser),
        }

        headers = dict(self.item.http_headers)
        headers.update(self.variant_headers)
        if headers:
            opts["http_headers"] = headers

        # Optional aria2 acceleration is only used when explicitly requested.
        aria2 = find_aria2c()
        if self.speed_mode == "Maximum" and aria2:
            opts["external_downloader"] = {"http": aria2, "https": aria2}
            opts["external_downloader_args"] = {
                "aria2c": ["-x16", "-s16", "-k1M", "--file-allocation=none", "--summary-interval=1"]
            }

        if self.quality.lower() == "mp3" or self.quality.lower().startswith("audio"):
            opts["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ]

        if self.download_subtitles:
            langs = [part.strip() for part in re.split(r"[,;]", self.subtitle_langs) if part.strip()]
            opts.update({
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": langs or ["en.*"],
                "embedsubtitles": True,
            })
        return opts

    def _download_once(self, source_url: str, logger: _CaptureLogger, exact_format: bool = True):
        opts = self._build_opts(logger, exact_format=exact_format)
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(normalize_url(source_url), download=True)
            result_paths = self._result_paths(result, ydl)
            self._validate_downloaded_files(result_paths)
            filename = str(result_paths[0]) if result_paths else ""
            if not filename and result:
                try:
                    filename = ydl.prepare_filename(result)
                except Exception:
                    filename = ""
            return filename

    @Slot()
    def run(self):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        logger = _CaptureLogger()
        source_url = self.variant_url or self.item.active_url()
        if not source_url:
            self.signals.error.emit(self.item.key, "No media URL is available for this download.")
            return

        try:
            self.signals.progress.emit(self.item.key, 0.0, "--", "--", "Starting")
            if self.item.media_kind == "file":
                filename = self._download_generic_file(source_url)
                if self.cancel_event.is_set():
                    self.signals.error.emit(self.item.key, "Cancelled")
                else:
                    self.signals.finished.emit(self.item.key, filename)
                return
            filename = ""
            last_error: Exception | None = None

            # Smart retry pass 1: exact requested representation.
            # Pass 2: if the exact format vanished, retry the same fresh URL with
            # Best. Temporary 403/404 endpoints are not bypassed; the UI asks the
            # user to re-scan Chrome for a fresh authorized URL.
            for attempt in range(2):
                if self.cancel_event.is_set():
                    raise yt_dlp.utils.DownloadError("Cancelled by user")
                try:
                    logger.clear()
                    filename = self._download_once(source_url, logger, exact_format=(attempt == 0))
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    text = f"{exc}\n{logger.tail()}".lower()
                    format_problem = any(marker in text for marker in (
                        "requested format is not available", "no video formats found", "format selector"
                    ))
                    if attempt == 0 and format_problem:
                        self.signals.progress.emit(self.item.key, 0.0, "--", "--", "Trying alternate quality")
                        time.sleep(0.4)
                        continue
                    raise

            if last_error:
                raise last_error
            if self.cancel_event.is_set():
                self.signals.error.emit(self.item.key, "Cancelled")
            else:
                self.signals.finished.emit(self.item.key, filename)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.signals.error.emit(self.item.key, "Cancelled")
                return

            parts = [str(exc).strip()]
            tail = logger.tail()
            if tail and tail not in parts[0]:
                parts.append(tail)
            raw = "\n".join(part for part in parts if part)
            self.signals.error.emit(self.item.key, _friendly_download_error(raw))
