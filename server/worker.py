"""Isolated network-facing extractor/downloader. Input and output are JSON lines."""
from __future__ import annotations
import json, os, re, sys, shutil, urllib.request, urllib.parse, html
from pathlib import Path
from .extractor_compat import create_downloader
from .sources import policy_report
from .core import install_network_guard, validate_url, inspect_manifest, sanitize_error


def emit(payload):
    print(json.dumps(payload,ensure_ascii=False),flush=True)

class QuietLogger:
    def debug(self,msg): pass
    def info(self,msg): pass
    def warning(self,msg): pass
    def error(self,msg): pass


def fetch_small(url,headers):
    validate_url(url)
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 StreamForge/3.0',**headers})
    with urllib.request.urlopen(req,timeout=25) as response:
        content=response.read(2*1024*1024+1)
        if len(content)>2*1024*1024: raise ValueError('Manifest/page exceeds inspection size limit.')
        return content.decode('utf-8',errors='replace'),response.headers.get('Content-Type','')


def manifest_status(url,headers):
    body,mime=fetch_small(url,headers)
    if body.lstrip().startswith('#EXTM3U') or '<MPD' in body or '<mpd' in body:
        return inspect_manifest(body,url)
    return None


def analyze(url,headers):
    import yt_dlp
    validate_url(url)
    policy=policy_report(url)
    if policy:return policy
    p=urllib.parse.urlsplit(url)
    manifest=None
    # All HLS/DASH candidates are inspected before they can be downloadable.
    if p.path.lower().endswith(('.m3u8','.mpd')):
        manifest=manifest_status(url,headers)
        if manifest and manifest['protection']!='Clear':
            return {'title':Path(p.path).name,'url':url,'formats':[], 'subtitles':[], 'duration':None,'protection':manifest['protection'],'manifest':manifest,'is_live':manifest['live'],'source':p.hostname,'downloadable':False}
    opts={'quiet':True,'no_warnings':True,'skip_download':True,'noplaylist':True,'playlist_items':'1','socket_timeout':25,'retries':1,'logger':QuietLogger(),'http_headers':headers,'cachedir':False,'allow_unplayable_formats':True}
    try:
        if shutil.which('node'):opts['js_runtimes']={'node':{}}
        with create_downloader(opts) as ydl: info=ydl.extract_info(url,download=False)
    except Exception as original:
        if p.path.lower().endswith(('.m3u8','.mpd','.mp4','.webm','.mp3','.m4a','.mov')):
            raise ValueError(sanitize_error(original)) from original
        if re.search(r'(?i)cloudflare|anti-bot|captcha|HTTP Error (?:403|429)',str(original)):
            raise ValueError(sanitize_error(original)) from original
        try: body,mime=fetch_small(url,headers)
        except Exception: raise ValueError(sanitize_error(original)) from original
        candidates=[]
        for candidate in re.findall(r'''(?:src|href)\s*=\s*["']([^"']+)["']''',body,re.I):
            if re.search(r'\.(mp4|webm|m3u8|mpd|mp3|m4a)(?:[?#]|$)',candidate,re.I):
                candidate=urllib.parse.urljoin(url,html.unescape(candidate))
                if candidate not in candidates: candidates.append(candidate)
        if candidates:
            results=[]
            for candidate in candidates[:8]:
                try: results.append(analyze(candidate,headers))
                except Exception: pass
            if results: return {'candidates':results,'page_url':url,'title':'Embedded media'}
        raise ValueError(sanitize_error(original))
    if not isinstance(info,dict): raise ValueError('No media detected.')
    if info.get('_type') in ('playlist','multi_video'):
        entries=[e for e in info.get('entries',[]) if isinstance(e,dict)]
        if not entries: raise ValueError('No media in this playlist.')
        info=entries[0]
    formats=[]; protection='Clear'; manifests={}
    for f in info.get('formats') or ([info] if info.get('url') else []):
        if not f.get('url','').startswith(('http://','https://')): continue
        protocol=str(f.get('protocol',''))
        mu=f.get('manifest_url') or (f['url'] if 'm3u8' in protocol or 'dash' in protocol else '')
        if f.get('has_drm'): protection='DRM Protected'
        if mu:
            if mu not in manifests:
                try:
                    manifest_headers={**(info.get('http_headers') or {}),**(f.get('http_headers') or {}),**headers}
                    manifests[mu]=manifest_status(mu,manifest_headers)
                except Exception: manifests[mu]={'protection':'Protection Unknown','tracks':[],'protocol':'Unknown','live':False}
            status=manifests[mu]
            if status and status['protection']!='Clear': protection=status['protection']
        raw_headers={**(info.get('http_headers') or {}),**(f.get('http_headers') or {}),**headers}
        allowed_headers={'user-agent','referer','origin','accept','accept-language'}
        safe_headers={str(k):str(v)[:1000] for k,v in raw_headers.items() if str(k).lower() in allowed_headers and isinstance(v,(str,int,float))}
        formats.append({'id':str(f.get('format_id','best')),'height':f.get('height'),'width':f.get('width'),'fps':f.get('fps'),'bitrate':f.get('tbr'),'size':f.get('filesize') or f.get('filesize_approx'),'ext':f.get('ext',''),'video_codec':f.get('vcodec',''),'audio_codec':f.get('acodec',''),'language':f.get('language',''),'protocol':protocol,'url':f['url'],'http_headers':safe_headers,'drm':bool(f.get('has_drm')),'note':f.get('format_note','')})
    subtitles=[]
    for lang,rows in (info.get('subtitles') or {}).items():
        subtitles.append({'language':lang,'formats':sorted({r.get('ext','') for r in rows})})
    return {'title':info.get('title') or 'Media','url':url,'duration':info.get('duration'),'thumbnail':info.get('thumbnail') or '', 'formats':formats,'subtitles':subtitles,'protection':protection,'manifest':manifest or next((m for m in manifests.values() if m),None),'is_live':bool(info.get('is_live')),'source':info.get('extractor_key') or p.hostname,'downloadable':protection=='Clear' and bool(formats)}


