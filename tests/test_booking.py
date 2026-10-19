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
        s='2030-05-06T11:00'; e='2030-05-06T11:50'
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
        storage.create_event('booking','2030-05-06T11:00','2030-05-06T11:50','测试')
        with self.assertRaises(ValueError):
            storage.create_event('walkin','2030-05-06T11:30','2030-05-06T12:20','测试二')
        storage.create_event('block','2030-05-06T11:50','2030-05-06T12:10')

    def test_cancel_releases_slot(self):
        token=storage.create_event('booking','2030-05-06T11:00','2030-05-06T11:50','测试')
        self.assertTrue(storage.cancel_event(token))
        storage.create_event('booking','2030-05-06T11:00','2030-05-06T11:50','测试二')

    def test_school_schedule_requires_confirmation(self):
        storage.save_school_schedule(self.periods,{(0,2):'初一(8)'},False)
        self.assertFalse(storage.school_snapshot()['confirmed'])
        with self.assertRaisesRegex(ValueError, '尚未核对'):
            storage.create_event('booking','2030-05-06T16:30','2030-05-06T17:20','测试')

    def test_teacher_class_blocks_recurring_booking_and_walkin(self):
        storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        # May 6, 2030 is a Monday. Period 3: 10:15-11:00; no extra buffer.
        self.assertEqual(__import__('datetime').date(2030,5,6).weekday(),0)
        with self.assertRaisesRegex(ValueError, '固定授课'):
            storage.create_event('booking','2030-05-06T10:50','2030-05-06T11:40','测试')
        with self.assertRaisesRegex(ValueError, '固定授课'):
            storage.create_event('walkin','2030-05-13T10:10','2030-05-13T10:30','测试')
        storage.create_event('booking','2030-05-06T16:30','2030-05-06T17:20','测试')

    def test_reject_course_edit_conflicting_with_existing_appointment(self):
        storage.create_event('booking','2030-05-06T10:50','2030-05-06T11:40','测试')
        with self.assertRaisesRegex(ValueError,'已确认'):
            storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        self.assertEqual(storage.school_snapshot()['lessons'],{(0,1):'测试课堂'})

    def test_student_candidate_excludes_class_intervals(self):
        storage.save_school_schedule(self.periods,{(0,3):'初二(9)'},True)
        now=__import__('datetime').datetime(2030,5,6,8,0)
        spans=schedule.slots_for_day(now.date(),now)
        self.assertFalse(any(s.hour==10 for s,e in spans))
        self.assertTrue(any(s.hour==16 for s,e in spans))

    def test_exact_bell_times_and_exercise(self):
        snap=storage.school_snapshot()
        self.assertEqual([(p['starts_at'], p['ends_at']) for p in snap['periods']], [
            ('08:00','08:45'),('09:00','09:45'),('10:15','11:00'),('11:15','12:00'),
            ('14:00','14:45'),('15:00','15:45'),('16:00','16:45'),('16:55','17:35')])
        self.assertEqual(snap['exercise']['starts_at'], '09:45')
        self.assertEqual(snap['exercise']['ends_at'], '10:15')
        self.assertEqual(snap['exercise']['enabled'], 1)
        self.assertEqual(__import__('datetime').datetime.strptime('17:35','%H:%M')-__import__('datetime').datetime.strptime('16:55','%H:%M'), timedelta(minutes=40))

    def test_exercise_blocks_even_if_teacher_has_no_class(self):
        storage.save_school_schedule(self.periods,{(0,1):'测试课堂'},True)
        with self.assertRaisesRegex(ValueError, '课间操'):
            storage.create_event('booking','2030-05-06T09:35','2030-05-06T10:25','测试')
        with self.assertRaisesRegex(ValueError, '课间操'):
            storage.create_event('walkin','2030-05-13T10:05','2030-05-13T10:25','测试')
        now=__import__('datetime').datetime(2030,5,6,7,0)
        slots=schedule.slots_for_day(now.date(),now)
        self.assertFalse(any(s < __import__('datetime').datetime(2030,5,6,10,15) and e > __import__('datetime').datetime(2030,5,6,9,45) for s,e in slots))
        self.assertTrue(any(s.hour==11 for s,e in slots))

    def test_eighth_period_is_forty_minute_afterschool_only_when_assigned(self):
        storage.save_school_schedule(self.periods,{(1,8):'测试课后服务'},True)
        with self.assertRaisesRegex(ValueError,'固定授课'):
            storage.create_event('walkin','2030-05-07T17:00','2030-05-07T17:20','测试')
        # On Wednesday, the teacher has no 8th-period lesson.
        storage.create_event('walkin','2030-05-08T17:00','2030-05-08T17:20','测试')

    def test_migration_only_replaces_legacy_unconfirmed_bell_template(self):
        with storage.connect() as db:
            for i,(begin,end) in enumerate(storage.REFERENCE_BELLS,1):
                db.execute('UPDATE school_periods SET starts_at=?,ends_at=? WHERE period=?',(begin,end,i))
        storage.init_db()
        # This setUp activated the timetable; active custom times MUST NOT be overwritten.
        self.assertEqual(storage.school_snapshot()['periods'][1]['ends_at'],'09:35')
        storage.pause_school_bookings()
        storage.init_db()
        self.assertEqual(storage.school_snapshot()['periods'][1]['ends_at'],'09:45')

    def test_exercise_change_does_not_replace_confirmed_booking(self):
        storage.save_school_schedule(self.periods,{(0,1):'测试课堂'},True,exercise_enabled=False)
        storage.create_event('booking','2030-05-06T09:30','2030-05-06T10:20','测试')
        with self.assertRaisesRegex(ValueError,'已确认'):
            storage.save_school_schedule(self.periods,{(0,1):'测试课堂'},True,
                                         exercise=('09:45','10:15'), exercise_enabled=True)
        self.assertEqual(storage.school_snapshot()['exercise']['enabled'],0)

    def test_schedule(self):
        now=schedule.now_local()
        future=now.date()+timedelta(days=5)
        self.assertTrue(all(e>s for s,e in schedule.slots_for_day(future,now)))
        self.assertFalse(schedule.is_valid_slot(now-timedelta(days=10),now))




class PhotoPresetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        storage.DB_PATH = self.tmp.name + '/photo.sqlite3'
        storage.init_db()

    def tearDown(self):
        self.tmp.cleanup()

    def test_auto_activate_and_exact_22_lessons(self):
        snap = storage.school_snapshot()
        self.assertTrue(snap['confirmed'])
        self.assertEqual(len(snap['lessons']), 22)
        self.assertEqual([sum(day == d for day, period in snap['lessons']) for d in range(5)], [6,5,6,2,3])
        self.assertEqual(set(snap['lessons']), set(storage.photo_lessons()))
        self.assertEqual(snap['exercise']['enabled'], 1)
        self.assertEqual(snap['periods'][7]['starts_at'], '16:55')
        self.assertEqual(snap['periods'][7]['ends_at'], '17:35')

    def test_daily_window_and_photo_conflicts(self):
        from datetime import datetime
        self.assertEqual(schedule.SESSION_MINUTES, 50)
        self.assertEqual(schedule.SLOT_MINUTES, 15)
        self.assertEqual(schedule.WINDOWS, [('10:00','17:35')])
        # Monday 2030-05-06: period 2 blocks 09:00–09:45.
        monday = datetime(2030,5,6,4,0)
        slots = schedule.slots_for_day(monday.date(), monday)
        self.assertFalse(any(s.hour < 10 for s,e in slots))
        self.assertIn(('16:45','17:35'), [(s.strftime('%H:%M'),e.strftime('%H:%M')) for s,e in slots])
        self.assertFalse(any(s < datetime(2030,5,6,9,45) and e > datetime(2030,5,6,9,0) for s,e in slots))
        self.assertTrue(all(s >= datetime(2030,5,6,10) and e <= datetime(2030,5,6,17,35) for s,e in slots))
        self.assertTrue(all(not (s < datetime(2030,5,6,10,15) and e > datetime(2030,5,6,9,45)) for s,e in slots))

    def test_lunch_available_on_free_day(self):
        from datetime import datetime
        thursday = datetime(2030,5,9,7)
        slots = schedule.slots_for_day(thursday.date(), thursday)
        self.assertTrue(any(s.hour==12 for s,e in slots))
        self.assertTrue(any(s.hour==13 for s,e in slots))
        self.assertIn(('10:15','11:05'),[(s.strftime('%H:%M'),e.strftime('%H:%M')) for s,e in slots])
        self.assertFalse(schedule.is_valid_slot(datetime(2030,5,9,9,30),thursday))

    def test_idempotent_and_preserves_custom_schedule(self):
        storage.init_db()
        self.assertEqual(len(storage.school_snapshot()['lessons']),22)
        storage.save_school_schedule(storage.DEFAULT_BELLS, {(0, 1): '自定义课程'}, True)
        storage.init_db()
        self.assertEqual(storage.school_snapshot()['lessons'],{(0,1):'自定义课程'})

    def test_force_preset_conflict_rejected(self):
        storage.save_school_schedule(storage.DEFAULT_BELLS, {(0,1):'自定义课程'}, True)
        storage.create_event('booking','2030-05-06T10:20','2030-05-06T11:10','测试')
        with self.assertRaisesRegex(ValueError,'已确认'):
            storage.save_school_schedule(storage.DEFAULT_BELLS, storage.photo_lessons(), True,
                                         exercise=storage.DEFAULT_EXERCISE, exercise_enabled=True)
        self.assertEqual(storage.school_snapshot()['lessons'],{(0,1):'自定义课程'})


if __name__=='__main__': unittest.main()
