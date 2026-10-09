import unittest, tempfile, threading, http.cookiejar, urllib.request, urllib.error, json, time
from unittest.mock import patch
from pathlib import Path
from server.app import Application,create_server
from server.free import seal,unseal,choices

URL='https://youtu.be/BaW_jenozKc'
def report():
 return {'title':'Owned fixture','duration':100000,'downloadable':True,'protection':'Clear','is_live':False,'formats':[
 {'id':'v','height':2160,'fps':60,'ext':'mp4','protocol':'https','url':'https://example.org/video.mp4','video_codec':'avc1','audio_codec':'none','size':5*1024**3},
 {'id':'a','protocol':'https','url':'https://example.org/audio.m4a','video_codec':'none','audio_codec':'aac','bitrate':128}]}

class FreeAPITests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name,'test-password-long-enough',start_runner=False)
  self.server=create_server(self.app,'127.0.0.1',0,secure_cookie=False);self.t=threading.Thread(target=self.server.serve_forever,daemon=True);self.t.start();self.base=f'http://127.0.0.1:{self.server.server_port}'
 def tearDown(self):self.server.shutdown();self.server.server_close();self.app.close();self.tmp.cleanup()
 def client(self):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def req(self,c,path,body=None,csrf=''):
  return c.open(urllib.request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':csrf}))
 def guest(self,c):
  with self.req(c,'/api/free/session') as r:return json.load(r)['csrf']
 def analyze(self,c,csrf):
  with patch.object(self.app,'analyze',return_value=report()):
   with self.req(c,'/api/free/analyze',{'url':URL},csrf) as r:return json.load(r)
 def test_public_home_and_private_isolation(self):
  c=self.client();self.assertTrue(self.guest(c))
  with self.req(c,'/') as r:
   html=r.read().decode();self.assertIn('MP3',html);self.assertNotIn('id="free-bulk"',html)
  with self.assertRaises(urllib.error.HTTPError) as e:self.req(c,'/api/jobs')
  self.assertEqual(e.exception.code,401)
 def test_analysis_keeps_high_quality_long_large_media_and_no_saved_job(self):
  c=self.client();csrf=self.guest(c);before=set(Path(self.tmp.name).rglob('*'));data=self.analyze(c,csrf)
  self.assertEqual([o['mode'] for o in data['options']],['video','mp3']);self.assertIn('2160p',data['options'][0]['label'])
  self.assertNotIn('example.org',json.dumps(data));self.assertEqual(self.app.jobs(),[]);self.assertEqual(before,set(Path(self.tmp.name).rglob('*')))
 def test_clear_direct_selection_and_protection(self):
  r=report();self.assertEqual([x['url'] for x in choices(r)[0]['sources']],['https://example.org/video.mp4','https://example.org/audio.m4a'])
  for key,value in [('is_live',True),('protection','DRM Protected'),('downloadable',False)]:
   test=report();test[key]=value;self.assertEqual(choices(test),[])
  r['formats'][0]['protocol']='m3u8_native';self.assertEqual([c['mode'] for c in choices(r)],['mp3'])
 def test_youtube_only_single_and_csrf(self):
  c=self.client();csrf=self.guest(c)
  for url in ['https://example.org/v.mp4','https://youtube.com.example.org/watch?v=BaW_jenozKc',URL+' '+URL]:
   with self.assertRaises(urllib.error.HTTPError) as e:self.req(c,'/api/free/analyze',{'url':url},csrf)
   self.assertEqual(e.exception.code,400)
  with self.assertRaises(urllib.error.HTTPError) as e:self.req(c,'/api/free/analyze',{'url':URL})
  self.assertEqual(e.exception.code,403)
 def test_token_integrity_owner_expiry(self):
  payload={'owner':'a','expires':time.time()+100,'sources':['https://example.org/x']};token=seal(self.app,payload)
  self.assertEqual(unseal(self.app,token,'a')['sources'],payload['sources'])
  for invalid,owner in [(token,'b'),(token[:-8]+'AAAAAAAA','a'),(seal(self.app,{**payload,'expires':time.time()-1}),'a')]:
   with self.assertRaises(ValueError):unseal(self.app,invalid,owner)
 def test_form_download_cross_session_and_csrf_blocked(self):
  a,b=self.client(),self.client();ac=self.guest(a);bc=self.guest(b);token=self.analyze(a,ac)['options'][0]['token']
  for client,csrf in [(a,''),(b,bc)]:
   data=urllib.parse.urlencode({'csrf':csrf,'token':token}).encode()
   with self.assertRaises(urllib.error.HTTPError) as e:client.open(urllib.request.Request(self.base+'/api/free/download',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'}))
   self.assertIn(e.exception.code,(400,403))
  self.assertEqual(self.app.jobs(),[])
 def test_old_queue_cannot_save_new_public_media(self):
  c=self.client();csrf=self.guest(c)
  with self.assertRaises(urllib.error.HTTPError) as e:self.req(c,'/api/free/jobs',{'url':URL},csrf)
  self.assertEqual(e.exception.code,400);self.assertEqual(self.app.jobs(),[])
 def test_server_verification_error_is_explicit(self):
  c=self.client();csrf=self.guest(c)
  with patch.object(self.app,'analyze',side_effect=ValueError('Sign in to confirm you are not a bot')):
   with self.assertRaises(urllib.error.HTTPError) as e:self.req(c,'/api/free/analyze',{'url':URL},csrf)
   self.assertIn('requesting verification',json.load(e.exception)['error'])
 def test_chunked_download_headers_and_no_media_saved(self):
  import subprocess,sys
  original=subprocess.Popen
  c=self.client();csrf=self.guest(c);token=self.analyze(c,csrf)['options'][0]['token']
  before=set(Path(self.tmp.name).rglob('*'))
  def worker(*args,**kwargs):
   return original([sys.executable,'-c','import sys,json;json.load(sys.stdin);sys.stdout.buffer.write(b\'{"ready":true}\\nfixture-media\');sys.stdout.buffer.flush()'],**kwargs)
  data=urllib.parse.urlencode({'csrf':csrf,'token':token}).encode()
  with patch('server.free.subprocess.Popen',side_effect=worker,create=True):
   with c.open(urllib.request.Request(self.base+'/api/free/download',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'})) as response:
    self.assertEqual(response.read(),b'fixture-media');self.assertEqual(response.headers['Transfer-Encoding'],'chunked');self.assertEqual(response.headers['X-Accel-Buffering'],'no');self.assertIn('attachment',response.headers['Content-Disposition'])
  self.assertEqual(self.app.jobs(),[]);self.assertEqual(before,set(Path(self.tmp.name).rglob('*')))
 def test_daily_quota_prevents_starting_converter(self):
  c=self.client();csrf=self.guest(c);token=self.analyze(c,csrf)['options'][0]['token']
  from server.free import signature
  for _ in range(10):self.app.db_write('INSERT INTO free_usage VALUES (?,?)',(signature(self.app,'free-ip:127.0.0.1'),time.time()))
  data=urllib.parse.urlencode({'csrf':csrf,'token':token}).encode()
  with self.assertRaises(urllib.error.HTTPError) as error:c.open(urllib.request.Request(self.base+'/api/free/download',data=data,headers={'Content-Type':'application/x-www-form-urlencoded'}))
  self.assertIn('Daily free limit',json.load(error.exception)['error'])
