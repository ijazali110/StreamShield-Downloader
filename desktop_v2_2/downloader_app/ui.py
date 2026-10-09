from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QProcess, QSettings, QThreadPool, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .browser_bridge import BrowserBridge, BrowserBridgeSignals
from .history import HistoryStore
from .media_probe import FormatProbeWorker
from .preview import PreviewController
from .models import MediaVariant, VideoItem, format_duration
from .workers import (
    AnalyzeWorker,
    DownloadWorker,
    direct_media_kind,
    extract_urls,
    normalize_url,
    site_label,
)


APP_STYLE = r"""
* {
    font-family: "Segoe UI Variable", "Segoe UI";
}
QWidget {
    background: transparent;
    color: #E5E2E1;
    font-size: 10pt;
}
QMainWindow, QWidget#Root {
    background: #131313;
}
QFrame#TopBar {
    background: #151515;
    border-bottom: 1px solid #2A2A2A;
}
QLabel#BrandName {
    color: #AFC8FF;
    font-size: 20pt;
    font-weight: 800;
}
QLabel#PageTitle {
    color: #F2F1F1;
    font-size: 31pt;
    font-weight: 800;
}
QLabel#PageSubtitle, QLabel#Muted, QLabel#MetaText {
    color: #A9ADBA;
}
QLabel#SectionLabel {
    color: #AFC8FF;
    font-size: 8.5pt;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#SectionTitle {
    color: #F0EEEE;
    font-size: 18pt;
    font-weight: 700;
}
QFrame#HeroCard, QFrame#VideoCard, QFrame#DownloadCard, QFrame#SettingsPanel,
QFrame#SelectionBar, QFrame#InputPill, QFrame#Sidebar, QFrame#Toast {
    background: #201F1F;
    border: 1px solid #333332;
    border-radius: 22px;
}
QFrame#VideoCard:hover, QFrame#DownloadCard:hover {
    border-color: #465068;
    background: #242323;
}
QFrame#Sidebar {
    background: #1B1B1B;
    border-radius: 0px;
    border-left: none;
    border-top: none;
    border-bottom: none;
    border-right: 1px solid #2A2A2A;
}
QTextEdit, QLineEdit, QComboBox, QSpinBox {
    background: #2A2A2A;
    color: #F0EEEE;
    border: 1px solid #3B3B3B;
    border-radius: 14px;
    selection-background-color: #4D8EFF;
}
QTextEdit {
    padding: 16px 18px;
    font-size: 14pt;
}
QLineEdit {
    padding: 0px 14px;
    min-height: 40px;
}
QComboBox, QSpinBox {
    padding: 0px 12px;
    min-height: 38px;
}
QTextEdit:focus, QLineEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #6F9FFF;
}
QComboBox::drop-down {
    border: none;
    width: 26px;
}
QComboBox QAbstractItemView {
    background: #262626;
    color: #F0EEEE;
    border: 1px solid #414141;
    selection-background-color: #334E79;
    padding: 6px;
}
QSpinBox::up-button, QSpinBox::down-button {
    width: 18px;
    border: none;
}
QPushButton {
    background: #292929;
    color: #E2E0E0;
    border: 1px solid #3A3A3A;
    border-radius: 16px;
    padding: 9px 16px;
    min-height: 34px;
    font-weight: 650;
}
QPushButton:hover {
    background: #303030;
    border-color: #505050;
}
QPushButton:pressed {
    background: #252525;
}
QPushButton:disabled {
    color: #686868;
    border-color: #2E2E2E;
    background: #222222;
}
QPushButton#Primary {
    color: #FFFFFF;
    border: 1px solid #668FFF;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #4D8EFF, stop:1 #6A23D4);
    border-radius: 18px;
    font-weight: 800;
}
QPushButton#Primary:hover {
    border-color: #87A9FF;
}
QPushButton#Ghost {
    background: transparent;
    border: 1px solid #3B3B3B;
}
QPushButton#TextButton {
    background: transparent;
    border: none;
    color: #B8BBC5;
    padding: 5px 8px;
    min-height: 24px;
    font-weight: 600;
}
QPushButton#TextButton:hover {
    color: #AFC8FF;
    background: transparent;
}
QPushButton#Nav {
    background: transparent;
    border: none;
    border-radius: 18px;
    color: #BABDC7;
    text-align: left;
    padding: 11px 16px;
    min-height: 38px;
    font-weight: 650;
}
QPushButton#Nav:hover {
    background: #242424;
    color: #FFFFFF;
}
QPushButton#NavActive {
    background: #5B20C9;
    border: none;
    border-radius: 18px;
    color: #E4D8FF;
    text-align: left;
    padding: 11px 16px;
    min-height: 38px;
    font-weight: 800;
}
QPushButton#WindowButton {
    background: transparent;
    border: none;
    border-radius: 13px;
    color: #B7BAC4;
    padding: 0px;
    min-height: 30px;
    min-width: 30px;
    max-height: 30px;
    max-width: 30px;
    font-size: 13pt;
}
QPushButton#WindowButton:hover {
    background: #292929;
    color: #FFFFFF;
}
QPushButton#CloseButton {
    background: transparent;
    border: none;
    border-radius: 13px;
    color: #B7BAC4;
    padding: 0px;
    min-height: 30px;
    min-width: 30px;
    max-height: 30px;
    max-width: 30px;
    font-size: 13pt;
}
QPushButton#CloseButton:hover {
    background: #4B1D22;
    color: #FFB4AB;
}
QPushButton#RoundAction {
    min-width: 38px;
    max-width: 38px;
    min-height: 38px;
    max-height: 38px;
    padding: 0px;
    border-radius: 19px;
    background: #292929;
}
QPushButton#RoundPrimary {
    min-width: 42px;
    max-width: 42px;
    min-height: 42px;
    max-height: 42px;
    padding: 0px;
    border-radius: 21px;
    color: white;
    border: 1px solid #668FFF;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #4D8EFF, stop:1 #6A23D4);
    font-size: 15pt;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 9px;
    border: 2px solid #717480;
    background: transparent;
}
QCheckBox::indicator:hover {
    border-color: #8FB1FF;
}
QCheckBox::indicator:checked {
    border: 2px solid #4D8EFF;
    background: #4D8EFF;
}
QProgressBar {
    background: #363636;
    border: none;
    border-radius: 3px;
    min-height: 5px;
    max-height: 5px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #4D8EFF;
    border-radius: 3px;
}
QScrollArea {
    border: none;
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 9px;
    margin: 4px 2px;
}
QScrollBar::handle:vertical {
    background: #3A3A3A;
    min-height: 28px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #505050;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: transparent;
    height: 0px;
}
QScrollBar:horizontal {
    height: 0px;
}
QFrame#Footer {
    background: #0F0F0F;
    border-top: 1px solid #242424;
}
QLabel#StatusSuccess { color: #4CD7F6; font-weight: 700; }
QLabel#StatusError { color: #FFB4AB; font-weight: 700; }
QLabel#StatusWarning { color: #F0CC6B; font-weight: 700; }
"""


QUALITY_OPTIONS = ["Best", "1080p", "720p", "480p", "360p", "MP3"]


def add_shadow(widget: QWidget, blur: int = 28, y: int = 8, opacity: int = 120):
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(Qt.black)
    widget.setGraphicsEffect(effect)


class TitleBar(QFrame):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self.setObjectName("TopBar")
        self.setFixedHeight(64)
        self._drag_offset = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 10, 20, 10)
        layout.setSpacing(10)

        icon = QLabel("↓")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(38, 38)
        icon.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #4D8EFF,stop:1 #6A23D4);"
            "border-radius:19px;color:white;font-size:17pt;font-weight:900;"
        )
        layout.addWidget(icon)

        brand = QLabel("Shield Stream")
        brand.setObjectName("BrandName")
        layout.addWidget(brand)
        layout.addStretch(1)

        self.home_btn = QPushButton("Home")
        self.home_btn.setObjectName("TextButton")
        self.home_btn.clicked.connect(lambda: window.show_page("home"))
        layout.addWidget(self.home_btn)

        self.downloads_btn = QPushButton("Downloads")
        self.downloads_btn.setObjectName("TextButton")
        self.downloads_btn.clicked.connect(lambda: window.show_page("downloads"))
        layout.addWidget(self.downloads_btn)

        settings_btn = QPushButton("Settings")
        settings_btn.setObjectName("TextButton")
        settings_btn.clicked.connect(window.open_settings)
        layout.addWidget(settings_btn)

        layout.addSpacing(12)
        min_btn = QPushButton("−")
        min_btn.setObjectName("WindowButton")
        min_btn.clicked.connect(window.showMinimized)
        layout.addWidget(min_btn)

        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("WindowButton")
        self.max_btn.clicked.connect(window.toggle_maximize)
        layout.addWidget(self.max_btn)

        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseButton")
        close_btn.clicked.connect(window.close)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.window.isMaximized():
            self._drag_offset = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton and not self.window.isMaximized():
            self.window.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.window.toggle_maximize()
        super().mouseDoubleClickEvent(event)


