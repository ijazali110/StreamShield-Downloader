from dataclasses import dataclass, field
from typing import Optional
import time
import uuid


@dataclass
class MediaVariant:
    """One selectable representation of a logical video/audio item."""

    label: str
    url: str
    kind: str = "video"
    height: Optional[int] = None
    width: Optional[int] = None
    bitrate: Optional[float] = None
    fps: Optional[float] = None
    codec: str = ""
    audio_codec: str = ""
    language: str = ""
    format_id: str = ""
    ext: str = ""
    http_headers: dict[str, str] = field(default_factory=dict)
    verified: bool = False

    def display_label(self) -> str:
        if self.label:
            return self.label
        if self.height:
            suffix = f" {int(self.fps)}fps" if self.fps and self.fps >= 50 else ""
            return f"{self.height}p{suffix}"
        if self.kind == "audio":
            return "Audio"
        return "Best"


@dataclass
class VideoItem:
    title: str
    webpage_url: str
    video_id: str = ""
    duration: Optional[float] = None
    thumbnail: str = ""
    source: str = "Video"
    playlist_title: str = ""
    extractor: str = ""
    direct_media: bool = False
    media_kind: str = ""
    http_headers: dict[str, str] = field(default_factory=dict)
    content_type: str = ""
    detector: str = ""
    verified: bool = False
    status_code: int = 0

    # V2.0 logical-media metadata. Browser streams that belong to the same
    # page/player can be grouped into a single card with multiple variants.
    page_url: str = ""
    frame_url: str = ""
    group_id: str = ""
    tab_id: int = 0
    variants: list[MediaVariant] = field(default_factory=list)
    subtitles: list[dict] = field(default_factory=list)
    refreshable: bool = False
    captured_at: float = field(default_factory=time.time)
    selected_variant_url: str = ""
    selected_format_id: str = ""
    preferred_quality: str = ""
    history_id: int = 0

    key: str = field(default_factory=lambda: uuid.uuid4().hex)

    def active_url(self) -> str:
        return self.selected_variant_url or self.webpage_url

    def merge_variant(self, variant: MediaVariant) -> bool:
        """Add a unique variant. Returns True when the list changed."""
        key = (variant.url.strip(), variant.format_id.strip(), variant.display_label().lower())
        for existing in self.variants:
            other = (existing.url.strip(), existing.format_id.strip(), existing.display_label().lower())
            if key == other:
                if variant.verified and not existing.verified:
                    existing.verified = True
                return False
        self.variants.append(variant)
        self.variants.sort(
            key=lambda v: (
                1 if v.kind == "audio" else 0,
                -(v.height or 0),
                -(v.bitrate or 0),
                v.display_label().lower(),
            )
        )
        return True


def format_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    try:
        total = max(0, int(seconds))
    except (TypeError, ValueError):
        return "--:--"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:d}:{secs:02d}"
