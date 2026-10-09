"""Compatibility with OK.ru's object-valued embedded metadata.

The stable 2026.08.19 extractor assumes flashvars.metadata is JSON text.
Register the fix on each downloader instance so page-to-embed delegation and
subsequent downloads use the same behavior, without patching installed packages.
"""
from yt_dlp import YoutubeDL
from yt_dlp.extractor.odnoklassniki import OdnoklassnikiIE


class CompatibleOdnoklassnikiIE(OdnoklassnikiIE):
    @classmethod
    def ie_key(cls):
        return OdnoklassnikiIE.ie_key()

    def _parse_json(self, json_string, *args, **kwargs):
        if isinstance(json_string, dict):
            return json_string
        return super()._parse_json(json_string, *args, **kwargs)


def create_downloader(options):
    options = dict(options)
    # Prefer clients supported by the local PO-token provider on YouTube.
    extractor_args = dict(options.get('extractor_args') or {})
    extractor_args.setdefault('youtube', {'player_client': ['mweb', 'web_safari', 'web_embedded', 'android_vr']})
    options['extractor_args'] = extractor_args
    downloader = YoutubeDL(options)
    downloader.add_info_extractor(CompatibleOdnoklassnikiIE())
    return downloader
