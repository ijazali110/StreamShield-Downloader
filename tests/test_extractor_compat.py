import html
import json
import unittest
from unittest.mock import patch
from server.extractor_compat import create_downloader


class EmbeddedMetadataTests(unittest.TestCase):
    def extract_fixture(self,metadata):
        player={'videoId':'12345678','flashvars':{'metadata':metadata}}
        page='<div data-options="'+html.escape(json.dumps(player),quote=True)+'"></div>'
        with create_downloader({'quiet':True,'no_warnings':True}) as downloader:
            extractor=downloader.get_info_extractor('Odnoklassniki')
            with patch.object(extractor,'_download_webpage',return_value=page):
                return extractor._extract_desktop('https://ok.ru/videoembed/12345678')

    def metadata(self):
        return {'provider':'UPLOADED_ODKL','movie':{'title':'Owned test fixture','duration':'8'},'videos':[{'name':'hd','url':'https://example.org/test.mp4'}]}

    def test_embedded_metadata_already_decoded_as_object(self):
        info=self.extract_fixture(self.metadata())
        self.assertEqual(info['title'],'Owned test fixture')
        self.assertEqual(info['formats'][0]['url'],'https://example.org/test.mp4')
        self.assertEqual(info['duration'],8)

    def test_legacy_metadata_json_string_still_works(self):
        info=self.extract_fixture(json.dumps(self.metadata()))
        self.assertEqual(info['formats'][0]['format_id'],'hd')
        self.assertEqual(info['title'],'Owned test fixture')

    def test_malformed_json_still_rejected(self):
        with self.assertRaises(Exception):
            self.extract_fixture('{broken json')

class ManifestSessionTests(unittest.TestCase):
    def test_manifest_verification_preserves_extractor_request_headers(self):
        from server import worker
        from unittest.mock import MagicMock
        from urllib.error import HTTPError
        info={'title':'Owned embedded fixture','formats':[{'format_id':'hls-720','url':'https://example.org/720.m3u8','manifest_url':'https://example.org/master.m3u8','protocol':'m3u8_native','height':720,'http_headers':{'User-Agent':'Fixture player client'},'has_drm':False}]}
        downloader=MagicMock()
        downloader.__enter__.return_value.extract_info.return_value=info
        def inspect(url,headers):
            if headers.get('User-Agent')!='Fixture player client':
                raise HTTPError(url,400,'Bad Request',{},None)
            return {'protocol':'HLS','protection':'Clear','tracks':[],'live':False}
        with patch.object(worker,'validate_url'), patch.object(worker,'create_downloader',return_value=downloader), patch.object(worker,'manifest_status',side_effect=inspect):
            result=worker.analyze('https://example.org/page',{})
        self.assertEqual(result['protection'],'Clear')
        self.assertTrue(result['downloadable'])

class DirectSourceErrors(unittest.TestCase):
    def test_direct_media_error_is_preserved_without_page_fallback(self):
        from server import worker
        from unittest.mock import MagicMock
        downloader=MagicMock()
        downloader.__enter__.return_value.extract_info.side_effect=ValueError('HTTP Error 403: source refused request')
        with patch.object(worker,'validate_url'),patch.object(worker,'create_downloader',return_value=downloader),patch.object(worker,'fetch_small',side_effect=AssertionError('Binary files must not enter HTML fallback')):
            with self.assertRaisesRegex(ValueError,'HTTP Error 403'):
                worker.analyze('https://example.org/media.mp4',{})
