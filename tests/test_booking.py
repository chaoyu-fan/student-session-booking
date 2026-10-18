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
        self.periods=[(x['starts_at'],x['ends_at']) for x in storage.school_snapshot()['periods']]
        # Pure booking tests start from an explicit confirmed, non-teaching schedule.
        storage.save_school_schedule(self.periods,{(0,1):'测试课堂'},True)
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

    def test_school_schedule_requires_confirmation(self):
        storage.save_school_schedule(self.periods,{(0,2):'初一(8)'},False)
        self.assertFalse(storage.school_snapshot()['confirmed'])
        with self.assertRaisesRegex(ValueError, '尚未核对'):
            storage.create_event('booking','2030-05-06T16:30','2030-05-06T17:20','测试')

    def test_teacher_class_blocks_recurring_booking_and_walkin(self):
        storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        # May 6, 2030 is a Monday. Period 3: 10:05-10:45, +10min buffer.
        self.assertEqual(__import__('datetime').date(2030,5,6).weekday(),0)
        with self.assertRaisesRegex(ValueError, '固定授课'):
            storage.create_event('booking','2030-05-06T10:00','2030-05-06T10:50','测试')
        with self.assertRaisesRegex(ValueError, '固定授课'):
            storage.create_event('walkin','2030-05-13T09:55','2030-05-13T10:15','测试')
        storage.create_event('booking','2030-05-06T16:30','2030-05-06T17:20','测试')

    def test_reject_course_edit_conflicting_with_existing_appointment(self):
        storage.create_event('booking','2030-05-06T10:00','2030-05-06T10:50','测试')
        with self.assertRaisesRegex(ValueError,'已确认'):
            storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        self.assertEqual(storage.school_snapshot()['lessons'],{(0,1):'测试课堂'})

    def test_student_candidate_excludes_class_intervals(self):
        storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        now=__import__('datetime').datetime(2030,5,6,8,0)
        spans=schedule.slots_for_day(now.date(),now)
        self.assertFalse(any(s.hour==10 for s,e in spans))
        self.assertTrue(any(s.hour==16 for s,e in spans))

    def test_schedule(self):
        now=schedule.now_local()
        future=now.date()+timedelta(days=5)
        self.assertTrue(all(e>s for s,e in schedule.slots_for_day(future,now)))
        self.assertFalse(schedule.is_valid_slot(now-timedelta(days=10),now))


if __name__=='__main__': unittest.main()
