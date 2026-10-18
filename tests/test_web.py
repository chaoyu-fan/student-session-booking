"""HTTP integration tests run when Flask dependencies are installed."""
import importlib.util
import os
import secrets
import tempfile
import unittest
from datetime import datetime

FLASK_PRESENT=importlib.util.find_spec('flask') is not None

@unittest.skipUnless(FLASK_PRESENT,'Flask not installed in offline authoring runtime; GitHub CI installs requirements')
class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import werkzeug.security
        os.environ['SESSION_SECRET']=secrets.token_hex(32)
        os.environ['ADMIN_PASSWORD_HASH']=werkzeug.security.generate_password_hash('TestSecretJustForTests')
        os.environ['COOKIE_SECURE']='false'
        os.environ['BOOKING_ACCESS_CODE']=''
        from app import web
        cls.web=web

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.web.storage.DB_PATH=self.tmp.name+'/db.sqlite3'
        self.web.storage.init_db()
        periods=[(p['starts_at'],p['ends_at']) for p in self.web.storage.school_snapshot()['periods']]
        self.web.storage.save_school_schedule(periods,{(0,1):'测试课堂'},True)
        self.client=self.web.app.test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_student_booking_and_receipt(self):
        page=self.client.get('/')
        self.assertEqual(page.status_code,200)
        self.assertIn('预约会谈时间'.encode(),page.data)
        with self.client.session_transaction() as sess: csrf=sess['_csrf']
        start=self.web.candidate_days()[0]['times'][0]['value']
        post=self.client.post('/book',data={'csrf':csrf,'starts_at':start,'name':'测试学生','student_class':'示例班'})
        self.assertEqual(post.status_code,303)
        receipt=self.client.get(post.location)
        self.assertIn('预约成功'.encode(),receipt.data)
        self.assertNotIn('测试学生'.encode(),self.client.get('/').data)
        duplicate=self.client.post('/book',data={'csrf':csrf,'starts_at':start,'name':'其他学生'})
        self.assertEqual(duplicate.status_code,302)
        self.assertEqual(len(self.web.storage.list_events(start[:10],start[:10]+'Z')),1)

    def test_csrf_and_teacher(self):
        self.assertIn(self.client.get('/admin').status_code,(301,302))
        self.assertEqual(self.client.post('/book',data={'name':'测试学生'}).status_code,400)
        login=self.client.get('/admin/login')
        with self.client.session_transaction() as sess: csrf=sess['_csrf']
        response=self.client.post('/admin/login',data={'csrf':csrf,'username':'teacher','password':'TestSecretJustForTests'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/admin').status_code,200)
