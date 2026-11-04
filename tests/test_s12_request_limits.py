"""Oversized uploads must be rejected before multipart spooling/DB effects.

Exercises actual parser/files and synthetic SQLite; streamed bodies must not
bypass the cap by omitting or understating Content-Length.
"""
import asyncio
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MIB = 1024 * 1024


def run():
    with tempfile.TemporaryDirectory(prefix='ramses-s12-limit-') as folder:
        os.environ.update(RAMSES_DB_PATH=str(Path(folder)/'synthetic.sqlite3'),
                          RAMSES_ADMIN_USER='s12_owner',
                          RAMSES_ADMIN_PASSWORD='synthetic_s12_owner_password_long')
        for key in ('GOOGLE_SHEET_ID','GOOGLE_SERVICE_ACCOUNT_JSON','GOOGLE_SHEET_TARGET'):
            os.environ.pop(key, None)
        from bootstrap import initialize, connect
        from app import app
        from fastapi.testclient import TestClient
        import starlette.formparsers as parser
        import httpx
        initialize()
        owner = TestClient(app)
        signed = owner.post('/api/login', json={'username':'s12_owner',
                            'password':'synthetic_s12_owner_password_long'})
        assert signed.status_code == 200, signed.text
        headers = {'X-CSRF-Token':signed.json()['csrf']}
        look = owner.get('/api/lookups').json()
        from datetime import datetime
        from zoneinfo import ZoneInfo
        today = datetime.now(ZoneInfo('Africa/Cairo')).date().isoformat()
        voucher = owner.post('/api/vouchers', headers=headers, json={
            'date':today,'kind':'receipt','department_id':look['departments'][0]['id'],
            'category_id':next(x['id'] for x in look['categories'] if x['code']=='medical_revenue'),
            'from_fund_id':next(x['id'] for x in look['funds'] if x['code']=='cash_main'),
            'shift':'central','amount':'1','description':'Synthetic S12 attachment limit test'})
        assert voucher.status_code == 200, voucher.text
        url=f"/api/vouchers/{voucher.json()['id']}/attachments"
        tables=('voucher_attachments','vouchers','audit_log','fund_movements','gl_journals')
        with connect() as c:
            before={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        real_spool=parser.SpooledTemporaryFile
        spools=[]
        def observed_spool(*args, **kwargs):
            spool=real_spool(*args, **kwargs)
            record={'file':spool,'bytes':0};spools.append(record)
            write=spool.write
            def observed_write(data):
                record['bytes']+=len(data)
                return write(data)
            spool.write=observed_write
            return spool
        # Public and signed requests: an excessive declaration must never reach
        # the parser, even on routes with different authorization requirements.
        with patch.object(parser,'SpooledTemporaryFile',observed_spool):
            for client, extra in ((TestClient(app),{}),(owner,headers)):
                response=client.post(url,headers=extra,
                    files={'file':('oversized.pdf',b'%PDF-1.4\n'+b'x'*(8*MIB),'application/pdf')})
                assert response.status_code == 413, (response.status_code,response.text)
            assert not spools, 'Declared oversized upload reached multipart parser'
            response=owner.post(url,headers=headers,files=[
                ('file',('first.pdf',b'x'*(4*MIB),'application/pdf')),
                ('extra',('second.pdf',b'x'*(4*MIB),'application/pdf'))])
            assert response.status_code == 413
            assert not spools, 'Multiple parts bypassed total request cap'
        boundary='synthetic-s12-boundary'
        prefix=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="stream.pdf"\r\n'
                'Content-Type: application/pdf\r\n\r\n').encode()
        suffix=f'\r\n--{boundary}--\r\n'.encode()
        async def streaming_probe(declared):
            consumed=[]
            async def body():
                yield prefix
                for _ in range(16):
                    consumed.append(MIB)
                    yield b'x'*MIB
                yield suffix
            h={'Content-Type':f'multipart/form-data; boundary={boundary}', **headers,
               'Cookie':'ramses_sid='+owner.cookies.get('ramses_sid')}
            if declared is not None:h['Content-Length']=declared
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
                response=await client.post(url,headers=h,content=body())
            assert response.status_code == 413,(declared,response.status_code,response.text)
            assert sum(consumed) <= 7*MIB, 'Read unbounded stream before rejection'
        for declared in (None,'1'):
            spools.clear()
            with patch.object(parser,'SpooledTemporaryFile',observed_spool):
                asyncio.run(streaming_probe(declared))
            assert sum(x['bytes'] for x in spools) <= 7*MIB
            assert all(x['file'].closed for x in spools), 'Rejected partial uploads leaked temporary files'
        with connect() as c:
            assert before=={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in tables}
        # A permitted 6 MiB file still works through the actual upload handler.
        legitimate=b'%PDF-1.4\n'+b'x'*(6*MIB-len(b'%PDF-1.4\n%%EOF'))+b'%%EOF'
        accepted=owner.post(url,headers=headers,files={'file':('within-cap.pdf',legitimate,'application/pdf')})
        assert accepted.status_code == 200, accepted.text
        attachments=owner.get(url).json()
        assert len(attachments)==1 and attachments[0]['file_size']==6*MIB, attachments
        # The per-file 6 MiB cap still applies below the total request cap.
        rejected=owner.post(url,headers=headers,files={'file':('over-file-cap.pdf',legitimate+b'x','application/pdf')})
        assert rejected.status_code == 413,rejected.text
        assert len(owner.get(url).json())==1
        # Oversized non-multipart data also stops before password verification.
        huge_json=TestClient(app).post('/api/login',json={
            'username':'s12_owner','password':'x'*(8*MIB)})
        assert huge_json.status_code == 413,huge_json.text
        assert owner.get('/health').status_code == 200
        with connect() as c:
            assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
        print('PASS S12 body limit: early 413, chunked/false length bounded, temp files closed, 6MiB upload accepted, no rejected financial effects')


if __name__=='__main__':
    run()
