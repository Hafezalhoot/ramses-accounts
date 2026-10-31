from pathlib import Path
import re
root=Path(__file__).resolve().parents[1]
ui=root/'static'
js=ui/'app.js'
s=js.read_text()
needle=" $('#logoutButton').onclick=async()=>{try{await post('/api/logout');}catch{}state.me=null;state.csrf='';showLogin();};"
assert s.count(needle)==1
s=s.replace(needle, " const logout=async()=>{try{await post('/api/logout');}catch{}state.me=null;state.csrf='';hideMenu();showLogin();};\n $('#logoutButton').onclick=logout;$('#mobileLogoutButton').onclick=logout;")
needle=" const b=data.trial_balance,quality=data.coverage;"
assert s.count(needle)==1
s=s.replace(needle," const b=data.trial_balance,quality=data.coverage;\n const integrity=await api('/api/accounting/patient-reconciliation'+params);")
needle=" const rows=entries.map(a=>"
assert s.count(needle)==1
block=""" const integrityRows=integrity.checks.map(x=>`<div class="integrity-line"><div><strong>${esc(x.name)}</strong><small>رقابة ${esc(x.code)} · المستندات مقابل دفتر الأستاذ</small></div><div class="integrity-values"><span>الدفتر <b>${fmt(x.expected_piasters)}</b></span><span>الأستاذ <b>${fmt(x.ledger_piasters)}</b></span><span class="${x.matched?'integrity-match':'integrity-mismatch'}">${x.matched?'متطابق':'فرق '+fmt(x.difference_piasters)}</span></div></div>`).join('');
 const integrityPanel=`<section class="panel integrity-panel" aria-label="مطابقة الدفاتر المساعدة مع الأستاذ"><div class="panel-header"><div><h2>مطابقة حسابات المرضى</h2><p>الفواتير والتحصيل والمقدمات والإشعارات الدائنة والمرتجعات حتى نهاية الشهر المختار.</p></div><span class="chip ${integrity.matched?'approved':'rejected'}">${integrity.matched?'متطابق':'فرق يستوجب التحقيق'}</span></div><div class="integrity-list">${integrityRows}</div><p class="integrity-scope">${esc(integrity.scope)}</p></section>`;
"""
s=s.replace(needle,block+needle)
needle=" warn+metrics+`<section class=\"panel accounting-section\">"
assert s.count(needle)==1
s=s.replace(needle," warn+metrics+integrityPanel+`<section class=\"panel accounting-section\">")
needle=" const options=b.accounts.filter(x=>x.control!=='fund').map(x=>[x.id,x.code+' · '+x.name]);"
assert s.count(needle)==1
s=s.replace(needle," const protectedCodes=new Set(['1200','2300','2310','2350','1190','2190','2110','1120','4100','4195']);\n   const options=b.accounts.filter(x=>x.control!== 'fund'&&!protectedCodes.has(x.code)).map(x=>[x.id,x.code+' · '+x.name]);")
js.write_text(s)

html_file=ui/'index.html';html=html_file.read_text()
match=re.search(r'(<nav class="nav" id="mainNav" aria-label="أقسام النظام">)(.*?)(</nav>)',html,re.S)
assert match
buttons=re.findall(r'<button data-view="([^"]+)"[^>]*>.*?</button>',match.group(2),re.S)
assert len(buttons)==16,buttons
mapping={k:re.search(r'<button data-view="'+re.escape(k)+r'"[^>]*>.*?</button>',match.group(2),re.S).group(0) for k in buttons}
order=['dashboard','billing','new','shifts','calendar','funds','ledger','reviews','cashierRecoveries','lateEntries','cashierCorrections','bank','accounting','reports','payroll','legacy']
assert set(order)==set(buttons)
nav=[]
for k in order:
    if k=='billing':nav.append('<div class="nav-group-label">الكاشير والتحصيل</div>')
    if k=='ledger':nav.append('<div class="nav-group-label">المراجعات والتسويات</div>')
    if k=='accounting':nav.append('<div class="nav-group-label">الحسابات والتقارير</div>')
    nav.append(mapping[k])
html=html[:match.start(2)]+'\n      '+'\n      '.join(nav)+'\n    '+html[match.end(2):]
html_file.write_text(html)

corrections=ui/'financial_corrections_ui.js'
s=corrections.read_text()
needle='  const types=[\'invoice\',\'collection\',\'shift\',...(canReview?[\'voucher\']:[])];'
assert s.count(needle)==1
# Accessible cards reuse the same data action attributes as the desktop table.
s=s.replace(needle,'''  const types=['invoice','collection','shift',...(canReview?['voucher']:[])];
  const ticketActions=t=>`<div class="row-actions">
    <button type="button" class="btn btn-small btn-outline" data-correction-history="${t.id}">السجل</button>
    ${t.status==='open'&&canReview&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-secondary" data-correction-review="${t.id}">مراجعة</button>`:''}
    ${t.status==='triaged'&&canReview&&t.source_type==='invoice'&&t.issue_type==='wrong_amount'&&!t.resolved_credit_id&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-primary" data-correction-credit="${t.id}">تخفيض فاتورة غير محصلة</button>`:''}
    ${t.status==='triaged'&&canReview&&t.source_type==='collection'&&t.issue_type==='wrong_patient'&&!t.resolved_reallocation_id&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-primary" data-correction-reassign="${t.id}">نقل تخصيص إيصال</button>`:''}
    ${['open','needs_evidence'].includes(t.status)?`<button type="button" class="btn btn-small btn-outline" data-correction-note="${t.id}">إضافة إفادة</button>`:''}
    </div>`;
  const ticketStatus=t=>t.resolved_credit_id?'تخفيض معتمد':t.resolved_reallocation_id?'إعادة تخصيص معتمدة':correctionStatusLabels[t.status]||t.status;''')
