"""Anonymous YouTube tier. Guest-bound stateless media transfer selections."""
import hashlib,hmac,secrets,time,re,json,urllib.parse,subprocess
FREE_MAX_BYTES=200*1024**2

def youtube_url(value):
 if not isinstance(value,str):raise ValueError('Paste a YouTube video link.')
 p=urllib.parse.urlsplit(value.strip());host=(p.hostname or '').lower()
 if p.scheme not in ('http','https') or p.username or p.password or p.port not in (None,80,443):raise ValueError('Paste a valid YouTube video link.')
 if host=='youtu.be':video=p.path.strip('/')
 elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'):
  if p.path=='/watch':video=urllib.parse.parse_qs(p.query).get('v',[''])[0]
  elif p.path.startswith(('/shorts/','/embed/','/live/')):video=p.path.split('/')[2]
  else:video=''
 else:video=''
 if not re.fullmatch(r'[A-Za-z0-9_-]{11}',video):raise ValueError('Paste one YouTube video link. Batch downloads belong to Personal.')
 return 'https://www.youtube.com/watch?v='+video

def signature(app,value):return hmac.new(app.password_hash,value.encode(),hashlib.sha256).hexdigest()
def guest(app,handler):
 from http.cookies import SimpleCookie
 try:
  c=SimpleCookie(handler.headers.get('Cookie',''));token=c['ss_guest'].value
  owner,created,sig=token.split('.')
  if not re.fullmatch(r'[0-9a-f]{32}',owner) or not hmac.compare_digest(sig,signature(app,owner+'.'+created)) or not 0<=time.time()-int(created)<86400:return None
  return {'owner':owner,'csrf':signature(app,'csrf:'+owner)}
 except (KeyError,ValueError):return None

def public_job(job):return {k:v for k,v in job.items() if not k.startswith('_')}
def ip_key(app,handler):
 ip=(handler.headers.get('X-Real-IP') or handler.client_address[0]) if handler.client_address[0]=='127.0.0.1' else handler.client_address[0]
 return signature(app,'free-ip:'+str(ip))
def rate(app,key,limit=12,window=600):
 with app.lock:
  now=time.time();app.free_rates={k:[t for t in times if now-t<window] for k,times in app.free_rates.items() if times and now-times[-1]<window}
  times=app.free_rates.setdefault(key,[])
  if len(times)>=limit or len(app.free_rates)>2000:raise ValueError('Free analysis limit reached. Please try again in 10 minutes.')
  times.append(now)

def seal(app,payload):
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 import base64
 nonce=secrets.token_bytes(12)
 key=hashlib.sha256(app.password_hash+b'public-stream-v1').digest()
 return base64.urlsafe_b64encode(nonce+AESGCM(key).encrypt(nonce,json.dumps(payload).encode(),b'shield-stream')).decode()

def unseal(app,token,owner):
 from cryptography.hazmat.primitives.ciphers.aead import AESGCM
 import base64
 try:
  if not isinstance(token,str) or len(token)>24000:raise ValueError()
  raw=base64.b64decode(token,altchars=b'-_',validate=True)
  key=hashlib.sha256(app.password_hash+b'public-stream-v1').digest()
  spec=json.loads(AESGCM(key).decrypt(raw[:12],raw[12:],b'shield-stream'))
  if spec['owner']!=owner or not 0<spec['expires']-time.time()<=1200:raise ValueError()
  return spec
 except Exception:raise ValueError('Download link expired or invalid. Analyze the video again.') from None

def choices(report):
 """Only clear, direct media can be piped to FFmpeg without segment files."""
 if not report.get('downloadable') or report.get('is_live') or report.get('protection')!='Clear':return []
 formats=[f for f in report.get('formats',[]) if not f.get('drm') and f.get('protocol') in ('http','https') and f.get('url','').startswith(('http://','https://'))]
 audios=[f for f in formats if f.get('audio_codec') not in ('none',None,'')]
 audio=max(audios,key=lambda f:(f.get('video_codec')=='none',f.get('bitrate') or 0),default=None)
 out=[]
 for f in sorted(formats,key=lambda f:((f.get('height') or 0),f.get('fps') or 0),reverse=True):
  if f.get('video_codec') in ('none',None,''):continue
  sources=[{'url':f['url'],'headers':f.get('http_headers',{})}]
  if f.get('audio_codec') in ('none',None,''):
   if not audio:continue
   sources.append({'url':audio['url'],'headers':audio.get('http_headers',{})})
  out.append({'label':str(f.get('height') or f.get('note') or 'Video')+('p' if f.get('height') else '')+' · '+str(f.get('fps') or 30)+' fps · MP4','mode':'video','sources':sources,'id':f['id']})
 if audio:out.append({'label':'MP3 audio · 192 kbps','mode':'mp3','sources':[{'url':audio['url'],'headers':audio.get('http_headers',{})}],'id':audio['id']})
 return out

