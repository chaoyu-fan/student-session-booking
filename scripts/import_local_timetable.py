#!/usr/bin/env python3
"""Import teacher timetable from a private JSON file on the server.

JSON: {"periods": [["08:00","08:40"],...eight],
       "lessons": [{"weekday":0,"period":2,"class_name":"初一(8)"},...]}
Defaults to a draft; requires --activate to open student online booking.
"""
import argparse
import json
from pathlib import Path
from app import storage

parser=argparse.ArgumentParser()
parser.add_argument('file',type=Path)
parser.add_argument('--activate',action='store_true')
args=parser.parse_args()
obj=json.loads(args.file.read_text(encoding='utf-8'))
lessons={(int(row['weekday']),int(row['period'])):str(row['class_name'])
         for row in obj['lessons']}
storage.init_db()
storage.save_school_schedule(obj['periods'],lessons,args.activate,
                             exercise=tuple(obj['exercise']) if 'exercise' in obj else None)
print('学校课表已导入。状态：' + ('已确认启用' if args.activate else '草稿；学生预约暂停'))