start=s.index('         <td><div class="row-actions"><button type="button" class="btn btn-small btn-outline" data-correction-history="${t.id}">')
end=s.index('</div></td></tr>`).',start) if False else s.index('           </div></td></tr>`',start)
s=s[:start]+'''         <td>${ticketActions(t)}</td></tr>`'''+s[end+len('           </div></td></tr>`'):]
needle="</tbody></table></div></section>`;"
assert s.count(needle)==1
s=s.replace(needle,"""</tbody></table></div>
      <div class="corrections-mobile" aria-label="بطاقات بلاغات التصحيح">${records.map(t=>`<article class="correction-mobile-card"><div class="correction-mobile-top"><div><strong>${esc(t.source_ref)}</strong><small>#${integer(t.id)} · ${esc(correctionTypeLabels[t.source_type]||t.source_type)}</small></div><span class="chip ${t.resolved_credit_id||t.resolved_reallocation_id?'approved':t.status==='open'?'pending':'archive'}">${esc(ticketStatus(t))}</span></div><div class="correction-mobile-issue"><span>المشكلة</span><strong>${esc(correctionIssueLabels[t.issue_type]||t.issue_type)}</strong></div><div class="correction-mobile-owner">المُبلّغ: ${esc(t.opened_by_name)}</div>${ticketActions(t)}</article>`).join('')||'<p class="empty">لا توجد بلاغات تصحيح.</p>'}</div>
      </section>`;""")
# Mutation while card & table both present: event delegation handlers apply to each element, okay.
corrections.write_text(s)

css=ui/'styles.css';style=css.read_text()
style+='''
/* G2I — Financial controls must be readable, discoverable and safe on phones. */
:root{--subtle:#4f6570}
input::placeholder,textarea::placeholder{color:#556e77}
.metric-foot,.unit,.data-table .tiny,.table-footer,.hint,.empty,
.chart-x,.summary-note,.form-grid .info-inline{color:#526b73}
.data-table th{color:#4d666d;font-size:12px}
.data-table td{font-size:13px}
.metric-foot,.mini-metric span,.form-help,.helper-note{font-size:12px}
.nav-group-label{padding:20px 20px 7px;font-size:11px;font-weight:800;color:#bad5d8;letter-spacing:.025em}
.sidebar-signout{display:none;min-height:44px;width:calc(100% - 28px);margin:14px;color:#fff;background:#234851;border:1px solid #44676a;align-items:center;gap:10px}
.sidebar-signout:hover{background:#2e5b61}
.integrity-panel{margin-bottom:20px}
.integrity-list{display:grid;gap:0;padding:0 18px}
.integrity-line{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:16px 2px;border-top:1px solid var(--border)}
.integrity-line strong{font-size:14px;display:block}
.integrity-line small{font-size:12px;color:var(--muted);display:block;margin-top:2px}
.integrity-values{display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-size:12px}
.integrity-values b{font-variant-numeric:tabular-nums;color:var(--ink);margin-inline-start:4px}
.integrity-match{color:#0e7255;font-weight:800}
.integrity-mismatch{color:#aa3e36;font-weight:800}
.integrity-scope{font-size:12px;color:var(--muted);padding:12px 22px 18px;margin:0}
.corrections-mobile{display:none}
@media(max-width:940px){.sidebar-signout{display:flex}}
@media(max-width:700px){
  .integrity-line{display:block;padding:15px 0}
  .integrity-values{margin-top:12px;gap:10px;justify-content:space-between}
  .financial-correction-form input,.financial-correction-form select{font-size:16px}
  .corrections-mobile{display:grid;gap:12px;padding:12px 0}
  .financial-correction-form+ .tiny{font-size:12px}
  .panel:has(.corrections-mobile) .table-wrap{display:none}
  .correction-mobile-card{border:1px solid var(--border);border-radius:13px;padding:16px;background:white}
  .correction-mobile-top{display:flex;justify-content:space-between;gap:8px;align-items:flex-start}
  .correction-mobile-top strong{display:block;font-size:14px;overflow-wrap:anywhere}
  .correction-mobile-top small{display:block;font-size:12px;color:var(--muted);margin-top:3px}
  .correction-mobile-top .chip{max-width:45%;white-space:normal;text-align:center;line-height:1.5}
  .correction-mobile-issue{display:grid;gap:4px;margin-top:13px;font-size:12px}
  .correction-mobile-issue span,.correction-mobile-owner{color:var(--muted)}
  .correction-mobile-issue strong{font-size:14px}
  .correction-mobile-owner{font-size:12px;margin:9px 0 12px}
  .correction-mobile-card .row-actions .btn{min-height:44px;flex:1 1 120px}
  .topbar .logout{display:grid!important;min-height:40px;min-width:40px;place-items:center}
  .topbar-right{min-width:0;flex:1}
  .crumb{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .crumb strong{overflow:hidden;text-overflow:ellipsis}
}
@media(max-width:380px){.topbar-left{gap:3px}.user-pill{min-width:0}}
'''
css.write_text(style)
print('Polished financial reconciliation, mobile logout, menu grouping and correction cards.')
