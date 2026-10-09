"""Bounded-memory media relay. Network reads go through Python's SSRF guard.
FFmpeg sees pipes only; no media filename, cache, segment file or output directory.
"""
import json, os, subprocess, sys, threading, urllib.request
from .core import install_network_guard, validate_url

class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def media_chunks(sources,mode,opener=None):
    if mode not in ('video','mp3') or not 1<=len(sources)<=2:
        raise ValueError('Invalid stream selection.')
    opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),PublicRedirect())
    responses=[];pipes=[];threads=[];errors=[];proc=None;stopping=threading.Event()
    try:
        allowed_headers={'user-agent','referer','origin','accept','accept-language'}
        for source in sources:
            if isinstance(source,str):
                url=source; source_headers={}
            elif isinstance(source,dict) and set(source).issubset({'url','headers'}) and isinstance(source.get('url'),str) and isinstance(source.get('headers',{}),dict):
                url=source['url']; source_headers=source.get('headers',{})
            else:
                raise ValueError('Invalid media source.')
            validate_url(url)
            request_headers={'User-Agent':'Mozilla/5.0','Accept-Encoding':'identity'}
            for key,value in source_headers.items():
                if str(key).lower() in allowed_headers and isinstance(value,str) and len(value)<=1000:
                    request_headers[str(key)]=value
            response=opener.open(urllib.request.Request(url,headers=request_headers),timeout=30)
            responses.append(response)
        for _ in responses:pipes.append(os.pipe())
        command=[os.environ.get('FFMPEG_PATH','ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-filter_threads','1']
        for read_fd,_ in pipes:
            command+=['-protocol_whitelist','pipe','-i',f'pipe:{read_fd}']
        if mode=='mp3':
            command+=['-map','0:a:0','-vn','-c:a','libmp3lame','-b:a','192k','-threads','1','-f','mp3','pipe:1']
        else:
            command+=['-map','0:v:0','-map',('1:a:0' if len(pipes)==2 else '0:a:0?'),'-c:v','copy','-c:a','aac','-b:a','192k','-threads','1','-movflags','frag_keyframe+empty_moov+default_base_moof','-f','mp4','pipe:1']
        proc=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,pass_fds=[r for r,w in pipes],bufsize=0)
        for r,w in pipes:os.close(r)
        def feed(response,fd):
            try:
                expected=response.headers.get('Content-Length');received=0
                with os.fdopen(fd,'wb',buffering=0) as sink:
                    while not stopping.is_set():
                        block=response.read(65536)
                        if not block:break
                        received+=len(block)
                        view=memoryview(block)
                        while view:
                            n=sink.write(view)
                            if not n:raise OSError('Transfer interrupted.')
                            view=view[n:]
                    if expected and not stopping.is_set() and received!=int(expected):raise OSError('Source transfer incomplete.')
            except Exception:
                if not stopping.is_set():
                    errors.append(True)
                    try:proc.terminate()
                    except ProcessLookupError:pass
            finally:response.close()
        for response,(_,fd) in zip(responses,pipes):
            thread=threading.Thread(target=feed,args=(response,fd),daemon=True);thread.start();threads.append(thread)
        while True:
            block=os.read(proc.stdout.fileno(),65536)
            if not block:break
            yield block
        if proc.wait(timeout=10)!=0 or errors:raise ValueError('The source transfer failed. Analyze again and retry.')
    finally:
        stopping.set()
        if proc:
            if proc.poll() is None:
                proc.terminate()
                try:proc.wait(timeout=3)
                except subprocess.TimeoutExpired:proc.kill();proc.wait()
            proc.stdout.close()
        # Once FFmpeg exits, writers unblock. Closing a live HTTP response can
        # block on its reader lock; do not let that hold up cancellation.
        for thread in threads:thread.join(timeout=.1)
        if not threads:
            for response in responses:response.close()
            for r,w in pipes:
                for fd in (r,w):
                    try:os.close(fd)
                    except OSError:pass

def main():
    install_network_guard()
    started=False
    try:
        request=json.load(sys.stdin)
        chunks=media_chunks(request['sources'],request['mode'])
        first=next(chunks)
        sys.stdout.buffer.write(b'{"ready":true}\n');started=True
        sys.stdout.buffer.write(first);sys.stdout.buffer.flush()
        for block in chunks:sys.stdout.buffer.write(block);sys.stdout.buffer.flush()
    except Exception:
        if not started:
            sys.stdout.buffer.write(b'{"ready":false,"error":"This source could not be streamed. Analyze again and retry."}\n');sys.stdout.buffer.flush()
        sys.exit(1)

if __name__=='__main__':main()