def record_live_hls(url,headers,directory,duration,max_bytes,rate_kbps=0):
    """Record clear MPEG-TS HLS via guarded Python requests; remux only local files."""
    import time, subprocess
    start=time.monotonic(); seen=set(); temporary=directory/'live-recording.ts.part'; written=0; segments=0
    while time.monotonic()-start<duration:
        body,_=fetch_small(url,headers); manifest=inspect_manifest(body,url)
        if manifest['protocol']!='HLS': raise ValueError('Live recording currently supports MPEG-TS HLS only.')
        if manifest['protection']!='Clear': raise ValueError('Live source became encrypted; recording stopped.')
        if '#EXT-X-MAP:' in body or '#EXT-X-BYTERANGE:' in body: raise ValueError('Live recording currently supports MPEG-TS HLS only.')
        lines=body.splitlines()
        if '#EXT-X-STREAM-INF:' in body:
            variants=[t for t in manifest['tracks'] if t['kind']=='video' and t.get('url')]
            if not variants: raise ValueError('Live playlist has no media tracks.')
            url=sorted(variants,key=lambda t:t.get('height',0),reverse=True)[0]['url']; continue
        seq_match=re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)',body)
        sequence=int(seq_match[1]) if seq_match else 0
        uris=[line.strip() for line in lines if line.strip() and not line.startswith('#')]
        if not uris: raise ValueError('Live playlist contains no segments.')
        for index,uri in enumerate(uris):
            identity=sequence+index
            if identity in seen: continue
            segment_url=urllib.parse.urljoin(url,uri); validate_url(segment_url)
            req=urllib.request.Request(segment_url,headers={'User-Agent':'Mozilla/5.0 StreamForge/3.0',**headers})
            received=0
            with urllib.request.urlopen(req,timeout=25) as response:
                first=response.read(188)
                if not first or first[0]!=0x47: raise ValueError('Live recording currently supports MPEG-TS HLS only.')
                with temporary.open('ab' if segments else 'wb') as stream:
                    chunk=first
                    while chunk:
                        written+=len(chunk); received+=len(chunk)
                        if written>max_bytes: raise ValueError('Per-job storage limit reached.')
                        stream.write(chunk)
                        if rate_kbps:
                            expected=received/(rate_kbps*1024); elapsed=time.monotonic()-start
                            if expected>elapsed: time.sleep(min(expected-elapsed,2))
                        chunk=response.read(256*1024)
            seen.add(identity); segments+=1
            emit({'event':'progress','status':'downloading','downloaded':written,'total':0,'speed':written/max(time.monotonic()-start,0.1),'eta':max(0,duration-(time.monotonic()-start))})
            if time.monotonic()-start>=duration: break
        if '#EXT-X-ENDLIST' in body: break
        time.sleep(min(1,max(0,duration-(time.monotonic()-start))))
    if not segments: raise ValueError('No live segments recorded.')
    output=directory/'live-recording.mp4'
    remux=subprocess.run([os.environ.get('FFMPEG_PATH','ffmpeg'),'-hide_banner','-loglevel','error','-y','-protocol_whitelist','file,pipe','-i',str(temporary),'-t',str(duration),'-c','copy','-movflags','+faststart',str(output)],capture_output=True,timeout=120)
    if remux.returncode: raise ValueError('Recorded live segments could not be remuxed.')
    temporary.unlink(missing_ok=True)


