"""V8.1E: effective-dated cashier coverage and conservative shift-table upgrade.

Only cash station scheduling lives here. No patient collections are inferred or posted.
"""
from __future__ import annotations
import re
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo('Africa/Cairo')
CODE = re.compile(r'^[a-z][a-z0-9_]{1,31}$')
DEFAULTS = {
    'external': [('night', 'السهر', 0), ('morning', 'الصباحي', 480), ('evening', 'المسائي', 960)],
    'internal': [('treasury', 'الخزنة العامة / الداخلية', 0)],
}


def upgrade_shift_table(c: sqlite3.Connection, db_path: Path):
    """Remove legacy 3-name CHECK while preserving IDs, child FKs and all rows.

    SQLite cannot drop a CHECK constraint in place. Run outside an open transaction.
    A one-time consistent snapshot is required before the table rebuild.
    """
    sqlrow = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='shift_sessions'").fetchone()
    if not sqlrow or not re.search(r"\bshift\s+IN\s*\(", sqlrow[0], flags=re.I):
        return False
    if c.in_transaction:
        raise RuntimeError('Shift migration must run outside an active transaction')
    from scripts.secure_backup import create_preupgrade
    from datetime import timezone
    import secrets
    folder = db_path.parent / 'pre_v81e_shift_backups'
    name = ('before_v81e_' + datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            + '_' + secrets.token_hex(4) + '.rbe')
    # Table rebuild is destructive DDL. Independently preserve its exact input
    # state with the same authenticated archive format as bootstrap preflight.
    create_preupgrade(c, folder, name)
    # Keep the existing SQL definition (including any additive old columns),
    # except the shift-name CHECK; avoid dropping future schema fields.
    old = sqlrow[0]
    modified = re.sub(r"\bshift\s+TEXT\s+NOT\s+NULL\s+CHECK\s*\(\s*shift\s+IN\s*\(\s*'morning'\s*,\s*'evening'\s*,\s*'night'\s*\)\s*\)",
                      'shift TEXT NOT NULL', old, count=1, flags=re.I)
    if modified == old or re.search(r"\bshift\s+IN\s*\(", modified, flags=re.I):
        raise RuntimeError('Unknown shift CHECK definition; refusing destructive migration')
    modified = re.sub(r'^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?shift_sessions["`]?',
                      'CREATE TABLE shift_sessions_v81e', modified, flags=re.I)
    indexes = [r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='shift_sessions' AND sql IS NOT NULL")]
    triggers = [r[0] for r in c.execute("SELECT sql FROM sqlite_master WHERE type='trigger' AND tbl_name='shift_sessions' AND sql IS NOT NULL")]
    cols = [r['name'] for r in c.execute('PRAGMA table_info(shift_sessions)')]
    select_cols = ','.join('"' + k + '"' for k in cols)
    c.execute('PRAGMA foreign_keys=OFF')
    try:
        c.execute('BEGIN IMMEDIATE')
        c.execute(modified)
        c.execute('INSERT INTO shift_sessions_v81e (' + select_cols + ') SELECT ' + select_cols + ' FROM shift_sessions')
        c.execute('DROP TABLE shift_sessions')
        c.execute('ALTER TABLE shift_sessions_v81e RENAME TO shift_sessions')
        for item in indexes + triggers:
            c.execute(item)
        violations = c.execute('PRAGMA foreign_key_check').fetchall()
        if violations:
            raise RuntimeError('Foreign keys invalid after shift upgrade: ' + str(violations[:3]))
        c.execute('COMMIT')
    except Exception:
        if c.in_transaction:
            c.execute('ROLLBACK')
        raise
    finally:
        c.execute('PRAGMA foreign_keys=ON')
    return True


def seed_schedules(c):
    for point in c.execute('SELECT id,kind,fund_id FROM billing_points').fetchall():
        exists = c.execute('SELECT 1 FROM cashier_schedule_versions WHERE point_id=?', (point['id'],)).fetchone()
        if exists:
            continue
        earliest = c.execute('SELECT MIN(business_date) FROM shift_sessions WHERE fund_id=?',(point['fund_id'],)).fetchone()[0] if point['fund_id'] else None
        today = datetime.now(CAIRO).date().isoformat()
        first = earliest or today
        # An old internal till may have used the 3-shift legacy convention.
        # Keep those rows coverable under a legacy revision, switch to the
        # approved single internal accounting period only for a clean day.
        if earliest and point['kind']=='internal' and earliest < today:
            add_version(c,point['id'],first,DEFAULTS['external'],None,reason='Legacy shift chronology')
            first=today
        if earliest and point['kind']=='internal' and earliest >= today:
            first=earliest
            existing = [tuple(x) for x in c.execute('SELECT DISTINCT shift FROM shift_sessions WHERE fund_id=?',(point['fund_id'],))]
            specs=DEFAULTS['external'] if existing and any(x[0] != 'treasury' for x in existing) else DEFAULTS['internal']
        else:
            specs=DEFAULTS[point['kind']]
        add_version(c,point['id'],first,specs,None,reason='Initial approved hospital configuration')
        c.execute('INSERT OR IGNORE INTO cashier_point_policies(point_id) VALUES (?)',(point['id'],))
        c.execute('INSERT OR IGNORE INTO cashier_point_lifecycle(point_id,starts_on,enabled) VALUES (?,?,1)',(point['id'],first))
    # Historical sessions get point identity without mutating their real times.
    c.execute('''UPDATE shift_sessions SET point_id=(SELECT id FROM billing_points p WHERE p.fund_id=shift_sessions.fund_id)
                 WHERE point_id IS NULL AND EXISTS(SELECT 1 FROM billing_points p WHERE p.fund_id=shift_sessions.fund_id)''')


def add_version(c,point_id,effective_from,slots,actor,reason=''):
    cur=c.execute('''INSERT INTO cashier_schedule_versions(point_id,starts_on,created_by,created_at,reason)
                     VALUES (?,?,?,?,?)''',(point_id,effective_from,actor,datetime.now(ZoneInfo('UTC')).isoformat(),reason))
    for code,name,start in slots:
        c.execute('''INSERT INTO cashier_schedule_slots(version_id,code,name,start_minute)
                     VALUES (?,?,?,?)''',(cur.lastrowid,code,name,start))
    return cur.lastrowid


def version_for(c,point_id,day):
    return c.execute('''SELECT * FROM cashier_schedule_versions
              WHERE point_id=? AND starts_on<=? ORDER BY starts_on DESC,id DESC LIMIT 1''',(point_id,day)).fetchone()


def point_enabled(c,point_id,day):
    r=c.execute('''SELECT enabled FROM cashier_point_lifecycle WHERE point_id=? AND starts_on<=?
                    ORDER BY starts_on DESC LIMIT 1''',(point_id,day)).fetchone()
    return r is not None and bool(r['enabled'])


def slots_for(c,point_id,day):
    v=version_for(c,point_id,day)
    if not v or not point_enabled(c,point_id,day):return []
    rows = list(c.execute('''SELECT code,name,start_minute FROM cashier_schedule_slots
                             WHERE version_id=? ORDER BY start_minute''',(v['id'],)))
    result=[]
    for i,row in enumerate(rows):
        end=rows[(i+1)%len(rows)]['start_minute']
        result.append({'code':row['code'],'name':row['name'],'start_minute':row['start_minute'],
                       'start':f"{row['start_minute']//60:02d}:{row['start_minute']%60:02d}",
                       'end_minute':end,'end':f"{end//60:02d}:{end%60:02d}",
                       'version_id':v['id']})
    return result


def historical_shift_name(c, point_id, business_date, code):
    """Display a recorded shift using the schedule in force on its business date.

    Never re-label old custody records from a newer station schedule. An
    unresolvable legacy code is displayed literally rather than invented.
    """
    if point_id is not None:
        slot = c.execute("""SELECT s.name FROM cashier_schedule_slots s
           JOIN cashier_schedule_versions v ON v.id=s.version_id
           WHERE v.point_id=? AND v.starts_on<=? AND s.code=?
           ORDER BY v.starts_on DESC,v.id DESC LIMIT 1""",
           (point_id,business_date,code)).fetchone()
        if slot:
            return slot['name']
    return {'night':'سهر','morning':'صباحي','evening':'مسائي'}.get(code,code)

def interval(day,slot):
    when=date.fromisoformat(day)
    start_min=slot['start_minute']; end_min=slot['end_minute']
    start=datetime.combine(when,time(start_min//60,start_min%60),tzinfo=CAIRO)
    extra=1 if end_min<=start_min else 0
    finish=datetime.combine(when+timedelta(days=extra),time(end_min//60,end_min%60),tzinfo=CAIRO)
    return start.isoformat(timespec='minutes'),finish.isoformat(timespec='minutes')


def validate_slots(slots):
    if not isinstance(slots,list) or not 1<=len(slots)<=24:
        raise ValueError('The station needs 1 to 24 shifts')
    from shift_schedule import minutes
    cleaned=[]
    for item in slots:
        code=str(item.get('code','')).strip().lower()
        name=str(item.get('name','')).strip()
        if not CODE.fullmatch(code) or code=='central':
            raise ValueError('Use unique Latin shift codes, 2-32 characters, not central')
        if not 2<=len(name)<=70:
            raise ValueError('Shift names must be 2-70 characters')
        cleaned.append((code,name,minutes(item['start'])))
    if len(set(t[0] for t in cleaned))!=len(cleaned) or len(set(t[2] for t in cleaned))!=len(cleaned):
        raise ValueError('Duplicate shift code or start time')
    return sorted(cleaned,key=lambda x:x[2])
