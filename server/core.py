from __future__ import annotations
import base64, ipaddress, os, re, socket, urllib.parse, xml.etree.ElementTree as ET
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = '3.5.0'
LAB_MAGIC = b'SF-LAB-GCM-v1\x00'
UUID_NAMES = {'edef8ba9-79d6-4ace-a3c8-27dcd51d21ed':'Widevine', '9a04f079-9840-4286-ab92-e65be0885f95':'PlayReady', '94ce86fb-07ff-4f43-adb8-93d2fa968ca2':'FairPlay', 'e2719d58-a985-b3c9-781a-b030af78d30e':'ClearKey'}

def public_address(value):
    try:
        addr=ipaddress.ip_address(value.split('%')[0])
        if getattr(addr,'ipv4_mapped',None): addr=addr.ipv4_mapped
        return addr.is_global
    except ValueError: return False

def validate_url(value, resolve=True):
    if not isinstance(value,str) or len(value)>8192: raise ValueError('A valid HTTP(S) URL is required.')
    p=urllib.parse.urlsplit(value.strip())
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password:
        raise ValueError('Only public HTTP(S) URLs without embedded credentials are supported.')
    try: port=p.port
    except ValueError: raise ValueError('Invalid URL port.')
    if port not in (None,80,443): raise ValueError('Only standard HTTP(S) ports are supported.')
    try:
        ipaddress.ip_address(p.hostname)
        if not public_address(p.hostname): raise ValueError('Private network URLs are blocked.')
    except ValueError as exc:
        if 'blocked' in str(exc): raise
    if p.hostname.lower() in ('localhost','localhost.localdomain') or p.hostname.endswith(('.local','.internal')):
        raise ValueError('Private network URLs are blocked.')
    if resolve:
        rows=socket.getaddrinfo(p.hostname,port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
        if not rows or any(not public_address(row[4][0]) for row in rows):
            raise ValueError('Private network URLs are blocked.')
    return urllib.parse.urlunsplit(p)

def install_network_guard():
    """Each isolated worker checks every DNS result, including extractor/redirect requests."""
    original=socket.getaddrinfo
    def guarded(host,*args,**kwargs):
        rows=original(host,*args,**kwargs)
        # The yt-dlp PO-token provider is an internal loopback-only dependency.
        # Permit only its exact localhost endpoint; keep every other private target blocked.
        service=args[0] if args else kwargs.get('port')
        if str(host) in ('127.0.0.1','localhost') and str(service)=='4416':
            if all(row[4][0] in ('127.0.0.1','::1') for row in rows):
                return rows
        if any(not public_address(row[4][0]) for row in rows):
            raise OSError('Private network destinations are blocked.')
        return rows
    socket.getaddrinfo=guarded
    # Remove proxy settings inherited from a process environment.
    for name in list(os.environ):
        if name.lower() in ('http_proxy','https_proxy','all_proxy'): os.environ.pop(name,None)

def redact_url(value):
    try:
        p=urllib.parse.urlsplit(value)
        host=p.hostname or ''
        if ':' in host: host='['+host+']'
        if p.port: host+=':'+str(p.port)
        query=urllib.parse.urlencode([(k,'[redacted]') for k,v in urllib.parse.parse_qsl(p.query,keep_blank_values=True)])
        return urllib.parse.urlunsplit((p.scheme,host,p.path,query,''))
    except Exception: return '[redacted URL]'

def sanitize_error(message):
    text=re.sub(r'https?://[^\s<>"\']+',lambda m:redact_url(m.group()),str(message))
    text=re.sub(r'(?i)(authorization|cookie|bearer|password|token)\s*[:=]\s*\S+',r'\1=[redacted]',text)
    # Errors go to a private dashboard, never expose raw server stack traces.
    return text[-1500:]

def attrs(line):
    return {m.group(1):m.group(2) if m.group(2) is not None else m.group(3) for m in re.finditer(r'([A-Z0-9-]+)=(?:"([^"]*)"|([^,]*))',line)}

def inspect_manifest(text,url):
    result={'protocol':'HLS' if text.lstrip().startswith('#EXTM3U') else 'DASH','protection':'Clear','tracks':[],'live':False}
    low=text.lower()
    for uuid,name in UUID_NAMES.items():
        if uuid in low: result['protection']=name+' Protected'; break
    if 'com.apple.streamingkeydelivery' in low or 'skd://' in low: result['protection']='FairPlay Protected'
    elif ('urn:mpeg:dash:mp4protection' in low or 'contentprotection' in low) and result['protection']=='Clear': result['protection']='Encrypted DASH'
    if result['protocol']=='HLS':
        lines=text.splitlines()
        result['live']= '#EXTINF:' in text and '#EXT-X-ENDLIST' not in text
        for i,line in enumerate(lines):
            if line.startswith(('#EXT-X-KEY:','#EXT-X-SESSION-KEY:')):
                a=attrs(line)
                if a.get('METHOD','NONE')!='NONE' and result['protection']=='Clear': result['protection']='Encrypted HLS'
            if line.startswith('#EXT-X-STREAM-INF:'):
                a=attrs(line); next_url=next((x.strip() for x in lines[i+1:] if x.strip() and not x.startswith('#')),'')
                w,h=(a.get('RESOLUTION','0x0').split('x')+['0'])[:2]
                result['tracks'].append({'kind':'video','height':int(h or 0),'width':int(w or 0),'bitrate':int(a.get('BANDWIDTH',0)), 'codec':a.get('CODECS',''),'url':urllib.parse.urljoin(url,next_url)})
            if line.startswith('#EXT-X-MEDIA:'):
                a=attrs(line)
                result['tracks'].append({'kind':a.get('TYPE','').lower(),'language':a.get('LANGUAGE',''),'name':a.get('NAME',''),'url':urllib.parse.urljoin(url,a.get('URI','')) if a.get('URI') else ''})
    else:
        root=ET.fromstring(text)
        result['live']=root.get('type')=='dynamic'
        for adaptation in root.iter():
            if adaptation.tag.split('}')[-1]!='AdaptationSet': continue
            for rep in adaptation:
                if rep.tag.split('}')[-1]!='Representation': continue
                result['tracks'].append({'id':rep.get('id',''),'kind':adaptation.get('contentType') or adaptation.get('mimeType','').split('/')[0], 'height':int(rep.get('height',adaptation.get('height','0'))), 'width':int(rep.get('width',adaptation.get('width','0'))), 'bitrate':int(rep.get('bandwidth','0')), 'codec':rep.get('codecs',adaptation.get('codecs','')), 'language':adaptation.get('lang','')})
    return result

def _lab_key(key_hex):
    try: key=bytes.fromhex(key_hex.strip())
    except (ValueError,AttributeError): raise ValueError('Supply your own 64-character hexadecimal lab key.')
    if len(key)!=32: raise ValueError('Supply your own 64-character hexadecimal lab key.')
    return key

def lab_encrypt(data,key_hex):
    nonce=os.urandom(12)
    return LAB_MAGIC+nonce+AESGCM(_lab_key(key_hex)).encrypt(nonce,data,LAB_MAGIC)

def lab_decrypt(data,key_hex):
    if not data.startswith(LAB_MAGIC) or len(data)<len(LAB_MAGIC)+28:
        raise ValueError('Only files created by the Shield Stream owned-media lab are accepted.')
    nonce=data[len(LAB_MAGIC):len(LAB_MAGIC)+12]
    try: return AESGCM(_lab_key(key_hex)).decrypt(nonce,data[len(LAB_MAGIC)+12:],LAB_MAGIC)
    except Exception: raise ValueError('Key is incorrect or this lab file has been modified.')
