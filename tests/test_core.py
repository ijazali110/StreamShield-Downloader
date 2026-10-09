import unittest, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import core

class CoreTests(unittest.TestCase):
    def test_protection_inherited_dash(self):
        manifest='<MPD xmlns="urn:mpeg:dash:schema:mpd:2011"><Period><AdaptationSet><ContentProtection schemeIdUri="urn:uuid:edef8ba9-79d6-4ace-a3c8-27dcd51d21ed"/><Representation id="hd" height="1080"/></AdaptationSet></Period></MPD>'
        self.assertEqual(core.inspect_manifest(manifest, 'https://example.org/v.mpd')['protection'], 'Widevine Protected')
    def test_hls_qualities_and_relative_paths(self):
        m='#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1920x1080\nhi/main.m3u8\n'
        r=core.inspect_manifest(m,'https://example.org/a/master.m3u8')
        self.assertEqual(r['tracks'][0]['url'],'https://example.org/a/hi/main.m3u8')
        self.assertEqual(r['tracks'][0]['height'],1080)
    def test_encrypted_hls_not_declared_clear(self):
        r=core.inspect_manifest('#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,KEYFORMAT="com.apple.streamingkeydelivery",URI="skd://test"\n','https://example.org/a.m3u8')
        self.assertEqual(r['protection'],'FairPlay Protected')
    def test_redacts_every_query_value_and_credentials(self):
        s=core.redact_url('https://user:secret@example.org/a?Policy=verysecret&X-Amz-Signature=alsosecret')
        self.assertNotIn('secret',s)
        self.assertNotIn('user',s)
        self.assertIn('example.org/a',s)
    def test_private_addresses_blocked(self):
        for address in ['127.0.0.1','10.0.0.2','169.254.169.254','::1','::ffff:127.0.0.1']:
            self.assertFalse(core.public_address(address))
    def test_url_credentials_and_schemes_rejected(self):
        for url in ['file:///etc/passwd','http://user:pw@example.org/a','http://127.0.0.1/a','http://example.org:22/a']:
            with self.assertRaises(ValueError): core.validate_url(url, resolve=False)
    def test_lab_roundtrip_and_wrong_key_no_output(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); key='00'*32
            blob=core.lab_encrypt(b'owned test media',key)
            self.assertEqual(core.lab_decrypt(blob,key),b'owned test media')
            with self.assertRaises(ValueError): core.lab_decrypt(blob,'11'*32)
            with self.assertRaises(ValueError): core.lab_decrypt(b'not our format',key)
    def test_hls_aes_is_encrypted(self):
        r=core.inspect_manifest('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="key.bin"\nseg.ts','https://example.org/m.m3u8')
        self.assertEqual(r['protection'],'Encrypted HLS')
    def test_clearkey_is_protected(self):
        r=core.inspect_manifest('<MPD><ContentProtection schemeIdUri="urn:uuid:e2719d58-a985-b3c9-781a-b030af78d30e"/></MPD>','https://example.org/m.mpd')
        self.assertNotEqual(r['protection'],'Clear')

if __name__=='__main__': unittest.main()
