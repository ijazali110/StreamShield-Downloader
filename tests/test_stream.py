import io,json,subprocess,tempfile,unittest,shutil,os
from pathlib import Path
from unittest.mock import patch
from server.stream_worker import media_chunks,PublicRedirect

class Response(io.BytesIO):
 def __init__(self,data):super().__init__(data);self.headers={'Content-Length':str(len(data))}
class Opener:
 def __init__(self,data):self.data=data
 def open(self,*args,**kwargs):return Response(self.data)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class PipeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.fixture=subprocess.check_output(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc=size=64x64:rate=10','-f','lavfi','-i','sine=frequency=880','-t','1','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-threads','1','-movflags','frag_keyframe+empty_moov','-f','mp4','pipe:1'])
 def stream(self,mode,count=1):
  with patch('server.stream_worker.validate_url'):
   return b''.join(media_chunks(['https://example.org/media']*count,mode,Opener(self.fixture)))
 def probe(self,data):
  result=subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name,codec_type','-of','json','pipe:0'],input=data)
  return json.loads(result)['streams']
 def test_real_mp3_conversion_has_audio_only(self):
  streams=self.probe(self.stream('mp3'));self.assertEqual(streams,[{'codec_name':'mp3','codec_type':'audio'}])
 def test_mux_stream_contains_video_and_audio_and_no_files(self):
  with tempfile.TemporaryDirectory() as folder:
   previous=os.getcwd();os.chdir(folder)
   try:
    streams=self.probe(self.stream('video',2));self.assertEqual({s['codec_type'] for s in streams},{'video','audio'});self.assertEqual(list(Path('.').iterdir()),[])
   finally:os.chdir(previous)
 def test_bad_media_is_not_reported_as_success(self):
  with patch('server.stream_worker.validate_url'):
   with self.assertRaises(ValueError):list(media_chunks(['https://example.org/x'],'mp3',Opener(b'not media')))
 def test_private_destination_and_redirect_rejected(self):
  with self.assertRaises(ValueError):list(media_chunks(['http://127.0.0.1/private'],'mp3'))
  with self.assertRaises(ValueError):PublicRedirect().redirect_request(None,None,302,'',{},'http://127.0.0.1/private')
 def test_consumer_cancellation_closes_converter(self):
  with patch('server.stream_worker.validate_url'):
   stream=media_chunks(['https://example.org/media'],'mp3',Opener(self.fixture));self.assertTrue(next(stream));stream.close()
