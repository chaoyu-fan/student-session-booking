"""Single-teacher, Chinese-language appointment website. No email required."""
import hmac
import os
import secrets
import threading
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix

from . import schedule, storage

app=Flask(__name__)
if not os.getenv('SESSION_SECRET') or not os.getenv('ADMIN_PASSWORD_HASH'):
    raise RuntimeError('SESSION_SECRET and ADMIN_PASSWORD_HASH are required. Run scripts/init.sh.')
app.secret_key=os.environ['SESSION_SECRET']
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',
                  SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','true').lower()=='true',
                  MAX_CONTENT_LENGTH=8*1024)
# Reverse proxy is controlled by our Compose and only one trusted hop is expected.
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1,x_host=1)
storage.init_db()
VISIT_WINDOWS=defaultdict(list)
VISIT_LOCK=threading.Lock()


def csrf_token():
    if '_csrf' not in session:
        session['_csrf']=secrets.token_urlsafe(32)
    return session['_csrf']

app.jinja_env.globals['csrf_token']=csrf_token


def verify_csrf():
    if not session.get('_csrf') or not request.form.get('csrf') or not hmac.compare_digest(str(session['_csrf']),str(request.form['csrf'])):
        abort(400,'请求已失效，请刷新页面后重试')


def rate_limited():
    ip=request.remote_addr or 'unknown'
    ts=time.monotonic()
    with VISIT_LOCK:
        VISIT_WINDOWS[ip]=[x for x in VISIT_WINDOWS[ip] if ts-x<3600]
        if len(VISIT_WINDOWS[ip])>=30:
            return True
        VISIT_WINDOWS[ip].append(ts)
        return False


def teacher_required(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if session.get('is_teacher') is not True:
            return redirect(url_for('login'))
        return f(*args,**kwargs)
    return wrap


def candidate_days():
    today=schedule.now_local().date()
    end=today+timedelta(days=schedule.HORIZON_DAYS)
    busy=storage.list_events(today.isoformat(),(end+timedelta(days=1)).isoformat())
    result=[]
    for d in (today+timedelta(days=i) for i in range(schedule.HORIZON_DAYS)):
        times=[]
        for s,e in schedule.slots_for_day(d):
            if not any(ev['starts_at']<schedule.fmt(e) and ev['ends_at']>schedule.fmt(s) for ev in busy):
                times.append({'value':schedule.fmt(s),'label':s.strftime('%H:%M')})
        if times:
            result.append({'day':d.isoformat(),'label':f'{d.month}月{d.day}日 · {"一二三四五六日"[d.weekday()]}','times':times})
    return result


@app.get('/healthz')
def health():
    with storage.connect() as db:
        db.execute('SELECT 1').fetchone()
    return {'ok':True,'service':'student-session-booking'}


@app.get('/')
def index():
    return render_template('index.html',days=candidate_days(),access_code=bool(os.getenv('BOOKING_ACCESS_CODE')))


@app.post('/book')
def book():
    verify_csrf()
    if request.form.get('website'):
        abort(400)
    if rate_limited():
        abort(429,'提交过于频繁，请稍后重试')
    code=os.getenv('BOOKING_ACCESS_CODE','')
    if code and not hmac.compare_digest(request.form.get('access_code',''),code):
        flash('预约访问码不正确')
        return redirect(url_for('index'))
    name=request.form.get('name','').strip()
    student_class=request.form.get('student_class','').strip()
    if len(name)<2 or len(name)>30 or len(student_class)>40:
        flash('请填写有效的姓名，班级不能超过 40 字')
        return redirect(url_for('index'))
    try:
        start=datetime.strptime(request.form['starts_at'],'%Y-%m-%dT%H:%M')
    except (ValueError,KeyError):
        abort(400,'请选择有效时段')
    if not schedule.is_valid_slot(start):
        flash('这个时间目前不可预约，请重新选择')
        return redirect(url_for('index'))
    end=start+timedelta(minutes=schedule.SESSION_MINUTES)
    try:
        token=storage.create_event('booking',schedule.fmt(start),schedule.fmt(end),name,student_class)
    except ValueError as ex:
        flash(str(ex))
        return redirect(url_for('index'))
    return redirect(url_for('receipt',token=token),code=303)


@app.get('/receipt/<token>')
def receipt(token):
    record=storage.get_event(token)
    if not record or record['kind']!='booking':
        abort(404)
    return render_template('receipt.html',record=record)


@app.route('/admin/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        verify_csrf()
        if rate_limited():
            abort(429)
        given=request.form.get('password','')
        expected=os.getenv('ADMIN_PASSWORD_HASH','')
        ok=(hmac.compare_digest(request.form.get('username',''),os.getenv('ADMIN_USERNAME','teacher'))
            and check_password_hash(expected,given))
        if ok:
            session.clear()
            session['is_teacher']=True
            session.permanent=False
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误')
    return render_template('login.html')


@app.post('/admin/logout')
@teacher_required
def logout():
    verify_csrf()
    session.clear()
    return redirect(url_for('index'))


@app.get('/admin')
@teacher_required
def dashboard():
    today=schedule.now_local().date()
    rows=storage.list_events(today.isoformat(),(today+timedelta(days=21)).isoformat())
    return render_template('admin.html',events=rows,today=today.isoformat(),day_end=(today+timedelta(days=21)).isoformat())


@app.post('/admin/event')
@teacher_required
def add_event():
    verify_csrf()
    kind=request.form.get('kind','')
    if kind not in ('walkin','block'):
        abort(400)
    try:
        start=datetime.strptime(request.form['starts_at'],'%Y-%m-%dT%H:%M')
        end=datetime.strptime(request.form['ends_at'],'%Y-%m-%dT%H:%M')
    except (KeyError,ValueError):
        flash('时间格式无效')
        return redirect(url_for('dashboard'))
    if end<=start or (end-start)>timedelta(hours=12) or start.date()<schedule.now_local().date()-timedelta(days=1):
        flash('时间范围无效（单次最多 12 小时）')
        return redirect(url_for('dashboard'))
    student=request.form.get('student','').strip()[:30] if kind=='walkin' else ''
    klass=request.form.get('student_class','').strip()[:40] if kind=='walkin' else ''
    try:
        storage.create_event(kind,schedule.fmt(start),schedule.fmt(end),student,klass)
        flash('已添加到日程')
    except ValueError as ex:
        flash(str(ex))
    return redirect(url_for('dashboard'))


@app.post('/admin/cancel/<token>')
@teacher_required
def cancel(token):
    verify_csrf()
    if storage.cancel_event(token):
        flash('已取消该日程；如涉及学生，请通过现有学校渠道通知学生')
    else:
        flash('未找到可取消的日程')
    return redirect(url_for('dashboard'))


@app.after_request
def security_headers(resp):
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['Referrer-Policy']='no-referrer'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Cache-Control']='no-store'
    resp.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; base-uri 'self'; frame-ancestors 'none'"
    return resp


@app.errorhandler(429)
def too_many(err):
    return render_template('error.html',message='操作太频繁，请稍后重试。'),429


@app.errorhandler(400)
def bad(err):
    return render_template('error.html',message='请求无效，请刷新后重试。'),400


@app.errorhandler(404)
def missing(err):
    return render_template('error.html',message='未找到该页面。'),404
