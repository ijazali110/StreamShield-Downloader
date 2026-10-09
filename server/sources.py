"""Provider guidance; service policies are not measured DRM fingerprints."""
from urllib.parse import urlsplit

def portal_policy(url):
    p=urlsplit(url); host=(p.hostname or '').lower()
    def domain(value):return host==value or host.endswith('.'+value)
    if domain('netflix.com'):
        return {'source':'Netflix','official_url':'https://help.netflix.com/en/node/54816','message':'Netflix titles use the official Netflix app for offline downloads. Open the title and tap Download when available. A Netflix Share link does not provide a downloadable movie file.'}
    if domain('primevideo.com') or (domain('amazon.com') and p.path.startswith('/gp/video')):
        return {'source':'Prime Video','official_url':'https://www.primevideo.com/','message':'Use the Download option in the official Prime Video app for eligible titles. A title-page link does not provide an exportable media file.'}
    return None

def policy_report(url):
    policy=portal_policy(url)
    if not policy:return None
    return {'title':policy['source']+' · official offline downloads','source':policy['source'],'url':url,'formats':[],'subtitles':[],'duration':None,'thumbnail':'','protection':'Official app required','downloadable':False,'is_live':False,'manifest':None,'availability':'official_app_only',**policy}
