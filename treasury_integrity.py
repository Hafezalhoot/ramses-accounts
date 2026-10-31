"""Source-to-GL reconciliation for hospital tills, wallets and bank accounts.

Amounts are integer piasters. Opening balances and actual cash physically
counted remain separate evidence; this module never certifies them by inference.
Read-only: no updates, postings, or repairs happen during reconciliation.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import opening_balances


def treasury_reconciliation(c, period: str):
    year, sep, month = period.partition('-')
    if sep != '-' or len(year) != 4 or len(month) != 2:
        raise ValueError('Invalid period')
    try:
        date(int(year), int(month), 1)
    except ValueError as exc:
        raise ValueError('Invalid period') from exc

    funds = [dict(r) for r in c.execute('''SELECT f.id,f.code,f.name,f.kind,f.opening_piasters,
        a.id gl_account_id FROM funds f LEFT JOIN gl_fund_accounts fa ON fa.fund_id=f.id
        LEFT JOIN gl_accounts a ON a.id=fa.account_id ORDER BY f.kind,f.name,f.id''')]
    by_id = {f['id']:f for f in funds}
    opening_reviews = {r['id']:r for r in opening_balances.detail(c,period)}
    source_opening = {r['journal_id']:r for r in opening_reviews.values()
                      if r['review_status']=='approved' and r['journal_id']
                      and r['effective_date'][:7]<=period}
    issues = []
    count = 0
    fund_issues = defaultdict(int)

    def issue(kind, message, fund_id=None, reference=None):
        nonlocal count
        count += 1
        if fund_id in by_id:
            fund_issues[fund_id] += 1
        if len(issues) < 40:
            issues.append({'type':kind, 'fund_id':fund_id, 'reference':reference, 'message':message})

    for f in funds:
        if f['gl_account_id'] is None:
            issue('missing_control_account','الحساب المالي ليس له حساب رقابي مرتبط بدفتر الأستاذ',f['id'])

    # Include legacy orphaned control accounts in addition to the mapped ones.
    for a in c.execute('''SELECT a.id,a.code FROM gl_accounts a WHERE a.control='fund'
       AND NOT EXISTS(SELECT 1 FROM gl_fund_accounts fa WHERE fa.account_id=a.id)'''):
        if c.execute('''SELECT 1 FROM gl_lines l JOIN gl_journals j ON j.id=l.journal_id
             WHERE l.account_id=? AND j.status='posted' AND substr(j.entry_date,1,7)<=? LIMIT 1''',
             (a['id'],period)).fetchone():
            issue('unmapped_control_gl',f'حساب رقابي غير مربوط بخزنة: {a["code"]}')

    movements = list(c.execute('''SELECT m.id,m.voucher_id,m.fund_id,m.amount_piasters,m.booked_on,
         v.date voucher_date,v.status voucher_status FROM fund_movements m
         JOIN vouchers v ON v.id=m.voucher_id WHERE substr(m.booked_on,1,7)<=?''',(period,)))
    actual = defaultdict(dict)
    book = defaultdict(int)
    for m in movements:
        actual[m['voucher_id']][m['fund_id']] = actual[m['voucher_id']].get(m['fund_id'],0)+m['amount_piasters']
        book[m['fund_id']] += m['amount_piasters']
        if m['voucher_date'] != m['booked_on'] or m['voucher_status'] not in ('approved','reversed'):
            issue('invalid_movement','حركة خزنة غير مرتبطة بسند معتمد في تاريخها الصحيح',m['fund_id'],m['voucher_id'])

    gl = defaultdict(int)
    gl_by_journal = defaultdict(dict)
    for r in c.execute('''SELECT j.id journal_id,fa.fund_id,SUM(l.debit_piasters-l.credit_piasters) value
       FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
       JOIN gl_fund_accounts fa ON fa.account_id=l.account_id
       WHERE j.status='posted' AND substr(j.entry_date,1,7)<=?
       GROUP BY j.id,fa.fund_id''',(period,)):
        gl[r['fund_id']] += int(r['value'])
        gl_by_journal[r['journal_id']][r['fund_id']] = int(r['value'])

    vouchers = {r['id']:dict(r) for r in c.execute('''SELECT id,date,kind,status,from_fund_id,
        to_fund_id,amount_piasters,reversal_of_id FROM vouchers
        WHERE substr(date,1,7)<=? AND status IN ('approved','reversed')''',(period,))}
    originals = {v['reversal_of_id'] for v in vouchers.values() if v['reversal_of_id']}
    old = {}
    if originals:
        placeholders=','.join('?' for _ in originals)
        old = {r['id']:dict(r) for r in c.execute(
            'SELECT id,kind,from_fund_id,to_fund_id,amount_piasters FROM vouchers WHERE id IN ('+placeholders+')',
            tuple(originals))}

    journal_by_voucher = defaultdict(list)
    for j in c.execute("SELECT id,source_id,status,entry_date FROM gl_journals WHERE origin='voucher' AND source_id IS NOT NULL"):
        journal_by_voucher[j['source_id']].append(j)

    def expected_legs(v):
        src = old.get(v['reversal_of_id']) if v['reversal_of_id'] else v
        if src is None:
            return None
        sign = -1 if v['reversal_of_id'] else 1
        amount = int(src['amount_piasters']) * sign
        if src['kind']=='receipt':
            return {src['from_fund_id']:amount}
        if src['kind']=='payment':
            return {src['from_fund_id']:-amount}
        if src['kind']=='transfer':
            return {src['from_fund_id']:-amount,src['to_fund_id']:amount}
        return None

    for vid,v in vouchers.items():
        expected = expected_legs(v)
        if not expected or any(fid not in by_id for fid in expected):
            issue('invalid_voucher','سند معتمد بتصنيف أو طرف خزنة غير سليم',reference=vid)
            continue
        recorded = actual.get(vid,{})
        journals = [j for j in journal_by_voucher.get(vid,[]) if j['status']=='posted']
        j = journals[0] if len(journals)==1 else None
        # A voucher's accounting source is dated at the original posting date.
        if j is None or j['entry_date'] != v['date']:
            issue('voucher_journal','قيد السند غير مرحل أو يحمل تاريخًا غير تاريخ المستند',reference=vid)
        gl_legs = gl_by_journal.get(j['id'],{}) if j and j['entry_date'][:7]<=period else {}
        for fid in set(expected)|set(recorded)|set(gl_legs):
            e = expected.get(fid,0)
            if recorded.get(fid,0) != e:
                issue('movement_leg','مبلغ أو جهة حركة الخزنة لا يطابق السند',fid,vid)
            if gl_legs.get(fid,0) != e:
                issue('gl_leg','قيد الخزنة في الأستاذ لا يطابق السند',fid,vid)

    # Extra movements whose dated vouchers are not in the recognized population.
    for vid,legs in actual.items():
        if vid not in vouchers:
            for fid in legs:
                issue('orphan_movement','حركة خزنة خارج سندات الفترة المعتمدة',fid,vid)

    # No manually posted GL line may write a fund account, even if another
    # unrelated fund entry happens to compensate for it numerically.
    for j in c.execute('''SELECT DISTINCT j.id,j.origin,j.source_id FROM gl_journals j
       JOIN gl_lines l ON l.journal_id=j.id
       JOIN gl_fund_accounts fa ON fa.account_id=l.account_id
       WHERE j.status='posted' AND substr(j.entry_date,1,7)<=?''',(period,)):
        if j['id'] in source_opening and j['origin']=='manual' and j['source_id']==source_opening[j['id']]['review_id']:
            continue  # A source-backed, independently approved opening is NOT a voucher.
        if j['origin'] != 'voucher' or j['source_id'] not in vouchers:
            issue('orphan_gl','قيد يؤثر على حساب خزنة دون سند مالي معتمد مرتبط',reference=j['id'])

    for f in funds:
        review=opening_reviews[f['id']]
        source_journal=review['journal_id'] if review['verified_as_of_period'] else None
        opening_gl=gl_by_journal.get(source_journal,{}).get(f['id'],0) if source_journal else 0
        f['movement_piasters'] = book[f['id']]
        f['gl_posted_piasters'] = gl[f['id']] - opening_gl
        f['gl_opening_piasters'] = opening_gl
        f['gl_total_piasters'] = gl[f['id']]
        f['difference_piasters'] = f['gl_posted_piasters'] - book[f['id']]
        f['book_balance_piasters'] = int(f['opening_piasters']) + book[f['id']]
        f['opening_requires_independent_verification'] = review['review_needed']
        f['opening_review_status'] = review['review_status'] or 'unreviewed'
        if review['review_needed']:
            issue('opening_unverified',review['review_issue'],f['id'],review['review_id'])
        if f['difference_piasters']:
            issue('fund_delta','إجمالي حركات الخزنة يختلف عن إجمالي القيود المرحلة',f['id'])

    # A sealed physical shift must still agree with its recorded count.
    # This is a current-state audit, not an as-of reconstruction: a variance
    # adjustment may have been posted the following month by an approver.
    shifts_checked=0
    for sh in c.execute('''SELECT id,fund_id,opening_piasters,counted_piasters,
         expected_piasters,reviewed_by,responsible_id,status FROM shift_sessions
         WHERE substr(business_date,1,7)=?''',(period,)):
        if sh['status'] != 'closed':
            issue('unclosed_shift','وردية من الشهر لم تُغلق باعتماد مستقل',sh['fund_id'],sh['id'])
            continue
        shifts_checked+=1
        all_legs=c.execute('''SELECT COALESCE(SUM(amount_piasters),0) FROM fund_movements
            WHERE shift_session_id=?''',(sh['id'],)).fetchone()[0]
        counted = sh['opening_piasters'] + all_legs
        if (counted != sh['counted_piasters'] or sh['expected_piasters'] != sh['counted_piasters']
             or sh['reviewed_by'] is None or sh['reviewed_by']==sh['responsible_id']):
            issue('shift_count','وردية مغلقة بجرد غير مطابق أو دون مراجعة مستقلة',sh['fund_id'],sh['id'])

    # Recheck approved bank statements *at month close*: a historical approved
    # badge does not replace verification of every active match and balance.
    for f in funds:
        if f['kind'] != 'bank':
            continue
        monthly = [m for m in movements if m['fund_id']==f['id'] and m['booked_on'][:7]==period]
        b=c.execute('''SELECT * FROM bank_statement_batches WHERE fund_id=? AND period=?
                  AND status!='voided' ORDER BY id DESC LIMIT 1''',(f['id'],period)).fetchone()
        if not monthly and not b:
            continue
        if not b or b['status']!='approved':
            issue('bank_not_approved','حركة بنكية أو كشف مستورد دون اعتماد مطابقة مكتملة',f['id'])
            continue
        lines=list(c.execute('''SELECT l.id,l.amount_piasters,l.tx_date,
           ma.movement_id,m.amount_piasters matched_amount,m.booked_on,m.fund_id matched_fund
           FROM bank_statement_lines l
           LEFT JOIN bank_statement_matches ma ON ma.line_id=l.id AND ma.status='active'
           LEFT JOIN fund_movements m ON m.id=ma.movement_id
           WHERE l.batch_id=?''',(b['id'],)))
        matched_ids=set()
        for line in lines:
            if (line['movement_id'] is None or line['matched_fund']!=f['id']
                or line['matched_amount']!=line['amount_piasters']
                or not line['booked_on'] or line['booked_on'][:7]!=period
                or line['tx_date'][:7]!=period or line['movement_id'] in matched_ids):
                issue('bank_match','سطر كشف بنك معتمد لا يطابق حركة دفتر سليمة',f['id'],line['id'])
            if line['movement_id'] is not None:
                matched_ids.add(line['movement_id'])
        if any(m['id'] not in matched_ids for m in monthly):
            issue('bank_unmatched_movement','حركة بنك غير مطابقة رغم اعتماد الكشف',f['id'])
        month_sum=sum(int(l['amount_piasters']) for l in lines)
        opening=int(f['opening_piasters'])+sum(m['amount_piasters'] for m in movements
                  if m['fund_id']==f['id'] and m['booked_on'][:7]<period)
        closing=opening+sum(m['amount_piasters'] for m in monthly)
        if (b['opening_piasters']!=opening or b['closing_piasters']!=closing
           or b['opening_piasters']+month_sum!=b['closing_piasters']):
            issue('bank_balance','رصيد كشف البنك المعتمد تغير أو لا يساوي دفتره',f['id'],b['id'])

    # G2K: link the POS transfer/fee to all original patient card receipt parts.
    # A balanced bank statement without this cross-check can conceal reallocation.
    for pos in c.execute("SELECT * FROM pos_settlements WHERE substr(settlement_date,1,7)<=?",(period,)):
        if pos['status']=='pending':
            issue('pos_pending','POS settlement awaiting review',pos['clearing_fund_id'],pos['id'])
            continue
        if pos['status']!='approved':
            continue
        if pos['created_by']==pos['reviewed_by'] or pos['reviewed_by'] is None:
            issue('pos_dual_control','POS settlement lacks independent review',pos['clearing_fund_id'],pos['id'])
        parts=list(c.execute('''SELECT sp.payment_part_id,sp.amount_piasters,sp.active,
           p.amount_piasters original_amount,p.fund_id,p.method,v.status voucher_status,
           v.kind voucher_kind,v.from_fund_id,bc.business_date
           FROM pos_settlement_parts sp
           LEFT JOIN billing_payment_parts p ON p.id=sp.payment_part_id
           LEFT JOIN billing_collections bc ON bc.id=p.collection_id
           LEFT JOIN vouchers v ON v.id=p.voucher_id
           WHERE sp.settlement_id=?''',(pos['id'],)))
        if (not parts or sum(x['amount_piasters'] for x in parts)!=pos['gross_piasters']
            or any(x['active']!=1 or x['original_amount']!=x['amount_piasters']
               or x['fund_id']!=pos['clearing_fund_id'] or x['method']!='card'
               or x['voucher_status']!='approved' or x['voucher_kind']!='receipt'
               or x['from_fund_id']!=pos['clearing_fund_id']
               or x['business_date']>pos['settlement_date'] for x in parts)):
            issue('pos_receipts','Approved POS batch differs from source card receipts',pos['clearing_fund_id'],pos['id'])
        transfer=c.execute('''SELECT kind,status,amount_piasters,from_fund_id,to_fund_id,date
             FROM vouchers WHERE id=?''',(pos['transfer_voucher_id'],)).fetchone()
        if (not transfer or transfer['kind']!='transfer' or transfer['status']!='approved'
            or transfer['date']!=pos['settlement_date']
            or transfer['amount_piasters']!=pos['net_piasters']
            or transfer['from_fund_id']!=pos['clearing_fund_id']
            or transfer['to_fund_id']!=pos['bank_fund_id']):
            issue('pos_net_transfer','Net bank transfer does not match approved POS batch',pos['bank_fund_id'],pos['id'])
        if pos['fee_piasters']:
            fee=c.execute('''SELECT v.kind,v.status,v.amount_piasters,v.from_fund_id,v.date,ca.code
                  FROM vouchers v LEFT JOIN categories ca ON ca.id=v.category_id
                  WHERE v.id=?''',(pos['fee_voucher_id'],)).fetchone()
            if (not fee or fee['kind']!='payment' or fee['status']!='approved'
                or fee['date']!=pos['settlement_date']
                or fee['amount_piasters']!=pos['fee_piasters']
                or fee['from_fund_id']!=pos['clearing_fund_id']
                or fee['code']!='pos_processing_fee'):
                issue('pos_fee','POS fee is not posted as the approved acquiring expense',pos['clearing_fund_id'],pos['id'])
        elif pos['fee_voucher_id'] is not None:
            issue('pos_unexpected_fee','Zero-fee POS batch has an unexpected fee voucher',pos['clearing_fund_id'],pos['id'])
        if pos['net_piasters']!=pos['gross_piasters']-pos['fee_piasters']:
            issue('pos_total','POS gross, fee and bank net no longer reconcile',pos['bank_fund_id'],pos['id'])

    for f in funds:
        f['issue_count'] = fund_issues[f['id']]
        f['matched'] = not f['issue_count'] and not f['difference_piasters']
        del f['gl_account_id']

    return {'period':period,'matched':count==0,'issue_count':count,'issues':issues,
            'funds':funds,'shift_count_checked':shifts_checked,
            'opening_review_required':sum(int(f['opening_requires_independent_verification']) for f in funds),
            'scope':'مطابقة حركة السندات والخزن مع قيود الأستاذ، وسلامة جرد الورديات المعتمدة وكشوف البنك. '
                    'أرصدة افتتاح الخزن تتطلب محضرًا مستقلًا وقيدًا متوازنًا؛ المستند المرجعي لا يثبت مطابقة النقدية الفعلية تلقائيًا.'}
