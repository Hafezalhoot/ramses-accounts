"""G3L read-only supplier AP source-to-2200 reconciliation.

This is deliberately *not* a certified vendor payable ledger. Only explicitly
linked approved inventory receipts and G3K supplier bank vouchers have vendor
provenance. Opening AP, tax, external invoices and unrelated manual 2200 entries
remain UNATTRIBUTED rather than being guessed or spread across vendors.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def supplier_control_ledger(c: sqlite3.Connection, as_of: str) -> dict:
    # One posted 2200 balance per journal, from the actual GL, not vouchers' current status.
    journals = {int(r['id']): dict(r) for r in c.execute('''
        SELECT j.id,j.entry_date,j.origin,j.source_id,
               SUM(l.credit_piasters-l.debit_piasters) ap_delta_piasters
          FROM gl_journals j JOIN gl_lines l ON l.journal_id=j.id
          JOIN gl_accounts a ON a.id=l.account_id AND a.code='2200'
         WHERE j.status='posted' AND j.entry_date<=?
         GROUP BY j.id
         ORDER BY j.entry_date,j.id''', (as_of,))}
    by_origin = {(r['origin'], r['source_id']): r for r in journals.values()
                 if r['source_id'] is not None}
    total_control = sum(int(j['ap_delta_piasters']) for j in journals.values())
    vendors: dict[int, dict] = {}
    mapped: set[int] = set()
    anomalies: list[dict] = []
    events: list[dict] = []

    def vendor_record(vendor_id: int, name: str, vendor_code: str) -> dict:
        return vendors.setdefault(vendor_id, {
            'vendor_id': vendor_id, 'vendor_name': name, 'vendor_code': vendor_code,
            'accrued_piasters': 0, 'gross_bank_payments_piasters': 0,
            'bank_reversals_piasters': 0, 'net_payments_piasters': 0,
            'balance_piasters': 0, 'legacy_attributed_piasters':0, 'approved_grn_count': 0,
            'approved_unmatched_grn_count': 0, 'posted_payment_count': 0})

    def assign(journal: dict | None, row: dict, *, kind: str, expected: int,
               vendor_id: int, vendor_name: str, vendor_code: str, source_id: int) -> None:
        if journal is None:
            anomalies.append({'type': 'missing_source_journal', 'kind': kind,
                              'source_id': source_id, 'vendor_id': vendor_id})
            return
        jid = int(journal['id'])
        if jid in mapped:
            anomalies.append({'type': 'journal_reused_across_sources', 'kind': kind,
                              'source_id': source_id, 'journal_id': jid})
            return
        mapped.add(jid)
        amount = int(journal['ap_delta_piasters'])
        if amount != expected:
            anomalies.append({'type': 'source_amount_mismatch', 'kind': kind,
                              'source_id': source_id, 'journal_id': jid,
                              'expected_piasters': expected, 'posted_piasters': amount})
        v = vendor_record(vendor_id, vendor_name, vendor_code)
        v['balance_piasters'] += amount
        if kind == 'receipt':
            v['accrued_piasters'] += amount
        elif kind == 'payment':
            v['gross_bank_payments_piasters'] -= amount
            v['net_payments_piasters'] -= amount
            v['posted_payment_count'] += 1
        elif kind=='historical_attribution':
            v['legacy_attributed_piasters']+=amount
        else:  # reversal of an actual payment journal
            v['bank_reversals_piasters'] += amount
            v['net_payments_piasters'] -= amount
        events.append({'journal_id': jid, 'entry_date': journal['entry_date'],
                       'kind': kind, 'source_id': source_id, 'vendor_id': vendor_id,
                       'vendor_name': vendor_name, 'ap_delta_piasters': amount})

    def reviewed_by_as_of(approved_at: str | None) -> bool:
        if not approved_at:
            return False
        try:
            reviewed = datetime.fromisoformat(approved_at)
            if reviewed.tzinfo is None:
                reviewed = reviewed.replace(tzinfo=timezone.utc)
            return reviewed.astimezone(ZoneInfo('Africa/Cairo')).date().isoformat() <= as_of
        except ValueError:
            return False

    receipts = c.execute('''
        SELECT r.id,r.journal_id,r.received_on,r.status,r.vendor_id,
               v.name vendor_name,v.code vendor_code,
               COALESCE((SELECT SUM(l.quantity*l.unit_cost_piasters)
                           FROM inventory_receipt_lines l WHERE l.receipt_id=r.id),0) expected_piasters,
               (SELECT im.reviewed_at FROM inventory_supplier_invoice_matches im
                 WHERE im.receipt_id=r.id AND im.status='approved' LIMIT 1) invoice_approved_at
          FROM inventory_receipts r JOIN inventory_vendors v ON v.id=r.vendor_id
         WHERE r.status='approved' AND r.received_on<=?
         ORDER BY r.received_on,r.id''',(as_of,)).fetchall()
    for receipt in receipts:
        row = dict(receipt)
        record = vendor_record(row['vendor_id'], row['vendor_name'], row['vendor_code'])
        record['approved_grn_count'] += 1
        if not reviewed_by_as_of(row['invoice_approved_at']):
            record['approved_unmatched_grn_count'] += 1
        jid = row['journal_id']
        journal = journals.get(int(jid)) if jid is not None else None
        # 1100 Dr / 2200 Cr is the one approved stock-receipt source.
        assign(journal, row, kind='receipt', expected=int(row['expected_piasters']),
               vendor_id=row['vendor_id'], vendor_name=row['vendor_name'],
               vendor_code=row['vendor_code'], source_id=row['id'])

    links = c.execute('''
        SELECT b.voucher_id,v.id payment_voucher_id,v.date,v.status,
               v.amount_piasters,v.reversal_of_id,p.id payment_request_id,
               ven.id vendor_id,ven.name vendor_name,ven.code vendor_code
          FROM inventory_supplier_bank_vouchers b JOIN vouchers v ON v.id=b.voucher_id
          JOIN inventory_supplier_payment_requests p ON p.id=b.payment_request_id
          JOIN inventory_supplier_due_lines dl ON dl.id=p.due_line_id
          JOIN inventory_supplier_due_schedules ds ON ds.id=dl.schedule_id
          JOIN inventory_supplier_invoice_matches im ON im.id=ds.invoice_match_id
          JOIN inventory_receipts r ON r.id=im.receipt_id
          JOIN inventory_vendors ven ON ven.id=r.vendor_id
         WHERE v.date<=? ORDER BY v.date,v.id''',(as_of,)).fetchall()
    for row_raw in links:
        row = dict(row_raw)
        # Rejected/pending vouchers have no approved cashbook journal; do not count them.
        journal = by_origin.get(('voucher',row['payment_voucher_id']))
        if journal or row['status'] in ('approved','reversed'):
            assign(journal, row, kind='payment', expected=-int(row['amount_piasters']),
                   vendor_id=row['vendor_id'],vendor_name=row['vendor_name'],
                   vendor_code=row['vendor_code'],source_id=row['voucher_id'])
        reversal_rows = c.execute('''SELECT id,date,status,amount_piasters FROM vouchers
                                    WHERE reversal_of_id=? AND date<=?''',
                                  (row['voucher_id'],as_of)).fetchall()
        for rev in reversal_rows:
            rev_j = by_origin.get(('voucher',rev['id']))
            if rev_j or rev['status']=='approved':
                assign(rev_j, row, kind='reversal', expected=int(row['amount_piasters']),
                       vendor_id=row['vendor_id'],vendor_name=row['vendor_name'],
                       vendor_code=row['vendor_code'],source_id=rev['id'])

    # G3M: explicitly reviewed historical mapping. Never infer vendor from GL memo.
    # Classifications take effect on reviewer date, without backdating reports or posting money.
    historical=c.execute("""SELECT m.id,m.gl_journal_id,m.vendor_id,m.reviewed_at,
                 v.name vendor_name,v.code vendor_code
          FROM supplier_journal_attributions m JOIN inventory_vendors v ON v.id=m.vendor_id
          WHERE m.status='approved' ORDER BY m.id""").fetchall()
    for raw in historical:
        doc=dict(raw)
        if not reviewed_by_as_of(doc['reviewed_at']):
            continue
        source=journals.get(int(doc['gl_journal_id']))
        if not source:
            continue
        if int(source['id']) in mapped:
            anomalies.append({'type':'historical_attribution_conflicts_with_source',
                               'journal_id':int(source['id']),'attribution_id':doc['id']})
            continue
        amount=int(source['ap_delta_piasters'])
        assign(source,doc,kind='historical_attribution',expected=amount,
               vendor_id=doc['vendor_id'],vendor_name=doc['vendor_name'],
               vendor_code=doc['vendor_code'],source_id=doc['id'])

    unattributed = [dict(journal_id=j['id'],entry_date=j['entry_date'],origin=j['origin'],
                         ap_delta_piasters=j['ap_delta_piasters'])
                    for jid,j in journals.items() if jid not in mapped]
    unattributed_amount = sum(int(j['ap_delta_piasters']) for j in unattributed)
    attributed_amount = sum(v['balance_piasters'] for v in vendors.values())
    for v in vendors.values():
        if v['balance_piasters'] < 0:
            anomalies.append({'type':'negative_vendor_ap_balance','vendor_id':v['vendor_id'],
                              'amount_piasters':v['balance_piasters']})
    # Missing source journals may not show up in the GL account balance; this
    # status requires BOTH a source-document audit and a financial control audit.
    reconciled = not anomalies and not unattributed and total_control==attributed_amount
    return {
        'as_of':as_of,'control_account':'2200',
        'control_2200_piasters':total_control,
        'attributed_2200_piasters':attributed_amount,
        'unattributed_2200_piasters':unattributed_amount,
        'reconciled':reconciled,
        'vendors':sorted(vendors.values(),key=lambda v:v['vendor_name']),
        'vendor_count':len(vendors),
        'anomalies':anomalies,
        'unattributed_journals':unattributed,
        'events':sorted(events,key=lambda e:(e['entry_date'],e['journal_id']),reverse=True)[:100],
        'event_count':len(events),
        'approved_legacy_attribution_count':sum(1 for v in vendors.values() if v['legacy_attributed_piasters']!=0),
        'event_rows_truncated':len(events)>100,
        'scope':('مطابقة دفتر 2200 بالكامل مع استلامات G3H/Supplier GRN وسندات G3K المنسوبة فقط؛ '
                 'القيود التاريخية تُنسب فقط بعد دليل ومراجعة مستقلة بدءًا من تاريخ الموافقة؛ وما لم يُراجع يبقى غير منسوب. '
                 'مطابقة حساب الأستاذ ليست إثبات وصول تحويل للمستفيد ولا اعتمادًا نهائيًا للأرصدة التاريخية.'),
    }
