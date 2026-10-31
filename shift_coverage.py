"""Expected station windows from immutable, effective-dated schedules.

This is a *read-only* operational control. Missing means missing electronic
registration, never an assertion that the station had zero transactions.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import cashier_ops

CAIRO = ZoneInfo('Africa/Cairo')
ATTENTION = {'missing', 'unclosed', 'awaiting_review', 'variance'}


def report(c, month, user, *, at=None, grace_minutes=None):
    at = (at or datetime.now(CAIRO)).astimezone(CAIRO)
    year, number = map(int, month.split('-'))
    days = [date(year, number, d) for d in range(1,monthrange(year,number)[1]+1)]
    clause = ''
    args = []
    if user['role']=='clerk':
        clause = ''' AND EXISTS(SELECT 1 FROM billing_point_access a
                 WHERE a.point_id=p.id AND a.user_id=? AND a.active=1)'''
        args.append(user['id'])
    elif user['role']=='reviewer':
        # Do not reveal restricted station schedules, shift IDs or totals
        # merely because the user has a reviewer role.
        clause = ''' AND NOT EXISTS(SELECT 1 FROM funds f WHERE f.id=p.fund_id
            AND (f.kind IN ('bank','wallet') OR f.cash_restricted=1)
            AND NOT EXISTS(SELECT 1 FROM user_fund_grants g
              JOIN users u ON u.id=g.user_id AND u.active=1
              WHERE g.user_id=? AND g.fund_id=f.id
              AND (g.can_submit=1 OR g.can_approve=1)))'''
        args.append(user['id'])
    points = [dict(r) for r in c.execute('''SELECT p.id,p.name,p.kind,p.fund_id,p.active,
              (SELECT MIN(s.business_date) FROM shift_sessions s WHERE s.point_id=p.id OR (s.point_id IS NULL AND s.fund_id=p.fund_id)) monitored_from
              FROM billing_points p WHERE EXISTS(SELECT 1 FROM cashier_schedule_versions v WHERE v.point_id=p.id)
            '''+clause+' ORDER BY p.id',args)]
    sessions={}
    ids=[p['id'] for p in points]
    funds={p['fund_id']:p['id'] for p in points if p['fund_id']}
    if ids:
        for row in c.execute('''SELECT s.id,s.point_id,s.fund_id,s.business_date,s.shift,s.status,
                  s.scheduled_start_at,s.scheduled_end_at,s.variance_piasters
                  FROM shift_sessions s WHERE substr(s.business_date,1,7)=?''',(month,)):
            pid=row['point_id'] or funds.get(row['fund_id'])
            if pid in ids:sessions[(pid,row['business_date'],row['shift'])]=dict(row)

    items=[]; daily=[]
    summary={k:0 for k in ('missing','unclosed','awaiting_review','variance','closed','open','upcoming','grace','not_monitored','station_days_incomplete')}
    for point in points:
        policy=c.execute('SELECT grace_minutes FROM cashier_point_policies WHERE point_id=?',(point['id'],)).fetchone()
        grace = grace_minutes if grace_minutes is not None else (policy['grace_minutes'] if policy else 120)
        for day in days:
            iso=day.isoformat()
            # Unbound stations have no physical drawer to operate. Scheduling
            # templates can exist while the owner configures a new point, but
            # they are not obligations and must not create phantom missing shifts.
            slots = cashier_ops.slots_for(c,point['id'],iso) if point['fund_id'] else []
            revision = cashier_ops.version_for(c,point['id'],iso)
            # Old records predate scheduling revisions. Preserve the legacy
            # three-shift expectation once that point's first session exists.
            if point['fund_id'] and revision is None and point['monitored_from'] and iso>=point['monitored_from']:
                import shift_schedule
                for legacy in shift_schedule.templates(c):
                    slots.append({**legacy,'name':{'night':'السهر','morning':'الصباحي','evening':'المسائي'}[legacy['code']],
                                  'version_id':None})

            if revision and 'operating_days' in revision.keys() and str(day.weekday()) not in revision['operating_days']:
                slots=[]
            records=[]
            for slot in slots:
                shift=slot['code']
                start,end=cashier_ops.interval(iso,slot)
                actual=sessions.get((point['id'],iso,shift))
                if actual:
                    start=actual['scheduled_start_at'] or start
                    end=actual['scheduled_end_at'] or end
                    if actual['status']=='closed':status='closed'
                    elif actual['status']=='submitted':
                        status='variance' if (actual['variance_piasters'] or 0) else 'awaiting_review'
                    else:
                        status='unclosed' if at>=datetime.fromisoformat(end)+timedelta(minutes=grace) else 'open'
                elif at<datetime.fromisoformat(start):status='upcoming'
                elif at<datetime.fromisoformat(end)+timedelta(minutes=grace):status='grace'
                else:status='missing'
                obj={'point_id':point['id'],'point_name':point['name'],'fund_id':point['fund_id'],
                     'business_date':iso,'shift':shift,'shift_name':slot['name'],
                     'starts_at':start,'ends_at':end,'status':status,
                     'session_id':actual['id'] if actual else None,
                     'schedule_version_id':slot['version_id']}
                items.append(obj);records.append(obj);summary[status]+=1
            # Preserve historical sessions even after a plan has been retired.
            known={x['shift'] for x in records}
            for (pid,d,code),s in sessions.items():
                if pid!=point['id'] or d!=iso or code in known:continue
                # Such a slot might be a previously recorded, but non-current,
                # legacy shift. It must never disappear from audit results.
                st = 'closed' if s['status']=='closed' else 'awaiting_review' if s['status']=='submitted' else 'unclosed'
                extra={'point_id':pid,'point_name':point['name'],'fund_id':point['fund_id'],
                       'business_date':iso,'shift':code,'shift_name':code,
                       'starts_at':s['scheduled_start_at'],'ends_at':s['scheduled_end_at'],
                       'status':st,'session_id':s['id'],'historical_extra':True}
                items.append(extra);records.append(extra);summary[st]+=1
            statuses={r['status'] for r in records}
            if not records:
                day_status='not_monitored' if not revision else 'not_required'
            elif statuses=={'closed'}:day_status='complete'
            elif statuses & ATTENTION:day_status='incomplete'
            else:day_status='in_progress'
            if day_status=='incomplete':summary['station_days_incomplete']+=1
            daily.append({'point_id':point['id'],'point_name':point['name'],'business_date':iso,
                          'status':day_status,'closed_shifts':sum(r['status']=='closed' for r in records),
                          'expected_shifts':len(slots),
                          'missing_shifts':sum(r['status']=='missing' for r in records)})
    return {'month':month,'timezone':'Africa/Cairo', 'points':points,'items':items,'days':daily,
            'summary':summary,
            'warnings':['Missing means no electronic shift, NOT no hospital activity.',
                        'Schedule versions never rewrite historical cashier shifts or cash movements.',
                        'Coverage is informational, not a cash, patient or GL posting.']}
