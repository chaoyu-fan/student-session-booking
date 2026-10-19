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
        self.assertEqual([(s.strftime('%H:%M'),e.strftime('%H:%M')) for s,e in slots
                          if s.hour<10], [('09:50','10:10')])
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
        self.assertEqual(schedule.WINDOWS, [('10:00','17:35')])
        monday = datetime(2030,5,6,4,0)
        slots = schedule.slots_for_day(monday.date(), monday)
        # Monday regular periods 3-7 are taught, but the 20m emergency and
        # 40m period-8 service are explicit schedule exceptions.
        self.assertEqual([(s.strftime('%H:%M'),e.strftime('%H:%M')) for s,e in slots],
                         [('09:50','10:10'),('16:55','17:35')])
        self.assertFalse(schedule.is_valid_slot(datetime(2030,5,6,16,45),monday))
        self.assertFalse(schedule.is_valid_slot(datetime(2030,5,6,8,0),monday))

    def test_only_free_bell_periods_are_offered(self):
        from datetime import datetime, date
        actual = []
        for day in range(5):
            d = date(2030,5,6) + timedelta(days=day)
            slots=schedule.slots_for_day(d, datetime(2030,5,6,4,0))
            times=[(s.strftime('%H:%M'),e.strftime('%H:%M')) for s,e in slots]
            actual.append(times)
            for start,end in slots:
                duration = 20 if start.strftime('%H:%M')=='09:50' else 40 if start.strftime('%H:%M')=='16:55' else 50
                self.assertEqual(end-start, timedelta(minutes=duration))
                self.assertLessEqual(end.strftime('%H:%M'),'17:35')
        self.assertEqual(actual, [
            [('09:50','10:10'),('16:55','17:35')],
            [('09:50','10:10'),('11:15','12:05'),('16:00','16:50')],
            [('09:50','10:10'),('16:55','17:35')],
            [('09:50','10:10'),('10:15','11:05'),('11:15','12:05'),('15:00','15:50'),('16:55','17:35')],
            [('10:15','11:05'),('11:15','12:05'),('16:55','17:35')],
        ])
        self.assertNotIn(('16:55','17:35'),actual[1])  # Tuesday 8th is taught
        self.assertFalse(any(start=='09:50' for start,end in actual[4]))  # Friday no emergency
        self.assertFalse(any(start.startswith('12:') or start.startswith('13:') for daily in actual for start,end in daily))

    def test_emergency_exercise_override_but_still_checks_actual_lessons(self):
        from datetime import datetime
        first=datetime(2030,5,6,7,0) # Monday
        self.assertTrue(schedule.is_valid_slot(datetime(2030,5,6,9,50),first))
        token=storage.create_event('booking','2030-05-06T09:50','2030-05-06T10:10','测试学生',
                                   topic='情绪低落',session_type='emergency')
        record=storage.get_event(token)
        self.assertEqual(record['topic'],'情绪低落')
        self.assertEqual(record['session_type'],'emergency')
        with self.assertRaisesRegex(ValueError,'刚刚被预约'):
            storage.create_event('booking','2030-05-06T09:50','2030-05-06T10:10','其他学生',
                                 topic='其他',session_type='emergency')
        # Editing unrelated teaching periods should preserve a booked emergency.
        storage.save_school_schedule(storage.DEFAULT_BELLS,storage.photo_lessons(),True,
                                     exercise_enabled=True)
        with self.assertRaisesRegex(ValueError,'已确认'):
            storage.save_school_schedule(storage.DEFAULT_BELLS[:1]+[('09:00','10:00')]+storage.DEFAULT_BELLS[2:],
                                         storage.photo_lessons(),True,exercise_enabled=True)

    def test_emergency_is_specific_and_regular_exercise_remains_blocked(self):
        with self.assertRaisesRegex(ValueError,'紧急咨询仅开放'):
            storage.create_event('booking','2030-05-10T09:50','2030-05-10T10:10','测试',
                                 session_type='emergency')
        with self.assertRaisesRegex(ValueError,'课间操'):
            storage.create_event('booking','2030-05-06T09:50','2030-05-06T10:10','测试',
                                 session_type='regular')
        with self.assertRaisesRegex(ValueError,'无效咨询主题'):
            storage.create_event('booking','2030-05-07T11:15','2030-05-07T12:05','测试',topic='随意描述')

    def test_after_school_can_book_only_if_not_taught(self):
        from datetime import datetime
        monday=datetime(2030,5,6,7)
        self.assertTrue(schedule.is_valid_slot(datetime(2030,5,6,16,55),monday))
        self.assertFalse(schedule.is_valid_slot(datetime(2030,5,7,16,55),monday))
        token=storage.create_event('booking','2030-05-06T16:55','2030-05-06T17:35','测试',
                                   topic='学习焦虑',session_type='after_school')
        self.assertEqual(storage.get_event(token)['ends_at'],'2030-05-06T17:35')
        with self.assertRaisesRegex(ValueError,'刚刚被预约'):
            storage.create_event('walkin','2030-05-06T17:10','2030-05-06T17:25','测试')

    def test_migration_of_existing_events_adds_topic_and_type(self):
        import sqlite3
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            storage.DB_PATH=tmp+'/legacy.sqlite3'
            with sqlite3.connect(storage.DB_PATH) as db:
                db.execute("CREATE TABLE events (id TEXT PRIMARY KEY,kind TEXT NOT NULL,student TEXT, "
                           "student_class TEXT,note TEXT,starts_at TEXT,ends_at TEXT,status TEXT,created_at TEXT)")
                db.execute("INSERT INTO events VALUES ('old1','booking','旧学生','','', '2030-05-06T11:15', '2030-05-06T12:05','active','2029-01-01')")
            storage.init_db()
            old=storage.get_event('old1')
            self.assertEqual(old['student'],'旧学生')
            self.assertEqual(old['topic'],'')
            self.assertEqual(old['session_type'],'regular')

    def test_teacher_rescheduled_period_changes_student_options(self):
        from datetime import datetime
        periods=storage.DEFAULT_BELLS
        storage.save_school_schedule(periods,{(3,4):'新增课程'},True,exercise_enabled=True)
        thursday=datetime(2030,5,9,7)
        times=[s.strftime('%H:%M') for s,e in schedule.slots_for_day(thursday.date(),thursday)]
        self.assertNotIn('11:15',times)
        self.assertIn('10:15',times)

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
