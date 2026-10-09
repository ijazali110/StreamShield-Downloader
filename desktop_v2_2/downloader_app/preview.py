from __future__ import annotations

import tempfile
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget
    HAS_QT_MEDIA = True
except Exception:
    HAS_QT_MEDIA = False
    QAudioOutput = QMediaPlayer = QVideoWidget = None

from .models import VideoItem
from .runtime import find_ffmpeg, find_ffplay


class _PreviewDialog(QDialog):
    failed = Signal(str)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Preview - {title}")
        self.resize(900, 560)
        self.setMinimumSize(640, 400)
        self.setStyleSheet(
            "QDialog{background:#111;color:#eee;} "
            "QPushButton{padding:8px 16px;} QLabel{color:#bbb;}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        self.video = QVideoWidget(self)
        self.video.setStyleSheet("background:#000;")
        layout.addWidget(self.video, 1)
        controls = QHBoxLayout()
        self.state = QLabel("Loading preview...")
        controls.addWidget(self.state)
        controls.addStretch(1)
        self.play_btn = QPushButton("Pause")
        self.play_btn.clicked.connect(self._toggle)
        controls.addWidget(self.play_btn)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        controls.addWidget(close_btn)
        layout.addLayout(controls)

        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._status)
        self.player.errorOccurred.connect(self._error)

    def open_url(self, url: str):
        path = Path(url)
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path.is_file() else QUrl(url))
        self.player.play()
        self.show()
        self.raise_()
        self.activateWindow()

    def _toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.play_btn.setText("Play")
        else:
            self.player.play()
            self.play_btn.setText("Pause")

    def _status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            self.state.setText("Preview ready")
        elif status == QMediaPlayer.MediaStatus.BufferedMedia:
            self.state.setText("Playing")
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.state.setText("Preview ended")
            self.play_btn.setText("Play")

    def _error(self, _error, text=""):
        message = str(text or self.player.errorString() or "The built-in preview player could not play this stream.")
        self.state.setText("Preview unavailable")
        self.failed.emit(message)

    def closeEvent(self, event):
        self.player.stop()
        super().closeEvent(event)


