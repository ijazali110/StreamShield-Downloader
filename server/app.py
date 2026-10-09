from __future__ import annotations
import math, hashlib, hmac, json, mimetypes, os, secrets, shutil, signal, sqlite3, subprocess, sys, threading, time, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from .free import dispatch_free, FREE_MAX_BYTES
from .core import VERSION, validate_url, redact_url, sanitize_error, lab_encrypt, lab_decrypt

ROOT=Path(__file__).resolve().parents[1]
MAX_JOB_BYTES=2*1024**3
MAX_STORAGE_BYTES=10*1024**3

class Application:
    def __init__(self,data,password,start_runner=True):
        self.data=Path(data); self.data.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.password_hash=hashlib.pbkdf2_hmac('sha256',password.encode(),b'StreamForge private dashboard',200000)
        self.db=self.data/'jobs.sqlite'; self.lock=threading.RLock(); self.stop=threading.Event()
        self.next_free_cleanup=0; self.free_rates={}; self.sessions={}; self.auth_failures={}; self.headers={}; self.processes={}; self.scan_slots=threading.BoundedSemaphore(2); self.stream_slots=threading.BoundedSemaphore(1); self.stream_processes=set()
        self.db_write('CREATE TABLE IF NOT EXISTS free_usage (ip TEXT, created REAL)')
        self.db_write('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created REAL, updated REAL, status TEXT, spec TEXT, progress TEXT, files TEXT, error TEXT)')
        os.chmod(self.db,0o600)
        self.db_write("UPDATE jobs SET status='paused', error='Server restarted. Retry to resume; supply session headers again if needed.' WHERE status IN ('queued','downloading','merging')")
        if start_runner: threading.Thread(target=self.runner,daemon=True).start()
    def connection(self): return sqlite3.connect(self.db,timeout=15)
    def db_write(self,sql,args=()):
        with self.lock,self.connection() as db: db.execute(sql,args)
    def jobs(self):
        with self.connection() as db: db.row_factory=sqlite3.Row; rows=db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 200').fetchall()
        out=[]
        for row in rows:
            r=dict(row); spec=json.loads(r.pop('spec')); r.update({k:v for k,v in spec.items() if k!='headers'}); r['url']=redact_url(r['url'])
            r['progress']=json.loads(r['progress']); r['files']=json.loads(r['files']); out.append(r)
        return out
    def raw_job(self,job_id):
        with self.connection() as db:
            db.row_factory=sqlite3.Row; row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
        if not row: raise FileNotFoundError('Job not found.')
        r=dict(row); r['spec']=json.loads(r['spec']); return r
    def update(self,job_id,**values):
        values['updated']=time.time()
        for name in ('progress','files'):
            if name in values: values[name]=json.dumps(values[name])
        self.db_write('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',(*values.values(),job_id))
    def parse_headers(self,value):
        if value is None: return {}
        if not isinstance(value,dict) or len(value)>8: raise ValueError('Supply at most 8 request headers.')
        allowed={'referer','origin','user-agent','authorization','cookie','accept-language'}
        result={}
        for k,v in value.items():
            if k.lower() not in allowed or not isinstance(v,str) or len(v)>8192 or '\n' in v or '\r' in v: raise ValueError('Invalid or unsupported request header.')
            result[k]=v
        return result
    def storage_size(self): return sum(p.stat().st_size for p in self.data.rglob('*') if p.is_file())
    def add_job(self,spec,guest_owner=None,guest_ip=None):
        url=validate_url(spec.get('url',''),resolve=False)
        headers=self.parse_headers(spec.get('headers'))
        format_id=str(spec.get('format_id') or 'best'); audio_id=str(spec.get('audio_id') or '')
        if not all(len(f)<=100 and all(c.isalnum() or c in '._-' for c in f) for f in (format_id,audio_id)): raise ValueError('Invalid format selection.')
        rate=int(spec.get('rate_kbps') or 0); duration=int(spec.get('duration_seconds') or 0); scheduled=float(spec.get('scheduled_at') or 0)
        if not math.isfinite(scheduled) or rate<0 or rate>102400 or duration<0 or duration>14400 or scheduled<0 or scheduled>time.time()+366*86400: raise ValueError('Invalid rate, duration, or schedule.')
        subs=spec.get('subtitles') or []
        if not isinstance(subs,list) or len(subs)>10 or any(not isinstance(x,str) or len(x)>40 or not all(c.isalnum() or c in '._-' for c in x) for x in subs): raise ValueError('Invalid subtitle languages.')
        title=str(spec.get('title') or 'Media')[:200]
        with self.lock:
            if len([j for j in self.jobs() if j['status'] in ('queued','downloading','merging')])>=30: raise ValueError('Queue limit reached (30 jobs).')
            if self.storage_size()>=MAX_STORAGE_BYTES: raise ValueError('Storage limit reached; delete completed jobs to free space.')
            spec={'url':url,'title':title,'format_id':format_id,'audio_id':audio_id,'rate_kbps':rate,'duration_seconds':duration,'scheduled_at':scheduled,'subtitles':subs}
            for job in self.jobs():
                if job['status'] in ('queued','downloading','merging'):
                    if job.get('_guest_owner')!=guest_owner:continue
                    old=self.raw_job(job['id'])['spec']
                    if old['url']==url and old['format_id']==format_id and old.get('audio_id','')==audio_id: raise ValueError('This selection is already in the queue.')
            if guest_owner:spec.update({'_guest_owner':guest_owner,'_guest_ip':guest_ip,'_free':True})
            job_id=secrets.token_hex(8); now=time.time()
            self.headers[job_id]=headers
            self.db_write('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?)',(job_id,now,now,'queued',json.dumps(spec),'{}','[]',''))
        return next(j for j in self.jobs() if j['id']==job_id)
    def spawn(self,request):
        p=subprocess.Popen([sys.executable,'-m','server.worker'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,start_new_session=True)
        p.stdin.write(json.dumps(request)+'\n'); p.stdin.close(); return p
    def analyze(self,spec):
        url=validate_url(spec.get('url',''),resolve=False); headers=self.parse_headers(spec.get('headers'))
        if not self.scan_slots.acquire(blocking=False): raise ValueError('Two scans are already running. Please wait.')
        p=None
        try:
            p=self.spawn({'action':'analyze','url':url,'headers':headers})
            # communicate cannot flush the already-closed stdin.
            p.stdin=None
            out,_=p.communicate(timeout=90)
            for line in out.splitlines():
                msg=json.loads(line)
                if msg['event']=='analysis': return msg['result']
                if msg['event']=='error': raise ValueError(msg['message'])
            raise ValueError('No media details returned.')
        except subprocess.TimeoutExpired:
            if p: self.terminate(p)
            raise ValueError('Scan timed out. Try a direct manifest URL or the desktop extension.')
        finally: self.scan_slots.release()
    @staticmethod
    def terminate(p):
        try: os.killpg(p.pid,signal.SIGTERM)
        except (ProcessLookupError,AttributeError):
            if p.poll() is None: p.terminate()
        try: p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try: os.killpg(p.pid,signal.SIGKILL)
            except (ProcessLookupError,AttributeError): p.kill()
    def runner(self):
        while not self.stop.wait(1):
            try:
                if time.time()>self.next_free_cleanup:
                    self.next_free_cleanup=time.time()+60
                    with self.connection() as db:
                        expired=db.execute("SELECT id,spec FROM jobs WHERE created<? AND status NOT IN ('queued','downloading','merging')",(time.time()-86400,)).fetchall()
                    for jid,spec in expired:
                        if json.loads(spec).get('_free'):self.action(jid,'delete',{})
                    self.db_write('DELETE FROM free_usage WHERE created<?',(time.time()-2*86400,))
                pending=[j for j in reversed(self.jobs()) if j['status']=='queued' and j.get('scheduled_at',0)<=time.time()]
                if not pending: continue
                self.run_job(pending[0]['id'])
            except Exception: pass
    def run_job(self,job_id):
        with self.lock:
            job=self.raw_job(job_id)
            if job['status']!='queued': return
            request={**job['spec'],'action':'download','directory':str(self.data/job_id),'headers':self.headers.get(job_id,{}),'max_bytes':FREE_MAX_BYTES if job['spec'].get('_free') else MAX_JOB_BYTES}
            if self.storage_size()>=MAX_STORAGE_BYTES or shutil.disk_usage(self.data).free<3*1024**3:
                self.update(job_id,status='failed',error='Not enough storage; clear completed jobs.'); return
            p=self.spawn(request); self.processes[job_id]=p
            self.update(job_id,status='downloading',error='',progress={})
        timed_out=threading.Event()
        def timeout(): timed_out.set(); self.terminate(p)
        timer=threading.Timer(max(3600,request.get('duration_seconds',0)+180),timeout); timer.start()
        done=False; last_saved=0
        try:
            for line in p.stdout:
                try: msg=json.loads(line)
                except ValueError: continue
                if msg['event']=='progress':
                    now=time.time()
                    if now-last_saved>=0.6:
                        if self.raw_job(job_id)['status'] in ('downloading','merging'):
                            self.update(job_id,progress=msg,status='merging' if msg['status']=='finished' else 'downloading')
                        last_saved=now
                        if self.storage_size()>MAX_STORAGE_BYTES:
                            self.update(job_id,status='failed',error='Total storage limit reached.'); self.terminate(p)
                elif msg['event']=='done':
                    with self.lock:
                        if self.raw_job(job_id)['status'] in ('downloading','merging'):
                            self.update(job_id,status='completed',files=msg['files'],progress={'percent':100},error=''); done=True
                elif msg['event']=='error':
                    if self.raw_job(job_id)['status'] in ('downloading','merging'):
                        self.update(job_id,status='failed',error=sanitize_error(msg['message']))
            p.wait()
            if not done and self.raw_job(job_id)['status'] in ('downloading','merging'):
                self.update(job_id,status='failed',error='Job time limit reached.' if timed_out.is_set() else 'Download process ended. Retry to resume partial files.')
        finally:
            timer.cancel()
            with self.lock: self.processes.pop(job_id,None); self.headers.pop(job_id,None)
    def action(self,job_id,action,body):
        with self.lock:
            job=self.raw_job(job_id); p=self.processes.get(job_id)
            if action in ('pause','cancel'):
                if job['status'] not in ('queued','downloading','merging'): raise ValueError('Job is not running or queued.')
                self.update(job_id,status='paused' if action=='pause' else 'cancelled',error='')
                if p: self.terminate(p)
            elif action=='retry':
                if job['status'] not in ('failed','paused','cancelled'): raise ValueError('Retry is available for paused, cancelled, or failed jobs.')
                spec=job['spec']
                if body.get('url'): spec['url']=validate_url(body['url'],resolve=False)
                if body.get('format_id'):
                    f=body['format_id']
                    if not isinstance(f,str) or len(f)>100 or not all(c.isalnum() or c in '._-' for c in f): raise ValueError('Invalid format selection.')
                    spec['format_id']=f
                self.headers[job_id]=self.parse_headers(body.get('headers')); spec['scheduled_at']=0
                self.db_write('UPDATE jobs SET spec=? WHERE id=?',(json.dumps(spec),job_id))
                self.update(job_id,status='queued',error='')
            elif action=='delete':
                if p or job['status'] in ('queued','downloading','merging'): raise ValueError('Cancel the job before deleting it.')
                shutil.rmtree(self.data/job_id,ignore_errors=True); self.db_write('DELETE FROM jobs WHERE id=?',(job_id,)); self.headers.pop(job_id,None)
            else: raise ValueError('Unknown action.')
    def close(self):
        self.stop.set()
        for process in list(self.stream_processes): self.terminate(process)
        for job_id,p in list(self.processes.items()):
            self.update(job_id,status='paused',error='Service stopped; retry to resume.'); self.terminate(p)


def create_server(app,host,port,secure_cookie=True):
    class Handler(BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args): pass
        def send(self,status,payload,content_type='application/json',extra=None):
            if isinstance(payload,(dict,list)): payload=json.dumps(payload,ensure_ascii=False).encode()
            if isinstance(payload,str): payload=payload.encode()
            self.send_response(status); self.send_header('Content-Type',content_type); self.send_header('Content-Length',str(len(payload)))
            self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Cache-Control','no-store'); self.send_header('Referrer-Policy','no-referrer'); self.send_header('X-Frame-Options','DENY')
            if content_type.startswith('text/html'): self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; media-src 'self' https:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'")
            for k,v in (extra or {}).items(): self.send_header(k,v)
            self.end_headers(); self.wfile.write(payload)
        def body(self,limit=32768):
            if self.headers.get('Transfer-Encoding'): raise ValueError('Chunked uploads are not supported.')
            size=int(self.headers.get('Content-Length','0'))
            if size<0 or size>limit: raise ValueError('Upload too large.')
            self.connection.settimeout(30)
            data=self.rfile.read(size)
            if len(data)!=size: raise ValueError('Incomplete upload.')
            return data
        def json_body(self):
            value=json.loads(self.body() or b'{}')
            if not isinstance(value,dict): raise ValueError('JSON object required.')
            return value
        def session(self):
            cookie=SimpleCookie()
            try: cookie.load(self.headers.get('Cookie','')); token=cookie.get('sf_session'); session=app.sessions.get(token.value if token else '')
            except Exception: session=None
            if session and session['expires']>time.time(): return session
            return None
        def dispatch(self):
            path=urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
            if path=='/api/health':
                return self.send(200,{'ok':True,'brand':'Shield Stream','version':VERSION,'ffmpeg':bool(shutil.which('ffmpeg'))})
            if self.command=='GET' and path in ('/','/features','/pricing','/features.html','/pricing.html','/site.js','/app.js','/free.js','/style.css','/manifest.webmanifest','/sw.js','/shield.svg','/icon-192.png','/icon-512.png'):
                filename={'/':'index.html','/features':'features.html','/pricing':'pricing.html'}.get(path,path.lstrip('/'))
                return self.send(200,(ROOT/'server/static'/filename).read_bytes(),'application/manifest+json' if filename.endswith('.webmanifest') else mimetypes.guess_type(filename)[0] or 'application/octet-stream')
            if self.command=='POST' and path=='/api/login':
                data=self.json_body(); ip=self.headers.get('X-Real-IP') if self.client_address[0]=='127.0.0.1' else self.client_address[0]
                failures=[t for t in app.auth_failures.get(ip,[]) if t>time.time()-300]
                if len(failures)>=10: return self.send(429,{'error':'Too many login attempts. Wait five minutes.'})
                password=str(data.get('password',''))
                if len(password)>200: raise ValueError('Invalid password.')
                candidate=hashlib.pbkdf2_hmac('sha256',password.encode(),b'StreamForge private dashboard',200000)
                if not hmac.compare_digest(candidate,app.password_hash):
                    failures.append(time.time()); app.auth_failures[ip]=failures
                    return self.send(401,{'error':'Incorrect password.'})
                app.auth_failures.pop(ip,None)
                # Prune expired sessions and bound the in-memory session table.
                now=time.time()
                app.sessions={k:v for k,v in app.sessions.items() if v['expires']>now}
                if len(app.sessions)>=100: app.sessions.pop(next(iter(app.sessions)))
                token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
                app.sessions[token]={'csrf':csrf,'expires':now+12*3600}
                mount=os.environ.get('STREAMFORGE_COOKIE_PATH','/')
                return self.send(200,{'ok':True,'csrf':csrf},extra={'Set-Cookie':f'sf_session={token}; Path={mount}; HttpOnly; SameSite=Strict; Max-Age=43200'+('; Secure' if secure_cookie else '')})
            free_result=dispatch_free(self,app,path,secure_cookie)
            if free_result is True:return
            free_file=isinstance(free_result,str)
            if free_file:path=free_result
            session=self.session()
            if not session and not free_file: return self.send(401,{'error':'Please log in.'})
            if self.command=='POST':
                if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']): return self.send(403,{'error':'Session validation failed. Log in again.'})
                origin=self.headers.get('Origin')
                expected=os.environ.get('STREAMFORGE_PUBLIC_ORIGIN')
                if expected and origin and origin!=expected: return self.send(403,{'error':'Unexpected request origin.'})
            if path=='/api/session' and self.command=='GET': return self.send(200,{'csrf':session['csrf'],'version':VERSION})
            if path=='/api/logout' and self.command=='POST':
                cookie=SimpleCookie(self.headers.get('Cookie','')); app.sessions.pop(cookie['sf_session'].value,None)
                return self.send(200,{'ok':True},extra={'Set-Cookie':'sf_session=; Path='+os.environ.get('STREAMFORGE_COOKIE_PATH','/')+'; Max-Age=0; HttpOnly; SameSite=Strict'})
            if path in ('/api/studio/windows','/api/studio/extension') and self.command=='GET':
                asset={'/api/studio/windows':ROOT/'releases'/'ShieldStream-Windows-V2.2-Studio-Preview.zip','/api/studio/extension':ROOT/'releases'/'ShieldStream-Chrome-Extension-V2.2.zip'}[path]
                if not asset.is_file(): raise FileNotFoundError('Studio preview package is unavailable.')
                data=asset.read_bytes()
                return self.send(200,data,'application/zip',{'Content-Disposition':"attachment; filename*=UTF-8''"+urllib.parse.quote(asset.name)})
            if path=='/api/settings' and self.command=='GET':
                return self.send(200,{'brand':'Shield Stream','version':VERSION,'concurrency':1,'max_job_bytes':MAX_JOB_BYTES,'max_storage_bytes':MAX_STORAGE_BYTES,'used_bytes':app.storage_size(),'ffmpeg':bool(shutil.which('ffmpeg')),'demo_url':os.environ.get('STREAMFORGE_DEMO_URL',''),'external_test_url':'https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4','capabilities':['Android install and share links','URL analysis','HLS/DASH inspection','non-DRM downloads','queue','manual URL refresh','resume/retry','subtitles','owned-media AES-GCM lab']})
            if path=='/api/analyze' and self.command=='POST': return self.send(200,app.analyze(self.json_body()))
            if path=='/api/jobs':
                if self.command=='GET': return self.send(200,app.jobs())
                if self.command=='POST': return self.send(201,app.add_job(self.json_body()))
            parts=path.strip('/').split('/')
            if len(parts)>=3 and parts[:2]==['api','jobs']:
                job_id=parts[2]
                if not all(c in '0123456789abcdef' for c in job_id) or len(job_id)!=16: raise FileNotFoundError('Job not found.')
                job=app.raw_job(job_id)
                if len(parts)==4 and parts[3]=='report' and self.command=='GET':
                    report=next(j for j in app.jobs() if j['id']==job_id)
                    report['protection_policy']='Remote encrypted/protected streams are inspection-only; custom local lab files require an explicit owner key.'
                    return self.send(200,report,extra={'Content-Disposition':f'attachment; filename="Shield-Stream-{job_id}-report.json"'})
                if len(parts)==4 and self.command=='POST':
                    app.action(job_id,parts[3],self.json_body()); return self.send(200,{'ok':True})
                if len(parts)==5 and parts[3]=='files' and self.command=='GET':
                    if job['status']!='completed': raise ValueError('Job has not completed.')
                    name=parts[4]; allowed={f['name'] for f in json.loads(job['files'])}
                    if name not in allowed or Path(name).name!=name: raise FileNotFoundError('File not found.')
                    file=app.data/job_id/name
                    if not file.is_file(): raise FileNotFoundError('File not found.')
                    size=file.stat().st_size; start=0; end=size-1; status=200
                    import re
                    if self.headers.get('Range'):
                        m=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers['Range'])
                        if not m: return self.send(416,{'error':'Unsupported range.'})
                        start=int(m[1]); end=min(int(m[2]) if m[2] else size-1,size-1); status=206
                        if start>end: return self.send(416,{'error':'Invalid range.'})
                    self.send_response(status); self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(end-start+1)); self.send_header('Accept-Ranges','bytes'); self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(name))
                    if status==206: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers()
                    with file.open('rb') as stream:
                        stream.seek(start); left=end-start+1
                        while left:
                            chunk=stream.read(min(left,256*1024))
                            if not chunk: break
                            self.wfile.write(chunk); left-=len(chunk)
                    return
            if path in ('/api/lab/encrypt','/api/lab/decrypt') and self.command=='POST':
                key=self.headers.get('X-Lab-Key',''); data=self.body(32*1024**2)
                if not data: raise ValueError('Select a local owned-media file.')
                result=lab_encrypt(data,key) if path.endswith('/encrypt') else lab_decrypt(data,key)
                name='owned-media.sflab' if path.endswith('/encrypt') else 'owned-media-restored.bin'
                return self.send(200,result,'application/octet-stream',{'Content-Disposition':f'attachment; filename="{name}"'})
            raise FileNotFoundError('Route not found.')
        def handle_request(self):
            try: self.dispatch()
            except (BrokenPipeError,ConnectionResetError): pass
            except FileNotFoundError as e: self.send(404,{'error':str(e)})
            except (ValueError,TypeError,KeyError,OverflowError) as e: self.close_connection=True; self.send(400,{'error':sanitize_error(e)})
            except Exception: self.close_connection=True; self.send(500,{'error':'Operation failed. Check the service health or retry.'})
        do_GET=handle_request
        do_POST=handle_request
    return ThreadingHTTPServer((host,port),Handler)


def main():
    password=os.environ.get('STREAMFORGE_PASSWORD','')
    if len(password)<16: sys.exit('Set STREAMFORGE_PASSWORD to a private password of at least 16 characters.')
    app=Application(os.environ.get('STREAMFORGE_DATA','./data'),password)
    server=create_server(app,'127.0.0.1',int(os.environ.get('STREAMFORGE_PORT','8122')),secure_cookie=os.environ.get('STREAMFORGE_SECURE_COOKIE','1')=='1')
    def shutdown(signum,frame):
        app.close(); threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,shutdown); signal.signal(signal.SIGINT,shutdown)
    try: server.serve_forever()
    finally: server.server_close(); app.close()

if __name__=='__main__': main()
