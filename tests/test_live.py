import unittest, tempfile
from pathlib import Path
from unittest.mock import patch
from server import worker

class LiveTests(unittest.TestCase):
    def test_live_rejects_encryption_before_any_segment_is_downloaded(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker,'fetch_small',return_value=('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key"\n#EXTINF:2,\na.ts\n','application/x-mpegurl')):
            with self.assertRaisesRegex(ValueError,'encrypted'):
                worker.record_live_hls('https://example.org/live.m3u8',{},Path(directory),1,1024)
            self.assertFalse(any(Path(directory).iterdir()))
    def test_live_fmp4_has_explicit_unsupported_result(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(worker,'fetch_small',return_value=('#EXTM3U\n#EXT-X-MAP:URI="init.mp4"\n#EXTINF:2,\na.m4s\n','application/x-mpegurl')):
            with self.assertRaisesRegex(ValueError,'MPEG-TS'):
                worker.record_live_hls('https://example.org/live.m3u8',{},Path(directory),1,1024)

if __name__=='__main__': unittest.main()