def download(request):
    import yt_dlp
    url=request['url']; headers=request.get('headers',{})
    info=analyze(url,headers)
    if info.get('candidates'): raise ValueError('Select a detected media URL before downloading.')
    if request.get('_free') and (info.get('is_live') or (info.get('duration') or 0)>1800):raise ValueError('Free downloads support on-demand videos up to 30 minutes.')
    if not info['downloadable']: raise ValueError('Protected, encrypted, or unknown streams are inspection-only.')
    directory=Path(request['directory']).resolve(); directory.mkdir(parents=True,exist_ok=True)
    available={f['id'] for f in info['formats'] if not f['drm']}
    selected=request.get('format_id','best')
    audio=request.get('audio_id','')
    if selected!='best' and selected not in available: raise ValueError('Format is unavailable. Analyze again or choose Best.')
    if audio and audio not in available: raise ValueError('Audio format is unavailable.')
    if selected=='best': selector='bestvideo*[height<=720]+bestaudio/best[height<=720]' if request.get('_free') else 'bestvideo*+bestaudio/best'
    else:
        f=next(f for f in info['formats'] if f['id']==selected)
        if request.get('_free') and (f.get('height') or 0)>720:raise ValueError('Free downloads support up to 720p.')
        selector=selected
        if f['audio_codec']=='none' and f['video_codec']!='none': selector+='+'+(audio or 'bestaudio')
    def progress(data):
        emit({'event':'progress','status':data.get('status'),'downloaded':data.get('downloaded_bytes',0),'total':data.get('total_bytes') or data.get('total_bytes_estimate') or 0,'speed':data.get('speed') or 0,'eta':data.get('eta') or 0,'fragment_index':data.get('fragment_index'),'fragment_count':data.get('fragment_count')})
        current=sum(p.stat().st_size for p in directory.rglob('*') if p.is_file())
        if current>request.get('max_bytes',2*1024**3): raise ValueError('Per-job storage limit reached.')
    opts={'format':selector,'outtmpl':str(directory/'%(title).120B [%(id)s].%(ext)s'),'quiet':True,'no_warnings':True,'logger':QuietLogger(),'noplaylist':True,'cachedir':False,'max_filesize':request.get('max_bytes',2*1024**3),'continuedl':True,'overwrites':False,'socket_timeout':25,'retries':8,'fragment_retries':8,'concurrent_fragment_downloads':4,'http_headers':headers,'progress_hooks':[progress],'merge_output_format':'mp4','ffmpeg_location':os.environ.get('FFMPEG_PATH') or None,'allow_unplayable_formats':False}
    if shutil.which('node'):opts['js_runtimes']={'node':{}}
    opts['hls_prefer_native']=True
    opts['postprocessor_args']={'ffmpeg_i':['-protocol_whitelist','file,pipe']}
    if request.get('rate_kbps'): opts['ratelimit']=request['rate_kbps']*1024
    if request.get('subtitles'):
        opts.update({'writesubtitles':True,'subtitleslangs':request['subtitles'],'subtitlesformat':'vtt/best'})
    if info.get('is_live'):
        duration=request.get('duration_seconds',0)
        if not duration: raise ValueError('Live streams require a recording duration.')
        chosen=next((f for f in info['formats'] if f['id']==selected),None)
        if not chosen: chosen=next((f for f in sorted(info['formats'],key=lambda f:f.get('height') or 0,reverse=True) if 'm3u8' in f['protocol']),None)
        if not chosen or 'm3u8' not in chosen['protocol']: raise ValueError('Live recording currently supports MPEG-TS HLS only.')
        record_live_hls(chosen['url'],headers,directory,duration,request.get('max_bytes',2*1024**3),request.get('rate_kbps',0))
    else:
        with create_downloader(opts) as ydl: ydl.download([url])
    if sum(p.stat().st_size for p in directory.iterdir() if p.is_file())>request.get('max_bytes',2*1024**3):raise ValueError('Per-job storage limit reached.')
    files=[{'name':p.name,'bytes':p.stat().st_size} for p in directory.iterdir() if p.is_file() and p.suffix not in ('.part','.ytdl','.temp')]
    media=[p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in ('.mp4','.webm','.mkv','.mp3','.m4a','.ogg','.wav','.mov','.flv','.ts')]
    if not media: raise ValueError('Download ended without a final media file.')
    import subprocess
    for p in media:
        check=subprocess.run([os.environ.get('FFPROBE_PATH','ffprobe'),'-v','error','-protocol_whitelist','file,pipe','-show_entries','format=duration','-of','json',str(p)],capture_output=True,text=True,timeout=30)
        if check.returncode: raise ValueError('Downloaded file failed media validation.')
    emit({'event':'done','files':files,'title':info['title']})


def main():
    request=json.loads(sys.stdin.readline())
    install_network_guard()
    try:
        if request['action']=='analyze': emit({'event':'analysis','result':analyze(request['url'],request.get('headers',{}))})
        else: download(request)
    except Exception as exc:
        emit({'event':'error','message':sanitize_error(exc)})
        sys.exit(1)

if __name__=='__main__': main()
