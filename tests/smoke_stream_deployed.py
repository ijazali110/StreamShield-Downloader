"""Operator HTTPS relay test with our original synthetic fixture.
This mints a test selection using the owner's existing server key; public
analysis still only accepts YouTube. No production access rule is modified.
No media is written to disk, and no secret/selection token is printed.
"""
import hashlib,http.cookiejar,json,subprocess,time,urllib.request,urllib.parse
from pathlib import Path
from types import SimpleNamespace
from server.free import seal
BASE='https://tool.vieapps.cloud/streamforge/'
env=dict(line.split('=',1) for line in Path('/etc/streamforge3.env').read_text().splitlines() if '=' in line)
app=SimpleNamespace(password_hash=hashlib.pbkdf2_hmac('sha256',env['STREAMFORGE_PASSWORD'].encode(),b'StreamForge private dashboard',200000))
jar=http.cookiejar.CookieJar();client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
with client.open(BASE+'api/free/session') as response:session=json.load(response)
owner=next(c.value.split('.')[0] for c in jar if c.name=='ss_guest')
root=Path('/var/lib/streamforge3')
def media_files():return {str(p.relative_to(root)):p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.name.startswith('jobs.sqlite')}
before=media_files()
for mode in ('video','mp3'):
 token=seal(app,{'owner':owner,'expires':time.time()+600,'title':'Original synthetic fixture','mode':mode,'sources':[BASE+'test/demo.mp4']})
 data=urllib.parse.urlencode({'csrf':session['csrf'],'token':token}).encode()
 request=urllib.request.Request(BASE+'api/free/download',data=data,headers={'Content-Type':'application/x-www-form-urlencoded','Origin':'https://tool.vieapps.cloud'})
 with client.open(request,timeout=100) as response:
  media=response.read();assert response.headers['Cache-Control']=='no-store';assert 'attachment' in response.headers['Content-Disposition']
 streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_name,codec_type','-of','json','pipe:0'],input=media))['streams']
 assert {s['codec_type'] for s in streams}==({'audio','video'} if mode=='video' else {'audio'})
 if mode=='mp3':assert streams[0]['codec_name']=='mp3'
 print('HTTPS '+mode+' streamed and probed:',len(media),'bytes; PASS')
assert before==media_files(),'Unexpected retained media file'
print('No new VPS media files: PASS')
