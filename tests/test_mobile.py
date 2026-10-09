import json, unittest, urllib.request
from server import worker
from server.app import Application, create_server
from unittest.mock import patch
from pathlib import Path

class MobileWorkflowTests(unittest.TestCase):
    def test_netflix_link_returns_official_app_guidance_without_network_extraction(self):
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('93.184.216.34',443))]), patch.object(worker,'create_downloader',side_effect=AssertionError('Should not attempt a DRM portal download')):
            r=worker.analyze('https://www.netflix.com/watch/123456',{})
        self.assertFalse(r['downloadable'])
        self.assertEqual(r['source'],'Netflix')
        self.assertEqual(r['availability'],'official_app_only')
        self.assertIn('Download',r['message'])
    def test_netflix_lookalike_domain_is_not_classified_as_netflix(self):
        from server.sources import portal_policy
        self.assertIsNone(portal_policy('https://netflix.com.example.org/watch/123'))
    def test_prime_policy_and_public_media(self):
        from server.sources import portal_policy
        self.assertEqual(portal_policy('https://www.primevideo.com/detail/123')['source'],'Prime Video')
        self.assertIsNone(portal_policy('https://example.org/video.mp4'))
    def test_share_target_requires_an_explicit_scan(self):
        root=Path(__file__).resolve().parents[1]/'server/static'
        manifest=json.loads((root/'manifest.webmanifest').read_text())
        self.assertEqual(manifest['name'],'Shield Stream')
        self.assertEqual(manifest['share_target']['method'],'GET')
        self.assertEqual(manifest['share_target']['params']['url'],'url')
        self.assertEqual(manifest['display'],'standalone')
        self.assertEqual(manifest['scope'],'./')
