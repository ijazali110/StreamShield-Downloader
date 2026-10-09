"""Run on the VPS as an operator, without printing the dashboard password."""
import http.cookiejar, urllib.request, urllib.error, json, time
from pathlib import Path
BASE='https://tool.vieapps.cloud/streamforge/'
env=dict(line.split('=',1) for line in Path('/etc/streamforge3.env').read_text().splitlines() if '=' in line)
client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf=''
def request(path,body=None,raw=None,headers=None):
    h={'X-CSRF-Token':csrf}; h.update(headers or {})
    if body is not None: raw=json.dumps(body).encode();h['Content-Type']='application/json'
    return client.open(urllib.request.Request(BASE+path,data=raw,headers=h),timeout=100)
def api(path,body=None):
    with request(path,body) as r: return json.load(r)
login=api('api/login',{'password':env['STREAMFORGE_PASSWORD']});csrf=login['csrf']
print('HTTPS private login: PASS')
protected=api('api/analyze',{'url':BASE+'test/protected.mpd'})
assert protected['protection']=='Widevine Protected' and not protected['downloadable'],protected
print('Protected manifest inspection: PASS')
mp4=api('api/analyze',{'url':BASE+'test/demo.mp4'})
assert mp4['downloadable'] and mp4['formats'],mp4
hls=api('api/analyze',{'url':BASE+'test/master.m3u8'})
assert hls['downloadable'] and {f['height'] for f in hls['formats']}=={360,720},hls
print('MP4 and HLS 360p/720p analysis: PASS')
job=api('api/jobs',{'url':mp4['url'],'title':'Verified MP4 · resume test','rate_kbps':64})
end=time.time()+60;paused=False
while time.time()<end:
    current=next(j for j in api('api/jobs') if j['id']==job['id'])
    if current['status']=='failed':raise AssertionError(current)
    if current['status']=='downloading' and current['progress'].get('downloaded',0)>0:
        api('api/jobs/'+job['id']+'/pause',{});paused=True;break
    time.sleep(.4)
assert paused,'Could not reach a resumable downloading state'
assert next(j for j in api('api/jobs') if j['id']==job['id'])['status']=='paused'
api('api/jobs/'+job['id']+'/retry',{})
print('Pause and retry/resume: PASS')
hlsjob=api('api/jobs',{'url':hls['url'],'title':'Verified HLS · 720p test','format_id':next(f['id'] for f in hls['formats'] if f['height']==720)})
for target in (job,hlsjob):
    end=time.time()+100
    while time.time()<end:
        state=next(j for j in api('api/jobs') if j['id']==target['id'])
        if state['status'] in ('completed','failed'):break
        time.sleep(.5)
    assert state['status']=='completed',state
    media=next(f for f in state['files'] if f['name'].endswith('.mp4'))
    with request('api/jobs/'+target['id']+'/files/'+urllib.parse.quote(media['name'])) as r: data=r.read()
    assert len(data)==media['bytes'] and b'ftyp' in data[:40]
    with request('api/jobs/'+target['id']+'/files/'+urllib.parse.quote(media['name']),headers={'Range':'bytes=0-31'}) as r: assert r.status==206 and len(r.read())==32
print('Final MP4 save and Range downloads (direct + HLS): PASS')
key='12'*32;payload=b'StreamForge owned-media educational test'
with request('api/lab/encrypt',raw=payload,headers={'X-Lab-Key':key}) as r: encrypted=r.read()
with request('api/lab/decrypt',raw=encrypted,headers={'X-Lab-Key':key}) as r: assert r.read()==payload
try:
    request('api/lab/decrypt',raw=encrypted,headers={'X-Lab-Key':'34'*32})
    raise AssertionError('Wrong key accepted')
except urllib.error.HTTPError as e: assert e.code==400
print('Owned-media encryption, authenticated restore, wrong-key rejection: PASS')
print('Verified job IDs:',job['id'],hlsjob['id'])
