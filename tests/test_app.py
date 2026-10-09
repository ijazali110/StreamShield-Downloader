import unittest, tempfile, sys, json, threading, urllib.request, urllib.error, http.cookiejar, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.app import Application, create_server

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.app=Application(Path(cls.tmp.name), 'test-password-that-is-long', start_runner=False)
        cls.server=create_server(cls.app, '127.0.0.1',0,secure_cookie=False)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True); cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls): cls.server.shutdown(); cls.server.server_close(); cls.app.close(); cls.tmp.cleanup()
    def client(self): return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def req(self,c,path,data=None,csrf=None,method=None):
        headers={'Content-Type':'application/json'}
        if csrf: headers['X-CSRF-Token']=csrf
        r=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
        return c.open(r)
    def login(self,c):
        with self.req(c,'/api/login',{'password':'test-password-that-is-long'}) as r: return json.load(r)['csrf']
    def test_jobs_require_login(self):
        with self.assertRaises(urllib.error.HTTPError) as e: self.req(self.client(),'/api/jobs')
        self.assertEqual(e.exception.code,401)
    def test_login_wrong_password(self):
        with self.assertRaises(urllib.error.HTTPError) as e: self.req(self.client(),'/api/login',{'password':'bad'})
        self.assertEqual(e.exception.code,401)
    def test_mutation_requires_csrf(self):
        c=self.client(); self.login(c)
        with self.assertRaises(urllib.error.HTTPError) as e: self.req(c,'/api/jobs',{'url':'https://example.org/v.mp4'})
        self.assertEqual(e.exception.code,403)
    def test_private_download_rejected(self):
        c=self.client(); token=self.login(c)
        with self.assertRaises(urllib.error.HTTPError) as e: self.req(c,'/api/jobs',{'url':'http://127.0.0.1/'},token)
        self.assertEqual(e.exception.code,400)
    def test_schedule_and_report_redaction(self):
        c=self.client(); token=self.login(c)
        with self.req(c,'/api/jobs',{'url':'https://example.org/v.mp4?token=SUPERSECRET','scheduled_at':time.time()+3600},token) as r: job=json.load(r)
        with self.req(c,f'/api/jobs/{job["id"]}/report') as r: report=r.read().decode()
        self.assertNotIn('SUPERSECRET',report)
        self.assertIn('queued',report)
    def test_lab_known_format_only(self):
        c=self.client(); token=self.login(c)
        with self.assertRaises(urllib.error.HTTPError) as e:
            c.open(urllib.request.Request(self.base+'/api/lab/decrypt',data=b'arbitrary third party encrypted video',headers={'X-CSRF-Token':token,'X-Lab-Key':'00'*32},method='POST'))
        self.assertEqual(e.exception.code,400)
    def test_queue_recovered_as_paused(self):
        self.app.db_write("UPDATE jobs SET status='downloading' WHERE status='queued'")
        other=Application(Path(self.tmp.name),'test-password-that-is-long',start_runner=False)
        self.assertFalse(any(j['status']=='downloading' for j in other.jobs()))
        other.close()

if __name__=='__main__': unittest.main()
