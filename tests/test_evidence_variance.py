"""V7.3 money invariants and document security. Synthetic records only."""
import os
import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def run():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['RAMSES_DB_PATH']=str(Path(tmp)/'ledger.sqlite3')
        os.environ['RAMSES_ADMIN_USER']='owner'
        os.environ['RAMSES_ADMIN_PASSWORD']='owner_long_staging_password'
        os.environ.pop('GOOGLE_SHEET_ID',None)
        os.environ.pop('GOOGLE_SERVICE_ACCOUNT_JSON',None)
        os.environ.pop('RAMSES_REQUIRE_PAYMENT_EVIDENCE',None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,reviewer,clerk,viewer=(TestClient(app) for _ in range(4))
        def login(client,name,password):
            v=client.post('/api/login',json={'username':name,'password':password})
            assert v.status_code==200,v.text
            return {'X-CSRF-Token':v.json()['csrf']}
        oh=login(owner,'owner','owner_long_staging_password')
        for name,role in [('reviewer','reviewer'),('cashier','clerk'),('reader','viewer')]:
            assert owner.post('/api/users',headers=oh,json={'username':name,'password':'employee_long_password_123','role':role}).status_code==200
        rh=login(reviewer,'reviewer','employee_long_password_123')
        ch=login(clerk,'cashier','employee_long_password_123')
        vh=login(viewer,'reader','employee_long_password_123')
        look=owner.get('/api/lookups').json()
        f=next(x['id'] for x in look['funds'] if x['code']=='cash_main')
        dept=look['departments'][0]['id']
        cat_receipt=next(x['id'] for x in look['categories'] if x['code']=='medical_revenue')
        cat_payment=next(x['id'] for x in look['categories'] if x['code']=='utilities')
        day=datetime.now().astimezone().date().isoformat()
        assert owner.post(f'/api/funds/{f}/opening',json={'amount':'1000'},headers=oh).status_code==200
        opened=clerk.post('/api/shifts/open',json={'business_date':day,'shift':'morning','fund_id':f},headers=ch)
        assert opened.status_code==200,opened.text
        shift_id=opened.json()['id']
        def voucher(kind,amount,cat):
            a=clerk.post('/api/vouchers',headers=ch,json={'date':day,'kind':kind,'department_id':dept,'category_id':cat,
                'from_fund_id':f,'shift':'morning','amount':str(amount),'description':'مستند مالي تجريبي لاختبار الحماية'})
            assert a.status_code==200,a.text
            return a.json()['id']
        receipt=voucher('receipt','100',cat_receipt)
        payment=voucher('payment','10',cat_payment)
        sample=b'%PDF-1.7\n1 0 obj <<>> endobj\n%%EOF\n'
        link=f'/api/vouchers/{payment}/attachments'
        assert owner.post(link,files={'file':('invoice.pdf',sample,'application/pdf')}).status_code==403
        assert viewer.get(link).status_code==403
        assert reviewer.post(link,files={'file':('invoice.pdf',sample,'application/pdf')},headers=rh).status_code==403
        assert clerk.post(link,files={'file':('bad.exe',sample,'application/pdf')},headers=ch).status_code==400
        assert clerk.post(link,files={'file':('oversize.pdf',b'%PDF-'+b'A'*(6*1024*1024),'application/pdf')},headers=ch).status_code==413
        uploaded=clerk.post(link,files={'file':('invoice.pdf',sample,'application/pdf')},headers=ch)
        assert uploaded.status_code==200,uploaded.text
        att=uploaded.json()['id']
        assert clerk.post(link,files={'file':('invoice.pdf',sample,'application/pdf')},headers=ch).status_code==409
        info=clerk.get(link).json()
        assert info[0]['file_size']==len(sample) and 'content' not in str(info)
        assert reviewer.get(link).status_code==200
        assert owner.get(f'/api/attachments/{att}/download').content==sample
        dl=clerk.get(f'/api/attachments/{att}/download')
        assert dl.headers['content-type'].startswith('application/octet-stream')
        assert 'attachment;' in dl.headers['content-disposition']
        assert viewer.get(f'/api/attachments/{att}/download').status_code==403
        assert TestClient(app).get(f'/api/attachments/{att}/download').status_code==401
        assert owner.get('/api/vouchers?status=pending').json()['items'][0]['attachment_count'] in (0,1)
        os.environ['RAMSES_REQUIRE_PAYMENT_EVIDENCE']='1'
        assert reviewer.post(f'/api/vouchers/{receipt}/decision',json={'decision':'approve'},headers=rh).status_code==200
        assert reviewer.post(f'/api/vouchers/{payment}/decision',json={'decision':'approve'},headers=rh).status_code==200
        assert clerk.post(link,files={'file':('another.pdf',sample+b'\n','application/pdf')},headers=ch).status_code==409
        without=voucher('payment','2',cat_payment)
        assert reviewer.post(f'/api/vouchers/{without}/decision',json={'decision':'approve'},headers=rh).status_code==409
        assert reviewer.post(f'/api/vouchers/{without}/decision',json={'decision':'reject','reason':'فاتورة غير مرفقة'},headers=rh).status_code==200
        os.environ.pop('RAMSES_REQUIRE_PAYMENT_EVIDENCE',None)
        # Backup restores the attachment bytes with the ledger, not as dangling files.
        snapshot=Path(tmp)/'snapshot.sqlite3'
        with sqlite3.connect(os.environ['RAMSES_DB_PATH']) as source,sqlite3.connect(snapshot) as target:
            source.backup(target)
        with sqlite3.connect(snapshot) as restored:
            assert restored.execute('SELECT content FROM voucher_attachments WHERE id=?',(att,)).fetchone()[0]==sample
        assert owner.post(f'/api/shifts/{shift_id}/variance-propose',headers=oh,json={'explanation':'تم تأكيد عجز صندوق بعد التحقيق'}).status_code==403
        sub=clerk.post(f'/api/shifts/{shift_id}/count',json={'counted_amount':'1070','note':'فارق 20 جنيه'},headers=ch)
        # 1000 + 100 -10 =1090, counted 1070 => shortage 20
        assert sub.status_code==200 and sub.json()['variance_piasters']==-2000,sub.text
        proposed=reviewer.post(f'/api/shifts/{shift_id}/variance-propose',json={'explanation':'بعد إعادة عد النقود تبين عجز عشرين جنيها تحت التحقيق'},headers=rh)
        assert proposed.status_code==200,proposed.text
        assert reviewer.post(f'/api/shifts/{shift_id}/variance-propose',json={'explanation':'تكرار فتح محضر عجز الجرد'},headers=rh).status_code==409
        assert reviewer.post(f'/api/shifts/{shift_id}/review',json={'decision':'recount','reason':'إعادة العد'},headers=rh).status_code==409
        assert reviewer.post(f'/api/shifts/{shift_id}/variance-decision',json={'decision':'approve','reason':'اعتمدته'},headers=rh).status_code==403
        authorized=owner.post(f'/api/shifts/{shift_id}/variance-decision',headers=oh,
            json={'decision':'approve','reason':'تسوية مؤقتة بعهدة عجز قيد البحث'})
        assert authorized.status_code==200,authorized.text
        assert authorized.json()['status']=='closed' and authorized.json()['adjustment_voucher_id']
        assert owner.post(f'/api/shifts/{shift_id}/variance-decision',headers=oh,
             json={'decision':'approve','reason':'اعتماد ثاني متكرر ممنوع'}).status_code==409
        sh=reviewer.get(f'/api/shifts/{shift_id}/movements').json()
        assert sh['expected_piasters']==107000 and sh['shift']['variance_piasters']==-2000
        assert len(sh['movements'])==3
        assert owner.post(f'/api/vouchers/{authorized.json()["adjustment_voucher_id"]}/reverse',headers=oh,
           json={'date':day,'reason':'لا يسمح بعكس التسوية المحاسبية المؤقتة'}).status_code==409
        variance_report=reviewer.get('/api/reconciliation/variances?month='+day[:7])
        assert variance_report.status_code==200 and variance_report.json()['shortage_piasters']==2000
        assert viewer.get('/api/reconciliation/variances?month='+day[:7]).status_code==403
        assert next(x for x in owner.get('/api/funds').json() if x['id']==f)['balance_piasters']==107000
        assert not any(x['code']=='cash_shortage' and x['direction']!='payment' for x in look['categories'])
        case=owner.get('/api/shifts?month='+day[:7]).json()['items'][0]['variance_case']
        assert case['status']=='approved' and case['adjustment_voucher_id']
        with connect() as db:
            row=db.execute('''SELECT ca.nature FROM vouchers v JOIN categories ca ON ca.id=v.category_id
                WHERE v.id=?''',(authorized.json()['adjustment_voucher_id'],)).fetchone()
            assert row['nature']=='asset' # shortage isn't reported as operating expense
        # Overage later, rejected case can be recounted rather than silently booked.
        evening=clerk.post('/api/shifts/open',json={'business_date':day,'shift':'evening','fund_id':f},headers=ch)
        assert evening.status_code==200,evening.text
        eid=evening.json()['id']
        assert clerk.post(f'/api/shifts/{eid}/count',json={'counted_amount':'1075'},headers=ch).status_code==200
        assert reviewer.post(f'/api/shifts/{eid}/variance-propose',headers=rh,
                 json={'explanation':'زيادة خمسة جنيهات في النقدية تحتاج مراجعـة'}).status_code==200
        rejected=owner.post(f'/api/shifts/{eid}/variance-decision',headers=oh,
                 json={'decision':'reject','reason':'تحقيق غير كاف، يجب إعادة العد'})
        assert rejected.status_code==200 and rejected.json()['status']=='submitted',rejected.text
        assert reviewer.post(f'/api/shifts/{eid}/review',headers=rh,
                 json={'decision':'recount','reason':'إعادة عد بعد رفض المحضر'}).status_code==200
        assert clerk.post(f'/api/shifts/{eid}/count',headers=ch,json={'counted_amount':'1075'}).status_code==200
        assert reviewer.post(f'/api/shifts/{eid}/variance-propose',headers=rh,
                 json={'explanation':'زيادة فعلية مؤقتة مثبتة في محضر تحقيق مستقل'}).status_code==200
        increased=owner.post(f'/api/shifts/{eid}/variance-decision',headers=oh,
                 json={'decision':'approve','reason':'اعتماد زيادة مالية قيد التحقق'})
        assert increased.status_code==200,increased.text
        assert next(x for x in owner.get('/api/funds').json() if x['id']==f)['balance_piasters']==107500
        summary=owner.get('/api/reconciliation/variances?month='+day[:7]).json()
        assert summary['overage_piasters']==500 and summary['approved_suspense_count']==2
        with connect() as db:
            case_statuses=[r[0] for r in db.execute('SELECT status FROM shift_variance_cases WHERE shift_session_id=? ORDER BY id',(eid,))]
            assert case_statuses==['rejected','approved']
        print('PASS — evidence BLOB/permissions/type/size/backup/immutability + investigation, shortage, overage, maker-checker, retries')


if __name__=='__main__':run()
