"""S9 test-first Chromium: date/fund changes in both opening dialogs.

Browser API requests are intercepted with synthetic fixtures; not a hospital
network or HTTPS acceptance test.
"""
from browser_helpers import chromium_options
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]


def run():
    from playwright.sync_api import sync_playwright
    today=datetime.now(ZoneInfo('Africa/Cairo')).date()
    day, tomorrow, closed=(today.isoformat(),(today+timedelta(days=1)).isoformat(),
                            (today+timedelta(days=2)).isoformat())
    month=day[:7]
    old='\u0648\u0631\u062f\u064a\u0629 \u0642\u062f\u064a\u0645\u0629'
    new='\u0648\u0631\u062f\u064a\u0629 \u0645\u0633\u062a\u0642\u0628\u0644\u064a\u0629'
    html=(ROOT/'static/index.html').read_text()
    for name in ('app.js','billing.js'):
        html=html.replace(f'<script src="/static/{name}" defer></script>','')
    html=html.replace('<link rel="stylesheet" href="/static/styles.css">','')
    fixtures={
        '/api/me':{'id':1,'username':'s9_owner','role':'owner','csrf':'synthetic','environment':'staging'},
        '/api/lookups':{'funds':[{'id':2,'name':'Synthetic station cash','kind':'cash'},
                                 {'id':4,'name':'Synthetic central cash','kind':'cash'}],
                        'employees':[],'departments':[],'categories':[],'shifts':[]},
        f'/api/dashboard?month={month}':{'daily':[],'latest':[],'pending':0},
        f'/api/shifts?month={month}':{'month':month,'items':[],
            'schedule':[{'code':'morning','start':'08:00','end':'16:00'}],
            'suggested':{'business_date':day,'shift':'early'}},
        '/api/cashier/plans':{'points':[{'id':7,'fund_id':2,'kind':'external','versions':[
            {'effective_from':day,'slots':[{'code':'early','name':old,'start':'00:00'}]},
            {'effective_from':tomorrow,'slots':[{'code':'future','name':new,'start':'00:00'}]}]}]},
        f'/api/shifts/coverage?month={month}':{'month':month,'summary':{},'items':[],
                                                'days':[],'points':[]},
        '/api/beds/catalog':{'items':[]},
        '/api/billing/config':{'points':[{'id':7,'fund_id':2,'name':'Synthetic station cash',
                     'kind':'external','active':True,'active_shift':None,'own_open_shift':False}],
              'services':[],'payment_channels':[],'shift_schedule':[],
              'suggested_shift':{'business_date':day,'shift':'early'}},
        '/api/billing/cases?point_id=7':{'items':[]},
    }
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True,**chromium_options(),
                                          args=['--no-sandbox','--disable-dev-shm-usage'])
        try:
            page=browser.new_page(viewport={'width':1280,'height':800})
            page.set_default_timeout(9000)
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.set_content(html)
            page.add_style_tag(content=(ROOT/'static/styles.css').read_text())
            page.evaluate('''({fixtures,day,tomorrow,closed,oldName,newName}) => {
                window.fetch=async url=>{
                    let payload=fixtures[url];
                    if(url.startsWith('/api/shifts/open-options?')){
                        const q=new URL(url,'http://example.test').searchParams;
                        const selected=q.get('business_date');
                        const fund=q.get('fund_id');
                        if(selected===day)await new Promise(r=>setTimeout(r,65));
                        else await new Promise(r=>setTimeout(r,4));
                        const slots=selected===closed?[]:
                          fund==='4'?[{code:'treasury',name:'Central shift',start:'00:00',end:'00:00'}]:
                          selected===tomorrow?[{code:'future',name:newName,start:'00:00',end:'00:00'}]:
                          [{code:'early',name:oldName,start:'00:00',end:'00:00'}];
                        payload={business_date:selected,fund_id:Number(fund),slots,
                            can_open:selected===day && slots.length>0,
                            message:selected!==day?'Future/closed date':''};
                    }
                    const found=payload!==undefined;
                    return {ok:found,status:found?200:404,json:async()=>payload??{detail:'No fixture '+url}};
                };
            }''',{'fixtures':fixtures,'day':day,'tomorrow':tomorrow,'closed':closed,
                  'oldName':old,'newName':new})
            page.add_script_tag(content=(ROOT/'static/billing.js').read_text())
            page.add_script_tag(content=(ROOT/'static/app.js').read_text())
            page.wait_for_selector('#shell:not([hidden])')
            page.locator('#mainNav [data-view=shifts]').click()
            page.wait_for_selector('#newShift')
            page.locator('#newShift').click()
            page.locator('#modal [name=fund_id]').select_option('2')
            page.wait_for_function('''() => [...document.querySelectorAll('#modal [name=shift] option')]
                .some(x=>x.value==='early')''')
            assert old in page.locator('#modal [name=shift]').inner_text()
            assert page.locator('#modalConfirm').is_enabled()
            page.locator('#modal [name=business_date]').fill(tomorrow)
            page.wait_for_function('''() => [...document.querySelectorAll('#modal [name=shift] option')]
                .some(x=>x.value==='future')''')
            assert new in page.locator('#modal [name=shift]').inner_text()
            assert old not in page.locator('#modal [name=shift]').inner_text()
            assert page.locator('#modalConfirm').is_disabled()
            page.locator('#modal [name=business_date]').fill(day)
            page.locator('#modal [name=fund_id]').select_option('4')
            page.wait_for_function('''() => [...document.querySelectorAll('#modal [name=shift] option')]
                .some(x=>x.value==='treasury')''')
            page.wait_for_timeout(160)
            assert 'early' not in [x.get_attribute('value') for x in page.locator('#modal [name=shift] option').all()]
            page.locator('#modal [name=business_date]').fill(closed)
            page.wait_for_function('''() => document.querySelector('#modalConfirm').disabled''')
            assert page.locator('#modal [name=shift]').input_value()==''
            page.locator('#modalCancel').click()
            page.set_viewport_size({'width':375,'height':812})
            assert page.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth+1')
            page.locator('#showSidebar').click()
            page.locator('#mainNav [data-view=billing]').click()
            page.wait_for_selector('#billingOpenShift')
            page.locator('#billingOpenShift').click()
            page.wait_for_function('''() => [...document.querySelectorAll('#modal [name=shift] option')]
                .some(x=>x.value==='early')''')
            assert old in page.locator('#modal [name=shift]').inner_text()
            page.locator('#modal [name=business_date]').fill(tomorrow)
            page.wait_for_function('''() => [...document.querySelectorAll('#modal [name=shift] option')]
                .some(x=>x.value==='future')''')
            assert page.locator('#modalConfirm').is_disabled()
            page.locator('#modalCancel').click()
            assert not errors,errors
            print('PASS S9 Chromium 1280/375: station and date changes, future blocked, stale responses ignored, billing picker matches')
        finally:
            browser.close()


if __name__=='__main__':
    run()
