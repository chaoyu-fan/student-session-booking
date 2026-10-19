#!/usr/bin/env python3
"""One-command import of the photograph-based weekly schedule for older deployments.

Run only after taking a database backup. If a confirmed appointment overlaps a
new teaching period, the transaction is rejected without changing the schedule.
"""
from app import storage

if __name__ == '__main__':
    storage.init_db()
    storage.save_school_schedule(storage.DEFAULT_BELLS, storage.photo_lessons(), True,
                                 exercise=storage.DEFAULT_EXERCISE, exercise_enabled=True)
    print('已启用照片课表：22节固定课，10:00–17:35学生预约窗口由.env控制（代码仍强制不早于10:00）。')