def download(handler,app,spec,ip):
 import os,subprocess,sys,select
 from pathlib import Path
 if app.stop.is_set() or not app.stream_slots.acquire(blocking=False):raise ValueError('A transfer is already running. Please try again shortly.')
 proc=None;started=False
 def chunk():
  if not select.select([proc.stdout],[],[],90)[0]:raise ValueError('The source stopped responding. Analyze again and retry.')
  return os.read(proc.stdout.fileno(),65536)
 try:
  rate(app,ip+':download',limit=12)
  with app.connection() as db:
   if db.execute('SELECT count(*) FROM free_usage WHERE ip=? AND created>?',(ip,time.time()-86400)).fetchone()[0]>=10:raise ValueError('Daily free limit reached (10 downloads).')
  proc=subprocess.Popen([sys.executable,'-m','server.stream_worker'],cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,bufsize=0)
  with app.lock:app.stream_processes.add(proc)
  proc.stdin.write(json.dumps({'mode':spec['mode'],'sources':spec['sources']}).encode());proc.stdin.close()
  # The worker emits one readiness line only after the first actual media bytes exist.
  line=b''
  while not line.endswith(b'\n'):
   if not select.select([proc.stdout],[],[],90)[0]:raise ValueError('Download startup timed out. Please retry.')
   b=os.read(proc.stdout.fileno(),1)
   if not b or len(line)>4096:raise ValueError('The stream could not be started.')
   line+=b
  ready=json.loads(line)
  if not ready.get('ready'):raise ValueError(ready.get('error','The source could not be downloaded.'))
  app.db_write('INSERT INTO free_usage VALUES (?,?)',(ip,time.time()))
  ext='mp3' if spec['mode']=='mp3' else 'mp4'
  filename=re.sub(r'[^\w .-]','',spec.get('title','YouTube'))[:100].strip() or 'YouTube'
  handler.send_response(200)
  for k,v in {'Content-Type':'audio/mpeg' if ext=='mp3' else 'video/mp4','Content-Disposition':"attachment; filename=\"Shield-Stream."+ext+"\"; filename*=UTF-8''"+urllib.parse.quote(filename+'.'+ext),'Transfer-Encoding':'chunked','Cache-Control':'no-store','X-Accel-Buffering':'no','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}.items():handler.send_header(k,v)
  handler.end_headers();started=True;handler.connection.settimeout(90)
  while True:
   data=chunk()
   if not data:break
   handler.wfile.write(('%X\r\n'%len(data)).encode()+data+b'\r\n');handler.wfile.flush()
  if proc.wait(timeout=10)!=0:raise ValueError('The source transfer was interrupted. Please retry.')
  handler.wfile.write(b'0\r\n\r\n');handler.wfile.flush()
 except Exception:
  if started:handler.close_connection=True
  else:raise
 finally:
  if proc:
   app.terminate(proc);proc.stdout.close()
   with app.lock:app.stream_processes.discard(proc)
  app.stream_slots.release()

def dispatch_free(handler,app,path,secure_cookie):
 if not path.startswith('/api/free/'):return False
 if path=='/api/free/session' and handler.command=='GET':
  g=guest(app,handler);extra={}
  if not g:
   owner=secrets.token_hex(16);stamp=str(int(time.time()));token=owner+'.'+stamp+'.'+signature(app,owner+'.'+stamp)
   g={'owner':owner,'csrf':signature(app,'csrf:'+owner)}
   extra={'Set-Cookie':'ss_guest='+token+'; Path='+__import__('os').environ.get('STREAMFORGE_COOKIE_PATH','/')+'; HttpOnly; SameSite=Strict; Max-Age=86400'+('; Secure' if secure_cookie else '')}
  handler.send(200,{'csrf':g['csrf'],'max_batch':1,'daily_limit':10,'media_storage':False},extra=extra);return True
 g=guest(app,handler)
 if not g:handler.send(401,{'error':'Your free session expired. Refresh the page.'});return True
 body=None
 if path=='/api/free/download' and handler.command=='POST':
  if not handler.headers.get('Content-Type','').startswith('application/x-www-form-urlencoded'):raise ValueError('Invalid download request.')
  body=urllib.parse.parse_qs(handler.body().decode(),max_num_fields=3)
  csrf=body.get('csrf',[''])[0]
 else:csrf=handler.headers.get('X-CSRF-Token','')
 if handler.command=='POST':
  if not hmac.compare_digest(csrf,g['csrf']):handler.send(403,{'error':'Session validation failed. Refresh the page.'});return True
  expected=__import__('os').environ.get('STREAMFORGE_PUBLIC_ORIGIN');origin=handler.headers.get('Origin')
  if expected and origin and origin!=expected:handler.send(403,{'error':'Unexpected request origin.'});return True
 if path=='/api/free/analyze' and handler.command=='POST':
  spec=handler.json_body()
  if set(spec)!={'url'}:raise ValueError('Free accepts one YouTube link. Batch downloads belong to Personal.')
  url=youtube_url(spec.get('url'));rate(app,ip_key(app,handler))
  try:report=app.analyze({'url':url})
  except ValueError as exc:
   if re.search(r'(?i)not a bot|confirm.*bot|captcha|sign in to confirm',str(exc)):raise ValueError('YouTube is requesting verification from this VPS. This video is unavailable here right now.') from None
   raise
  selections=[]
  for choice in choices(report):
   token=seal(app,{'owner':g['owner'],'expires':time.time()+1200,'title':str(report.get('title') or 'YouTube')[:150],'mode':choice['mode'],'sources':choice['sources']})
   selections.append({'label':choice['label'],'mode':choice['mode'],'token':token})
  handler.send(200,{'title':report.get('title'),'duration':report.get('duration'),'options':selections,'downloadable':bool(selections),'message':'' if selections else 'No clear, directly streamable formats are available for this video.'});return True
 if path=='/api/free/download' and handler.command=='POST':
  try:
   spec=unseal(app,body.get('token',[''])[0],g['owner']);download(handler,app,spec,ip_key(app,handler))
  except ValueError as exc:
   if 'text/html' not in handler.headers.get('Accept',''):raise
   import html
   handler.send(400,'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Download · Shield Stream</title><link rel="stylesheet" href="../../style.css"><main class="marketing-main"><h1>Download unavailable</h1><p>'+html.escape(str(exc))+'</p><a class="primary" href="../../">Return to downloader →</a></main>','text/html')
  return True
 if path=='/api/free/jobs' and handler.command=='POST':raise ValueError('The public saved-file queue is retired. Analyze one YouTube link to download directly.')
 raise FileNotFoundError('Route not found.')
