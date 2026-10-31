"""Editable cashier shift templates. The business date is the LOCAL START DATE.

A shift beginning at 00:00 Cairo on 2026-10-31 is night of 2026-10-31,
not the previous day's evening. This module never mutates old shift dates.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Africa/Cairo')
NAMES = ('night', 'morning', 'evening')
DEFAULT_STARTS = {'night': 0, 'morning': 480, 'evening': 960}


def minutes(hhmm):
    if not isinstance(hhmm, str) or len(hhmm) != 5 or hhmm[2] != ':':
        raise ValueError('Expected HH:MM in 24-hour clock')
    h, m = hhmm[:2], hhmm[3:]
    if not (h.isdecimal() and m.isdecimal() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ValueError('Invalid HH:MM clock time')
    return int(h)*60+int(m)


def hhmm(value):
    return f'{value//60:02d}:{value%60:02d}'


def templates(c):
    values = {r['code']: r['start_minute'] for r in c.execute('SELECT code,start_minute FROM shift_templates')}
    starts = {**DEFAULT_STARTS, **values}
    order = sorted(starts, key=lambda name: starts[name])
    if len(set(starts.values())) != 3:
        raise ValueError('Shift start times must be different')
    return [{ 'code': name, 'start_minute': starts[name],
              'start': hhmm(starts[name]), 'end_minute': starts[order[(i+1)%3]],
              'end': hhmm(starts[order[(i+1)%3]]) }
            for i,name in enumerate(order)]


def current_window(c, at=None):
    at = at or datetime.now(ZONE)
    local = at.astimezone(ZONE)
    minute = local.hour*60+local.minute
    slots = templates(c)
    for item in slots:
        start, end = item['start_minute'], item['end_minute']
        if (start < end and start <= minute < end) or (start > end and (minute >= start or minute < end)):
            business_day = local.date() - timedelta(days=1) if start > end and minute < end else local.date()
            return {'shift': item['code'], 'business_date': business_day.isoformat(),
                    'start': item['start'], 'end': item['end']}
    raise ValueError('Uncovered clock minute')


def planned_interval(c, day, shift):
    day = date.fromisoformat(day)
    row = next((r for r in templates(c) if r['code']==shift), None)
    if not row:
        raise ValueError('Unknown shift template')
    s, e = row['start_minute'], row['end_minute']
    start = datetime.combine(day, time(s//60, s%60), tzinfo=ZONE)
    end_day = day + timedelta(days=1) if e <= s else day
    finish = datetime.combine(end_day, time(e//60,e%60), tzinfo=ZONE)
    return start.isoformat(timespec='minutes'),finish.isoformat(timespec='minutes')