class VideoCard(QFrame):
    selection_changed = Signal()
    download_requested = Signal(str)
    preview_requested = Signal(str)

    def __init__(self, item: VideoItem, default_quality: str, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("VideoCard")
        self.setMinimumHeight(126)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._variant_by_label: dict[str, object] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 13, 14, 12)
        outer.setSpacing(8)

        main = QHBoxLayout()
        main.setSpacing(12)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(lambda *_: self.selection_changed.emit())
        main.addWidget(self.checkbox, 0, Qt.AlignVCenter)

        self.thumb = QLabel("No preview")
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(144, 81)
        self.thumb.setStyleSheet(
            "background:#171717;border:1px solid #343434;border-radius:12px;"
            "color:#777A84;font-size:8pt;"
        )
        main.addWidget(self.thumb)

        info = QVBoxLayout()
        info.setSpacing(5)
        self.title_label = QLabel(item.title)
        self.title_label.setStyleSheet("color:#F1EFEF;font-size:12.5pt;font-weight:700;")
        self.title_label.setToolTip(item.title)
        self.title_label.setWordWrap(False)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        info.addWidget(self.title_label)

        self.meta_label = QLabel("")
        self.meta_label.setObjectName("MetaText")
        self.meta_label.setStyleSheet("font-size:9.5pt;")
        info.addWidget(self.meta_label)

        self.state_text = QLabel("Ready")
        self.state_text.setObjectName("Muted")
        self.state_text.setStyleSheet("font-size:9pt;")
        info.addWidget(self.state_text)
        info.addStretch(1)
        main.addLayout(info, 1)

        self.quality_combo = QComboBox()
        self.quality_combo.setFixedWidth(145)
        main.addWidget(self.quality_combo, 0, Qt.AlignVCenter)

        self.preview_btn = QPushButton("▶")
        self.preview_btn.setObjectName("RoundAction")
        self.preview_btn.setToolTip("Preview / play before downloading")
        self.preview_btn.clicked.connect(lambda: self.preview_requested.emit(self.item.key))
        main.addWidget(self.preview_btn, 0, Qt.AlignVCenter)

        self.download_btn = QPushButton("↓")
        self.download_btn.setObjectName("RoundPrimary")
        self.download_btn.setToolTip("Download this video")
        self.download_btn.clicked.connect(lambda: self.download_requested.emit(self.item.key))
        main.addWidget(self.download_btn, 0, Qt.AlignVCenter)

        outer.addLayout(main)

        self.progress_wrap = QWidget()
        progress_layout = QVBoxLayout(self.progress_wrap)
        progress_layout.setContentsMargins(176, 0, 102, 0)
        progress_layout.setSpacing(5)
        progress_top = QHBoxLayout()
        self.progress_status = QLabel("")
        self.progress_status.setObjectName("Muted")
        self.progress_status.setStyleSheet("font-size:8.5pt;")
        self.progress_meta = QLabel("")
        self.progress_meta.setObjectName("Muted")
        self.progress_meta.setStyleSheet("font-size:8.5pt;")
        progress_top.addWidget(self.progress_status)
        progress_top.addStretch(1)
        progress_top.addWidget(self.progress_meta)
        progress_layout.addLayout(progress_top)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        progress_layout.addWidget(self.progress)
        self.progress_wrap.hide()
        outer.addWidget(self.progress_wrap)

        self.set_variants(item.variants, default_quality)
        self.refresh_meta()

    def refresh_meta(self):
        source = self.item.source or "Website"
        details = [format_duration(self.item.duration), source]
        if self.item.verified:
            details.append("Verified stream")
        if self.item.variants:
            details.append(f"{len(self.item.variants)} qualities")
        if self.item.subtitles:
            languages = {str(row.get("language") or "") for row in self.item.subtitles if isinstance(row, dict)}
            details.append(f"{len(languages) or len(self.item.subtitles)} subtitle track(s)")
        self.meta_label.setText("   •   ".join(details))

    def set_variants(self, variants, preferred: str = "Best"):
        previous = self.quality_combo.currentText() if self.quality_combo.count() else preferred
        self.quality_combo.blockSignals(True)
        self.quality_combo.clear()
        self._variant_by_label.clear()

        if variants:
            used: dict[str, int] = {}
            for variant in variants:
                base = variant.display_label()
                used[base] = used.get(base, 0) + 1
                label = base
                if used[base] > 1:
                    suffix = variant.ext.upper() if getattr(variant, "ext", "") else str(used[base])
                    label = f"{base} • {suffix}"
                self._variant_by_label[label] = variant
                self.quality_combo.addItem(label)
            # Prefer the user's requested quality by prefix when possible.
            target = preferred or previous
            idx = next((i for i in range(self.quality_combo.count()) if self.quality_combo.itemText(i).lower().startswith(target.lower())), -1)
            if idx < 0 and previous:
                idx = self.quality_combo.findText(previous)
            self.quality_combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            self.quality_combo.addItems(QUALITY_OPTIONS)
            self.quality_combo.setCurrentText(preferred if preferred in QUALITY_OPTIONS else "Best")
        self.quality_combo.blockSignals(False)
        self.refresh_meta()

    def selected_download_choice(self) -> dict:
        label = self.quality_combo.currentText()
        variant = self._variant_by_label.get(label)
        if variant is None:
            return {"quality": label, "url": "", "format_id": "", "headers": {}}
        return {
            "quality": label,
            "url": getattr(variant, "url", "") or "",
            "format_id": getattr(variant, "format_id", "") or "",
            "headers": dict(getattr(variant, "http_headers", {}) or {}),
        }

    def preview_url(self) -> str:
        choice = self.selected_download_choice()
        return choice.get("url") or self.item.active_url()

    def set_thumbnail(self, pixmap: QPixmap):
        self.thumb.setPixmap(pixmap.scaled(self.thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self.thumb.setText("")

    def set_state(self, state: str, percent: float = 0, speed: str = "", eta: str = "", error: str = ""):
        s = state.lower()
        self.state_text.setText(state)
        self.state_text.setToolTip(error)

        if s in {"starting", "queued", "downloading", "processing", "trying alternate quality"}:
            self.progress_wrap.show()
            self.progress.setValue(max(0, min(100, int(percent))))
            self.progress_status.setText(state.upper())
            if s == "downloading":
                remaining = "" if eta in {"", "--"} else f" • {eta} remaining"
                self.progress_meta.setText(f"{speed}{remaining}")
            else:
                self.progress_meta.setText("")
            self.state_text.setStyleSheet("font-size:9pt;color:#AFC8FF;font-weight:700;")
            self.download_btn.setEnabled(False)
            self.download_btn.setText("…")
        elif s in {"done", "completed", "complete"}:
            self.progress_wrap.show()
            self.progress.setValue(100)
            self.progress_status.setText("DOWNLOAD COMPLETE")
            self.progress_meta.setText("")
            self.state_text.setText("✓ Downloaded")
            self.state_text.setStyleSheet("font-size:9pt;color:#4CD7F6;font-weight:700;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText("↻")
            self.download_btn.setToolTip("Download again")
        elif s == "already downloaded":
            self.progress_wrap.hide()
            self.state_text.setText("✓ Already downloaded")
            self.state_text.setStyleSheet("font-size:9pt;color:#4CD7F6;font-weight:700;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText("↻")
            self.download_btn.setToolTip("Download again")
        elif s == "failed":
            self.progress_wrap.hide()
            self.state_text.setText("Download failed")
            self.state_text.setStyleSheet("font-size:9pt;color:#FFB4AB;font-weight:700;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText("↻")
            self.download_btn.setToolTip(error or "Retry download")
        elif s == "cancelled":
            self.progress_wrap.hide()
            self.state_text.setText("Cancelled")
            self.state_text.setStyleSheet("font-size:9pt;color:#F0CC6B;font-weight:700;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText("↻")
        elif s == "probing":
            self.progress_wrap.hide()
            self.state_text.setText("Checking qualities…")
            self.state_text.setStyleSheet("font-size:9pt;color:#AFC8FF;")
        else:
            self.progress_wrap.hide()
            self.state_text.setText("Ready")
            self.state_text.setStyleSheet("font-size:9pt;color:#A9ADBA;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText("↓")


class DownloadTaskCard(QFrame):
    cancel_requested = Signal(str)
    retry_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(self, item: VideoItem, quality: str, parent=None):
        super().__init__(parent)
        self.item = item
        self.setObjectName("DownloadCard")
        self.setMinimumHeight(128)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(15)

        self.thumb = QLabel("No preview")
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setFixedSize(154, 87)
        self.thumb.setStyleSheet(
            "background:#171717;border:1px solid #343434;border-radius:12px;"
            "color:#777A84;font-size:8pt;"
        )
        layout.addWidget(self.thumb)

        center = QVBoxLayout()
        center.setSpacing(7)
        title = QLabel(item.title)
        title.setStyleSheet("font-size:13pt;font-weight:700;color:#F0EEEE;")
        title.setToolTip(item.title)
        center.addWidget(title)
        meta = QLabel(f"{quality}   •   {format_duration(item.duration)}   •   {item.source or 'Website'}")
        meta.setObjectName("MetaText")
        center.addWidget(meta)

        status_row = QHBoxLayout()
        self.status = QLabel("QUEUED")
        self.status.setStyleSheet("color:#AFC8FF;font-size:8.5pt;font-weight:800;")
        self.speed_eta = QLabel("")
        self.speed_eta.setObjectName("Muted")
        status_row.addWidget(self.status)
        status_row.addStretch(1)
        status_row.addWidget(self.speed_eta)
        center.addLayout(status_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        center.addWidget(self.progress)
        layout.addLayout(center, 1)

        self.action_btn = QPushButton("×")
        self.action_btn.setObjectName("RoundAction")
        self.action_btn.setToolTip("Cancel download")
        self.action_btn.clicked.connect(self._action)
        self.mode = "cancel"
        layout.addWidget(self.action_btn, 0, Qt.AlignVCenter)

    def _action(self):
        if self.mode == "cancel":
            self.cancel_requested.emit(self.item.key)
        elif self.mode == "retry":
            self.retry_requested.emit(self.item.key)
        else:
            self.open_folder_requested.emit(self.item.key)

    def set_thumbnail(self, pixmap: QPixmap):
        self.thumb.setPixmap(pixmap.scaled(self.thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
        self.thumb.setText("")

    def set_state(self, state: str, percent: float = 0, speed: str = "", eta: str = "", error: str = ""):
        s = state.lower()
        if s == "downloading":
            self.status.setText("DOWNLOADING")
            self.status.setStyleSheet("color:#AFC8FF;font-size:8.5pt;font-weight:800;")
            remaining = "" if eta in {"", "--"} else f" • {eta} remaining"
            self.speed_eta.setText(f"{speed}{remaining}")
            self.progress.setValue(max(0, min(100, int(percent))))
            self.mode = "cancel"
            self.action_btn.setText("×")
            self.action_btn.setToolTip("Cancel download")
        elif s in {"starting", "queued", "processing", "trying alternate quality"}:
            self.status.setText(state.upper())
            self.status.setStyleSheet("color:#AFC8FF;font-size:8.5pt;font-weight:800;")
            self.speed_eta.setText("")
            self.progress.setValue(max(0, min(100, int(percent))))
            self.mode = "cancel"
            self.action_btn.setText("×")
        elif s in {"done", "complete", "completed"}:
            self.status.setText("✓ DOWNLOAD COMPLETE")
            self.status.setStyleSheet("color:#4CD7F6;font-size:8.5pt;font-weight:800;")
            self.speed_eta.setText("")
            self.progress.setValue(100)
            self.mode = "folder"
            self.action_btn.setText("⌂")
            self.action_btn.setToolTip("Open download folder")
        elif s == "failed":
            self.status.setText("DOWNLOAD FAILED")
            self.status.setStyleSheet("color:#FFB4AB;font-size:8.5pt;font-weight:800;")
            self.status.setToolTip(error)
            self.speed_eta.setText("")
            self.mode = "retry"
            self.action_btn.setText("↻")
            self.action_btn.setToolTip(error or "Retry")
        elif s == "cancelled":
            self.status.setText("CANCELLED")
            self.status.setStyleSheet("color:#F0CC6B;font-size:8.5pt;font-weight:800;")
            self.speed_eta.setText("")
            self.mode = "retry"
            self.action_btn.setText("↻")


class SettingsDialog(QDialog):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(560)
        self.setStyleSheet(APP_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        panel = QFrame()
        panel.setObjectName("SettingsPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        top = QHBoxLayout()
        title = QLabel("Settings")
        title.setObjectName("SectionTitle")
        top.addWidget(title)
        top.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("WindowButton")
        close.clicked.connect(self.reject)
        top.addWidget(close)
        layout.addLayout(top)

        downloads_label = QLabel("DOWNLOADS")
        downloads_label.setObjectName("SectionLabel")
        layout.addWidget(downloads_label)

        self.default_quality = QComboBox()
        self.default_quality.addItems(QUALITY_OPTIONS)
        layout.addWidget(self._setting_row("Default Quality", "Quality used for newly analyzed videos.", self.default_quality))

        self.parallel = QSpinBox()
        self.parallel.setRange(1, 8)
        self.parallel.setFixedWidth(100)
        layout.addWidget(self._setting_row("Simultaneous Downloads", "How many videos can download at the same time.", self.parallel))

        self.folder = QLineEdit()
        self.folder.setReadOnly(True)
        browse = QPushButton("Browse")
        browse.setObjectName("Ghost")
        browse.clicked.connect(self._browse)
        folder_controls = QWidget()
        folder_layout = QHBoxLayout(folder_controls)
        folder_layout.setContentsMargins(0, 0, 0, 0)
        folder_layout.setSpacing(8)
        folder_layout.addWidget(self.folder, 1)
        folder_layout.addWidget(browse)
        layout.addWidget(self._setting_row("Download Folder", "Where completed files are saved.", folder_controls))

        access_label = QLabel("SITE ACCESS")
        access_label.setObjectName("SectionLabel")
        layout.addWidget(access_label)

        self.use_browser_session = QCheckBox("Use browser session")
        self.browser = QComboBox()
        self.browser.addItems(["Chrome", "Edge", "Firefox", "Brave", "Chromium", "Opera", "Vivaldi"])
        self.browser.setFixedWidth(120)
        browser_controls = QWidget()
        browser_layout = QHBoxLayout(browser_controls)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(8)
        browser_layout.addWidget(self.use_browser_session)
        browser_layout.addWidget(self.browser)
        layout.addWidget(self._setting_row(
            "Browser Session",
            "Optional. Use your own signed-in browser session for sites that require login. Disabled by default.",
            browser_controls,
        ))

        performance_label = QLabel("PERFORMANCE")
        performance_label.setObjectName("SectionLabel")
        layout.addWidget(performance_label)

        self.speed_mode = QComboBox()
        self.speed_mode.addItems(["Normal", "Fast", "Maximum"])
        self.speed_mode.setFixedWidth(120)
        layout.addWidget(self._setting_row(
            "Speed Mode",
            "Normal is conservative, Fast is recommended, Maximum uses aggressive parallel transfers when supported.",
            self.speed_mode,
        ))

        self.fragments = QComboBox()
        self.fragments.addItems(["1", "2", "4", "8", "12", "16", "24", "32"])
        self.fragments.setFixedWidth(100)
        layout.addWidget(self._setting_row("Download Fragments", "Advanced HLS/DASH segment concurrency. Resume is always enabled.", self.fragments))

        media_label = QLabel("MEDIA")
        media_label.setObjectName("SectionLabel")
        layout.addWidget(media_label)
        self.download_subtitles = QCheckBox("Download and embed subtitles when available")
        self.subtitle_langs = QLineEdit()
        self.subtitle_langs.setPlaceholderText("en.*, ur.*, hi.*")
        self.subtitle_langs.setFixedWidth(190)
        sub_controls = QWidget()
        sub_layout = QHBoxLayout(sub_controls)
        sub_layout.setContentsMargins(0, 0, 0, 0)
        sub_layout.setSpacing(8)
        sub_layout.addWidget(self.download_subtitles)
        sub_layout.addWidget(self.subtitle_langs)
        layout.addWidget(self._setting_row(
            "Subtitles",
            "Optional. Download matching subtitles/captions and embed them when the selected output supports it.",
            sub_controls,
        ))

        privacy_label = QLabel("PRIVACY & HISTORY")
        privacy_label.setObjectName("SectionLabel")
        layout.addWidget(privacy_label)
        self.keep_history = QCheckBox("Keep completed-download history")
        self.warn_duplicates = QCheckBox("Warn before downloading the same video again")
        privacy_controls = QWidget()
        privacy_layout = QVBoxLayout(privacy_controls)
        privacy_layout.setContentsMargins(0, 0, 0, 0)
        privacy_layout.setSpacing(4)
        privacy_layout.addWidget(self.keep_history)
        privacy_layout.addWidget(self.warn_duplicates)
        clear_history = QPushButton("Clear History")
        clear_history.setObjectName("Ghost")
        clear_history.clicked.connect(window.clear_history_records)
        privacy_layout.addWidget(clear_history)
        layout.addWidget(self._setting_row(
            "Local History",
            "Only titles, source URLs and completed file paths are stored. Browser cookies/authorization headers are never saved.",
            privacy_controls,
        ))

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save Changes")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

        outer.addWidget(panel)
        add_shadow(panel, 36, 10)

    def _setting_row(self, title: str, description: str, control: QWidget) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet("QFrame{background:#252424;border:1px solid #343434;border-radius:14px;}")
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 12, 14, 12)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight:700;color:#ECEAEA;")
        desc = QLabel(description)
        desc.setObjectName("Muted")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size:8.5pt;")
        text.addWidget(title_label)
        text.addWidget(desc)
        row.addLayout(text, 1)
        row.addWidget(control)
        return frame

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def _save(self):
        self.window.apply_settings_from_dialog()
        self.accept()


class Toast(QFrame):
    retry_clicked = Signal()
    details_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setFixedWidth(390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 13, 16, 13)
        layout.setSpacing(8)
        top = QHBoxLayout()
        self.title = QLabel("Download failed")
        self.title.setStyleSheet("font-weight:800;color:#F3F1F1;")
        top.addWidget(self.title)
        top.addStretch(1)
        close = QPushButton("×")
        close.setObjectName("WindowButton")
        close.clicked.connect(self.hide)
        top.addWidget(close)
        layout.addLayout(top)
        self.message = QLabel("")
        self.message.setObjectName("Muted")
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.details = QPushButton("Details")
        self.details.setObjectName("Ghost")
        self.details.clicked.connect(self.details_clicked.emit)
        self.retry = QPushButton("Retry")
        self.retry.setObjectName("Primary")
        self.retry.clicked.connect(self.retry_clicked.emit)
        actions.addWidget(self.details)
        actions.addWidget(self.retry)
        layout.addLayout(actions)
        add_shadow(self, 28, 8)
        self.hide()


class MainWindow(QMainWindow):
    PAGE_HOME = 0
    PAGE_RESULTS = 1
    PAGE_DOWNLOADS = 2

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shield Stream Video Downloader")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            self.resize(min(1440, int(available.width() * 0.93)), min(900, int(available.height() * 0.9)))
        else:
            self.resize(1280, 800)
        self.setMinimumSize(940, 650)

        self.settings = QSettings("LocalTools", "FastVideoDownloader")
        self.analysis_pool = QThreadPool(self)
        self.analysis_pool.setMaxThreadCount(1)
        self.probe_pool = QThreadPool(self)
        self.probe_pool.setMaxThreadCount(2)
        self.download_pool = QThreadPool(self)
        self.download_pool.setMaxThreadCount(3)
        self.network = QNetworkAccessManager(self)

        self.items: dict[str, VideoItem] = {}
        self.cards: dict[str, VideoCard] = {}
        self.task_cards: dict[str, DownloadTaskCard] = {}
        self.workers: dict[str, DownloadWorker] = {}
        self.seen_urls: set[str] = set()
        self.group_to_key: dict[str, str] = {}
        self.probe_workers: dict[str, object] = {}
        self.last_errors: dict[str, str] = {}
        self.last_filenames: dict[str, str] = {}
        self.download_quality: dict[str, str] = {}
        self.duplicate_overrides: set[str] = set()
        self.duplicate_count = 0
        self.analysis_errors: list[str] = []
        self.analysis_warnings: list[str] = []
        self.output_dir = str(Path.home() / "Downloads" / "FastVideoDownloader")
        self.default_quality = "1080p"
        self.fragments = 8
        self.parallel_downloads = 3
        self.use_browser_session = False
        self.browser_name = "chrome"
        self.speed_mode = "Fast"
        self.download_subtitles = False
        self.subtitle_langs = "en.*"
        self.history_enabled = True
        self.duplicate_warning = True
        self.stale_stream_seconds = 150
        self.toast_key: str | None = None
        self.toast_details = ""
        self.browser_bridge_status = ""
        self._browser_analysis_worker = None
        self._preview_pending_key: str | None = None
        self.history = HistoryStore(Path.home() / ".streamforge" / "history.sqlite3")
        self.preview_controller = PreviewController(self)
        self.preview_controller.error.connect(lambda msg: self.show_toast("Preview unavailable", msg, retry=False) if hasattr(self, "toast") else None)
        self.preview_controller.preparing.connect(
            lambda msg: self.show_toast("Preparing preview", msg, retry=False) if hasattr(self, "toast") else None
        )

        self.browser_bridge_signals = BrowserBridgeSignals()
        self.browser_bridge_signals.media_received.connect(self.on_browser_media_received)
        self.browser_bridge_signals.status.connect(self.on_browser_bridge_status)
        self.browser_bridge = BrowserBridge(self.browser_bridge_signals)

        self._restore_settings_values()
        self._build_ui()
        self.setStyleSheet(APP_STYLE)
        self.download_pool.setMaxThreadCount(self.parallel_downloads)
        self._sync_settings_dialog()
        self._update_footer_path()
        self.update_selection_bar()
        QTimer.singleShot(0, self.browser_bridge.start)
        QTimer.singleShot(120, self._load_history_into_downloads)

    # ---------- UI construction ----------
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        shell = QVBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.title_bar = TitleBar(self)
        shell.addWidget(self.title_bar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._make_home_page())
        self.stack.addWidget(self._make_results_page())
        self.stack.addWidget(self._make_downloads_page())
        shell.addWidget(self.stack, 1)

        self.footer_bar = self._make_footer()
        shell.addWidget(self.footer_bar)

        self.settings_dialog = SettingsDialog(self)
        self.toast = Toast(self)
        self.toast.retry_clicked.connect(self._retry_toast_action)
        self.toast.details_clicked.connect(self._show_toast_details)

    def _make_home_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 34, 28, 30)
        layout.setSpacing(0)
        layout.addStretch(1)

        content = QWidget()
        content.setMaximumWidth(850)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(18)

        title = QLabel("Download Videos")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignCenter)
        subtitle = QLabel("Paste a video, webpage, multiple links, or a playlist to get started.")
        subtitle.setObjectName("PageSubtitle")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size:13pt;")
        content_layout.addWidget(title)
        content_layout.addWidget(subtitle)
        content_layout.addSpacing(22)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero.setMinimumHeight(295)
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(30, 24, 30, 24)
        hero_layout.setSpacing(13)
        label = QLabel("VIDEO, PAGE OR PLAYLIST URL")
        label.setObjectName("SectionLabel")
        hero_layout.addWidget(label)

        self.url_input = QTextEdit()
        self.url_input.setPlaceholderText("Paste a video or webpage URL here...")
        self.url_input.setMinimumHeight(138)
        self.url_input.setMaximumHeight(160)
        hero_layout.addWidget(self.url_input)

        actions = QHBoxLayout()
        self.paste_btn = QPushButton("▣  Paste from clipboard")
        self.paste_btn.setObjectName("TextButton")
        self.paste_btn.clicked.connect(self.paste_clipboard)
        actions.addWidget(self.paste_btn)
        actions.addStretch(1)
        self.analyze_btn = QPushButton("⌕  Analyze")
        self.analyze_btn.setObjectName("Primary")
        self.analyze_btn.setMinimumWidth(170)
        self.analyze_btn.clicked.connect(self.analyze_links)
        actions.addWidget(self.analyze_btn)
        hero_layout.addLayout(actions)

        self.analysis_notice = QLabel("")
        self.analysis_notice.setWordWrap(True)
        self.analysis_notice.hide()
        hero_layout.addWidget(self.analysis_notice)
        content_layout.addWidget(hero)
        add_shadow(hero, 34, 10)

        centered = QHBoxLayout()
        centered.addStretch(1)
        centered.addWidget(content, 1)
        centered.addStretch(1)
        layout.addLayout(centered)
        layout.addStretch(1)
        return page

    def _make_results_page(self) -> QWidget:
        page = QWidget()
        shell = QHBoxLayout(page)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._make_sidebar("videos"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(16)

        input_pill = QFrame()
        input_pill.setObjectName("InputPill")
        pill_layout = QHBoxLayout(input_pill)
        pill_layout.setContentsMargins(18, 9, 10, 9)
        self.results_url = QLineEdit()
        self.results_url.setReadOnly(True)
        self.results_url.setStyleSheet("background:transparent;border:none;font-size:10pt;")
        pill_layout.addWidget(self.results_url, 1)
        change_btn = QPushButton("Change")
        change_btn.setObjectName("Ghost")
        change_btn.clicked.connect(lambda: self.show_page("home"))
        pill_layout.addWidget(change_btn)
        layout.addWidget(input_pill)

        heading = QHBoxLayout()
        heading_text = QVBoxLayout()
        heading_text.setSpacing(2)
        self.results_title = QLabel("Videos")
        self.results_title.setObjectName("SectionTitle")
        self.results_count = QLabel("0 videos")
        self.results_count.setObjectName("Muted")
        heading_text.addWidget(self.results_title)
        heading_text.addWidget(self.results_count)
        heading.addLayout(heading_text)
        heading.addStretch(1)
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.setObjectName("Ghost")
        self.select_all_btn.clicked.connect(lambda: self.set_all_selected(True))
        unselect = QPushButton("Clear Selection")
        unselect.setObjectName("Ghost")
        unselect.clicked.connect(lambda: self.set_all_selected(False))
        heading.addWidget(self.select_all_btn)
        heading.addWidget(unselect)
        layout.addLayout(heading)

        self.results_scroll = QScrollArea()
        self.results_scroll.setWidgetResizable(True)
        results_inner = QWidget()
        self.results_cards_layout = QVBoxLayout(results_inner)
        self.results_cards_layout.setContentsMargins(0, 0, 6, 0)
        self.results_cards_layout.setSpacing(12)
        self.results_cards_layout.addStretch(1)
        self.results_scroll.setWidget(results_inner)
        layout.addWidget(self.results_scroll, 1)

        self.selection_bar = QFrame()
        self.selection_bar.setObjectName("SelectionBar")
        bar = QHBoxLayout(self.selection_bar)
        bar.setContentsMargins(18, 10, 12, 10)
        bar.setSpacing(10)
        self.selection_label = QLabel("0 videos selected")
        self.selection_label.setStyleSheet("font-weight:700;")
        bar.addWidget(self.selection_label)
        bar.addStretch(1)
        label = QLabel("Quality")
        label.setObjectName("Muted")
        bar.addWidget(label)
        self.bulk_quality = QComboBox()
        self.bulk_quality.addItems(QUALITY_OPTIONS)
        self.bulk_quality.setCurrentText(self.default_quality)
        self.bulk_quality.setFixedWidth(110)
        self.bulk_quality.currentTextChanged.connect(self.apply_bulk_quality)
        bar.addWidget(self.bulk_quality)
        clear_btn = QPushButton("Clear")
        clear_btn.setObjectName("Ghost")
        clear_btn.clicked.connect(lambda: self.set_all_selected(False))
        bar.addWidget(clear_btn)
        download_selected = QPushButton("↓  Download Selected")
        download_selected.setObjectName("Primary")
        download_selected.clicked.connect(self.download_selected)
        bar.addWidget(download_selected)
        add_shadow(self.selection_bar, 24, 6)
        layout.addWidget(self.selection_bar)

        shell.addWidget(body, 1)
        return page

    def _make_downloads_page(self) -> QWidget:
        page = QWidget()
        shell = QHBoxLayout(page)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        shell.addWidget(self._make_sidebar("downloads"))

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(16)

        heading = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(1)
        title = QLabel("Queue Activity")
        title.setObjectName("SectionTitle")
        subtitle = QLabel("Monitoring active and completed downloads.")
        subtitle.setObjectName("Muted")
        text.addWidget(title)
        text.addWidget(subtitle)
        heading.addLayout(text)
        heading.addStretch(1)
        cancel = QPushButton("Cancel Active")
        cancel.setObjectName("Ghost")
        cancel.clicked.connect(self.cancel_all)
        clear = QPushButton("Clear Finished")
        clear.setObjectName("Ghost")
        clear.clicked.connect(self.clear_finished_tasks)
        heading.addWidget(cancel)
        heading.addWidget(clear)
        layout.addLayout(heading)

        self.downloads_scroll = QScrollArea()
        self.downloads_scroll.setWidgetResizable(True)
        inner = QWidget()
        self.downloads_layout = QVBoxLayout(inner)
        self.downloads_layout.setContentsMargins(0, 0, 6, 0)
        self.downloads_layout.setSpacing(12)
        self.empty_downloads = QLabel("Your download queue will appear here.")
        self.empty_downloads.setObjectName("Muted")
        self.empty_downloads.setAlignment(Qt.AlignCenter)
        self.empty_downloads.setStyleSheet("font-size:12pt;padding:60px;")
        self.downloads_layout.addWidget(self.empty_downloads)
        self.downloads_layout.addStretch(1)
        self.downloads_scroll.setWidget(inner)
        layout.addWidget(self.downloads_scroll, 1)

        shell.addWidget(body, 1)
        return page

    def _make_sidebar(self, active: str) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(205)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 22, 16, 20)
        layout.setSpacing(9)

        videos = QPushButton("▦   Videos")
        videos.setObjectName("NavActive" if active == "videos" else "Nav")
        videos.clicked.connect(lambda: self.show_page("results"))
        downloads = QPushButton("↓   Downloads")
        downloads.setObjectName("NavActive" if active == "downloads" else "Nav")
        downloads.clicked.connect(lambda: self.show_page("downloads"))
        settings = QPushButton("⚙   Settings")
        settings.setObjectName("Nav")
        settings.clicked.connect(self.open_settings)
        layout.addWidget(videos)
        layout.addWidget(downloads)
        layout.addWidget(settings)
        layout.addStretch(1)
        return sidebar

    def _make_footer(self) -> QFrame:
        footer = QFrame()
        footer.setObjectName("Footer")
        footer.setFixedHeight(44)
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(22, 5, 22, 5)
        layout.setSpacing(8)
        self.path_btn = QPushButton("")
        self.path_btn.setObjectName("TextButton")
        self.path_btn.clicked.connect(self.choose_output_dir)
        layout.addWidget(self.path_btn)
        layout.addStretch(1)
        self.open_folder_btn = QPushButton("Open Folder")
        self.open_folder_btn.setObjectName("TextButton")
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        layout.addWidget(self.open_folder_btn)
        grip = QSizeGrip(footer)
        grip.setFixedSize(16, 16)
        layout.addWidget(grip, 0, Qt.AlignBottom)
        return footer

    # ---------- Settings ----------
    def _restore_settings_values(self):
        default_downloads = str(Path.home() / "Downloads" / "FastVideoDownloader")
        self.output_dir = str(self.settings.value("output_dir", default_downloads))
        self.default_quality = str(self.settings.value("quality", "1080p"))
        if self.default_quality not in QUALITY_OPTIONS:
            self.default_quality = "1080p"
        self.parallel_downloads = int(self.settings.value("parallel", 3))
        self.fragments = int(self.settings.value("fragments", 8))
        raw_browser_session = self.settings.value("use_browser_session", False)
        self.use_browser_session = str(raw_browser_session).lower() in {"1", "true", "yes"}
        self.browser_name = str(self.settings.value("browser_name", "chrome")).lower()
        self.speed_mode = str(self.settings.value("speed_mode", "Fast")).title()
        if self.speed_mode not in {"Normal", "Fast", "Maximum"}:
            self.speed_mode = "Fast"
        raw_subtitles = self.settings.value("download_subtitles", False)
        self.download_subtitles = str(raw_subtitles).lower() in {"1", "true", "yes"}
        self.subtitle_langs = str(self.settings.value("subtitle_langs", "en.*"))
        raw_history = self.settings.value("history_enabled", True)
        self.history_enabled = str(raw_history).lower() not in {"0", "false", "no"}
        raw_duplicate = self.settings.value("duplicate_warning", True)
        self.duplicate_warning = str(raw_duplicate).lower() not in {"0", "false", "no"}

    def _sync_settings_dialog(self):
        self.settings_dialog.default_quality.setCurrentText(self.default_quality)
        self.settings_dialog.parallel.setValue(self.parallel_downloads)
        self.settings_dialog.folder.setText(self.output_dir)
        self.settings_dialog.fragments.setCurrentText(str(self.fragments))
        self.settings_dialog.use_browser_session.setChecked(self.use_browser_session)
        self.settings_dialog.speed_mode.setCurrentText(self.speed_mode)
        self.settings_dialog.download_subtitles.setChecked(self.download_subtitles)
        self.settings_dialog.subtitle_langs.setText(self.subtitle_langs)
        self.settings_dialog.keep_history.setChecked(self.history_enabled)
        self.settings_dialog.warn_duplicates.setChecked(self.duplicate_warning)
        browser_display = self.browser_name.title()
        index = self.settings_dialog.browser.findText(browser_display, Qt.MatchFixedString)
        self.settings_dialog.browser.setCurrentIndex(index if index >= 0 else 0)

    def apply_settings_from_dialog(self):
        self.default_quality = self.settings_dialog.default_quality.currentText()
        self.parallel_downloads = self.settings_dialog.parallel.value()
        self.output_dir = self.settings_dialog.folder.text().strip() or self.output_dir
        self.fragments = int(self.settings_dialog.fragments.currentText())
        self.use_browser_session = self.settings_dialog.use_browser_session.isChecked()
        self.browser_name = self.settings_dialog.browser.currentText().lower()
        self.speed_mode = self.settings_dialog.speed_mode.currentText()
        self.download_subtitles = self.settings_dialog.download_subtitles.isChecked()
        self.subtitle_langs = self.settings_dialog.subtitle_langs.text().strip() or "en.*"
        self.history_enabled = self.settings_dialog.keep_history.isChecked()
        self.duplicate_warning = self.settings_dialog.warn_duplicates.isChecked()
        self.download_pool.setMaxThreadCount(self.parallel_downloads)
        self.bulk_quality.setCurrentText(self.default_quality)
        self._update_footer_path()
        self._save_settings()

    def _save_settings(self):
        self.settings.setValue("output_dir", self.output_dir)
        self.settings.setValue("quality", self.default_quality)
        self.settings.setValue("parallel", self.parallel_downloads)
        self.settings.setValue("fragments", self.fragments)
        self.settings.setValue("use_browser_session", self.use_browser_session)
        self.settings.setValue("browser_name", self.browser_name)
        self.settings.setValue("speed_mode", self.speed_mode)
        self.settings.setValue("download_subtitles", self.download_subtitles)
        self.settings.setValue("subtitle_langs", self.subtitle_langs)
        self.settings.setValue("history_enabled", self.history_enabled)
        self.settings.setValue("duplicate_warning", self.duplicate_warning)

    def closeEvent(self, event):
        self._save_settings()
        try:
            self.browser_bridge.stop()
        except Exception:
            pass
        try:
            self.preview_controller.stop()
        except Exception:
            pass
        event.accept()

    def open_settings(self):
        self._sync_settings_dialog()
        self.settings_dialog.exec()

    # ---------- Window ----------
    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
            self.title_bar.max_btn.setText("□")
        else:
            self.showMaximized()
            self.title_bar.max_btn.setText("❐")

    def show_page(self, page: str):
        mapping = {"home": self.PAGE_HOME, "results": self.PAGE_RESULTS, "downloads": self.PAGE_DOWNLOADS}
        index = mapping.get(page, self.PAGE_HOME)
        if index == self.PAGE_RESULTS and not self.cards:
            index = self.PAGE_HOME
        self.stack.setCurrentIndex(index)

    # ---------- Input / Analyze ----------
    def paste_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        current = self.url_input.toPlainText().strip()
        self.url_input.setPlainText(f"{current}\n{text}".strip() if current else text)

    def analyze_links(self):
        urls = extract_urls(self.url_input.toPlainText())
        if not urls:
            self.show_toast("No valid link", "Paste at least one valid video, webpage, or playlist URL.", retry=False)
            return

        self.duplicate_count = 0
        self.analysis_errors.clear()
        self.analysis_warnings.clear()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analyzing…")
        self._set_analysis_notice("busy", f"Analyzing {len(urls)} link(s)…")
        self.results_url.setText("   •   ".join(urls[:2]) + ("   •   …" if len(urls) > 2 else ""))

        worker = AnalyzeWorker(urls, browser=self.browser_name if self.use_browser_session else None)
        worker.signals.item.connect(self.add_video_item)
        worker.signals.status.connect(lambda msg: self._set_analysis_notice("busy", msg))
        worker.signals.warning.connect(self.on_analysis_warning)
        worker.signals.error.connect(self.on_analysis_error)
        worker.signals.finished.connect(self.on_analysis_finished)
        self._analysis_worker = worker
        self.analysis_pool.start(worker)

    def on_analysis_warning(self, message: str):
        self.analysis_warnings.append(message)
        self._set_analysis_notice("warning", message.splitlines()[0])

    def on_analysis_error(self, message: str):
        self.analysis_errors.append(message)
        self._set_analysis_notice("error", message.splitlines()[0] if message else "Analysis failed")

    def on_analysis_finished(self, added: int, failed: int):
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("⌕  Analyze")
        actual_added = max(0, added - self.duplicate_count)
        if actual_added > 0:
            self.analysis_notice.hide()
            playlist_names = {item.playlist_title for item in self.items.values() if item.playlist_title}
            if len(playlist_names) == 1:
                self.results_title.setText(next(iter(playlist_names)))
            elif len(playlist_names) > 1:
                self.results_title.setText("Analyzed Videos")
            else:
                self.results_title.setText("Videos")
            self._refresh_results_count()
            self.show_page("results")
        elif self.analysis_errors:
            details = "\n\n".join(self.analysis_errors[:3])
            self.show_toast("No downloadable media found", "This page may be unsupported, protected, or require a browser session. Open Details for more information.", details=details, retry=True)
        else:
            self.show_toast("Nothing found", "No downloadable media was returned for this link.", retry=True)

    def _set_analysis_notice(self, state: str, text: str):
        palette = {
            "busy": ("#263044", "#BFD1FF", "#465B83"),
            "warning": ("#302A1F", "#F0CC6B", "#5A4D2E"),
            "error": ("#351E21", "#FFB4AB", "#6A343B"),
        }
        bg, fg, border = palette.get(state, palette["busy"])
        self.analysis_notice.setText(text)
        self.analysis_notice.setStyleSheet(
            f"background:{bg};color:{fg};border:1px solid {border};border-radius:12px;padding:8px 11px;"
        )
        self.analysis_notice.show()

    def add_video_item(self, item: VideoItem):
        normalized = item.webpage_url.strip()
        if not normalized:
            self.duplicate_count += 1
            return

        # Browser capture can expose multiple qualities/URLs for one logical
        # video. When a stable group id exists, merge those variants into the
        # existing card instead of creating duplicates.
        if item.group_id and item.group_id in self.group_to_key:
            existing_key = self.group_to_key[item.group_id]
            existing = self.items.get(existing_key)
            card = self.cards.get(existing_key)
            if existing and card:
                changed = False
                for variant in item.variants:
                    label = variant.display_label().lower()
                    if label and label not in {"best", "video", "hls", "dash"}:
                        existing.variants = [v for v in existing.variants if not (v.kind == variant.kind and v.display_label().lower() == label)]
                    changed = existing.merge_variant(variant) or changed
                existing.webpage_url = item.webpage_url or existing.webpage_url
                existing.http_headers.update(item.http_headers)
                existing.verified = existing.verified or item.verified
                existing.captured_at = max(existing.captured_at, item.captured_at)
                existing.status_code = item.status_code or existing.status_code
                existing.content_type = item.content_type or existing.content_type
                if item.thumbnail and not existing.thumbnail:
                    existing.thumbnail = item.thumbnail
                    self.load_thumbnail(item.thumbnail, card)
                if item.title and existing.title.lower().startswith("video from browser"):
                    existing.title = item.title
                    card.title_label.setText(item.title)
                    card.title_label.setToolTip(item.title)
                if item.preferred_quality:
                    existing.preferred_quality = item.preferred_quality
                if changed or item.preferred_quality:
                    card.set_variants(existing.variants, existing.preferred_quality or card.quality_combo.currentText())
                card.refresh_meta()
                self.show_toast("Stream refreshed", "A fresh browser stream/quality was merged into the existing video card.", retry=False)
                return

        if normalized in self.seen_urls:
            self.duplicate_count += 1
            return

        self.seen_urls.add(normalized)
        self.items[item.key] = item
        if item.group_id:
            self.group_to_key[item.group_id] = item.key
        card = VideoCard(item, item.preferred_quality or self.default_quality)
        card.selection_changed.connect(self.update_selection_bar)
        card.download_requested.connect(self.start_download)
        card.preview_requested.connect(self.preview_item)
        self.cards[item.key] = card
        self.results_cards_layout.insertWidget(self.results_cards_layout.count() - 1, card)
        if item.thumbnail:
            self.load_thumbnail(item.thumbnail, card)
        self._refresh_results_count()
        self.update_selection_bar()

        # Direct browser/manifest items benefit from an immediate lightweight
        # format probe so the quality menu can show real representations.
        if item.direct_media or item.extractor == "browser-extension":
            self._probe_item(item.key)

    def _probe_item(self, key: str):
        item = self.items.get(key)
        card = self.cards.get(key)
        if not item or not card or key in self.probe_workers:
            return
        card.set_state("Probing")
        worker = FormatProbeWorker(item, browser=self.browser_name if self.use_browser_session else None)
        worker.signals.ready.connect(self._on_probe_ready)
        worker.signals.error.connect(self._on_probe_error)
        self.probe_workers[key] = worker
        self.probe_pool.start(worker)

    def _on_probe_ready(self, key: str, variants, subtitles, metadata):
        self.probe_workers.pop(key, None)
        item = self.items.get(key)
        card = self.cards.get(key)
        if not item or not card:
            return
        resolved_variants = list(variants or [])
        if item.preferred_quality and resolved_variants:
            preferred = item.preferred_quality.lower()
            matching_resolved = any(v.display_label().lower().startswith(preferred) for v in resolved_variants)
            if matching_resolved:
                # Remove the temporary browser-manifest placeholder for the
                # chosen quality so the resolved yt-dlp representation becomes
                # the actual selected download choice.
                item.variants = [
                    v for v in item.variants
                    if not (
                        not getattr(v, "format_id", "")
                        and v.display_label().lower().startswith(preferred)
                        and getattr(v, "url", "") == item.webpage_url
                    )
                ]
        for variant in resolved_variants:
            item.merge_variant(variant)
        item.subtitles = list(subtitles or [])
        if isinstance(metadata, dict):
            title = str(metadata.get("title") or "").strip()
            if title and (not item.title or item.title.lower().startswith("video from browser") or item.title.lower().startswith("media from")):
                item.title = title
                card.title_label.setText(title)
                card.title_label.setToolTip(title)
            if metadata.get("duration") is not None:
                item.duration = metadata.get("duration")
            thumbnail = str(metadata.get("thumbnail") or "").strip()
            if thumbnail and not item.thumbnail:
                item.thumbnail = thumbnail
                self.load_thumbnail(thumbnail, card)
        card.set_variants(item.variants, item.preferred_quality or self.default_quality)
        card.refresh_meta()
        card.set_state("Ready")
        if self._preview_pending_key == key:
            self._preview_pending_key = None
            QTimer.singleShot(0, lambda k=key: self.preview_item(k))

    def _on_probe_error(self, key: str, message: str):
        self.probe_workers.pop(key, None)
        card = self.cards.get(key)
        if card:
            card.set_state("Ready")
        if self._preview_pending_key == key:
            self._preview_pending_key = None
            self.show_toast("Preview unavailable", "Shield Stream could not resolve a playable preview stream for this page.", details=message, retry=False)

    def preview_item(self, key: str):
        item = self.items.get(key)
        card = self.cards.get(key)
        if not item or not card:
            return
        if not item.variants and not item.direct_media:
            self._preview_pending_key = key
            self.show_toast("Preparing preview", "Resolving a temporary playable stream. This does not download the video.", retry=False)
            self._probe_item(key)
            return
        choice = card.selected_download_choice()
        url = choice.get("url") or item.active_url()
        if item.refreshable and item.captured_at and __import__("time").time() - item.captured_at > self.stale_stream_seconds:
            self.show_toast(
                "Stream may have expired",
                "This browser stream is older than a few minutes. Preview it now; if it fails, run Power scan again in Chrome to refresh it.",
                retry=False,
            )
        preview_item = item
        # Preview uses the selected variant's safe request headers.
        if choice.get("headers"):
            preview_item.http_headers = dict(item.http_headers) | dict(choice.get("headers") or {})
        self.preview_controller.play(preview_item, url)

    def load_thumbnail(self, url: str, target):
        reply = self.network.get(QNetworkRequest(QUrl(url)))

        def done():
            data = reply.readAll().data()
            pixmap = QPixmap()
            if data and pixmap.loadFromData(data):
                target.set_thumbnail(pixmap)
                task = self.task_cards.get(getattr(target, "item", VideoItem("", "")).key) if hasattr(target, "item") else None
                if task and task is not target:
                    task.set_thumbnail(pixmap)
            reply.deleteLater()

        reply.finished.connect(done)


    # ---------- Browser companion ----------
    def on_browser_bridge_status(self, message: str):
        self.browser_bridge_status = message or ""
        if "unavailable" in self.browser_bridge_status.lower() and hasattr(self, "toast"):
            self.show_toast(
                "Browser companion unavailable",
                "Chrome could not connect to the local Shield Stream bridge. Restart Shield Stream and try again.",
                details=self.browser_bridge_status,
                retry=False,
            )

    @staticmethod
    def _browser_headers(payload: dict) -> dict[str, str]:
        headers: dict[str, str] = {}
        user_agent = str(payload.get("user_agent") or "").strip()
        referer = str(
            payload.get("referer")
            or payload.get("frame_url")
            or payload.get("page_url")
            or ""
        ).strip()
        origin = str(payload.get("origin") or "").strip()
        if user_agent:
            headers["User-Agent"] = user_agent
        if referer.startswith(("http://", "https://")):
            headers["Referer"] = referer
        if origin.startswith(("http://", "https://")):
            headers["Origin"] = origin
        return headers

    def on_browser_media_received(self, payload):
        if not isinstance(payload, dict):
            return
        url = normalize_url(str(payload.get("url") or "").strip())
        if not url.startswith(("http://", "https://")):
            return

        kind = str(payload.get("kind") or "").strip().lower()
        page_url = str(payload.get("page_url") or "").strip()
        frame_url = str(payload.get("frame_url") or "").strip()
        title = str(payload.get("title") or "").strip() or "Video from browser"

        if kind == "player":
            self.show_toast(
                "Player detected - stream not found yet",
                "The extension found an embedded player, not the media stream. Keep playback running in Chrome and click Scan again.",
                retry=False,
            )
            return

        if kind == "page":
            self._analyze_browser_page(url, title)
            return

        inferred_kind = direct_media_kind(url)
        media_kind = kind if kind in {"video", "audio", "hls", "dash"} else inferred_kind
        if not media_kind:
            self.show_toast(
                "Not a direct media stream",
                "Chrome sent a URL that is not a recognized direct media stream. Keep playback running and scan again.",
                details=url,
                retry=False,
            )
            return

        source_url = page_url if page_url.startswith(("http://", "https://")) else (frame_url or url)
        headers = self._browser_headers(payload)
        quality_hint = str(payload.get("quality_hint") or "").strip()
        preferred_quality = str(payload.get("preferred_quality") or quality_hint or "").strip()
        variant_label = quality_hint or ({"hls": "HLS", "dash": "DASH", "audio": "Audio", "video": "Video"}.get(media_kind, "Best"))
        variant = MediaVariant(
            label=variant_label,
            url=url,
            kind=media_kind,
            http_headers=headers,
            verified=bool(payload.get("verified")),
        )
        detected_at = payload.get("detected_at") or 0
        try:
            detected_at = float(detected_at)
            if detected_at > 100000000000:  # extension uses milliseconds
                detected_at /= 1000.0
        except Exception:
            detected_at = 0.0
        if not detected_at:
            detected_at = __import__("time").time()

        group_id = str(payload.get("group_id") or "").strip()
        if not group_id:
            group_id = f"{int(payload.get('tab_id') or 0)}|{source_url}|{title.lower()}"

        item = VideoItem(
            title=title,
            webpage_url=url,
            duration=None,
            thumbnail=str(payload.get("thumbnail") or "").strip(),
            source=site_label(source_url, "Browser"),
            extractor="browser-extension",
            direct_media=True,
            media_kind=media_kind,
            http_headers=headers,
            content_type=str(payload.get("content_type") or "").strip(),
            detector=str(payload.get("detector") or "").strip(),
            verified=bool(payload.get("verified")),
            status_code=int(payload.get("status_code") or 0) if str(payload.get("status_code") or "0").isdigit() else 0,
            page_url=page_url,
            frame_url=frame_url,
            group_id=group_id,
            tab_id=int(payload.get("tab_id") or 0) if str(payload.get("tab_id") or "0").isdigit() else 0,
            variants=[variant],
            refreshable=True,
            captured_at=detected_at,
            preferred_quality=preferred_quality,
        )

        existed_group = bool(group_id and group_id in self.group_to_key)
        was_url_new = url not in self.seen_urls
        self.add_video_item(item)

        self.results_title.setText("Videos from Browser")
        self.results_url.setText(source_url)
        self._refresh_results_count()
        self.show_page("results")
        stream_label = {"hls": "HLS", "dash": "DASH", "audio": "Audio", "video": "Video"}.get(media_kind, "Media")
        if existed_group:
            message = f"A fresh {variant_label} stream was merged into the existing video."
        elif not was_url_new:
            message = "This browser stream is already in the video list."
        else:
            verify_text = " Verified by the browser network response." if item.verified else ""
            message = f"{stream_label} stream added.{verify_text} Preview it before downloading if you want to verify the content."
        self.show_toast("Received from Chrome", message, retry=False)

    def _analyze_browser_page(self, url: str, title: str = "Browser page"):
        self.toast_details = ""
        self.show_toast(
            "Analyzing browser page",
            "Shield Stream is checking the player URL. If nothing is found, start playback and scan again in Chrome.",
            retry=False,
        )
        worker = AnalyzeWorker(
            [url],
            browser=self.browser_name if self.use_browser_session else None,
        )
        worker.signals.item.connect(self.add_video_item)
        worker.signals.error.connect(self._on_browser_page_error)
        worker.signals.finished.connect(lambda added, failed: self._on_browser_page_finished(url, title, added, failed))
        self._browser_analysis_worker = worker
        self.analysis_pool.start(worker)

    def _on_browser_page_error(self, message: str):
        self.toast_details = message or "Browser player could not be analyzed."

    def _on_browser_page_finished(self, url: str, title: str, added: int, failed: int):
        if added > 0:
            self.results_title.setText(title or "Videos from Browser")
            self.results_url.setText(url)
            self._refresh_results_count()
            self.show_page("results")
            return
        self.show_toast(
            "No direct stream found yet",
            "Play the video in Chrome, open the Shield Stream extension, then click Scan again.",
            details=self.toast_details if failed else "",
            retry=False,
        )

    # ---------- Selection ----------
    def selected_keys(self) -> list[str]:
        return [key for key, card in self.cards.items() if card.checkbox.isChecked()]

    def set_all_selected(self, selected: bool):
        for card in self.cards.values():
            card.checkbox.blockSignals(True)
            card.checkbox.setChecked(selected)
            card.checkbox.blockSignals(False)
        self.update_selection_bar()

    def update_selection_bar(self, *_args):
        if not hasattr(self, "selection_bar"):
            return
        selected = len(self.selected_keys())
        self.selection_label.setText(f"{selected} video{'s' if selected != 1 else ''} selected")
        self.selection_bar.setVisible(selected > 0)

    def apply_bulk_quality(self, quality: str):
        for key in self.selected_keys():
            card = self.cards.get(key)
            if card:
                card.quality_combo.setCurrentText(quality)

    def _refresh_results_count(self):
        count = len(self.cards)
        self.results_count.setText(f"{count} video{'s' if count != 1 else ''}")

    # ---------- Download ----------
    def download_selected(self):
        keys = self.selected_keys()
        if not keys:
            return
        for key in keys:
            self.start_download(key)
        self.show_page("downloads")

    def start_download(self, key: str):
        if key in self.workers:
            return
        item = self.items.get(key)
        card = self.cards.get(key)
        if not item or not card:
            return
        if not self.output_dir:
            self.open_settings()
            return

        # Duplicate detection uses local completed-download history only. It
        # never stores browser cookies or authorization headers.
        if self.history_enabled and self.duplicate_warning and key not in self.duplicate_overrides:
            existing = self.history.find_existing(item)
            if existing:
                card.set_state("Already downloaded")
                box = QMessageBox(self)
                box.setWindowTitle("Already downloaded")
                box.setIcon(QMessageBox.Icon.Information)
                box.setText("This video appears to have been downloaded before.")
                box.setInformativeText(str(existing.get("filename") or ""))
                open_btn = box.addButton("Open Existing", QMessageBox.ButtonRole.ActionRole)
                again_btn = box.addButton("Download Again", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                clicked = box.clickedButton()
                if clicked is open_btn:
                    filename = str(existing.get("filename") or "")
                    if filename:
                        QDesktopServices.openUrl(QUrl.fromLocalFile(filename))
                    return
                if clicked is not again_btn:
                    return
                self.duplicate_overrides.add(key)

        # Browser/CDN stream URLs often contain short-lived tokens. A fresh
        # Power Scan replaces the matching quality in-place through group_id.
        if item.refreshable and item.captured_at:
            age = __import__("time").time() - item.captured_at
            if age > self.stale_stream_seconds:
                box = QMessageBox(self)
                box.setWindowTitle("Stream may be expired")
                box.setIcon(QMessageBox.Icon.Warning)
                box.setText("This captured browser stream is a few minutes old.")
                box.setInformativeText("For the most reliable download, keep the video playing in Chrome and run Power Scan again. You can still try this URL now.")
                refresh_btn = box.addButton("Refresh from Chrome", QMessageBox.ButtonRole.ActionRole)
                continue_btn = box.addButton("Try Download", QMessageBox.ButtonRole.AcceptRole)
                box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                box.exec()
                if box.clickedButton() is refresh_btn:
                    if self.browser_bridge.request_refresh(item):
                        self.show_toast(
                            "Refresh requested",
                            "Keep the video playing and open the Shield Stream extension. It will run a fresh capture and merge the new stream into this card.",
                            retry=False,
                        )
                    else:
                        self.show_toast("Refresh unavailable", "This item is not linked to an active browser tab. Run Power Scan manually in the extension.", retry=False)
                    return
                if box.clickedButton() is not continue_btn:
                    return

        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        choice = card.selected_download_choice()
        quality = choice.get("quality") or card.quality_combo.currentText()
        variant_url = choice.get("url") or ""
        format_id = choice.get("format_id") or ""
        # For manifest formats, keeping the master URL plus format id lets
        # yt-dlp fetch/merge companion audio when DASH exposes it separately.
        if format_id and item.media_kind in {"hls", "dash"}:
            variant_url = ""

        worker = DownloadWorker(
            item=item,
            output_dir=self.output_dir,
            quality=quality,
            concurrent_fragments=self.fragments,
            browser=self.browser_name if self.use_browser_session else None,
            format_id=format_id,
            variant_url=variant_url,
            variant_headers=choice.get("headers") or {},
            speed_mode=self.speed_mode,
            download_subtitles=self.download_subtitles,
            subtitle_langs=self.subtitle_langs,
        )
        worker.signals.progress.connect(self.on_download_progress)
        worker.signals.finished.connect(self.on_download_finished)
        worker.signals.error.connect(self.on_download_error)
        self.workers[key] = worker
        self.download_quality[key] = quality

        card.set_state("Queued")
        task = self._ensure_task_card(item, quality)
        task.set_state("Queued")
        self.download_pool.start(worker)
        self.show_page("downloads")

    def _ensure_task_card(self, item: VideoItem, quality: str) -> DownloadTaskCard:
        task = self.task_cards.get(item.key)
        if task:
            return task
        task = DownloadTaskCard(item, quality)
        task.cancel_requested.connect(self.cancel_download)
        task.retry_requested.connect(self.start_download)
        task.open_folder_requested.connect(self.open_download_item_folder)
        self.task_cards[item.key] = task
        self.empty_downloads.hide()
        self.downloads_layout.insertWidget(self.downloads_layout.count() - 1, task)
        source_card = self.cards.get(item.key)
        if source_card and source_card.thumb.pixmap() and not source_card.thumb.pixmap().isNull():
            task.set_thumbnail(source_card.thumb.pixmap())
        elif item.thumbnail:
            self.load_thumbnail(item.thumbnail, task)
        return task

    def on_download_progress(self, key: str, percent: float, speed: str, eta: str, status_text: str):
        card = self.cards.get(key)
        task = self.task_cards.get(key)
        if card:
            card.set_state(status_text, percent, speed, eta)
        if task:
            task.set_state(status_text, percent, speed, eta)

    def on_download_finished(self, key: str, filename: str):
        self.last_errors.pop(key, None)
        self.last_filenames[key] = filename
        self.workers.pop(key, None)
        self.duplicate_overrides.discard(key)
        card = self.cards.get(key)
        task = self.task_cards.get(key)
        if card:
            card.set_state("Done", 100)
        if task:
            task.set_state("Done", 100)
        item = self.items.get(key)
        if self.history_enabled and item and filename:
            try:
                item.history_id = self.history.add_completed(item, self.download_quality.get(key, "Best"), filename)
            except Exception:
                pass

    def on_download_error(self, key: str, message: str):
        self.last_errors[key] = message
        self.workers.pop(key, None)
        state = "Cancelled" if message == "Cancelled" else "Failed"
        card = self.cards.get(key)
        task = self.task_cards.get(key)
        if card:
            card.set_state(state, error=message)
        if task:
            task.set_state(state, error=message)
        if state == "Failed":
            item = self.items.get(key)
            lower = (message or "").lower()
            if item and item.refreshable and any(marker in lower for marker in ("403", "404", "forbidden", "expired", "invalid token")):
                requested = self.browser_bridge.request_refresh(item)
                refresh_note = " A fresh capture was requested from the Chrome companion." if requested else ""
                self.show_toast(
                    "Fresh stream needed",
                    "The captured browser URL may have expired." + refresh_note + " Keep the video playing and open the extension; then retry this card.",
                    details=message,
                    retry=True,
                    key=key,
                )
            else:
                first = message.splitlines()[0] if message else "Unable to download this video."
                self.show_toast("Download failed", first, details=message, retry=True, key=key)

    def cancel_download(self, key: str):
        worker = self.workers.get(key)
        if worker:
            worker.cancel()

    def cancel_all(self):
        for worker in list(self.workers.values()):
            worker.cancel()

    def clear_finished_tasks(self):
        removable = []
        for key, task in self.task_cards.items():
            if key not in self.workers and (key in self.last_filenames or key in self.last_errors):
                removable.append(key)
        for key in removable:
            task = self.task_cards.pop(key)
            task.setParent(None)
            task.deleteLater()
        if not self.task_cards:
            self.empty_downloads.show()

    def clear_history_records(self):
        answer = QMessageBox.question(
            self,
            "Clear download history",
            "Remove saved completed-download history from this PC? Downloaded files will not be deleted.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.history.clear()
        except Exception as exc:
            self.show_toast("Could not clear history", str(exc), retry=False)
            return
        for key in [key for key in self.task_cards if key.startswith("history-")]:
            task = self.task_cards.pop(key, None)
            if task:
                task.setParent(None)
                task.deleteLater()
            self.items.pop(key, None)
            self.last_filenames.pop(key, None)
        if not self.task_cards:
            self.empty_downloads.show()
        self.show_toast("History cleared", "Downloaded files were left untouched.", retry=False)

    def _load_history_into_downloads(self):
        if not self.history_enabled:
            return
        try:
            rows = self.history.recent(30)
        except Exception:
            return
        for row in reversed(rows):
            filename = str(row.get("filename") or "")
            if filename and not Path(filename).exists():
                continue
            item = VideoItem(
                title=str(row.get("title") or Path(filename).name or "Downloaded video"),
                webpage_url=str(row.get("url") or ""),
                page_url=str(row.get("page_url") or ""),
                source=str(row.get("source") or "History"),
                history_id=int(row.get("id") or 0),
                key=f"history-{int(row.get('id') or 0)}",
            )
            if item.key in self.task_cards:
                continue
            self.items[item.key] = item
            self.last_filenames[item.key] = filename
            task = self._ensure_task_card(item, str(row.get("quality") or "Best"))
            task.set_state("Done", 100)

    def open_download_item_folder(self, key: str):
        filename = self.last_filenames.get(key, "")
        if filename:
            path = Path(filename)
            folder = path.parent if path.suffix else path
            if folder.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
                return
        self.open_output_folder()

    # ---------- Folder ----------
    def choose_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose download folder", self.output_dir)
        if folder:
            self.output_dir = folder
            self.settings_dialog.folder.setText(folder)
            self._update_footer_path()
            self._save_settings()

    def _update_footer_path(self):
        display = self.output_dir
        if len(display) > 75:
            display = "…" + display[-72:]
        self.path_btn.setText(f"▣  Save to: {display}")
        self.path_btn.setToolTip(self.output_dir)

    def open_output_folder(self):
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.output_dir))

    # ---------- Error toast ----------
    def show_toast(self, title: str, message: str, details: str = "", retry: bool = False, key: str | None = None):
        self.toast_key = key
        self.toast_details = details or message
        self.toast.title.setText(title)
        self.toast.message.setText(message)
        self.toast.retry.setVisible(retry)
        self.toast.details.setVisible(bool(details))
        self.toast.adjustSize()
        self._position_toast()
        self.toast.show()
        self.toast.raise_()
        if not retry:
            QTimer.singleShot(5500, self.toast.hide)

    def _retry_toast_action(self):
        self.toast.hide()
        if self.toast_key:
            self.start_download(self.toast_key)
        else:
            self.analyze_links()

    def _show_toast_details(self):
        QMessageBox.information(self, "Details", self.toast_details)

    def _position_toast(self):
        if not hasattr(self, "toast"):
            return
        margin = 22
        x = max(margin, self.width() - self.toast.width() - margin)
        y = max(70, self.height() - self.toast.height() - 62)
        self.toast.move(x, y)

    def resizeEvent(self, event):
        self._position_toast()
        super().resizeEvent(event)

    # ---------- Compatibility helpers retained for older calls ----------
    def download_all(self):
        for key in list(self.cards):
            self.start_download(key)

    def clear_list(self):
        if self.workers:
            self.show_toast("Downloads are active", "Cancel active downloads before clearing the video list.", retry=False)
            return
        for card in self.cards.values():
            card.setParent(None)
            card.deleteLater()
        for task in self.task_cards.values():
            task.setParent(None)
            task.deleteLater()
        self.items.clear()
        self.cards.clear()
        self.task_cards.clear()
        self.seen_urls.clear()
        self.group_to_key.clear()
        self.last_errors.clear()
        self.last_filenames.clear()
        self.empty_downloads.show()
        self._refresh_results_count()
        self.update_selection_bar()
        self.show_page("home")

    def install_deno(self):
        script = Path(__file__).resolve().parent.parent / "install_deno_windows.bat"
        if script.exists():
            QProcess.startDetached("cmd.exe", ["/c", "start", "", str(script)])