class PreviewController(QObject):
    """Preview selected media before downloading.

    V2.0.1 removes the hard dependency on ffplay. Header-bound streams first
    use ffplay when it is already installed. If ffplay is unavailable, the
    bundled/system ffmpeg prepares a short local compatibility preview and the
    normal in-app Qt player opens it. This means Referer/Origin protected
    *non-DRM* streams can still be verified before download without requiring
    the user to install a second player binary.
    """

    error = Signal(str)
    preparing = Signal(str)
    started = Signal(str)
    stopped = Signal()

    PREVIEW_SECONDS = 30

    def __init__(self, parent=None):
        super().__init__(parent)
        self.owner = parent
        self.process: QProcess | None = None
        self.prepare_process: QProcess | None = None
        self.dialog: _PreviewDialog | None = None
        self.current_key = ""
        self.temp_preview: Path | None = None
        self._prepare_item: VideoItem | None = None
        self._prepare_target = ""
        self._prepare_codec = "libx264"
        self._cleanup_old_preview_files()

    @staticmethod
    def _header_blob(headers: dict[str, str]) -> str:
        safe = []
        for key, value in (headers or {}).items():
            k = str(key).strip().replace("\r", "").replace("\n", "")
            v = str(value).strip().replace("\r", "").replace("\n", "")
            if k and v and k.lower() not in {"cookie", "authorization", "proxy-authorization"}:
                safe.append(f"{k}: {v}")
        return "\r\n".join(safe) + ("\r\n" if safe else "")

    @staticmethod
    def _cleanup_old_preview_files():
        root = Path(tempfile.gettempdir())
        cutoff = time.time() - 24 * 3600
        for path in root.glob("streamforge_preview_*.mp4"):
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink(missing_ok=True)
            except Exception:
                pass

    def _cleanup_temp(self):
        path = self.temp_preview
        self.temp_preview = None
        if not path:
            return
        try:
            path.unlink(missing_ok=True)
        except Exception:
            # Windows can keep the file locked briefly after Media Foundation
            # releases it. Try once more a little later.
            QTimer.singleShot(1500, lambda p=path: self._unlink_quietly(p))

    @staticmethod
    def _unlink_quietly(path: Path):
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass

    def stop(self):
        if self.dialog:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.prepare_process and self.prepare_process.state() != QProcess.NotRunning:
            self.prepare_process.kill()
            self.prepare_process.waitForFinished(1000)
        self.prepare_process = None
        if self.process and self.process.state() != QProcess.NotRunning:
            self.process.kill()
            self.process.waitForFinished(1200)
        self.process = None
        self._prepare_item = None
        self._prepare_target = ""
        self.current_key = ""
        self._cleanup_temp()
        self.stopped.emit()

    def _play_external(self, item: VideoItem, target: str):
        ffplay = find_ffplay()
        if not ffplay:
            if item.http_headers:
                self._prepare_local_preview(item, target)
                return
            QDesktopServices.openUrl(QUrl.fromLocalFile(target) if Path(target).is_file() else QUrl(target))
            self.started.emit(item.key)
            return

        args = [
            "-hide_banner", "-loglevel", "warning", "-autoexit",
            "-window_title", f"Shield Stream Preview - {item.title[:80]}",
        ]
        headers = self._header_blob(item.http_headers)
        if headers:
            args += ["-headers", headers]
        args += [target]
        proc = QProcess(self)
        proc.setProgram(ffplay)
        proc.setArguments(args)
        proc.errorOccurred.connect(lambda _err: self.error.emit(proc.errorString() or "Preview player failed to start."))
        proc.finished.connect(lambda *_: self._on_finished(proc))
        proc.start()
        if not proc.waitForStarted(2500):
            self.error.emit(proc.errorString() or "Preview player could not start.")
            proc.deleteLater()
            return
        self.process = proc
        self.current_key = item.key
        self.started.emit(item.key)

    def _ffmpeg_input_args(self, item: VideoItem) -> list[str]:
        headers = dict(item.http_headers or {})
        args: list[str] = []
        referer = str(headers.pop("Referer", headers.pop("referer", "")) or "").strip()
        user_agent = str(headers.pop("User-Agent", headers.pop("user-agent", "")) or "").strip()
        if referer:
            args += ["-referer", referer]
        if user_agent:
            args += ["-user_agent", user_agent]
        blob = self._header_blob(headers)
        if blob:
            args += ["-headers", blob]
        return args

    def _prepare_local_preview(self, item: VideoItem, target: str, codec: str = "libx264"):
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            self.error.emit(
                "Preview needs FFmpeg for this stream. Run install_ffmpeg_windows.bat once, then retry Preview."
            )
            return
        if not HAS_QT_MEDIA:
            self.error.emit("The in-app media player is unavailable in this Python/Qt installation.")
            return

        self._cleanup_temp()
        output = Path(tempfile.gettempdir()) / f"streamforge_preview_{uuid.uuid4().hex}.mp4"
        self.temp_preview = output
        self._prepare_item = item
        self._prepare_target = target
        self._prepare_codec = codec

        args = ["-hide_banner", "-loglevel", "error", "-y"]
        args += self._ffmpeg_input_args(item)
        args += [
            "-i", target,
            "-t", str(self.PREVIEW_SECONDS),
            "-map", "0:v:0?", "-map", "0:a:0?",
        ]
        if codec == "libx264":
            args += ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"]
        else:
            args += ["-c:v", "mpeg4", "-q:v", "6"]
        args += [
            "-c:a", "aac", "-b:a", "128k",
            "-movflags", "+faststart",
            str(output),
        ]

        proc = QProcess(self)
        proc.setProgram(ffmpeg)
        proc.setArguments(args)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.finished.connect(lambda code, status, p=proc: self._on_prepare_finished(p, int(code)))
        proc.errorOccurred.connect(lambda _err, p=proc: self._on_prepare_start_error(p))
        self.prepare_process = proc
        self.current_key = item.key
        self.preparing.emit(
            f"Preparing a {self.PREVIEW_SECONDS}-second local preview. This stream needs request headers, so Shield Stream is using FFmpeg automatically."
        )
        proc.start()
        if not proc.waitForStarted(2500):
            self._on_prepare_start_error(proc)

    def _on_prepare_start_error(self, proc: QProcess):
        if self.prepare_process is not proc:
            return
        message = proc.errorString() or "FFmpeg could not start the preview helper."
        self.prepare_process = None
        self.error.emit(message)
        proc.deleteLater()

    def _on_prepare_finished(self, proc: QProcess, exit_code: int):
        if self.prepare_process is not proc:
            proc.deleteLater()
            return
        self.prepare_process = None
        details = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()
        item = self._prepare_item
        target = self._prepare_target
        codec = self._prepare_codec
        output = self.temp_preview
        proc.deleteLater()

        if not item or not output:
            return
        valid = False
        try:
            valid = output.is_file() and output.stat().st_size > 32 * 1024
        except Exception:
            valid = False

        if exit_code != 0 or not valid:
            # Some FFmpeg builds do not include libx264. Retry once using the
            # built-in MPEG-4 encoder before reporting an error.
            if codec == "libx264":
                self._prepare_local_preview(item, target, codec="mpeg4")
                return
            self.error.emit(
                "Shield Stream could not create a local preview for this stream. "
                + (details[-700:] if details else "The server may have rejected the preview request or the media codec is unsupported.")
            )
            self._cleanup_temp()
            return

        self._open_in_app(item, str(output), local_compat=True)

    def _open_in_app(self, item: VideoItem, target: str, local_compat: bool = False):
        try:
            dialog = _PreviewDialog(item.title, self.owner)
            dialog.failed.connect(lambda message: self._fallback_after_qt_failure(item, target, message, dialog))
            if local_compat:
                dialog.state.setText(f"{self.PREVIEW_SECONDS}s compatibility preview")
            dialog.open_url(target)
            self.dialog = dialog
            self.current_key = item.key
            self.started.emit(item.key)
        except Exception as exc:
            self.error.emit(str(exc) or "The in-app preview player could not start.")

    def play(self, item: VideoItem, url: str | None = None):
        self.stop()
        target = str(url or item.active_url() or "").strip()
        if not target:
            self.error.emit("No previewable media URL is available for this item.")
            return

        if HAS_QT_MEDIA and not item.http_headers:
            self._open_in_app(item, target)
            return

        self._play_external(item, target)

    def _fallback_after_qt_failure(self, item: VideoItem, target: str, message: str, dialog: _PreviewDialog):
        if self.dialog is dialog:
            dialog.close()
            dialog.deleteLater()
            self.dialog = None

        # A local compatibility preview has already been normalized by FFmpeg.
        # If Windows still cannot play it, ffplay is the only useful fallback.
        if self.temp_preview and Path(target) == self.temp_preview:
            if find_ffplay():
                self._play_external(item, target)
            else:
                self.error.emit(message)
            return

        if find_ffplay():
            self._play_external(item, target)
        elif item.http_headers:
            self._prepare_local_preview(item, target)
        else:
            self.error.emit(message)

    def _on_finished(self, proc: QProcess):
        if self.process is proc:
            self.process = None
            self.current_key = ""
            self.stopped.emit()
        proc.deleteLater()
