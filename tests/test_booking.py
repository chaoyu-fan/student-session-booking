import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app import schedule
from app import storage


class BookingStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        storage.DB_PATH = self.temp.name + '/test.sqlite3'
        storage.init_db()
    def tearDown(self):
        self.temp.cleanup()

    def test_double_booking_serialized(self):
        s='2030-05-06T10:00'; e='2030-05-06T10:50'
        def book_one(_):
            try:
                storage.create_event('booking',s,e,'测试学生')
                return 'ok'
            except ValueError:
                return 'blocked'
        with ThreadPoolExecutor(max_workers=4) as pool:
            results=list(pool.map(book_one,range(4)))
        self.assertEqual(results.count('ok'),1)
        self.assertEqual(results.count('blocked'),3)

    def test_partial_overlap_rejected(self):
        storage.create_event('booking','2030-05-06T10:00','2030-05-06T10:50','测试')
        with self.assertRaises(ValueError):
            storage.create_event('walkin','2030-05-06T10:30','2030-05-06T11:20','测试二')
        storage.create_event('block','2030-05-06T10:50','2030-05-06T11:10')

    def test_cancel_releases_slot(self):
        token=storage.create_event('booking','2030-05-06T10:00','2030-05-06T10:50','测试')
        self.assertTrue(storage.cancel_event(token))
        storage.create_event('booking','2030-05-06T10:00','2030-05-06T10:50','测试二')

    def test_schedule(self):
        now=schedule.now_local()
        future=now.date()+timedelta(days=5)
        self.assertTrue(all(e>s for s,e in schedule.slots_for_day(future,now)))
        self.assertFalse(schedule.is_valid_slot(now-timedelta(days=10),now))


if __name__=='__main__': unittest.main()
