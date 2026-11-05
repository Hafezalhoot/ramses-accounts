"""Pricing contracts actually flow through clinical fulfillment, invoice and GL."""
import os,sys,tempfile,json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]


def run():
    with tempfile.TemporaryDirectory(prefix='s14-pricing-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'test.sqlite3'),RAMSES_ADMIN_USER='owner',RAMSES_ADMIN_PASSWORD='synthetic_s14_owner_password')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','RAMSES_SECURE_COOKIES'):os.environ.pop(key,None)
        from bootstrap import initialize,connect
        initialize()
        from app import app
        from fastapi.testclient import TestClient
        owner,clerk,outsider=TestClient(app),TestClient(app),TestClient(app)
        def ok(r,status=200):
            assert r.status_code==status,(r.status_code,r.text[:700]);return r.json() if status==200 else None
        oh={'X-CSRF-Token':ok(owner.post('/api/login',json={'username':'owner','password':'synthetic_s14_owner_password'}))['csrf']}
        def post(path,data=None,client=owner,headers=oh,status=200):return ok(client.post(path,json=data,headers=headers),status)
        cid=post('/api/users',{'username':'cashier','password':'synthetic_s14_cashier_password','role':'clerk'})['id']
        ch={'X-CSRF-Token':ok(clerk.post('/api/login',json={'username':'cashier','password':'synthetic_s14_cashier_password'}))['csrf']}
        cfg=ok(owner.get('/api/billing/config'));point=next(p['id'] for p in cfg['points'] if p['kind']=='external')
        post(f'/api/billing/points/{point}/assign',{'user_id':cid})
        dept=next(d['id'] for d in ok(owner.get('/api/lookups'))['departments'] if d['code']=='CLINIC')
        service=post('/api/billing/services',{'code':'OXYGEN_HOUR','name':'أكسجين للساعة — وهمي','department_id':dept,'suggested_point':'either'})['id']
        day=datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat();tomorrow=(datetime.fromisoformat(day)+timedelta(days=1)).date().isoformat()
        cash=post('/api/pricing/lists',{'code':'CASH','name':'قائمة نقدي تجريبية'})['id']
        corporate=post('/api/pricing/lists',{'code':'CONTRACT','name':'قائمة تعاقد تجريبية'})['id']
        ipd=post('/api/pricing/locations',{'code':'IPD','name':'غرفة داخلي','department_id':dept})['id']
        theatre=post('/api/pricing/locations',{'code':'OR','name':'غرفة عمليات','department_id':dept})['id']
        post(f'/api/pricing/services/{service}/details',{'unit':'ساعة','description':'استهلاك أكسجين بالساعة — وصف وهمي'})
        people={}
        for code,category in (('DOC_A','doctor'),('DOC_B','doctor'),('NURSE_A','nurse'),('NURSE_B','nurse')):
            people[code]=post('/api/pricing/people',{'code':code,'name':'شخص وهمي '+code,'category':category})['id']
        rules=[{'target':'person','person_id':people['DOC_A'],'when':'always','basis':'collected','percentage':'10','distribution':'shared'},
               {'target':'category','category':'nurse','when':'performed','basis':'collected','percentage':'20','distribution':'shared'}]
        def rate(pl,loc,amount,cost=None,rules=None,date=day):
            return post('/api/pricing/rates',{'price_list_id':pl,'location_id':loc,'service_id':service,'valid_from':date,'amount':amount,'estimated_cost':cost,'rules':rules or []})
        rate(cash,ipd,'200','60',rules);rate(cash,theatre,'100','25');rate(corporate,ipd,'180',None)
        post(f'/api/pricing/services/{service}/details',{'unit':'دقيقة','description':'لا تحويل وحدة الساعة تحت نفس التعريفة'},status=409)
        rate(cash,ipd,'220','65',rules,date=tomorrow)
        qbody={'price_list_id':cash,'location_id':ipd,'lines':[{'service_id':service,'quantity':1,'performer_ids':[people['NURSE_A'],people['NURSE_B']]}]}
        q=post('/api/pricing/quote',qbody)
        assert q['gross_piasters']==20000 and q['net_piasters']==20000
        assert q['cost_complete'] and q['estimated_cost_piasters']==6000
        shares=q['lines'][0]['commission_preview'];assert sum(x['amount_piasters'] for x in shares)==6000
        assert {x['person_id']:x['amount_piasters'] for x in shares}=={people['DOC_A']:2000,people['NURSE_A']:2000,people['NURSE_B']:2000}
        assert post('/api/pricing/quote',{**qbody,'location_id':theatre})['net_piasters']==10000
        incomplete=post('/api/pricing/quote',{**qbody,'price_list_id':corporate})
        assert not incomplete['cost_complete'] and incomplete['estimated_cost_piasters'] is None
        post('/api/pricing/rates',{'price_list_id':cash,'location_id':ipd,'service_id':service,'valid_from':day,'amount':'200',
             'rules':[dict(rules[0],percentage='101')]},status=422)
        # A signed-in clerk cannot inspect costs/rules or manage the catalog.
        post('/api/pricing/lists',{'code':'BAD','name':'ممنوع'},clerk,ch,status=403)
        public=ok(clerk.get('/api/pricing/catalog'));assert 'estimated_cost' not in json.dumps(public)
        assert 'rules' not in json.dumps(public) and outsider.get('/api/pricing/catalog').status_code==401
        patient=post('/api/billing/patients',{'display_name':'مريض تسعير وهمي','request_id':'s14_patient_0000001'},clerk,ch)
        case=post('/api/billing/cases',{'patient_id':patient['id'],'kind':'outpatient','point_id':point,'business_date':day,'request_id':'s14_case_0000000001'},clerk,ch)['id']
        public_quote=post('/api/pricing/quote',{**qbody,'case_id':case},clerk,ch)
        # A cashier can reproduce the concurrency token from public values.
        # Including hidden low-entropy costs/rules creates an offline guessing oracle.
        import hashlib
        token_input={'day':day,'price_list_id':cash,'package_version_id':None,'lines':public_quote['lines']}
        expected=hashlib.sha256(json.dumps(token_input,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        assert public_quote['quote_hash']==expected,'Quote token must not fingerprint private costs or fee rules'
        post(f'/api/billing/cases/{case}/services',{'service_id':service,'quantity':1,'request_id':'s14_bypass_00000001'},clerk,ch,status=409)
        items=[{'service_id':service,'location_id':ipd,'quantity':2},{'service_id':service,'location_id':theatre,'quantity':1}]
        package_body={'code':'OP_TEST','name':'باقة أكسجين وهمية','price_list_id':cash,'valid_from':day,'items':items,'final_amount':'450'}
        preview=post('/api/pricing/package-preview',package_body)
        assert (preview['gross_piasters'],preview['net_piasters'],preview['discount_piasters'])==(50000,45000,5000)
        assert preview['estimated_cost_piasters']==14500
        post('/api/pricing/packages',{**package_body,'preview_hash':'0'*64},status=409)
        package=post('/api/pricing/packages',{**package_body,'preview_hash':preview['preview_hash']})
        body={'price_list_id':cash,'case_id':case,'package_version_id':package['id'],'performers':[
             {'service_id':service,'location_id':ipd,'person_ids':[people['NURSE_A'],people['NURSE_B']]}]}
        quote=post('/api/pricing/quote',body,clerk,ch)
        assert [x['net_piasters'] for x in quote['lines']]==[36000,9000]
        assert 'commission_preview' not in json.dumps(quote) and 'estimated_cost' not in json.dumps(quote)
        orderbody={**body,'quote_hash':quote['quote_hash'],'request_id':'s14_order_000000001'}
        order=post('/api/pricing/orders',orderbody,clerk,ch)
        replay=post('/api/pricing/orders',orderbody,clerk,ch);assert replay['id']==order['id'] and replay['replayed']
        lines=order['line_ids'];assert len(lines)==2
        # Later prices do not rewrite the accepted contract or historical lines.
        rate(cash,ipd,'999','500')
        post('/api/pricing/orders',{**qbody,'case_id':case,'quote_hash':q['quote_hash'],'request_id':'s14_stale_000000001'},clerk,ch,status=409)
        post(f'/api/billing/lines/{lines[0]}/fulfill')
        post(f'/api/billing/cases/{case}/drafts',{'request_id':'s14_partial_0000001'},clerk,ch,status=409)
        post(f'/api/billing/lines/{lines[1]}/cancel',{'reason':'لا إلغاء جزئي للباقة'},clerk,ch,status=409)
        post(f'/api/billing/lines/{lines[1]}/fulfill')
        detail=ok(clerk.get(f'/api/billing/cases/{case}'))
        assert detail['unbilled_piasters']==45000
        assert detail['services'][0]['unit_price_piasters']==20000
        draft=post(f'/api/billing/cases/{case}/drafts',{'request_id':'s14_draft_000000001'},clerk,ch)
        assert draft['total_piasters']==45000
        inv=post(f'/api/billing/drafts/{draft["id"]}/issue',{'request_id':'s14_invoice_0000001'},clerk,ch)
        assert inv['amount_piasters']==45000
        printed=clerk.get(f'/api/billing/invoices/{inv["id"]}/print')
        assert printed.status_code==200 and '450.00' in printed.text and 'خصم' in printed.text
        # The user's exact policy, on the full production schema/API: two
        # occurrences, different doctors, fixed100 each; reject one, approve one.
        fixed=[{'target':'category','category':'doctor','when':'performed','kind':'fixed',
                'fixed_amount':'100','discount_affects':False,'basis':'collected','distribution':'shared'}]
        rate(cash,ipd,'200','40',fixed)
        second=post('/api/billing/cases',{'patient_id':patient['id'],'kind':'outpatient','point_id':point,
                    'business_date':day,'request_id':'s14_case_0000000002'},clerk,ch)['id']
        fixed_body={'case_id':second,'price_list_id':cash,'location_id':ipd,'lines':[{'service_id':service,'quantity':2,
            'occurrence_performers':[{'occurrence_no':1,'person_ids':[people['DOC_A']]},
                                     {'occurrence_no':2,'person_ids':[people['DOC_B']]}]}]}
        fixed_quote=post('/api/pricing/quote',fixed_body,clerk,ch)
        fixed_order=post('/api/pricing/orders',{**fixed_body,'quote_hash':fixed_quote['quote_hash'],'request_id':'s14_fixed_order_001'},clerk,ch)
        post(f'/api/billing/lines/{fixed_order["line_ids"][0]}/fulfill')
        fdraft=post(f'/api/billing/cases/{second}/drafts',{'request_id':'s14_fixed_draft_001'},clerk,ch)['id']
        finvoice=post(f'/api/billing/drafts/{fdraft}/issue',{'request_id':'s14_fixed_issue_001'},clerk,ch)['id']
        proposals=[x for x in ok(owner.get('/api/service-fees/queue'))['items'] if x['invoice_id']==finvoice]
        assert len(proposals)==2 and {x['amount_piasters'] for x in proposals}=={10000}
        assert {x['person_id'] for x in proposals}=={people['DOC_A'],people['DOC_B']}
        assert ok(owner.get('/api/service-fees/balances'))['items']==[]
        approved=None
        for proposal in proposals:
            decision='reject' if proposal['occurrence_no']==1 else 'approve'
            body={k:proposal[k] for k in ('line_id','occurrence_no','rule_index','person_id','calculation_hash')}
            body.update(expected_amount_piasters=proposal['amount_piasters'],decision=decision,
                        reason='قرار مراجعة مستقل لكل مرة تنفيذ وهمية',request_id=f's14_fee_decide_000{proposal["occurrence_no"]}')
            result=post('/api/service-fees/decisions',body)
            if decision=='approve':approved=result['id']
        balances=ok(owner.get('/api/service-fees/balances'))['items']
        assert len(balances)==1 and balances[0]['person_id']==people['DOC_B'] and balances[0]['amount_piasters']==10000
        credit=post(f'/api/billing/cases/{second}/credits',{'invoice_id':finvoice,'amount':'1','request_id':'s14_fee_credit_0001','reason':'اختبار تخفيض بعد استحقاق أتعاب معتمد'},clerk,ch)['id']
        post(f'/api/billing/credits/{credit}/decision',{'decision':'approve','note':'يجب أن يتوقف قبل عكس المستحق'},status=409)
        third=TestClient(app)
        third_id=post('/api/users',{'username':'third_reviewer','password':'synthetic_s14_reviewer_password','role':'reviewer'})['id']
        post(f'/api/billing/points/{point}/assign',{'user_id':third_id})
        th={'X-CSRF-Token':ok(third.post('/api/login',json={'username':'third_reviewer','password':'synthetic_s14_reviewer_password'}))['csrf']}
        post(f'/api/service-fees/decisions/{approved}/reverse',{'reason':'عكس موثق لاختبار تصحيح الفاتورة','request_id':'s14_fee_reverse_001'},third,th)
        post(f'/api/billing/credits/{credit}/decision',{'decision':'approve','note':'اعتماد بعد عكس الأتعاب'})
        assert not [x for x in ok(owner.get('/api/service-fees/queue'))['items'] if x['invoice_id']==finvoice]
        with connect() as c:
            journal=c.execute('SELECT journal_id FROM billing_invoices WHERE id=?',(inv['id'],)).fetchone()[0]
            assert c.execute('SELECT SUM(debit_piasters),SUM(credit_piasters) FROM gl_lines WHERE journal_id=?',(journal,)).fetchone()[:]==(45000,45000)
            for table in ('pricing_rate_versions','pricing_package_versions','pricing_line_terms','pricing_orders'):
                try:c.execute('DELETE FROM '+table)
                except Exception:pass
                else:raise AssertionError('Mutable pricing evidence: '+table)
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            accounts={r['code']:r['id'] for r in c.execute("SELECT id,code FROM gl_accounts WHERE code IN ('2320','5196')")}
        post('/api/accounting/journals',{'date':day,'memo':'لا مستحقات أشخاص عبر قيد يدوي عام',
             'lines':[{'account_id':accounts['5196'],'debit':'1','credit':'0'},
                      {'account_id':accounts['2320'],'debit':'0','credit':'1'}]},status=409)
        post(f'/api/billing/points/{point}/assign',{'user_id':cid,'active':False})
        post('/api/pricing/orders',orderbody,clerk,ch,status=403)
        print('PASS S14 pricing: lists/locations, exact bundle allocation, cost secrecy, provider rule previews, snapshots, no bypass, independent service proof, net invoice and balanced GL')


if __name__=='__main__':run()
