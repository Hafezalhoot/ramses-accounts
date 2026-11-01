"use strict";

const state = {
  me:null, csrf:"", lookups:null, view:"dashboard",
  month:new Date().toLocaleDateString("sv-SE").slice(0,7), shiftMonth:new Date().toLocaleDateString("sv-SE").slice(0,7), payrollMonth:new Date().toLocaleDateString("sv-SE").slice(0,7),
  ledger:{page:1,q:"",kind:"",status:"",department:""}, legacy:{page:1,q:"",issues_only:false},
  bankMonth:new Date().toLocaleDateString("sv-SE").slice(0,7), bankFundId:null,
  prefill:null, payrollWorkPage:1, payrollAdjPage:1
};
const $ = (s,root=document)=>root.querySelector(s);
const $$ = (s,root=document)=>[...root.querySelectorAll(s)];
const ico=(n)=>`<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
const esc=(v)=>String(v??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;");
const money=(c)=>Number(c||0)/100;
const fmt=(c)=>money(c).toLocaleString("en-US",{maximumFractionDigits:2,minimumFractionDigits:2});
const integer=(x)=>Number(x||0).toLocaleString("en-US");
const labelType={receipt:"إيراد / تحصيل",payment:"صرف",transfer:"تحويل بين حسابات"};
const shiftStateLabels={open:"قيد التشغيل",submitted:"بانتظار مراجعة الجرد",closed:"وردية مقفلة"};
const stateLabels={pending:"بانتظار الاعتماد",approved:"معتمد",rejected:"مرفوض",reversed:"تمت التسوية"};
const roleLabels={owner:"مدير النظام",reviewer:"مراجع الحسابات",clerk:"مدخل بيانات",viewer:"مشاهد التقارير",clinician:"موثّق خدمات طبي - اختبار"};
const categoryNatures={revenue:"إيراد تشغيل",expense:"تكلفة تشغيل",asset:"شراء أصل / مخزون",liability:"التزام / قرض",equity:"حقوق ملكية",payroll_payment:"سداد راتب مستحق",advance:"سلفة موظف"};
const kindChip=(k)=>`<span class="chip type-${esc(k)}">${labelType[k]||esc(k)}</span>`;
const statusChip=(s)=>`<span class="chip ${esc(s)}">${stateLabels[s]||esc(s)}</span>`;
const opt=(id,label,selected)=>`<option value="${esc(id)}" ${String(selected??"")===String(id)?"selected":""}>${esc(label)}</option>`;
const empty=(txt)=>`<div class="empty">${ico("file")}${esc(txt)}</div>`;
const th=(cols)=>`<thead><tr>${cols.map(x=>`<th>${esc(x)}</th>`).join("")}</tr></thead>`;
const table=(cols,rows)=>`<div class="table-wrap"><table class="data-table">${th(cols)}<tbody>${rows||`<tr><td colspan="${cols.length}" class="empty">لا توجد بيانات لعرضها</td></tr>`}</tbody></table></div>`;
const periodInput=(value,id)=>`<label class="compact-field">الفترة <input class="month-input" id="${esc(id)}" type="month" value="${esc(value)}" aria-label="الفترة المحاسبية"></label>`;
const head=(tag,title,desc,actions="")=>`<div class="page-heading"><div><div class="eyebrow">${tag}</div><h1>${title}</h1><p>${desc}</p></div><div class="page-actions">${actions}</div></div>`;
const metric=(title,amt,variant="",foot="",icon="wallet",unit="ج.م")=>`<article class="metric ${variant}"><div class="metric-head"><span>${title}</span><span class="metric-icon">${ico(icon)}</span></div><strong class="metric-number ${variant==='expense'?'bad':variant==='income'?'good':''}">${unit==='ج.م'?fmt(amt):integer(amt)}${unit?` <span class="unit">${unit}</span>`:""}</strong><div class="metric-foot">${foot}</div></article>`;

async function api(path,options={}) {
  const method=options.method||"GET";
  const headers={"Accept":"application/json",...(options.body && !(options.body instanceof FormData)?{"Content-Type":"application/json"}:{}),...(method!=="GET"&&method!=="HEAD"&&state.csrf?{"X-CSRF-Token":state.csrf}:{}),...(options.headers||{})};
  let response;
  try{response=await fetch(path,{...options,headers,credentials:"same-origin"});}
  catch {throw Error("تعذر الاتصال بالخادم؛ افحص الشبكة وحاول مجددًا");}
  let result={};
  try{result=await response.json();}catch {result={};}
  if(!response.ok){
    if(response.status===401&&path!=="/api/login") showLogin();
    throw Error(typeof result.detail==="string"?result.detail:`خطأ بالخادم (${response.status})`);
  }
  return result;
}
function post(path,data={}){return api(path,{method:"POST",body:JSON.stringify(data)});}
function toast(message,bad=false){const e=$("#toast");e.textContent=message;e.classList.toggle("error",bad);e.hidden=false;clearTimeout(toast.timer);toast.timer=setTimeout(()=>e.hidden=true,4800);}
function errorView(message){$("#content").innerHTML=`<div class="info-box warning">${ico("alert")}<div>${esc(message)}</div></div>`;}
function showLogin(){state.me=null;state.csrf="";state.view="dashboard";$("#content").replaceChildren();$("#shell").hidden=true;$("#loginPage").hidden=false;}
async function login(e){
 e.preventDefault();const form=e.currentTarget;$("#loginError").hidden=true;
 const button=$("button[type=submit]",form);button.disabled=true;
 try{
   const data=await post("/api/login",Object.fromEntries(new FormData(form)));
   state.me=data;state.csrf=data.csrf;form.reset();await bootstrapUI();
 }catch(error){$("#loginError").textContent=error.message;$("#loginError").hidden=false;}
 finally{button.disabled=false;}
}
async function bootstrapUI(){
 // The clinical identity is denied the finance lookup API by design.
 if(state.me.role==='clinician'){
   state.lookups={departments:[],categories:[],funds:[],employees:[],shifts:[]};
   state.view='clinical';
 }else{
   try{state.lookups=await api("/api/lookups");}
   catch(error){errorView(error.message);return;}
 }
 $("#loginPage").hidden=true;$("#shell").hidden=false;
 $("#usernameLabel").textContent=state.me.username;$("#userAvatar").textContent=state.me.username.slice(0,1).toUpperCase();
 $("#roleLabel").textContent=roleLabels[state.me.role]||state.me.role;
 const trial=true; // G2P is not approved for live hospital finances, regardless of environment string.
 const eLabel=$(".environment-label");
 eLabel.textContent="بيئة اختبار • لا تسجل بيانات مالية فعلية";
 eLabel.classList.toggle("test-mode",trial);
 $(".site-footer span:last-child").textContent="V8.1E-G3H • غير معتمد للتشغيل الحقيقي";
 const allowed={entry:["clerk","reviewer","owner"],review:["reviewer","owner"],payroll:["reviewer","owner"],inventory:["clerk","reviewer","owner"],clinical:["clinician"],reports:["viewer","reviewer","owner"],accounting:["reviewer","owner"],owner:["owner"]};
 $$('[data-permission]').forEach(el=>{el.hidden=!(allowed[el.dataset.permission]||[]).includes(state.me.role)});
 try{if(['owner','reviewer','clerk'].includes(state.me.role)){await api('/api/inventory/overview');}else{throw Error('no inventory role');}}catch{const nav=$('[data-view="inventory"]');if(nav)nav.hidden=true;}
 if((state.me.role==="clerk")&&["reviews","legacy","payroll","reports","bank","accounting","admin"].includes(state.view))state.view="dashboard";
 await navigate(state.view);
}
function hideMenu(){$("#sidebar").classList.remove("open");$("#mobileShade").hidden=true;}
async function navigate(view){
 if(!state.me)return;
 if(state.me.role==='clinician' && view!=='clinical'){
   toast('الحساب الطبي مخصص لإثبات الخدمات فقط',true);return;
 }
 const restricted={clinical:["clinician"],inventory:["owner","reviewer","clerk"],billing:["owner","reviewer","clerk"],shifts:["owner","reviewer","clerk"],calendar:["owner","reviewer","clerk"],cashierCorrections:["owner","reviewer","clerk"],lateEntries:["owner","reviewer","clerk"],cashierRecoveries:["owner","reviewer","clerk"],cashierSettings:["owner"],reviews:["owner","reviewer"],legacy:["owner","reviewer"],payroll:["owner","reviewer"],reports:["owner","reviewer","viewer"],accounting:["owner","reviewer"],bank:["owner","reviewer"],admin:["owner"],new:["owner","reviewer","clerk"]};
 if(restricted[view]&&!restricted[view].includes(state.me.role)){toast("ليست لديك صلاحية لهذه الصفحة",true);return;}
 state.view=view;hideMenu();$$('.nav-link[data-view]').forEach(b=>b.classList.toggle("active",b.dataset.view===view));
 const titles={clinical:"إثبات الخدمات الطبي",inventory:"المخزن المركزي",billing:"الحالات والفواتير",dashboard:"نظرة عامة",new:"تسجيل سند",ledger:"دفتر الحركات",reviews:"الاعتمادات",funds:"الخزن والحسابات",shifts:"الورديات والجرد",calendar:"تقويم الورديات",cashierSettings:"إعدادات ورديات الكاشير",cashierRecoveries:"تسوية فروق الخزنة",cashierCorrections:"بلاغات تصحيح العمليات",lateEntries:"استدراك العمليات المتأخرة",payroll:"المرتبات",reports:"التقارير",accounting:"دفتر الأستاذ",bank:"مطابقة البنك",legacy:"الأرشيف التاريخي",admin:"الإدارة"};
 $("#crumbTitle").textContent=titles[view]||"الإدارة المالية";
 $("#content").innerHTML='<div class="loading-state">جاري تحميل البيانات…</div>';
 try{
  const f={clinical:renderClinical,inventory:window.renderInventory,billing:window.renderBilling,dashboard:renderDashboard,new:renderNew,ledger:renderLedger,reviews:renderReviews,funds:renderFunds,shifts:renderShifts,calendar:window.renderCashierCalendar,cashierSettings:window.renderCashierSettings,cashierRecoveries:window.renderCashierRecoveries,cashierCorrections:window.renderFinancialCorrections,lateEntries:window.renderLateEntries,payroll:renderPayroll,reports:renderReports,accounting:renderAccounting,bank:renderBankReconciliation,legacy:renderLegacy,admin:renderAdmin}[view];
  await f();
 }catch(error){errorView(error.message);}
}
function attachMonth(id,property='month',view=state.view){const e=$("#"+id);if(e)e.onchange=()=>{state[property]=e.value;navigate(view);};}
const deptOptions=(v="")=>`<option value="">كل الأقسام</option>`+(state.lookups?.departments||[]).map(d=>opt(d.id,d.name,v)).join("");
const fundOptions=(v="")=>`<option value="">اختر الحساب المالي</option>`+(state.lookups?.funds||[]).map(f=>opt(f.id,f.name,v)).join("");
const employeeOptions=(v="")=>`<option value="">اختر الموظف</option>`+(state.lookups?.employees||[]).map(e=>opt(e.id,e.name,v)).join("");

function renderChart(daily,month){
 const dayCount=new Date(+month.slice(0,4),+month.slice(5,7),0).getDate();
 const data=Array.from({length:dayCount},(_,i)=>({in:0,out:0}));
 for(const d of daily){const n=+d.date.slice(-2)-1;if(n>=0&&n<data.length){if(d.kind==='receipt')data[n].in+=d.amount;else if(d.kind==='payment')data[n].out+=d.amount;}}
 const peak=Math.max(1,...data.flatMap(d=>[Math.abs(d.in),Math.abs(d.out)]));
 if(daily.length===0)return empty("مافيش حركات معتمدة في الفترة دي بعد.");
 return `<div class="chart-container"><div class="chart-bars" role="img" aria-label="حركة يومية: الإيرادات باللون الأخضر والمنصرف باللون البرتقالي">${data.map((d,i)=>`<div class="bar-pair" title="اليوم ${i+1} — إيرادات ${fmt(d.in)}، منصرف ${fmt(d.out)}"><div class="bar in" style="height:${Math.round(Math.max(0,d.in)/peak*100)}%"></div><div class="bar out" style="height:${Math.round(Math.max(0,d.out)/peak*100)}%"></div></div>`).join("")}</div><div class="chart-x"><span>١</span><span>${Math.ceil(dayCount/2)}</span><span>${dayCount}</span></div></div>`;
}
async function renderDashboardCoverage(month){
  let response;
  try{response=await api('/api/shifts/coverage?month='+encodeURIComponent(month))}catch{return}
  const host=$('#dashboardCoverageAlert');
  if(!host||state.month!==month||state.view!=='dashboard')return;
  const summary=response.summary||{};
  const need=(summary.missing||0)+(summary.unclosed||0)+(summary.awaiting_review||0)+(summary.variance||0);
  if(!need)return;
  host.innerHTML=`<div class="info-box warning" role="status">${ico('alert')}<div><strong>\u062a\u0646\u0628\u064a\u0647 \u0648\u0631\u062f\u064a\u0627\u062a \u063a\u064a\u0631 \u0645\u0643\u062a\u0645\u0644\u0629: ${integer(need)}</strong><p>\u064a\u0648\u062c\u062f \u0648\u0631\u062f\u064a\u0627\u062a \u0627\u0646\u062a\u0647\u062a \u0648\u0644\u0645 \u062a\u0633\u062c\u0644 \u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a\u064b\u0627\u060c \u0623\u0648 \u0648\u0631\u062f\u064a\u0627\u062a \u0645\u062a\u0623\u062e\u0631\u0629 \u0641\u064a \u0627\u0644\u0625\u0642\u0641\u0627\u0644 \u0648\u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629. \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0645\u0627\u0644\u064a \u0627\u0644\u0645\u0639\u0631\u0648\u0636 \u0642\u062f \u064a\u0643\u0648\u0646 \u063a\u064a\u0631 \u0645\u0643\u062a\u0645\u0644.</p><button class="btn btn-small btn-secondary" data-go="shifts">\u0627\u0641\u062a\u062d \u0633\u062c\u0644 \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a</button></div></div>`;
}

async function renderDashboardLateEntries(month){
  // Calm in-dashboard reminder; never treats a paper incident as financial revenue.
  const host=$('#dashboardLateEntriesAlert');
  if(!host||state.month!==month||state.view!=='dashboard')return;
  let data;
  try{data=await api('/api/late-entries?month='+encodeURIComponent(month))}catch{return}
  const pending=(data.items||[]).filter(i=>i.status!=='resolved');
  if(!pending.length)return;
  host.innerHTML=`<div class="info-box warning" role="status">${ico('file')}
    <div><strong>${integer(pending.length)} واقعة استدراك لم تُطابق</strong>
    <p>هناك ورديات أو مستندات ورقية لم تكتمل مطابقتها إلكترونيًا. السجل لا يُنشئ نقدية أو إيرادًا جديدًا.</p>
    <button class="btn btn-small btn-secondary" data-go="lateEntries">افتح سجل الاستدراك</button></div></div>`;
}
async function renderDashboard(){
 const d=await api(`/api/dashboard?month=${encodeURIComponent(state.month)}`);
 let r=null;if(state.me.role!=="clerk")r=await api(`/api/reports?month=${encodeURIComponent(state.month)}`);
 const c=$("#content");
 const list=(r?.categories||[]).slice(0,6);const mx=Math.max(1,...list.map(x=>Math.abs(x.amount_piasters)));
 c.innerHTML=head("الصفحة الرئيسية","الوضع المالي في لمحة","ملخص الحركات الجديدة المعتمدة فقط؛ الأرشيف التاريخي معزول عن التشغيل.",`<button class="btn btn-primary" data-go="new">${ico("plus")} سند جديد</button>`)+
 `<div class="filter-strip panel">${periodInput(state.month,"dashboardMonth")}<span class="helper-note">الحسابات تبدأ من أرصدة افتتاحية تعتمدها الإدارة، وليست من أرقام يونيو المستوردة.</span></div>`+
 `<div id="dashboardCoverageAlert" aria-live="polite"></div>`+
 `<div id="dashboardLateEntriesAlert" aria-live="polite"></div>`+
 `<div class="metrics">${metric("إجمالي المقبوضات",d.receipts_piasters,"income","لا تشمل التحويلات بين الخزن","wallet")}${metric("إجمالي المدفوعات",d.payments_piasters,"expense","تشمل المدفوعات غير التشغيلية","arrow")}${metric("صافي حركة النقدية",d.cash_difference_piasters,"neutral","ليس صافي ربح ولا رصيد خزنة","chart")}${metric("سندات تنتظر الاعتماد",d.pending,"warning","غير مُدرجة في المجاميع","shield","")}</div>`+
 `<div class="dashboard-grid"><section class="panel"><div class="panel-header"><div><h2>الحركة المالية اليومية</h2><p>مقارنة المقبوضات والمدفوعات داخل الفترة</p></div><div class="legend"><span><i class="in"></i>وارد</span><span><i class="out"></i>منصرف</span></div></div>${renderChart(d.daily,state.month)}</section>`+
 `<section class="panel"><div class="panel-header"><div><h2>أكبر بنود الصرف</h2><p>حركات معتمدة حسب التصنيف</p></div></div>${list.length?`<div class="category-list">${list.map(x=>`<div><div class="category-line"><span>${esc(x.category)}</span><b class="amount">${fmt(x.amount_piasters)}</b></div><div class="progress-track"><div class="progress-fill" style="width:${Math.round(Math.abs(x.amount_piasters)/mx*100)}%"></div></div></div>`).join("")}</div>`:empty("التصنيفات تظهر بعد اعتماد المصروفات.")}</section></div>`+
 `<section class="panel"><div class="panel-header"><div><h2>آخر السندات</h2><p>الأحدث تسجيلًا، مع حالة كل سند</p></div><button class="btn ghost" data-go="ledger">عرض الدفتر ${ico("arrow")}</button></div>${table(["رقم السند","التاريخ","النوع","القسم","المبلغ","الحالة"],d.latest.map(x=>`<tr><td class="tiny">${esc(x.voucher_no)}</td><td>${esc(x.date)}</td><td>${kindChip(x.kind)}</td><td>${esc(x.department||"حركة تحويل")}</td><td class="num">${fmt(x.amount_piasters)}</td><td>${statusChip(x.status)}</td></tr>`).join(""))}</section>`+
 `<div class="info-box" style="margin-top:18px">${ico("alert")}<div>${esc(d.note)}${d.legacy_issues!==null?` أرشيف يونيو يحتوي ${integer(d.legacy_issues)} ملاحظة مراجعة منفصلة.`:""}</div></div>`;
 attachMonth("dashboardMonth");refreshPending(d.pending);
 if(['owner','reviewer','clerk'].includes(state.me.role)){
   renderDashboardCoverage(state.month);
   renderDashboardLateEntries(state.month);
 }
}
function refreshPending(n){const e=$("#pendingMenu");e.hidden=!(n>0);e.textContent=String(n);}

function initialFormValues(){
 const p=state.prefill||{};state.prefill=null;
 return {kind:p.kind||"payment",employee_id:p.employee_id||"",salary_period:p.salary_period||"",category_code:p.category_code||"",department_id:p.department_id||""};
}
async function renderClinical(){
 const data=await api('/api/billing/clinical/queue');
 const pending=data.items||[];
 // Inventory is a separately scoped, optional clinical worklist; it must not
 // break the existing medical service workflow if no stock-return grant exists.
 let inspectionItems=[],inspectionNotice='';
 try{inspectionItems=(await api('/api/inventory/inspections/queue')).items||[];}
 catch(error){inspectionNotice='قائمة فحص المرتجعات غير متاحة لحسابك حاليًا. تحقق من تفويض القسم أو اتصال الخدمة.';}
 $('#content').innerHTML=head('إثبات الخدمات · تجربة', 'الإثبات الطبي المستقل',
   'لا ينشئ هذا الإجراء فاتورة أو حركة نقدية. دوّن فقط مرجع تنفيذ قابل للتحقق وبعد مراجعة واقعية للخدمة.',
   `<button class="btn btn-secondary" id="refreshClinical">${ico('refresh')} تحديث القائمة</button>`)+
   `<div class="info-box warning">${ico('alert')}<div><strong>نموذج للاختبار فقط:</strong> الحساب الطبي المستقل لا يثبت ترخيصًا مهنيًا أو توقيعًا إلكترونيًا معتمدًا. ملفات المصدر تُقرأ لحساب بصمة SHA-256 فقط ولا تُحفظ في الحسابات؛ احتفظ بالأصل في السجل الطبي المصرّح به، ولا تستخدم ملفات مرضى حقيقية في التجربة.</div></div>`+
   `<section class="panel" style="margin-top:18px"><div class="panel-header"><h2>خدمات بانتظار الإثبات</h2><p>يعرض فقط الخدمات من الأقسام المفوّض بها الحساب، بدون أسعار أو أرصدة.</p></div>`+
   table(['الحالة','المريض (الكود)','الخدمة','العدد','الوضع','الإجراء'],pending.map(x=>`<tr>`+
     `<td>${esc(x.case_no)}</td><td>${esc(x.patient_code)}</td><td>${esc(x.service_name)}</td>`+
     `<td class="num">${integer(x.quantity)}</td><td>${x.state==='fulfilled'?'منفذة سابقًا · تحتاج إثبات':'مطلوبة'}</td>`+
     `<td>${x.document_required?'<span class="chip pending">بصمة ملف إلزامية</span>':''}<button class="btn btn-small btn-primary" data-clinical-attest="${esc(x.line_id)}" data-clinical-doc-required="${x.document_required?1:0}">إثبات التنفيذ</button></td></tr>`).join(''))+`</section>`+
   `<section class="panel" style="margin-top:18px"><div class="panel-header"><div><h2>حجر وفحص المستلزمات المرتجعة</h2><p>كل مرتجع محاسبي معتمد محجوز إلى أن يصدر قرار طبي منفصل. القائمة بحسب الأقسام الممنوحة لك، ولا تعرض بيانات مريض أو أسعارًا.</p></div></div>`+
   (inspectionNotice?`<p class="section-subtitle" role="status">${esc(inspectionNotice)}</p>`:'')+
   (inspectionItems.length?table(['المستلزم / الدفعة','القسم','الكمية','تاريخ الرد','الصلاحية','قرار طبي مستقل'],inspectionItems.map(x=>`<tr>`+
     `<td><strong>${esc(x.item_name)}</strong><small class="inv-muted">${esc(x.item_code)} · ${esc(x.batch_ref||'بدون رقم تشغيلة')}</small></td>`+
     `<td>${esc(x.department_name)}</td><td class="num">${integer(x.quantity)}</td><td>${esc(x.returned_on)}</td><td>${esc(x.expiry_date||'غير مسجل')}</td>`+
     `<td><div class="inv-actions"><button class="btn btn-small btn-primary" data-return-inspect="${Number(x.return_line_id)}:release">إجازة بعد الفحص</button>`+
     `<button class="btn btn-small btn-outline" data-return-inspect="${Number(x.return_line_id)}:reject">رفض طبي</button></div></td></tr>`).join('')):empty('لا توجد مرتجعات تنتظر الفحص في أقسامك حاليًا.'))+
   `</section>`;
 $('#refreshClinical').onclick=()=>navigate('clinical');
 $$('[data-clinical-attest]',$('#content')).forEach(btn=>btn.onclick=async()=>{
   const lineId=Number(btn.dataset.clinicalAttest);
   if(!Number.isSafeInteger(lineId)||lineId<=0){toast('رقم بند الخدمة غير صحيح',true);return;}
   const needsFile=btn.dataset.clinicalDocRequired==='1';
   const details=await modal('إثبات تنفيذ خدمة','تحقق من المستند الطبي في سجله الأصلي قبل المتابعة. يتم الاحتفاظ ببصمة الملف ونوعه وحجمه فقط، ولا تحفظ الحسابات محتوى المستند أو اسمه. هذا ليس توقيعًا طبيًا معتمدًا.',[
     {name:'evidence_reference',label:'مرجع التقرير أو أمر التنفيذ',required:true,placeholder:'SYN-CLINICAL-REFERENCE-0001'},
     {name:'file',type:'file',label:needsFile?'ملف المصدر الطبي (إلزامي، حتى 6 ميجابايت)':'ملف المصدر الطبي (اختياري، حتى 6 ميجابايت)',required:needsFile}]);
   if(!details)return;
   const file=details.file;
   try{
     if(file&&file.size){
       const payload=new FormData();
       payload.append('evidence_reference',details.evidence_reference);
       payload.append('file',file,file.name);
       await api(`/api/billing/clinical/lines/${lineId}/attest-document`,{method:'POST',body:payload});
       toast('تم إثبات الخدمة وحفظ بصمة المستند دون حفظ محتواه');
     }else{
       if(needsFile){toast('اختر ملف المصدر المطلوب أولًا',true);return;}
       await post(`/api/billing/clinical/lines/${lineId}/attest`,{evidence_reference:details.evidence_reference});
       toast('تم إثبات الخدمة بمرجع تجريبي دون بصمة مصدر');
     }
     await navigate('clinical');
   }catch(error){toast(error.message,true);}
 });
 $$('[data-return-inspect]',$('#content')).forEach(btn=>btn.onclick=async()=>{
   const [rawId,decision]=btn.dataset.returnInspect.split(':');
   const id=Number(rawId);
   if(!Number.isSafeInteger(id)||id<1)return;
   const release=decision==='release';
   const fields=[{name:'evidence_ref',label:'رقم محضر الفحص أو موافقة مكافحة العدوى',required:true},
                 {name:'note',label:'قرار الطبيب والمبرر (12 حرفًا على الأقل)',required:true}];
   if(release)fields.push(...[
     ['unused_confirmed','أؤكد أن الوحدة لم تستخدم'],
     ['packaging_intact','أؤكد سلامة العبوة الأصلية'],
     ['infection_control_clearance','أؤكد وجود موافقة مكافحة العدوى'],
   ].map(([name,label])=>({name,type:'select',label,options:[['false','لا'],['true','نعم']]})));
   const result=await modal(release?'قرار إفراج طبي تجريبي':'رفض إعادة الاستخدام',
      'كل قرار غير قابل للتعديل. الرفض يبقي الكمية في الحجر لحين تسوية مستقلة، ولا ينشئ قيدًا ماليًا جديدًا. لا تستخدم نظام التجربة لاتخاذ قرار سلامة مستلزمات حقيقية.',fields);
   if(!result)return;
   try{
     await post(`/api/inventory/inspections/${id}/decision`,{
       decision,inspected_on:new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'}),
       evidence_ref:result.evidence_ref,note:result.note,
       unused_confirmed:result.unused_confirmed==='true',
       packaging_intact:result.packaging_intact==='true',
       infection_control_clearance:result.infection_control_clearance==='true'});
     toast(release?'تم تسجيل الإفراج الطبي المستقل على مستلزم تجريبي':'تم الرفض؛ سيظل المستلزم محجوزًا طبيًا');
     await navigate('clinical');
   }catch(error){toast(error.message,true);}
 });
}

async function renderNew(){
 const p=initialFormValues();const categories=state.lookups.categories;
 const catId=(categories.find(x=>x.code===p.category_code)||{}).id||"";
 $("#content").innerHTML=head("السندات المالية","تسجيل سند جديد","كل سند يمر بالمراجعة قبل الترحيل إلى حركة الخزنة.")+
 `<div class="entry-layout"><section class="panel panel-pad"><h2 class="section-title">بيانات الحركة</h2><p class="section-subtitle">ادخل بيانات السند كما هي بالمستند؛ لا تُسجل أي بيانات طبية حساسة غير ضرورية.</p><form id="voucherForm"><div class="kind-control" role="radiogroup" aria-label="نوع السند">${[["receipt","إيراد / تحصيل"],["payment","صرف"],["transfer","تحويل داخلي"]].map(([k,l])=>`<label><input type="radio" name="kind" value="${k}" ${p.kind===k?"checked":""}><span>${l}</span></label>`).join("")}</div>
 <div class="form-grid">
 <label>التاريخ <input required name="date" type="date" value="${new Date().toLocaleDateString("sv-SE")}"></label>
 <label>الوردية <select name="shift" required>${state.lookups.shifts.map(s=>opt(s.code,s.name,"central")).join("")}</select><small class="info-inline">الوردية مختلفة عن الخزنة.</small></label>
 <label>الحساب المالي <select required name="from_fund_id">${fundOptions()}</select></label>
 <label id="targetFundField" hidden>الحساب المُحوّل إليه <select name="to_fund_id">${fundOptions()}</select></label>
 <label id="deptField">مركز التكلفة <select name="department_id" required><option value="">اختر القسم</option>${state.lookups.departments.map(d=>opt(d.id,d.name,p.department_id)).join("")}</select></label>
 <label id="categoryField">التصنيف <select name="category_id" required></select><small id="classHint" class="info-inline"></small></label>
 <label>المبلغ بالجنيه <input type="number" name="amount" step="0.01" min="0.01" inputmode="decimal" placeholder="0.00" required></label>
 <label>رقم المستند / إيصال <input name="reference_no" maxlength="100" placeholder="اختياري"></label>
 <label id="employeeField" hidden>الموظف <select name="employee_id">${employeeOptions(p.employee_id)}</select></label>
 <label id="salaryPeriodField" hidden>شهر الاستحقاق <input type="month" name="salary_period" value="${esc(p.salary_period)}"></label>
 <label class="full">البيان أو سبب الحركة <textarea name="description" required minlength="5" maxlength="500" placeholder="مثال: سداد مستحق شركة أو إيراد خدمات الاستقبال"></textarea></label>
 </div><div class="form-footer"><button type="submit" class="btn btn-primary">${ico("check")} إرسال للاعتماد</button><button type="reset" class="btn btn-secondary">مسح البيانات</button></div><div class="form-error" id="voucherError" hidden></div></form></section>
 <aside class="panel form-aside"><h2 class="section-title">خطوات التسجيل</h2>${[["1","إدخال السند","تحديد الخزنة والقسم وطبيعة الحركة"],["2","مراجعة مستقلة","مراجع آخر يعتمد أو يرفض السند"],["3","ترحيل تلقائي","الحركات المعتمدة فقط تؤثر على الرصيد"]].map(x=>`<div class="aside-block"><div class="aside-index">${x[0]}</div><div><strong>${x[1]}</strong><small>${x[2]}</small></div></div>`).join("")}<div class="aside-warning">${ico("alert")} السلفة ليست راتبًا مصروفًا مرتين. والتحويل بين الخزن لا يُحسب إيرادًا أو مصروفًا جديدًا.</div></aside></div>`;
 const form=$("#voucherForm");
 function update(){
  const k=$('input[name="kind"]:checked',form).value;
  const catEl=$('[name="category_id"]',form);let old=catEl.value||catId;
  catEl.innerHTML='<option value="">اختر التصنيف</option>'+categories.filter(c=>c.direction===k).map(c=>opt(c.id,c.name,old)).join('');
  const isTransfer=k==='transfer';$("#targetFundField").hidden=!isTransfer;$("#deptField").hidden=isTransfer;$("#categoryField").hidden=isTransfer;
  $('[name="to_fund_id"]',form).required=isTransfer;$('[name="department_id"]',form).required=!isTransfer;catEl.required=!isTransfer;
  const cat=categories.find(c=>String(c.id)===catEl.value);
  $("#classHint").textContent=cat?"الطبيعة: "+(categoryNatures[cat.nature]||cat.nature):"التصنيف يحدد نوع الحساب، وليس اسم المستفيد فقط.";
  const payroll=cat&&(cat.nature==='payroll_payment'||cat.nature==='advance');
  $("#employeeField").hidden=!payroll;$("#salaryPeriodField").hidden=!(cat&&cat.nature==='payroll_payment');
  $('[name="employee_id"]',form).required=!!payroll;
  $('[name="salary_period"]',form).required=!!(cat&&cat.nature==='payroll_payment');
 }
 $$('input[name="kind"]',form).forEach(e=>e.onchange=()=>{form.querySelector('[name="category_id"]').value="";update();});
 $('[name="category_id"]',form).onchange=update;
 update();
 form.onreset=()=>{delete form.dataset.requestId;setTimeout(update,0);};
 // A changed form represents a different intended posting, not a network retry.
 form.addEventListener("input",()=>{delete form.dataset.requestId;});
 form.onsubmit=async e=>{
  e.preventDefault();const err=$("#voucherError");err.hidden=true;
  const f=Object.fromEntries(new FormData(form));
  const data={date:f.date,kind:f.kind,from_fund_id:Number(f.from_fund_id),shift:f.shift,amount:String(f.amount),
    department_id:f.kind==='transfer'?null:Number(f.department_id),category_id:f.kind==='transfer'?null:Number(f.category_id),
    to_fund_id:f.kind==='transfer'?Number(f.to_fund_id):null,
    client_request_id:form.dataset.requestId || (form.dataset.requestId = (globalThis.crypto?.randomUUID?.() || (Date.now().toString(36)+Math.random().toString(36).slice(2,17)))),
    employee_id:f.employee_id&&!$('#employeeField').hidden?Number(f.employee_id):null,
    salary_period:f.salary_period||null,description:f.description,reference_no:f.reference_no};
  const cat=categories.find(x=>x.id===data.category_id);
  if(!cat||!['advance','payroll_payment'].includes(cat.nature)){data.employee_id=null;data.salary_period=null;}
  if(cat&&cat.nature==='advance'){data.salary_period=null;}
  const btn=$('button[type=submit]',form);btn.disabled=true;
  try{const res=await post("/api/vouchers",data);toast(`تم إرسال ${res.voucher_no} للمراجعة`);await navigate("ledger");}
  catch(error){err.textContent=error.message;err.hidden=false;}
  finally{btn.disabled=false;}
 };
}

async function showVoucherEvidence(voucherId,number,allowUpload){
  const docs=await api(`/api/vouchers/${voucherId}/attachments`);
  const list=docs.length?`<div class="evidence-links">${docs.map(doc=>
    `<a class="evidence-link" href="/api/attachments/${doc.id}/download" download>${ico('file')} ${esc(doc.file_name)} <span class="tiny">${Math.ceil(doc.file_size/1024)} KB</span></a>`
  ).join('')}</div>`:'<p>لا توجد مستندات مرفقة بهذا السند حتى الآن.</p>';
  const editable=allowUpload&&docs.length<3;
  const message=`<strong>السند ${esc(number)}</strong>${list}<div class="tiny">المستندات محفوظة داخل قاعدة البيانات؛ يسمح بـPDF / JPG / PNG، بحجم حتى 6 ميجابايت لكل ملف.</div>`;
  const form=await modal('مستندات الإثبات',message,editable?[
    {name:'file',type:'file',label:'أضف مستندًا (حتى ثلاثة مستندات)',required:true}
  ]:[]);
  if(!form||!editable)return;
  const file=form.file;
  if(!file || !file.size)return toast('اختر ملف مستند صالحًا',true);
  const payload=new FormData();payload.append('file',file,file.name);
  try{
    await api(`/api/vouchers/${voucherId}/attachments`,{method:'POST',body:payload});
    toast('تم حفظ المستند مع السند بنجاح');navigate(state.view);
  }catch(e){toast(e.message,true)}
}

async function renderLedger(){
 const filters=state.ledger;
 const query=new URLSearchParams({month:state.month,page:String(filters.page)});
 if(filters.q)query.set("q",filters.q);if(filters.kind)query.set("kind",filters.kind);
 if(filters.status)query.set("status",filters.status);if(filters.department)query.set("department",filters.department);
 const d=await api("/api/vouchers?"+query);
 const actions=state.me.role==='owner'||state.me.role==='reviewer'?`<button id="downloadCsv" class="btn btn-secondary">${ico("download")} تصدير CSV</button>`:"";
 $("#content").innerHTML=head("سجل القيود","دفتر الحركات","سندات مرقمة، لا حذف مباشر للحركات، وتسوية موثقة عند الحاجة.",actions)+
 `<section class="panel"><div class="toolbar"><label class="search">بحث برقم السند أو البيان<input id="ledgerSearch" type="search" placeholder="ابحث في السندات…" value="${esc(filters.q)}"></label><label>النوع<select id="ledgerKind"><option value="">كل الأنواع</option>${Object.entries(labelType).map(([k,v])=>opt(k,v,filters.kind)).join("")}</select></label><label>الحالة<select id="ledgerStatus"><option value="">كل الحالات</option>${Object.entries(stateLabels).map(([k,v])=>opt(k,v,filters.status)).join("")}</select></label><label>القسم<select id="ledgerDept">${deptOptions(filters.department)}</select></label></div>`+
 table(["رقم السند","التاريخ","نوع الحركة","التصنيف / البيان","المبلغ","الحالة","الإجراء"],d.items.map(v=>`<tr><td><b>${esc(v.voucher_no)}</b><div class="tiny">${esc(v.created_user)}</div></td><td>${esc(v.date)}</td><td>${kindChip(v.kind)}<div class="tiny">${esc(v.department||v.to_fund||"")}</div></td><td><div>${esc(v.category||"تحويل داخلي")}</div><div class="tiny desc" title="${esc(v.description)}">${esc(v.description)}</div></td><td class="num">${fmt(v.amount_piasters)}</td><td>${statusChip(v.status)}</td><td><div class="row-actions">${state.me.role!=='viewer'?`<button class="btn btn-small btn-outline" data-evidence="${v.id}" data-number="${esc(v.voucher_no)}" data-upload="${v.status==='pending'&&v.created_user===state.me.username?1:0}">${ico('file')} مستندات (${integer(v.attachment_count)})</button>`:''}${state.me.role==='owner'&&v.status==='approved'?`<button class="btn btn-small btn-secondary" data-reverse="${v.id}" data-number="${esc(v.voucher_no)}">تسوية</button>`:''}</div></td></tr>`).join(""))+
 `<div class="table-footer"><span>${integer(d.count)} سند • صفحة ${d.page} من ${d.pages||1}</span><div class="paging"><button class="btn btn-secondary" id="ledgerPrev" ${d.page<=1?'disabled':''}>السابق</button><button class="btn btn-secondary" id="ledgerNext" ${d.page>=d.pages?'disabled':''}>التالي</button></div></div></section>`+
 `<div class="info-box" style="margin-top:18px">${ico("shield")}<div>الترحيل إلى الخزن يحدث فقط بعد الاعتماد. تسوية سند معتمد تنشئ سندًا عكسيًا مستقلًا يحفظ أثر السند الأصلي.</div></div>`;
 let timer;
 $("#ledgerSearch").oninput=e=>{clearTimeout(timer);timer=setTimeout(()=>{state.ledger.q=e.target.value;state.ledger.page=1;navigate('ledger');},400);};
 for(const [id,key] of [["ledgerKind","kind"],["ledgerStatus","status"],["ledgerDept","department"]])$("#"+id).onchange=e=>{state.ledger[key]=e.target.value;state.ledger.page=1;navigate("ledger");};
 $("#ledgerPrev").onclick=()=>{state.ledger.page--;navigate("ledger");};
 $("#ledgerNext").onclick=()=>{state.ledger.page++;navigate("ledger");};
 $("#downloadCsv")?.addEventListener("click",()=>window.location.assign("/api/export/vouchers.csv"));
  $$('[data-evidence]').forEach(b=>b.onclick=async()=>{
    try{await showVoucherEvidence(Number(b.dataset.evidence),b.dataset.number,b.dataset.upload==='1')}
    catch(e){toast(e.message,true)}
  });
 $$('[data-reverse]').forEach(b=>b.onclick=async()=>{
  const result=await modal("تسوية سند معتمد",`سيُنشأ قيد عكسي للسند ${esc(b.dataset.number)} بدلاً من حذفه.`,[
     {name:"date",type:"date",label:"تاريخ التسوية",value:new Date().toLocaleDateString('sv-SE'),required:true},
     {name:"reason",type:"textarea",label:"سبب التسوية",placeholder:"شرح دقيق لسبب عكس السند",required:true}]);
  if(!result)return;
  try{await post(`/api/vouchers/${b.dataset.reverse}/reverse`,result);toast("تم إنشاء سند التسوية بنجاح");navigate('ledger');}
  catch(err){toast(err.message,true)}
 });
}

async function renderReviews(){
 const d=await api("/api/reviews");
 $("#content").innerHTML=head("الرقابة الداخلية","مراجعة واعتماد السندات","لا تدخل هذه الحركات في رصيد أي خزنة قبل الموافقة عليها.")+
 `<div class="info-box">${ico("shield")}<div>فصل المهام مفعل: لا يمكن للمستخدم اعتماد سند أدخله بنفسه، حتى لو كان صاحب صلاحية مراجعة.</div></div>`+
 `<section class="panel"><div class="panel-header"><h2>في انتظار المراجعة</h2><span class="chip pending">${integer(d.length)} سند</span></div>`+
 table(["رقم السند","التاريخ","البيان","المسجل بواسطة","المبلغ","القرار"],d.map(v=>`<tr><td><b>${esc(v.voucher_no)}</b></td><td>${esc(v.date)}</td><td><div class="desc" title="${esc(v.description)}">${esc(v.description)}</div><div class="tiny">${esc(v.department||'تحويل داخلي')}</div></td><td>${esc(v.created_user)}</td><td class="num review-amount">${fmt(v.amount_piasters)}</td><td><div class="review-evidence"><button class="btn btn-small btn-outline" data-review-evidence="${v.id}" data-number="${esc(v.voucher_no)}">${ico('file')} مستندات (${integer(v.attachment_count)})</button>${state.me.username===v.created_user?`<span class="chip archive">مسجل بواسطة حسابك</span>`:`<div class="row-actions"><button class="btn btn-small btn-primary" data-decision="approve" data-id="${v.id}">اعتماد</button><button class="btn btn-small btn-secondary" data-decision="reject" data-id="${v.id}">رفض</button></div>`}</div></td></tr>`).join(""))+`</section>`;
 refreshPending(d.length);
  $$('[data-review-evidence]').forEach(b=>b.onclick=async()=>{
    try{await showVoucherEvidence(Number(b.dataset.reviewEvidence),b.dataset.number,false)}
    catch(e){toast(e.message,true)}
  });
 $$('[data-decision]').forEach(b=>b.onclick=async()=>{
  const approval=b.dataset.decision==='approve';
  const data=await modal(approval?'اعتماد سند مالي':'رفض سند مالي',approval?'بعد الاعتماد سيُرحل المبلغ إلى الخزنة المختارة.':'تسجيل سبب الرفض إلزامي.',
    [{name:'reason',type:'textarea',label:approval?'ملاحظة الاعتماد (اختياري)':'سبب الرفض',placeholder:'مراجعة المستند وتبرير القرار',required:!approval}]);
  if(!data)return;
  try{await post(`/api/vouchers/${b.dataset.id}/decision`,{decision:b.dataset.decision,reason:data.reason||''});toast(approval?'تم اعتماد السند وترحيله للخزنة':'تم رفض السند مع حفظ السبب');navigate('reviews');}
  catch(error){toast(error.message,true)}
 });
}

async function renderFunds(){
 const funds=await api('/api/funds');
 const opening=state.me.role==='clerk'?null:await api('/api/accounting/opening-reviews?period='+encodeURIComponent(state.month));
 const openingMap=new Map((opening?.funds||[]).map(x=>[x.id,x]));
 let total=funds.reduce((s,f)=>s+(f.balance_piasters||0),0);
 $("#content").innerHTML=head("إدارة السيولة","الخزن والحسابات المالية","رصيد كل خزنة أو محفظة يُحسب من حركاتها المعتمدة دون خلطه بالوردية.",state.me.role==='owner'?`<button class="btn btn-primary" id="addFund">${ico('plus')} إضافة خزنة / حساب</button>`:'')+
 `<div class="${state.me.role==='clerk'?'info-box':''}">${state.me.role==='clerk'?'عرض أسماء الحسابات فقط؛ الأرصدة متاحة للمراجع والإدارة.':''}</div>`+
 `<div class="fund-grid">${funds.map(f=>`<article class="panel fund-card"><div class="fund-heading"><span>${esc(f.name)}</span><span class="fund-type">${f.kind==='cash'?(f.cash_restricted?'نقدي · تفويض محمي':'نقدي · وضع قديم'):(f.kind==='wallet'?'محفظة إلكترونية':'بنكي')}</span></div><strong class="fund-balance">${f.balance_piasters===undefined?'—':fmt(f.balance_piasters)+' ج.م'}</strong><p class="fund-secondary">رصيد افتتاحي: ${f.opening_piasters===undefined?'محدود الصلاحية':fmt(f.opening_piasters)} • ${integer(f.transaction_count)} حركة</p>${(()=>{const r=openingMap.get(f.id);if(!r)return '';return `<div class="fund-opening-review"><span class="chip ${r.review_status==='approved'&&r.verified_as_of_period?'approved':r.review_status==='pending'?'pending':'rejected'}">${r.review_status==='approved'&&r.verified_as_of_period?'الافتتاح معتمد':r.review_status==='pending'?'محضر تحت المراجعة':r.review_needed?'افتتاح غير معتمد':'افتتاح صفري / غير موثق'}</span>${r.review_issue&&r.review_needed?`<small>${esc(r.review_issue)}</small>`:''}${r.evidence_reference?`<small>مستند: ${esc(r.evidence_reference)}</small>`:''}</div>`})()}<div class="fund-opening-actions">${state.me.role==='owner'&&f.transaction_count===0&&!openingMap.get(f.id)?.review_status?`<button class="btn btn-small btn-outline" data-opening="${f.id}" data-fundname="${esc(f.name)}">تحديد الرصيد</button>`:''}${state.me.role==='owner'&&!openingMap.get(f.id)?.review_status?`<button class="btn btn-small btn-primary" data-opening-submit="${f.id}">طلب اعتماد الافتتاح</button>`:''}${openingMap.get(f.id)?.can_review?`<button class="btn btn-small btn-primary" data-opening-decision="${openingMap.get(f.id).review_id}" data-result="approve">اعتماد</button><button class="btn btn-small btn-outline" data-opening-decision="${openingMap.get(f.id).review_id}" data-result="reject">رفض</button>`:''}</div></article>`).join('')}</div>`+
 `<div class="info-box warning">${ico('alert')}<div>الرصيد الافتتاحي يتطلب إثبات عد نقدية أو كشف بنك/محفظة، ثم مراجعة شخص مستقل وقيدًا متوازنًا. لا تستخدمه لإدخال حركات يونيو المؤرشفة أو الإيرادات. المحضر المسجل لا يثبت وحده وصول المال فعلًا.</div></div>`;
 $('#addFund')?.addEventListener('click',async()=>{
   const data=await modal('إضافة خزنة أو محفظة','الحساب يظهر في قائمة السندات فور إنشائه.',[
    {name:'name',label:'اسم الحساب',required:true,placeholder:'مثال: خزنة الاستقبال'},
    {name:'code',label:'كود إنجليزي فريد',required:true,placeholder:'er_cash'},
    {name:'kind',type:'select',label:'نوع الحساب',options:[['cash','نقدي'],['wallet','محفظة إلكترونية'],['bank','حساب بنكي']]},
    {name:'restricted_cash',type:'select',label:'تطبيق تفويضات الخزنة من أول تشغيلها',options:[['true','نعم (موصى به)'],['false','لا، إعداد انتقالي']]}
   ]);
   if(!data)return;
   try{await post('/api/funds',{...data,restricted_cash:data.kind==='cash'&&data.restricted_cash==='true'});state.lookups=await api('/api/lookups');toast('تمت إضافة الحساب');navigate('funds');}catch(e){toast(e.message,true)}
 });
 $$('[data-opening-submit]').forEach(b=>b.onclick=async()=>{
  const fund=funds.find(x=>x.id===+b.dataset.openingSubmit);
  if(!fund)return;
  const kind={cash:'cash_count',bank:'bank_statement',wallet:'wallet_statement'}[fund.kind];
  const fields=[
   {name:'effective_date',label:'تاريخ بداية الرصيد (لا يأتي بعد أول حركة)',type:'date',value:state.month+'-01',required:true},
   {name:'evidence_reference',label:fund.kind==='cash'?'رقم محضر الجرد الموقّع':'مرجع كشف الحساب الأصلي',required:true,placeholder:'مثال: OPEN-2026-10-01'},
   {name:'evidence_note',label:'بيان مستند الإثبات والمطابقة',type:'textarea',required:true,placeholder:'من قام بالمراجعة؟ وأين يوجد المستند الأصلي؟'}
  ];
  if(fund.opening_piasters>0)fields.push({name:'offset_account_id',label:'الحساب المقابل (يختاره المحاسب وفق الأرصدة)',type:'select',options:(opening?.offset_accounts||[]).map(x=>[x.id,x.code+' · '+x.name]),required:true});
  const info=await modal('طلب اعتماد رصيد افتتاحي',`<strong>${esc(fund.name)}</strong> · ${fmt(fund.opening_piasters)} جنيه. المراجع يجب أن يكون مستخدمًا آخر مفوضًا على الخزنة.`,fields);
  if(!info)return;
  const payload={...info,evidence_kind:kind,offset_account_id:info.offset_account_id?+info.offset_account_id:null};
  try{await post(`/api/funds/${fund.id}/opening-review`,payload);toast('تم إرسال المحضر للمراجعة المستقلة');navigate('funds')}
  catch(e){toast(e.message,true)}
 });
 $$('[data-opening-decision]').forEach(b=>b.onclick=async()=>{
  const decision=b.dataset.result;
  const review=opening?.funds?.find(x=>x.review_id===+b.dataset.openingDecision);
  if(!review)return;
  const info=await modal(decision==='approve'?'اعتماد الرصيد الافتتاحي':'رفض محضر الرصيد الافتتاحي',
    `راجع المستند الأصلي قبل القرار. <strong>${esc(review.name)}</strong> · ${fmt(review.opening_piasters)} ج.م. ${decision==='approve'?'سيُثبت قيد افتتاحي متوازن ولا يمكن تعديل المحضر بعده.':''}`,
    [{name:'note',label:'سبب القرار وإثبات المراجعة',type:'textarea',required:true,placeholder:'اذكر التحقق من الكشف أو العد والمستند الأصلي'}]);
  if(!info)return;
  try{await post(`/api/accounting/opening-reviews/${review.review_id}/decision`,{decision,note:info.note});toast(decision==='approve'?'تم اعتماد الرصيد وقيده في الأستاذ':'تم رفض المحضر مع الاحتفاظ بسجله');navigate('funds')}
  catch(e){toast(e.message,true)}
 });
 $$('[data-opening]').forEach(b=>b.onclick=async()=>{
  const data=await modal('تحديد الرصيد الافتتاحي',`الحساب: ${esc(b.dataset.fundname)}. يتم ذلك قبل أول حركة فقط.`,[
   {name:'amount',label:'الرصيد الافتتاحي بالجنيه',type:'number',value:'0',required:true,placeholder:'0.00'}]);
  if(!data)return;
  try{await post(`/api/funds/${b.dataset.opening}/opening`,data);toast('تم تسجيل الرصيد؛ الخطوة التالية إرسال محضر افتتاح للمراجعة');navigate('funds');}
  catch(e){toast(e.message,true)}
 });
}

async function renderShiftCoveragePanel(month){
  const host=$('#shiftCoverage');
  if(!host)return;
  let data;
  try{
    data=await api('/api/shifts/coverage?month='+encodeURIComponent(month));
  }catch(e){
    if($('#shiftCoverage'))$('#shiftCoverage').innerHTML=`<p class="empty">\u062a\u0639\u0630\u0631 \u062a\u062d\u0645\u064a\u0644 \u0645\u0624\u0634\u0631 \u0627\u0643\u062a\u0645\u0627\u0644 \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a \u0641\u064a \u0647\u0630\u0647 \u0627\u0644\u0646\u0633\u062e\u0629.</p>`;
    return;
  }
  if(state.shiftMonth!==month||!$('#shiftCoverage'))return;
  const root=$('#shiftCoverage');
  const name=Object.fromEntries((data.items||[]).map(x=>[x.shift,x.shift_name||x.shift]));
  const statuses={missing:'\u0648\u0631\u062f\u064a\u0629 \u063a\u064a\u0631 \u0645\u0633\u062c\u0644\u0629 \u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a\u064b\u0627',unclosed:'\u0648\u0631\u062f\u064a\u0629 \u0645\u0641\u062a\u0648\u062d\u0629 \u0648\u0645\u062a\u0623\u062e\u0631\u0629',awaiting_review:'\u0628\u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629',closed:'\u0645\u0642\u0641\u0648\u0644\u0629 \u0648\u0645\u0639\u062a\u0645\u062f\u0629',open:'\u0645\u0641\u062a\u0648\u062d\u0629',grace:'\u062e\u0644\u0627\u0644 \u0627\u0644\u0648\u0631\u062f\u064a\u0629 \u0623\u0648 \u0645\u0647\u0644\u0629 \u0627\u0644\u0625\u062f\u062e\u0627\u0644',upcoming:'\u0644\u0645 \u064a\u062d\u0646 \u0645\u0648\u0639\u062f\u0647\u0627',not_monitored:'\u0644\u0627 \u062a\u0648\u062c\u062f \u0628\u064a\u0627\u0646\u0627\u062a \u0643\u0627\u0641\u064a\u0629 \u0644\u0644\u0631\u0635\u062f'};
  const labelDaily={complete:'\u0645\u0643\u062a\u0645\u0644\u0629',incomplete:'\u063a\u064a\u0631 \u0645\u0643\u062a\u0645\u0644\u0629',in_progress:'\u0642\u064a\u062f \u0627\u0644\u0627\u0633\u062a\u0643\u0645\u0627\u0644',not_monitored:'\u063a\u064a\u0631 \u0645\u0631\u0635\u0648\u062f\u0629'};
  const styleOf=s=>s==='closed'||s==='complete'?'approved':s==='missing'||s==='unclosed'||s==='incomplete'?'rejected':s==='awaiting_review'||s==='grace'?'pending':'archive';
  const badge=s=>`<span class="chip ${styleOf(s)}" title="${esc(statuses[s]||s)}">${esc(statuses[s]||s)}</span>`;
  const shifts=new Map((data.items||[]).map(s=>[`${s.point_id}:${s.business_date}:${s.shift}`,s]));
  root.innerHTML=`<div class="panel-header"><div><h2>\u0627\u0643\u062a\u0645\u0627\u0644 \u0648\u0631\u062f\u064a\u0627\u062a \u0646\u0642\u0627\u0637 \u0627\u0644\u062a\u062d\u0635\u064a\u0644</h2><p>\u064a\u0639\u0631\u0636 \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a \u0627\u0644\u0645\u062a\u0648\u0642\u0639\u0629 \u062d\u062a\u0649 \u0644\u0648 \u0644\u0645 \u062a\u064f\u0633\u062c\u0644 \u0641\u064a \u0627\u0644\u0646\u0638\u0627\u0645.</p></div></div>
    <div class="mini-metrics shift-metrics shift-coverage-metrics"><div class="mini-metric"><span>\u0648\u0631\u062f\u064a\u0627\u062a \u0627\u0646\u062a\u0647\u062a \u0648\u0644\u0645 \u062a\u064f\u0633\u062c\u0644 \u0625\u0644\u0643\u062a\u0631\u0648\u0646\u064a\u064b\u0627</span><strong>${integer(data.summary.missing)}</strong></div><div class="mini-metric"><span>\u0648\u0631\u062f\u064a\u0629 \u0645\u0641\u062a\u0648\u062d\u0629 \u0648\u0645\u062a\u0623\u062e\u0631\u0629</span><strong>${integer(data.summary.unclosed)}</strong></div><div class="mini-metric"><span>\u0628\u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629</span><strong>${integer(data.summary.awaiting_review)}</strong></div></div>
    <div class="filter-strip shift-coverage-filter"><label>\u0646\u0642\u0637\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644 <select id="coveragePoint" aria-label="\u0646\u0642\u0637\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644"><option value="all">\u0643\u0644 \u0646\u0642\u0627\u0637 \u0627\u0644\u062a\u062d\u0635\u064a\u0644</option>${(data.points||[]).map(p=>`<option value="${p.id}">${esc(p.name)}</option>`).join('')}</select></label>
    <label>\u0639\u0631\u0636 <select id="coverageStatus" aria-label="\u0641\u0644\u062a\u0631 \u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629"><option value="attention">\u064a\u062d\u062a\u0627\u062c \u0645\u062a\u0627\u0628\u0639\u0629</option><option value="all">\u062c\u0645\u064a\u0639 \u0627\u0644\u062d\u0627\u0644\u0627\u062a</option><option value="complete">\u0645\u0643\u062a\u0645\u0644\u0629</option><option value="in_progress">\u0642\u064a\u062f \u0627\u0644\u0627\u0633\u062a\u0643\u0645\u0627\u0644</option><option value="not_monitored">\u063a\u064a\u0631 \u0645\u0631\u0635\u0648\u062f\u0629</option></select></label><label>\u0627\u0644\u0648\u0631\u062f\u064a\u0629 <select id="coverageShift" aria-label="\u0627\u0644\u0648\u0631\u062f\u064a\u0629"><option value="all">\u0643\u0644 \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a</option><option value="night">\u0633\u0647\u0631</option><option value="morning">\u0635\u0628\u0627\u062d\u064a</option><option value="evening">\u0645\u0633\u0627\u0626\u064a</option></select></label><label>\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629 <select id="coverageSlotStatus" aria-label="\u062d\u0627\u0644\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629"><option value="all">\u062c\u0645\u064a\u0639 \u0627\u0644\u062d\u0627\u0644\u0627\u062a</option><option value="missing">\u063a\u064a\u0631 \u0645\u0633\u062c\u0644\u0629</option><option value="unclosed">\u0645\u0641\u062a\u0648\u062d\u0629 \u0645\u062a\u0623\u062e\u0631\u0629</option><option value="awaiting_review">\u0628\u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629</option><option value="closed">\u0645\u0642\u0641\u0648\u0644\u0629</option></select></label></div>
    <div id="coverageRows" aria-live="polite"></div><div class="info-box"><div>\u0627\u0644\u062a\u0646\u0628\u064a\u0647\u0627\u062a \u0644\u0644\u0645\u062a\u0627\u0628\u0639\u0629 \u0641\u0642\u0637\u061b \u0644\u0627 \u062a\u064f\u062b\u0628\u062a \u0623\u0646 \u0627\u0644\u0645\u0648\u0638\u0641 \u063a\u0627\u0628 \u0648\u0644\u0627 \u062a\u064f\u0646\u0634\u0626 \u0642\u064a\u0648\u062f\u064b\u0627 \u0645\u0627\u0644\u064a\u0629. \u0627\u0644\u0631\u0635\u062f \u0627\u0644\u062a\u0627\u0631\u064a\u062e\u064a \u064a\u0628\u062f\u0623 \u0645\u0646 \u0623\u0648\u0644 \u0648\u0631\u062f\u064a\u0629 \u0645\u0633\u062c\u0644\u0629 \u0644\u0643\u0644 \u0646\u0642\u0637\u0629 \u062a\u062d\u0635\u064a\u0644.</div></div>`;
  const renderRows=()=>{
    const point=$('#coveragePoint')?.value||'all',status=$('#coverageStatus')?.value||'attention';
    const code=$('#coverageShift')?.value||'all',slotStatus=$('#coverageSlotStatus')?.value||'all';
    const days=(data.days||[]).filter(d=>{
      if(point!=='all'&&String(d.point_id)!==point)return false;
      if(status!=='all'&&(status==='attention'?d.status!=='incomplete':d.status!==status))return false;
      return (data.items||[]).some(s=>s.point_id===d.point_id&&s.business_date===d.business_date&&
        (code==='all'||s.shift===code)&&(slotStatus==='all'||s.status===slotStatus)) ||
        (code==='all'&&slotStatus==='all');
    }).sort((a,b)=>b.business_date.localeCompare(a.business_date)||a.point_id-b.point_id);
    const renderSlots=d=>(data.items||[]).filter(s=>s.point_id===d.point_id&&s.business_date===d.business_date)
      .filter(s=>(code==='all'||s.shift===code)&&(slotStatus==='all'||s.status===slotStatus))
      .map(s=>`<span class="shift-slot-inline"><b>${esc(s.shift_name||s.shift)}</b> ${badge(s.status)}</span>`).join('')||'—';
    const rows=days.map(d=>`<tr><td>${esc(d.business_date)}</td><td>${esc(d.point_name)}</td><td>${renderSlots(d)}</td><td><span class="chip ${styleOf(d.status)}">${esc(labelDaily[d.status]||d.status)}</span></td></tr>`).join('');
    const cards=days.map(d=>`<article class="shift-coverage-card"><strong>${esc(d.point_name)}</strong><small>${esc(d.business_date)} · ${esc(labelDaily[d.status]||d.status)}</small><div class="shift-coverage-chips">${renderSlots(d)}</div></article>`).join('');
    $('#coverageRows').innerHTML=days.length?`<div class="shift-coverage-desktop">${table(['اليوم','نقطة التحصيل','الورديات وحالاتها','حالة اليومية'],rows)}</div><div class="shift-coverage-mobile">${cards}</div>`:'<p class="empty">لا توجد ورديات في الفلتر المختار.</p>';
  };
  const picker=$('#coverageShift');
  picker.innerHTML='<option value="all">كل الورديات</option>'+[...new Map((data.items||[]).map(s=>[s.shift,s.shift_name||s.shift])).entries()].map(([k,v])=>opt(k,v)).join('');
  $('#coveragePoint')?.addEventListener('change',renderRows);
  $('#coverageStatus')?.addEventListener('change',renderRows);
  $('#coverageShift')?.addEventListener('change',renderRows);
  $('#coverageSlotStatus')?.addEventListener('change',renderRows);
  renderRows();
}

async function renderShifts(){
  const data=await api('/api/shifts?month='+encodeURIComponent(state.shiftMonth));
  const rows=data.items||[];
  const config=await api('/api/cashier/plans').catch(()=>({points:[]}));
  const scheduleOld=data.schedule||[{code:'night',start:'00:00',end:'08:00'},
    {code:'morning',start:'08:00',end:'16:00'},
    {code:'evening',start:'16:00',end:'00:00'}];
  const schedule=[...new Map([...scheduleOld,...config.points.flatMap(p=>p.versions.at(-1)?.slots||[])]
       .map(s=>[s.code,s])).values()];
  const suggested=data.suggested||{business_date:new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'}),shift:'morning'};
  const labels=Object.fromEntries(config.points.flatMap(p=>p.versions.at(-1)?.slots||[]).map(s=>[s.code,s.name]));
  Object.assign(labels,{night:'سهر',morning:'صباحي',evening:'مسائي'});
  const windowOptions=schedule.map(x=>[x.code,`${labels[x.code]||x.code} (${x.start} - ${x.end})`]);
  const orderedOptions=[...windowOptions].sort((a,b)=>Number(b[0]===suggested.shift)-Number(a[0]===suggested.shift));
  const stats={open:0,submitted:0,closed:0};
  rows.forEach(s=>stats[s.status]++);
  const canReview=['owner','reviewer'].includes(state.me.role);
  const options=(state.lookups?.funds||[]).filter(f=>['cash','wallet'].includes(f.kind)).map(f=>[String(f.id),f.name]);
  function shiftButtons(s){
    const controls=[];
    if(canReview)controls.push(`<button class="btn btn-small btn-secondary" data-shift-action="details" data-shift-id="${s.id}">${ico('list')} كشف الحركة</button>`);
    if(s.can_handoff)controls.push(`<button class="btn btn-small btn-primary" data-shift-action="handoff" data-shift-id="${s.id}">\u0627\u0633\u062a\u0644\u0627\u0645 \u0627\u0644\u0639\u0647\u062f\u0629</button>`);
    if(canReview || s.mine)controls.push(`<button class="btn btn-small btn-outline" data-shift-action="evidence" data-shift-id="${s.id}">إثباتات الوردية</button>`);
    if(canReview || s.mine)controls.push(`<button class="btn btn-small btn-outline" data-shift-action="daily" data-shift-id="${s.id}">\u064a\u0648\u0645\u064a\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629</button>`);
    if(s.status==='open'&&s.mine)controls.push(`<button class="btn btn-small btn-primary" data-shift-action="count" data-shift-id="${s.id}">تسليم الجرد</button>`);
    if(s.status==='submitted'&&s.can_review){
      if(s.variance_piasters===0)controls.push(`<button class="btn btn-small btn-primary" data-shift-action="approve" data-shift-id="${s.id}">اعتماد وإقفال</button>`);
      if(s.variance_piasters!==0 && state.me.role==='reviewer' && (!s.variance_case || s.variance_case.status==='rejected'))
        controls.push(`<button class="btn btn-small btn-secondary" data-shift-action="variance-propose" data-shift-id="${s.id}">محضر فرق الجرد</button>`);
      if(s.variance_piasters!==0 && s.can_variance_decision){
        controls.push(`<button class="btn btn-small btn-primary" data-shift-action="variance-approve" data-shift-id="${s.id}">اعتماد التسوية</button>`);
        controls.push(`<button class="btn btn-small btn-secondary" data-shift-action="variance-reject" data-shift-id="${s.id}">رفض التحقيق</button>`);
      }
      if(s.variance_case?.status!=='proposed')controls.push(`<button class="btn btn-small btn-outline" data-shift-action="recount" data-shift-id="${s.id}">طلب إعادة العد</button>`);
    }
    return controls.join('');
  }
  const printed=rows.map(s=>{
    const label=shiftStateLabels[s.status]||s.status;
    const style=s.status==='closed'?'approved':s.status==='submitted'?'pending':'type-transfer';
    const diff=s.variance_piasters;
    const counted=s.counted_piasters==null?'—':fmt(s.counted_piasters)+' ج.م';
    const variance=diff==null?'—':`${diff>0?'+':''}${fmt(diff)} ج.م`;
    return `<tr><td><b>${esc(s.business_date)}</b><br><span class="tiny">${esc(labels[s.shift]||s.shift)}</span></td>
      <td>${esc(s.fund_name)}</td><td>${esc(s.responsible_name)}</td>
      <td><span class="chip ${style}">${esc(label)}</span></td>
      <td>${counted}</td><td>${diff==null?'—':`<b class="${diff===0?'good': 'bad'}">${variance}</b>`}</td>
      <td><div class="row-actions">${shiftButtons(s)||'<span class="tiny">—</span>'}</div></td></tr>`;
  }).join('');
  const mobileCards=rows.map(s=>{
    const diff=s.variance_piasters;
    const actions=shiftButtons(s);
    return `<article class="panel shift-mobile-card">
      <div class="shift-mobile-top"><div><strong>${esc(s.fund_name)}</strong><small>${esc(s.business_date)} · ${esc(labels[s.shift]||s.shift)}</small></div>
        <span class="chip ${s.status==='closed'?'approved':s.status==='submitted'?'pending':'type-transfer'}">${esc(shiftStateLabels[s.status])}</span></div>
      <div class="shift-mobile-owner">صاحب العهدة: <b>${esc(s.responsible_name)}</b></div>
      <div class="shift-mobile-details"><div><span>العد الفعلي</span><strong>${s.counted_piasters==null?'—':fmt(s.counted_piasters)+' ج.م'}</strong></div>
        <div><span>فرق الجرد</span><strong class="${diff===0?'good':diff==null?'':'bad'}">${diff==null?'—':fmt(diff)+' ج.م'}</strong></div></div>
      ${actions?`<div class="shift-mobile-actions">${actions}</div>`:''}</article>`;
  }).join('')||empty('لا توجد ورديات خلال الشهر المحدد.');
  $('#content').innerHTML=head('ضبط حركة الخزن','الورديات والجرد اليومي',
       'صاحب العهدة يعدّ النقد، والمراجع يحقق في الفروق، والمالك أو المحاسب المُفوّض يعتمد التسوية المستقلة عند الحاجة.',
       `<button class="btn btn-primary" id="newShift">${ico('plus')} فتح وردية</button>${state.me.role==='owner'?`<button class="btn btn-secondary" id="shiftScheduleSetup">${ico('settings')} \u0645\u0648\u0627\u0639\u064a\u062f \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a</button>`:''}${canReview?`<button class="btn btn-secondary" id="cashierDaySummary">${ico('chart')} \u064a\u0648\u0645\u064a\u0629 \u0627\u0644\u0643\u0627\u0634\u064a\u0631</button>`:''}`)+
    `<div class="filter-strip panel">${periodInput(state.shiftMonth,'shiftMonth')}<span class="helper-note">الأرصدة داخل هذه الشاشة بالقروش وتُعرض بالجنيه. لا تُرحّل فروق الجرد تلقائيًا.</span></div>`+
    `<div class="info-box"><div><strong>\u0645\u0648\u0627\u0639\u064a\u062f \u0627\u0644\u0648\u0631\u062f\u064a\u0627\u062a \u0642\u0627\u0628\u0644\u0629 \u0644\u0644\u062a\u063a\u064a\u064a\u0631:</strong> ${schedule.map(x=>`${labels[x.code]} ${x.start}-${x.end}`).join(' | ')}<small> \u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0633\u0647\u0631 \u0647\u0648 \u064a\u0648\u0645 \u0628\u062f\u0627\u064a\u062a\u0647 \u0628\u0639\u062f \u0645\u0646\u062a\u0635\u0641 \u0627\u0644\u0644\u064a\u0644.</small></div></div>`+
    `<div class="mini-metrics shift-metrics"><div class="mini-metric"><span>وردية مفتوحة</span><strong>${integer(stats.open)}</strong></div>
      <div class="mini-metric"><span>تنتظر الاعتماد</span><strong>${integer(stats.submitted)}</strong></div>
      <div class="mini-metric"><span>أُغلقت بعد المطابقة</span><strong>${integer(stats.closed)}</strong></div></div>`+
    `<section id="shiftCoverage" class="panel" aria-live="polite"></section>`+
    `<section class="panel"><div class="panel-header"><div><h2>سجل الورديات</h2><p>فرق الجرد الحقيقي يحتاج تحقيق مراجع واعتماد مالك وقيد عهدة مستقل قبل الإقفال.</p></div></div>`+
      `<div class="shift-desktop-only">${table(['اليوم / الفترة','الخزنة','صاحب العهدة','الحالة','العد الفعلي','فرق الجرد','الإجراء'],printed)}</div><div class="shift-mobile-only">${mobileCards}</div></section><section class="panel" id="shiftDetails" hidden aria-live="polite"></section>`+
    `<div class="info-box warning">${ico('alert')}<div><strong>الوردية ليست سندًا ماليًا.</strong> لا تُسوّى الفروق تلقائيًا. بعد التحقيق يقدّم المراجع محضرًا، ويعتمده المالك أو يرفضه، مع قيد عجز/زيادة معلق لا يدخل الإيرادات التشغيلية. لا يجوز للشخص نفسه تسليم الجرد واعتماده.</div></div>`;
  renderShiftCoveragePanel(state.shiftMonth);
  attachMonth('shiftMonth','shiftMonth','shifts');
  $('#cashierDaySummary')?.addEventListener('click',async()=>{
    const form=await modal('\u064a\u0648\u0645\u064a\u0629 \u0643\u0627\u0634\u064a\u0631\u0627\u062a \u0627\u0644\u0645\u0633\u062a\u0634\u0641\u0649',
      '\u0627\u0644\u062a\u062d\u0635\u064a\u0644 \u0627\u0644\u0646\u0642\u062f\u064a \u0644\u064a\u0633 \u0625\u064a\u0631\u0627\u062f\u064b\u0627 \u0645\u0643\u062a\u0633\u0628\u064b\u0627.',[
      {name:'business_date',type:'date',label:'\u062a\u0627\u0631\u064a\u062e \u0627\u0644\u064a\u0648\u0645\u064a\u0629',value:suggested.business_date,required:true}]);
    if(!form)return;
    try{
      const report=await api('/api/shifts/day-summary?business_date='+encodeURIComponent(form.business_date));
      const body=(report.stations||[]).map(sh=>`<tr><td>${esc(sh.point_name)}</td><td>${esc(labels[sh.shift])}</td><td>${esc(sh.responsible_name)}</td><td>${fmt(sh.cash_credited_piasters)}</td><td>${fmt(sh.cash_debited_piasters)}</td><td>${esc(sh.handoff_status||sh.status)}</td></tr>`).join('');
      const ways=Object.entries(report.payment_method_totals_piasters||{}).map(([method,value])=>`<tr><td>${esc(method)}</td><td>${fmt(value)}</td></tr>`).join('');
      const completion=report.is_provisional?'<div class="info-box warning">\u064a\u0648\u0645\u064a\u0629 \u0645\u0624\u0642\u062a\u0629: \u0648\u0631\u062f\u064a\u0627\u062a \u0623\u0648 \u0645\u0631\u0627\u062c\u0639\u0627\u062a \u0644\u0645 \u062a\u0643\u062a\u0645\u0644.</div>':'';
      await modal('\u064a\u0648\u0645\u064a\u0629 \u0627\u0644\u0643\u0627\u0634\u064a\u0631 - '+esc(form.business_date),
        completion+table(['\u0646\u0642\u0637\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644','\u0627\u0644\u0648\u0631\u062f\u064a\u0629','\u0627\u0644\u0645\u0648\u0638\u0641','\u0627\u0644\u0625\u0636\u0627\u0641\u0627\u062a','\u0627\u0644\u0633\u062d\u0628','\u0627\u0644\u0627\u0633\u062a\u0644\u0627\u0645'],body)+
        table(['\u0648\u0633\u064a\u0644\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644','\u0627\u0644\u0645\u0628\u0644\u063a'],ways)+
        `<p>\u0648\u0631\u062f\u064a\u0627\u062a \u0644\u0645 \u062a\u0639\u062a\u0645\u062f \u0628\u0639\u062f: ${integer(report.pending_accounting_review)}</p>`);
    }catch(e){toast(e.message,true)}
  });
  $('#shiftScheduleSetup')?.addEventListener('click',()=>navigate('cashierSettings'));
  $('#newShift').onclick=async()=>{
    const form=await modal('فتح وردية خزنة','يجب فتح وردية الخزنة قبل تسجيل سنداتها. لا يمكن فتح ورديتين نشطتين للحساب نفسه.',[
      {name:'business_date',label:'تاريخ الوردية',type:'date',value:suggested.business_date,required:true},
      {name:'shift',label:'الفترة',type:'select',required:true,options:orderedOptions},
      {name:'fund_id',label:'الخزنة أو المحفظة',type:'select',required:true,options}
    ],form=>{
       const fund=form.elements.fund_id,shift=form.elements.shift;
       const refresh=()=>{
         const point=config.points.find(p=>String(p.fund_id)===fund.value);
         const slots=point?.versions?.at(-1)?.slots;
         const alternatives=(slots||scheduleOld).map(x=>[x.code,`${x.name||labels[x.code]||x.code} — ${x.start||''}`]);
         shift.innerHTML='<option value="">اختر الوردية</option>'+alternatives.map(x=>opt(x[0],x[1],suggested.shift)).join('');
       };
       fund.addEventListener('change',refresh);refresh();
    });
    if(!form)return;
    try{await post('/api/shifts/open',{...form,fund_id:Number(form.fund_id)});toast('تم فتح الوردية باسمك؛ يمكن الآن تسجيل حركاتها');state.shiftMonth=form.business_date.slice(0,7);navigate('shifts')}
    catch(e){toast(e.message,true)}
  };
  $$('[data-shift-action]').forEach(button=>button.onclick=async()=>{
    const id=Number(button.dataset.shiftId),action=button.dataset.shiftAction;
    const row=rows.find(s=>s.id===id);if(!row)return;
    if(action==='evidence'){
      try{
        const existing=await api(`/api/cashier/shifts/${id}/attachments`);
        const list=existing.map(a=>`<p><a href="/api/cashier/shift-attachments/${a.id}/download" target="_blank" rel="noopener">${esc(a.kind==='report'?'كشف الوردية':'صورة الظرف')} — ${esc(a.file_name)}</a></p>`).join('')||'<p>لم تُرفع مستندات لهذه الوردية بعد.</p>';
        const fields=row.status==='closed'?[]:[
          {name:'kind',type:'select',label:'نوع إثبات الوردية',required:true,options:[['report','كشف الوردية'],['envelope','صورة الظرف']]},
          {name:'file',type:'file',label:'صورة أو PDF (حد أقصى 6 ميجابايت)',required:true}];
        const form=await modal('مستندات الوردية',list+'<p>المرفقات أصل محفوظ وغير قابل للحذف أو التعديل بعد الرفع.</p>',fields);
        if(!form||row.status==='closed')return;
        const payload=new FormData();payload.append('file',form.file,form.file.name);
        await api(`/api/cashier/shifts/${id}/attachments/${encodeURIComponent(form.kind)}`,{method:'POST',body:payload});
        toast('تم رفع إثبات الوردية وحفظه في السجل');navigate('shifts');
      }catch(e){toast(e.message,true)}
      return;
    }
    if(action==='handoff'){
      const form=await modal('\u0627\u0633\u062a\u0644\u0627\u0645 \u0627\u0644\u0639\u0647\u062f\u0629 \u0628\u0639\u062f \u0627\u0644\u062c\u0631\u062f',
       '\u0627\u0639\u062f\u062f \u0627\u0644\u0646\u0642\u062f\u064a\u0629 \u0628\u0646\u0641\u0633\u0643. \u0627\u0644\u0645\u0631\u0627\u062c\u0639 \u0627\u0644\u0645\u062d\u0627\u0633\u0628\u064a \u0634\u062e\u0635 \u0622\u062e\u0631.',[
        {name:'counted_amount',type:'number',label:'\u0627\u0644\u0645\u0628\u0644\u063a \u0627\u0644\u0645\u0639\u062f\u0648\u062f \u0628\u0627\u0644\u062c\u0646\u064a\u0647',required:true},
        {name:'decision',type:'select',label:'\u0627\u0644\u0642\u0631\u0627\u0631',options:[['accept','\u0645\u0637\u0627\u0628\u0642 - \u0627\u0633\u062a\u0644\u0645\u062a'],['reject','\u063a\u064a\u0631 \u0645\u0637\u0627\u0628\u0642 - \u0625\u0639\u0627\u062f\u0629 \u0627\u0644\u0639\u062f']]},
        {name:'note',type:'textarea',label:'\u0633\u0628\u0628 \u0631\u0641\u0636 \u0627\u0644\u0639\u062f / \u0645\u0644\u0627\u062d\u0638\u0627\u062a'}]);
      if(!form)return;
      try{await post(`/api/shifts/${id}/handoff`,form);toast('\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0645\u062d\u0636\u0631 \u0627\u0644\u0627\u0633\u062a\u0644\u0627\u0645');navigate('shifts');}catch(e){toast(e.message,true)}
      return;
    }
    if(action==='daily'){
      try{const r=await api(`/api/shifts/${id}/daily-report`);
        const cash=r.cash_movements||[],ways=r.payment_methods||[];
        const html=`<p>${esc(r.business_date)} - ${esc(labels[r.shift]||r.shift)} - ${esc(r.fund_name)}</p>`+
          `<p>\u0627\u0644\u0639\u0647\u062f\u0629 \u0648\u062d\u0631\u0643\u0627\u062a \u0627\u0644\u062f\u0631\u062c</p>`+
          table(['\u0627\u0644\u0628\u064a\u0627\u0646','\u0627\u0644\u0645\u0628\u0644\u063a'],[
            ['\u0631\u0635\u064a\u062f \u0627\u0644\u0628\u062f\u0627\u064a\u0629',r.opening_piasters],
            ['\u0625\u0636\u0627\u0641\u0627\u062a',r.cash_credited_piasters],['\u0633\u062d\u0628',r.cash_debited_piasters],
            ['\u0627\u0644\u0645\u062a\u0648\u0642\u0639',r.expected_piasters]
          ].map(([a,b])=>`<tr><td>${a}</td><td>${b==null?'--':fmt(b)}</td></tr>`).join(''))+
          `<p>\u0648\u0633\u0627\u0626\u0644 \u0627\u0644\u062f\u0641\u0639 (\u063a\u064a\u0631 \u0627\u0644\u0646\u0642\u062f\u064a \u062e\u0627\u0631\u062c \u0627\u0644\u062f\u0631\u062c)</p>`+
          table(['\u0627\u0644\u0648\u0633\u064a\u0644\u0629','\u0627\u0644\u0645\u0628\u0644\u063a'],ways.map(w=>`<tr><td>${esc(w.method)}</td><td>${fmt(w.total_piasters)}</td></tr>`).join(''))+
          table(['\u0627\u0644\u0633\u0646\u062f','\u0627\u0644\u0628\u064a\u0627\u0646','\u0627\u0644\u0623\u062b\u0631'],cash.map(x=>`<tr><td>${esc(x.voucher_no)}</td><td>${esc(x.description)}</td><td>${fmt(x.amount_piasters)}</td></tr>`).join(''));
        await modal('\u064a\u0648\u0645\u064a\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629',html);
      }catch(e){toast(e.message,true)}
      return;
    }
    if(action==='details'){
      try{
        const d=await api(`/api/shifts/${id}/movements`);
        const sh=d.shift;
        const posted=d.movements.map(m=>`<tr><td><b>${esc(m.voucher_no)}</b><br><span class="tiny">${esc(m.date)}</span></td>
            <td>${esc(m.description)}</td><td>${esc(m.created_by)}</td>
            <td class="num ${m.amount_piasters<0?'bad':'good'}">${fmt(m.amount_piasters)}</td></tr>`).join('');
        const el=$('#shiftDetails');
        el.innerHTML=`<div class="panel-header"><div><h2>كشف حركة وردية ${esc(sh.fund_name)}</h2><p>${esc(sh.business_date)} · صاحب العهدة: ${esc(sh.responsible_name)}</p></div></div>
          <div class="shift-summary-grid"><div>رصيد عند الفتح<strong>${fmt(sh.opening_piasters)} ج.م</strong></div>
          <div>إضافات معتمدة<strong class="good">${fmt(d.credited_piasters)} ج.م</strong></div>
          <div>سحوبات معتمدة<strong class="bad">${fmt(d.debited_piasters)} ج.م</strong></div>
          <div>الرصيد المتوقع<strong>${fmt(d.expected_piasters)} ج.م</strong></div></div>`+
          table(['رقم السند / التاريخ','البيان','المدخل','أثر الحركة بالجنيه'],posted);
        el.hidden=false;el.scrollIntoView({behavior:'smooth',block:'nearest'});
      }catch(e){toast(e.message,true)}
      return;
    }
    if(action==='variance-propose'){
      const form=await modal('محضر تحقيق فرق جرد',`الفرق: ${fmt(row.variance_piasters)} جنيه. بعد التقديم لن يُقفل الجرد إلا بقرار المالك أو المفوّض.`,[
        {name:'explanation',label:'نتيجة الفحص وسبب الفرق (12 حرفًا على الأقل)',type:'textarea',required:true}
      ]);
      if(!form)return;
      try{await post(`/api/shifts/${id}/variance-propose`,form);toast('تم إرسال محضر التحقيق للمعتمد المستقل');navigate('shifts')}
      catch(e){toast(e.message,true)}
      return;
    }
    if(action==='variance-approve'||action==='variance-reject'){
      const approve=action==='variance-approve';
      const note=row.variance_case?.explanation||'';
      const form=await modal(approve?'اعتماد تسوية فرق الجرد':'رفض محضر فرق الجرد',
        `فرق الجرد: <strong>${fmt(row.variance_piasters)} جنيه</strong>. التحقيق: ${esc(note)}. ${approve?'سيُسجل قيد عهدة مؤقت مستقل ويُغلق الجرد.':'ستبقى الوردية قيد المراجعة.'}`,[
        {name:'reason',label:'تعليل القرار (إلزامي)',type:'textarea',required:true}
      ]);
      if(!form)return;
      try{await post(`/api/shifts/${id}/variance-decision`,{...form,decision:approve?'approve':'reject'});
        toast(approve?'تم اعتماد التسوية وإقفال الجرد':'رُفض المحضر ويمكن طلب إعادة الجرد');navigate('shifts')}
      catch(e){toast(e.message,true)}
      return;
    }
    let form,path;
    if(action==='count'){
      form=await modal('تسليم جرد الوردية',`الخزنة: ${esc(row.fund_name)}. عدّ الأموال فعليًا قبل تسجيل القيمة. هذه الخطوة تجمّد حركة الحساب إلى حين المراجعة.`,[
        {name:'counted_amount',label:'الرصيد الفعلي بالجنيه',type:'number',value:'0',required:true},
        {name:'note',label:'ملاحظة تسليم / أي فرق',type:'textarea',placeholder:'اختياري'},
        {name:'envelope_present',label:'النقدية محفوظة في ظرف فعلي',type:'checkbox'}]);
      path=`/api/shifts/${id}/count`;
    }else if(action==='recount'){
      form=await modal('طلب إعادة الجرد',`الفرق المسجل: ${row.variance_piasters===null?'—':fmt(row.variance_piasters)+' ج.م'}. تعود الوردية لصاحب العهدة ليعيد العد.`,[
        {name:'reason',label:'سبب إعادة العد (إلزامي)',type:'textarea',required:true}]);
      if(form)form.decision='recount';path=`/api/shifts/${id}/review`;
    }else{
      form=await modal('اعتماد وإقفال الوردية',`الجرد مطابق والصندوق: ${esc(row.fund_name)}. بعد الاعتماد لا يمكن إعادة فتح نفس الوردية.`,[
        {name:'reason',label:'ملاحظة الاعتماد (اختياري)',type:'textarea'}]);
      if(form)form.decision='approve';path=`/api/shifts/${id}/review`;
    }
    if(!form)return;
    try{const result=await post(path,form);toast(result.status==='closed'?'تم اعتماد وإقفال الوردية':result.status==='open'?'تم إرجاع الوردية لإعادة العد':'تم تسليم الجرد للمراجع');navigate('shifts')}
    catch(e){toast(e.message,true)}
  });
}

async function renderPayroll(){
 const period=state.payrollMonth;
 const [d,times,adjustments]=await Promise.all([
   api('/api/payroll?period='+encodeURIComponent(period)),
   api('/api/payroll/work-entries?period='+encodeURIComponent(period)+'&page='+state.payrollWorkPage),
   api('/api/payroll/adjustments?period='+encodeURIComponent(period)+'&page='+state.payrollAdjPage)
 ]);
 const isOwner=state.me.role==='owner',canManage=isOwner||state.me.role==='reviewer';
 const items=d.items;
 const fmtMinutes=m=>`${Math.floor((m||0)/60)} ساعة و${String((m||0)%60).padStart(2,'0')} دقيقة`;
 const typeLabel=v=>v.pay_type==='hourly'?'بالساعة':v.pay_type==='monthly'?'شهري':'غير محدد';
 const signoffLabel=s=>({pending:'بانتظار اعتماد آخر',approved:'معتمد للصرف',rejected:'مرفوض للمراجعة',legacy:'كشف سابق'}[s]||'لم يصدر');
 const signoffBadge=s=>`<span class="chip ${s==='approved'?'approved':s==='pending'?'pending':s==='rejected'?'rejected':'archive'}">${esc(signoffLabel(s))}</span>`;
 const adjustmentLabels={overtime_premium:'علاوة عمل إضافي',paid_leave_credit:'بدل إجازة مدفوعة',bonus:'مكافأة',other_addition:'إضافة أخرى',lateness_deduction:'خصم تأخير',absence_deduction:'خصم غياب',other_deduction:'خصم آخر'};
 const isAddition=kind=>['overtime_premium','paid_leave_credit','bonus','other_addition'].includes(kind);
 const rateLabel=v=>v.pay_type==='hourly'?`${fmt(v.hourly_rate_piasters)} ج.م / ساعة`:
    v.monthly_piasters!==null?`${fmt(v.monthly_piasters)} ج.م / شهر`:'—';
 const actions=v=>{
   let bs=[];
   if(isOwner)bs.push(`<button class="btn btn-small btn-${v.pay_type?'outline':'primary'}" data-salary="${v.id}">${v.pay_type?'شروط أجر جديدة':'تحديد نوع الأجر'}</button>`);
   if(canManage&&v.pay_type==='hourly'&&v.accrual_id===null)bs.push(`<button class="btn btn-small btn-secondary" data-hour="${v.id}">تسجيل ساعات</button>`);
   if(canManage&&v.pay_type&&v.accrual_id===null)bs.push(`<button class="btn btn-small btn-outline" data-adjust="${v.id}">بند أجر / خصم</button>`);
   if(isOwner&&v.pay_type&&v.accrual_id===null){
     if(v.pending_adjustments)bs.push(`<span class="chip pending">بنود أجر تنتظر مراجعة</span>`);
     else if(v.pay_type==='hourly'&&v.pending_work_entries)bs.push(`<span class="chip pending">ساعات تنتظر مراجعة</span>`);
     else if(v.pay_type==='hourly'&&!v.approved_work_entries)bs.push(`<span class="chip pending">أدخل ساعات معتمدة أولًا</span>`);
     else bs.push(`<button class="btn btn-small btn-primary" data-accrual="${v.id}">إعداد كشف للمراجعة</button>`);
   }
   if(canManage&&v.accrual_id&&v.signoff_status==='pending'&&v.prepared_by!==state.me.id)
     bs.push(`<button class="btn btn-small btn-primary" data-signoff="${v.accrual_id}" data-decision="approve">اعتماد الكشف</button><button class="btn btn-small btn-outline" data-signoff="${v.accrual_id}" data-decision="reject">رفض</button>`);
   if(isOwner&&v.accrual_id&&v.signoff_status==='rejected')bs.push(`<button class="btn btn-small btn-secondary" data-resubmit="${v.accrual_id}">إعادة تقديم</button>`);
   if(isOwner&&v.accrual_id&&v.can_correct)bs.push(`<button class="btn btn-small btn-outline" data-correct="${v.accrual_id}">تصحيح الاستحقاق</button>`);
   if(isOwner&&v.due_piasters>0)bs.push(`<button class="btn btn-small btn-secondary" data-pay="${v.id}" data-dept="${v.department_id||''}">صرف</button>`);
   if(isOwner&&v.advances_outstanding_piasters>0&&v.due_piasters>0)bs.push(`<button class="btn btn-small btn-secondary" data-allocate="${v.id}" data-available="${v.advances_outstanding_piasters}">تسوية سلفة</button>`);
   return `<div class="row-actions">${bs.join('')||'—'}</div>`;
 };
 const desktop=table(['الموظف / القسم','نظام الأجر','الأجر المتفق عليه','ساعات معتمدة','الأساسي المحسوب','صافي الاستحقاق','حالة الاعتماد','المتبقي','الإجراء'],items.map(v=>`<tr>
   <td><b>${esc(v.name)}</b><div class="tiny">${esc(v.department||'لم يُحدد قسم')}</div></td>
   <td><span class="chip ${v.pay_type?'type-transfer':'pending'}">${typeLabel(v)}</span></td>
   <td class="num">${rateLabel(v)}</td>
   <td>${v.pay_type==='hourly'?esc(fmtMinutes(v.approved_work_minutes)):'—'}${v.pending_work_entries?`<div class="tiny text-danger">${integer(v.pending_work_entries)} قيد المراجعة</div>`:''}</td>
   <td class="num">${v.estimated_base_piasters===null?'—':fmt(v.estimated_base_piasters)}</td>
   <td class="num">${v.accrual_piasters===null?'—':fmt(v.accrual_piasters)}</td>
   <td>${signoffBadge(v.signoff_status)}</td>
   <td class="num ${v.due_piasters>0?'text-danger':''}">${v.due_piasters===null?'—':fmt(v.due_piasters)}</td>
   <td>${actions(v)}</td></tr>`).join(''));
 const mobile=items.map(v=>`<article class="panel payroll-card">
   <div class="payroll-card-head"><div><strong>${esc(v.name)}</strong><small>${esc(v.department||'القسم غير محدد')}</small></div><span class="chip ${v.pay_type?'type-transfer':'pending'}">${typeLabel(v)}</span></div>
   <div class="payroll-card-signoff">${signoffBadge(v.signoff_status)}</div>
   <div class="payroll-card-details"><div><span>الأجر المتفق عليه</span><strong>${rateLabel(v)}</strong></div>
   <div><span>الأساسي المحسوب</span><strong>${v.estimated_base_piasters===null?'—':fmt(v.estimated_base_piasters)+' ج.م'}</strong></div>
   <div><span>الصافي المُعَدّ للمراجعة</span><strong>${v.accrual_piasters===null?'—':fmt(v.accrual_piasters)+' ج.م'}</strong></div>
   <div><span>المتبقي</span><strong>${v.due_piasters===null?'—':fmt(v.due_piasters)+' ج.م'}</strong></div></div>
   ${v.pay_type==='hourly'?`<p class="payroll-hours">الساعات المعتمدة: ${esc(fmtMinutes(v.approved_work_minutes))}${v.pending_work_entries?` • ${integer(v.pending_work_entries)} قيد المراجعة`:''}</p>`:''}
   <div class="payroll-card-actions">${actions(v)}</div></article>`).join('') || empty('لا يوجد موظفون حتى الآن');
 const workShift=t=>({morning:'صباحي',evening:'مسائي',night:'ليلي',central:'إداري'}[t.shift]||t.shift);
 const workStatus=t=>({pending:'بانتظار المراجعة',approved:'معتمد',rejected:'مرفوض',voided:'ملغي بتصحيح'}[t.status]||t.status);
 const workButtons=t=>{
   let list=[];
   if(t.status==='pending'&&canManage&&t.created_by_name!==state.me.username){
     list.push(`<button class="btn btn-small btn-primary" data-work-decision="approve" data-work-id="${t.id}">اعتماد</button>`);
     list.push(`<button class="btn btn-small btn-outline" data-work-decision="reject" data-work-id="${t.id}">رفض</button>`);
   }
   if(t.status==='approved'&&isOwner&&!items.some(x=>x.id===t.employee_id&&x.accrual_id))
     list.push(`<button class="btn btn-small btn-outline" data-work-void="${t.id}">تصحيح</button>`);
   return `<div class="row-actions">${list.join('')||'<span class="tiny">—</span>'}</div>`;
 };
 const workBadge=t=>`<span class="chip ${t.status==='approved'?'approved':t.status==='pending'?'pending':'rejected'}">${esc(workStatus(t))}</span>`;
 const timeRows=times.items.map(t=>`<tr><td><b>${esc(t.employee_name)}</b></td><td>${esc(t.work_date)}</td>
   <td>${esc(workShift(t))}</td><td>${esc(fmtMinutes(t.work_minutes))}</td><td>${esc(t.note||'—')}</td><td>${esc(t.created_by_name)}</td>
   <td>${workBadge(t)}</td><td>${workButtons(t)}</td></tr>`).join('');
 const timeCards=times.items.map(t=>`<article class="panel payroll-time-card">
    <div class="payroll-card-head"><div><strong>${esc(t.employee_name)}</strong><small>${esc(t.work_date)} • ${esc(workShift(t))}</small></div>${workBadge(t)}</div>
    <div class="payroll-time-duration">${esc(fmtMinutes(t.work_minutes))}</div>
    <p class="payroll-hours">وصف العمل: ${esc(t.note||'—')}</p>
    <p class="payroll-hours">سجّلها: ${esc(t.created_by_name)}${t.review_note?' • سبب القرار: '+esc(t.review_note):''}</p>
    <div class="payroll-card-actions">${workButtons(t)}</div></article>`).join('')||empty('لا توجد سجلات ساعات في الشهر');
 const adjustmentBadge=a=>`<span class="chip ${a.status==='approved'?'approved':a.status==='pending'?'pending':'rejected'}">${esc({pending:'بانتظار المراجعة',approved:'معتمد',rejected:'مرفوض',voided:'ملغى بتصحيح'}[a.status]||a.status)}</span>`;
 const adjustmentButtons=a=>{
   const list=[];
   if(a.status==='pending'&&canManage&&a.created_by_name!==state.me.username){
     list.push(`<button class="btn btn-small btn-primary" data-adjust-decision="approve" data-adjust-id="${a.id}">اعتماد</button>`);
     list.push(`<button class="btn btn-small btn-outline" data-adjust-decision="reject" data-adjust-id="${a.id}">رفض</button>`);
   }
   if(isOwner&&a.status==='approved'&&!items.some(v=>v.id===a.employee_id&&v.accrual_id))
     list.push(`<button class="btn btn-small btn-outline" data-adjust-void="${a.id}">إلغاء موثق</button>`);
   return `<div class="row-actions">${list.join('')||'<span class="tiny">—</span>'}</div>`;
 };
 const adjustmentRows=adjustments.items.map(a=>`<tr><td><b>${esc(a.employee_name)}</b></td><td>${esc(adjustmentLabels[a.kind]||a.kind)}</td>
    <td class="num ${isAddition(a.kind)?'text-success':'text-danger'}">${isAddition(a.kind)?'+':'−'}${fmt(a.amount_piasters)}</td>
    <td class="adj-reason">${esc(a.note)}</td><td>${adjustmentBadge(a)}</td><td>${adjustmentButtons(a)}</td></tr>`).join('');
 const adjustmentCards=adjustments.items.map(a=>`<article class="panel payroll-time-card">
    <div class="payroll-card-head"><div><strong>${esc(a.employee_name)}</strong><small>${esc(adjustmentLabels[a.kind]||a.kind)}</small></div>${adjustmentBadge(a)}</div>
    <div class="payroll-time-duration ${isAddition(a.kind)?'text-success':'text-danger'}">${isAddition(a.kind)?'+':'−'}${fmt(a.amount_piasters)} ج.م</div>
    <p class="payroll-hours">${esc(a.note)}</p><p class="payroll-hours">المدخل: ${esc(a.created_by_name)}${a.reviewed_by_name?' • المراجع: '+esc(a.reviewed_by_name):''}</p>
    <div class="payroll-card-actions">${adjustmentButtons(a)}</div></article>`).join('')||empty('لا توجد بنود إضافات أو خصومات لهذا الشهر');
 $('#content').innerHTML=head('الموارد البشرية','المرتبات والساعات','نوعا أجر، وبنود حضور وإضافي وغياب موثقة، واعتماد مستقل للكشف قبل الصرف.',
   (isOwner?`<button class="btn btn-secondary" id="addEmployee">${ico('plus')} موظف جديد</button>`:'')+
   `<button class="btn btn-secondary" id="exportPayroll">${ico('download')} تصدير المرتبات</button>`+
   `<button class="btn btn-secondary" id="exportHours">${ico('download')} كشف ساعات العمل</button>`)+
 `<div class="filter-strip panel">${periodInput(period,'payrollMonth')}<span class="helper-note">ساعات العمل تختلف عن وردية الخزنة، وتوثق يدويًا حتى اعتمادها من مراجع آخر.</span></div>`+
 `<div class="mini-metrics payroll-metrics"><div class="mini-metric"><span>موظفون بالساعة</span><strong>${integer(d.hourly_employees)}</strong></div>
  <div class="mini-metric"><span>موظفون شهريون</span><strong>${integer(d.monthly_employees)}</strong></div>
  <div class="mini-metric"><span>سجلات ساعات تنتظر الاعتماد</span><strong>${integer(d.pending_work_entries)}</strong></div>
  <div class="mini-metric"><span>إضافات وخصومات معلقة</span><strong>${integer(d.pending_adjustments||0)}</strong></div>
  <div class="mini-metric"><span>كشوف تحتاج توقيعًا ثانيًا</span><strong>${integer(d.pending_signoffs||0)}</strong></div>
  <div class="mini-metric"><span>رواتب معتمدة متبقية</span><strong>${fmt(d.due_total_piasters)} ج.م</strong></div></div>`+
 `<section class="panel"><div class="panel-header"><div><h2>كشف المستحقات</h2><p>الموظف بالساعة: أجر الساعة × الساعات المعتمدة، ويُقرب الإجمالي مرة واحدة لأقرب قرش.</p></div></div>
 <div class="payroll-desktop-only">${desktop}</div><div class="payroll-mobile-only">${mobile}</div></section>`+
 `<section class="panel" style="margin-top:18px"><div class="panel-header"><div><h2>سجل ساعات العمل والاعتماد</h2><p>لن تدخل الساعات المعلقة في احتساب الراتب. ولا يمكن للمستخدم اعتماد الساعات التي أدخلها بنفسه.</p></div></div>
 <div class="work-log-desktop">${table(['الموظف','التاريخ','الفترة','المدة','وصف العمل','أدخلها','الحالة','الإجراء'],timeRows)}</div>
 <div class="work-log-mobile">${timeCards}</div>
 <div class="table-footer"><span>السجلات: ${integer(times.total)} · صفحة ${integer(times.page)} من ${integer(Math.max(1,times.pages))} · المعلقة أولًا</span>
 <div class="paging"><button class="btn btn-small btn-secondary" id="workPrev" ${times.page<=1?'disabled':''}>السابق</button>
 <button class="btn btn-small btn-secondary" id="workNext" ${times.page>=times.pages?'disabled':''}>التالي</button></div></div></section>`+
 `<section class="panel" style="margin-top:18px"><div class="panel-header"><div><h2>الإضافي والخصومات والإجازات المدفوعة</h2><p>مبالغ يدوية معللة، تُراجع قبل إعداد الاستحقاق. لا يُفترض معدل إضافي أو غياب تلقائي.</p></div></div>
 <div class="payroll-adj-desktop">${table(['الموظف','نوع البند','المبلغ','سبب البند','المراجعة','الإجراء'],adjustmentRows)}</div>
 <div class="payroll-adj-mobile">${adjustmentCards}</div>
 <div class="table-footer"><span>عدد البنود: ${integer(adjustments.total)} · صفحة ${integer(adjustments.page)} من ${integer(Math.max(1,adjustments.pages))}</span>
 <div class="paging"><button class="btn btn-small btn-secondary" id="adjPrev" ${adjustments.page<=1?'disabled':''}>السابق</button>
 <button class="btn btn-small btn-secondary" id="adjNext" ${adjustments.page>=adjustments.pages?'disabled':''}>التالي</button></div></div></section>`+
 `<div class="info-box" style="margin-top:18px">${ico('shield')}<div>${esc(d.note)} لا تُحوّل الساعات مباشرة إلى مصروف نقدي؛ الاستحقاق يسبق السند المالي.</div></div>`;
 attachMonth('payrollMonth','payrollMonth','payroll');
 $('#payrollMonth').addEventListener('change',()=>{state.payrollWorkPage=1;state.payrollAdjPage=1});
 $('#workPrev')?.addEventListener('click',()=>{if(state.payrollWorkPage>1){state.payrollWorkPage--;navigate('payroll')}});
 $('#workNext')?.addEventListener('click',()=>{if(state.payrollWorkPage<times.pages){state.payrollWorkPage++;navigate('payroll')}});
 $('#adjPrev')?.addEventListener('click',()=>{if(state.payrollAdjPage>1){state.payrollAdjPage--;navigate('payroll')}});
 $('#adjNext')?.addEventListener('click',()=>{if(state.payrollAdjPage<adjustments.pages){state.payrollAdjPage++;navigate('payroll')}});
 $('#exportPayroll').onclick=()=>window.location.assign('/api/payroll/export.csv?period='+encodeURIComponent(period));
 $('#exportHours').onclick=()=>window.location.assign('/api/payroll/work-entries/export.csv?period='+encodeURIComponent(period));
 $('#addEmployee')?.addEventListener('click',async()=>{
   const data=await modal('إضافة موظف','حدد اسم الموظف ووظيفته أولًا ثم نوع أجره.',[
     {name:'name',label:'اسم الموظف',required:true},{name:'code',label:'كود الموظف',required:true,placeholder:'EMP040'},
     {name:'job_title',label:'الوظيفة'},{name:'department_id',label:'القسم',type:'select',options:state.lookups.departments.map(x=>[x.id,x.name])}
   ]);
   if(!data)return;data.department_id=data.department_id?Number(data.department_id):null;
   try{await post('/api/employees',data);state.lookups=await api('/api/lookups');toast('تم إنشاء ملف الموظف');navigate('payroll')}catch(e){toast(e.message,true)}
 });
 $$('[data-salary]').forEach(b=>b.onclick=async()=>{
   const emp=items.find(v=>v.id===+b.dataset.salary);if(!emp)return;
   const nextMonth=new Date(Date.UTC(+period.slice(0,4),+period.slice(5,7),1)).toISOString().slice(0,7);
   const chosen=await modal('نوع الأجر للموظف',`الموظف: ${esc(emp.name)}. ${emp.pay_type?'لا تغير شهرًا له شروط أجر قائمة؛ اعمل شروطًا جديدة من شهر لاحق.':'اختر نظام الأجر الأول.'}`, [
      {name:'month',type:'month',label:'يسري من شهر',value:emp.pay_type?nextMonth:period,required:true},
      {name:'pay_type',type:'select',label:'نظام الحساب',required:true,options:[['monthly','راتب شهري ثابت'],['hourly','أجر بالساعة']]}
   ]);
   if(!chosen)return;
   const isHourly=chosen.pay_type==='hourly';
   const amount=await modal(isHourly?'تحديد أجر الساعة':'تحديد الراتب الشهري',
     `الموظف: ${esc(emp.name)} • ${isHourly?'الأجر لكل ساعة عمل':'الراتب الأساسي الشهري'}`,[
      {name:'amount',type:'number',label:isHourly?'أجر الساعة بالجنيه':'الراتب الشهري بالجنيه',required:true,placeholder:'0.00'},
      {name:'note',label:'ملاحظات التعاقد (اختياري)'}
   ]);
   if(!amount)return;
   const payload={month:chosen.month,pay_type:chosen.pay_type,note:amount.note};
   payload[isHourly?'hourly_rate':'monthly_salary']=amount.amount;
   try{await post(`/api/employees/${emp.id}/salary-term`,payload);toast('تم حفظ نوع الأجر وشروطه');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-hour]').forEach(b=>b.onclick=async()=>{
   const emp=items.find(v=>v.id===+b.dataset.hour);if(!emp)return;
   const form=await modal('إدخال ساعات عمل',`الموظف: ${esc(emp.name)} · أجر الساعة: ${fmt(emp.hourly_rate_piasters)} ج.م. سيتطلب الإدخال اعتماد مستخدم آخر.`,[
     {name:'work_date',label:'تاريخ العمل',type:'date',required:true,value:period+'-01'},
     {name:'shift',label:'الفترة',type:'select',required:true,options:[['morning','صباحية'],['evening','مسائية'],['night','ليلية'],['central','عمل إداري']]},
     {name:'hours',label:'ساعات كاملة',type:'number',step:'1',value:'8',required:true},
     {name:'minutes',label:'دقائق إضافية (0–59)',type:'number',step:'1',value:'0',required:true},
     {name:'note',label:'وصف العمل / مرجع الحضور',required:true,placeholder:'وردية المعمل أو كشف الحضور'}
   ]);
   if(!form)return;
   try{await post('/api/payroll/work-entries',{...form,employee_id:emp.id,hours:Number(form.hours),minutes:Number(form.minutes)});toast('تم تسجيل الساعات؛ بانتظار اعتماد شخص آخر');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-work-decision]').forEach(b=>b.onclick=async()=>{
   const entry=times.items.find(v=>v.id===+b.dataset.workId);if(!entry)return;
   const isApprove=b.dataset.workDecision==='approve';
   const data=await modal(isApprove?'اعتماد ساعات العمل':'رفض ساعات العمل',
     `${esc(entry.employee_name)} • ${esc(entry.work_date)} • ${esc(fmtMinutes(entry.work_minutes))} • سجلها ${esc(entry.created_by_name)} • وصف العمل: ${esc(entry.note||'—')}`, 
     isApprove?[]:[{name:'reason',label:'سبب الرفض',type:'textarea',required:true}]);
   if(!data)return;
   try{await post(`/api/payroll/work-entries/${entry.id}/decision`,{decision:isApprove?'approve':'reject',reason:data.reason||''});toast('تم تسجيل قرار مراجعة الساعات');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-work-void]').forEach(b=>b.onclick=async()=>{
   const data=await modal('تصحيح سجل ساعات معتمد','إلغاء سجل الساعات قبل اعتماد كشف الراتب؛ سيبقى تاريخ التعديل في سجل المراجعة.',[
     {name:'reason',label:'سبب التصحيح',type:'textarea',required:true}
   ]);
   if(!data)return;
   try{await post(`/api/payroll/work-entries/${+b.dataset.workVoid}/void`,{decision:'void',reason:data.reason});toast('تم إلغاء السجل المعتمد؛ سجّل الصحيح من جديد');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-adjust]').forEach(b=>b.onclick=async()=>{
   const emp=items.find(v=>v.id===+b.dataset.adjust);if(!emp)return;
   const values=Object.entries(adjustmentLabels).map(([value,label])=>[value,label]);
   const form=await modal('طلب بند إضافة أو خصم',`الموظف: ${esc(emp.name)} • الفترة: ${esc(period)}. المبلغ يدوي حسب السياسة التي تعتمدها الإدارة، وليس خصمًا آليًا.`,[
     {name:'kind',type:'select',label:'نوع البند',required:true,options:values},
     {name:'amount',type:'number',label:'المبلغ بالجنيه',required:true,placeholder:'0.00'},
     {name:'note',type:'textarea',label:'السبب / مرجع الموافقة',required:true,placeholder:'اذكر اليوم والسبب ومرجع إذن الإدارة'}
   ]);
   if(!form)return;
   try{await post('/api/payroll/adjustments',{...form,employee_id:emp.id,period});toast('تم إرسال البند للمراجعة');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-adjust-decision]').forEach(b=>b.onclick=async()=>{
   const record=adjustments.items.find(a=>a.id===+b.dataset.adjustId);if(!record)return;
   const decision=b.dataset.adjustDecision;
   const fields=decision==='approve'?[]:[{name:'reason',type:'textarea',label:'سبب الرفض',required:true}];
   const form=await modal(decision==='approve'?'اعتماد بند أجر':'رفض بند أجر',
      `${esc(record.employee_name)} • ${esc(adjustmentLabels[record.kind]||record.kind)} • ${fmt(record.amount_piasters)} ج.م • ${esc(record.note)}`,fields);
   if(!form)return;
   try{await post(`/api/payroll/adjustments/${record.id}/decision`,{decision,reason:form.reason||''});toast('تم تسجيل قرار المراجعة');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-adjust-void]').forEach(b=>b.onclick=async()=>{
   const form=await modal('إلغاء بند أجر معتمد','لا يمكن الإلغاء بعد إعداد كشف الاستحقاق، وسيظل أثر العملية في سجل المراجعة.',[
       {name:'reason',type:'textarea',label:'سبب الإلغاء',required:true}]);
   if(!form)return;
   try{await post(`/api/payroll/adjustments/${+b.dataset.adjustVoid}/void`,{reason:form.reason});toast('تم إلغاء البند قبل إعداد الكشف');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-signoff]').forEach(b=>b.onclick=async()=>{
   const record=items.find(v=>v.accrual_id===+b.dataset.signoff);if(!record)return;
   const decision=b.dataset.decision;
   const form=await modal(decision==='approve'?'الاعتماد النهائي لكشف الأجر':'رفض كشف الأجر',
     `${esc(record.name)} • الصافي: ${fmt(record.accrual_piasters)} ج.م • تأكد من ساعات العمل والبنود المعتمدة. بعد الموافقة يمكن ترحيل سند الصرف مع مراجعة سند مستقلة.`,
     decision==='approve'?[]:[{name:'reason',type:'textarea',label:'سبب رفض الكشف',required:true}]);
   if(!form)return;
   try{await post(`/api/payroll/accrual/${record.accrual_id}/decision`,{decision,reason:form.reason||''});toast('تم تسجيل قرار اعتماد كشف المرتبات');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-resubmit]').forEach(b=>b.onclick=async()=>{
   const form=await modal('إعادة تقديم الكشف المرفوض','راجع الأرقام والمستندات قبل إعادة إرساله لمراجع مستقل.',[
     {name:'reason',type:'textarea',label:'سبب إعادة التقديم',required:true}]);
   if(!form)return;
   try{await post(`/api/payroll/accrual/${+b.dataset.resubmit}/resubmit`,{reason:form.reason});toast('أُعيد تقديم الكشف للمراجعة');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-accrual]').forEach(b=>b.onclick=async()=>{
   const emp=items.find(v=>v.id===+b.dataset.accrual);if(!emp)return;
   const base=emp.estimated_base_piasters;
   const extra=emp.pay_type==='hourly'?`الساعات: ${esc(fmtMinutes(emp.approved_work_minutes))}، وسعر الساعة: ${fmt(emp.hourly_rate_piasters)} ج.م. `:'';
   const form=await modal('إعداد استحقاق للمراجعة',`${esc(emp.name)} • ${extra}الأساسي: ${fmt(base)} ج.م. البنود المعتمدة: إضافات ${fmt(emp.approved_adjustment_additions_piasters)} وخصومات ${fmt(emp.approved_adjustment_deductions_piasters)} ج.م. الكشف لا يُصرف قبل اعتماد شخص آخر.`,[
     {name:'additions',type:'number',label:'إضافة يدوية أخرى (بدون تكرار البنود المعتمدة)',value:'0',required:true},
     {name:'deductions',type:'number',label:'خصم يدوي آخر (بدون تكرار البنود المعتمدة)',value:'0',required:true}
   ]);
   if(!form)return;
   try{await post('/api/payroll/accrual',{employee_id:emp.id,period,...form});toast('تم إعداد الاستحقاق وإرساله لمراجع آخر');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-correct]').forEach(b=>b.onclick=async()=>{
   const record=items.find(v=>v.accrual_id===+b.dataset.correct);if(!record)return;
   const form=await modal('تصحيح مستحقات قبل الصرف',`الموظف: ${esc(record.name)}. لا يجوز تغيير الساعات المعتمدة بعد اعتماد الاستحقاق.`,[
     {name:'additions',type:'number',label:'الإضافات بالجنيه',value:String(money(record.additions_piasters)),required:true},
     {name:'deductions',type:'number',label:'الخصومات بالجنيه',value:String(money(record.deductions_piasters)),required:true},
     {name:'reason',type:'textarea',label:'سبب التصحيح',required:true}
   ]);
   if(!form)return;
   try{await post(`/api/payroll/accrual/${record.accrual_id}/correct`,form);toast('تم تصحيح الاستحقاق وإعادته للمراجعة');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-pay]').forEach(b=>b.onclick=()=>{
   state.prefill={kind:'payment',employee_id:b.dataset.pay,salary_period:period,category_code:'salary_payment',department_id:b.dataset.dept};navigate('new');
 });
 $$('[data-allocate]').forEach(b=>b.onclick=async()=>{
   const form=await modal('تسوية سلفة مع الراتب',`السلف المتاحة: ${fmt(+b.dataset.available)} جنيه`,[
     {name:'amount',label:'مبلغ التسوية بالجنيه',type:'number',required:true}]);
   if(!form)return;
   try{await post('/api/payroll/allocate-advance',{employee_id:+b.dataset.allocate,period,amount:form.amount});toast('تم تحديث المستحق والسلفة');navigate('payroll')}
   catch(e){toast(e.message,true)}
 });
}

async function renderBankReconciliation(){
 const parms=new URLSearchParams({period:state.bankMonth});
 if(state.bankFundId)parms.set('fund_id',state.bankFundId);
 let d;
 try{d=await api('/api/bank-reconciliation?'+parms)}
 catch(err){
  if(state.me.role==='reviewer' && state.bankFundId && /تفويض|صلاحية/.test(err.message)){
   // The owner may revoke the selected bank while this page is open.
   state.bankFundId=null;
   d=await api('/api/bank-reconciliation?'+new URLSearchParams({period:state.bankMonth}));
  }else throw err;
 }
 if(!d.banks.length){
   $('#content').innerHTML=head('المراجعة البنكية','مطابقة كشف الحساب','اربط حركات دفتر البنك بكشف البنك فقط بعد إنشاء حساب بنكي.')+
   `<div class="info-box warning">${ico('alert')}<div>${state.me.role==='owner'?'لا توجد حسابات بنكية فعالة. أضف حسابًا بنكيًا من شاشة الخزن والحسابات.':'لم تُمنح صلاحية مراجعة أي حساب بنكي لحسابك. اطلب تفويضًا محددًا من المالك.'}</div></div>`;
   return;
 }
 state.bankFundId=d.fund.id;
 const b=d.batch;
 const statusText=b?({draft:'قيد المطابقة',approved:'مُطابق ومعتمد'}[b.status]||b.status):'لم يُستورد كشف';
 const canSubmit=d.permissions?.can_submit===true;
 const canApprove=d.permissions?.can_approve===true;
 const editable=canSubmit && b && b.status==='draft' && !d.month_closed;
 const bankReady=!!b && d.unmatched_bank_count===0 && d.unmatched_ledger.length===0 &&
    d.pending_vouchers===0 && d.balance_difference_piasters===0 &&
    d.bank_opening_piasters===d.ledger_opening_piasters;
 const canSign=canApprove && b && b.status==='draft' && !d.month_closed &&
    b.imported_by!==state.me.id && bankReady;
 const signHold=b?.imported_by===state.me.id?'لا يجوز لمستورد الكشف اعتماده بنفسه.':
    !canApprove?'يلزم تفويض اعتماد مستقل من المالك.':
    !bankReady?'يجب استكمال مطابقة جميع الحركات والأرصدة قبل الاعتماد.':
    'بانتظار مراجع آخر مخوّل بالاعتماد.';
 const bankSelect=`<label class="compact-field">الحساب البنكي <select id="bankFundFilter">${d.banks.map(x=>opt(x.id,x.name,d.fund.id)).join('')}</select></label>`;
 const rows=d.lines.map(line=>{
   const matched=!!line.match_id;
   const choices=d.unmatched_ledger.filter(m=>m.amount_piasters===line.amount_piasters);
   const matchWidget=editable && !matched ? `<div class="bank-action-row"><label>حركة دفتر مقابلة
     <select aria-label="اختر الحركة المقابلة للسطر ${line.id}" data-bank-choice="${line.id}"><option value="">اختر سندًا بنفس القيمة والإشارة</option>${choices.map(m=>opt(m.movement_id,`${m.voucher_no} · ${m.booked_on} · ${m.description.slice(0,45)} · ${fmt(m.amount_piasters)}`)).join('')}</select></label>
     <button class="btn btn-primary" data-bank-match="${line.id}" ${choices.length?'':'disabled'}>مطابقة</button></div>`:'';
   const undo=editable && matched?`<button class="btn btn-secondary" data-bank-unmatch="${line.match_id}">فك المطابقة</button>`:'';
   return `<article class="panel bank-line"><div class="bank-line-top"><div><strong>${esc(line.tx_date)} <span class="tiny">#${line.line_no}</span></strong><p>${esc(line.description)}</p><small>مرجع البنك: ${esc(line.reference||'غير مدخل')}</small></div>
     <div class="bank-line-status"><strong class="amount ${line.amount_piasters<0?'bad':'good'}">${fmt(line.amount_piasters)} ج.م</strong><span class="chip ${matched?'approved':'pending'}">${matched?'مطابق':'غير مطابق'}</span></div></div>
     ${matched?`<p class="bank-match-info">${ico('check')} سند ${esc(line.voucher_no)} · ${esc(line.match_date)} ${undo}</p>`:matchWidget}</article>`;
 });
 const unmatched=d.unmatched_ledger.map(m=>`<div class="bank-ledger-row"><div><strong>${esc(m.voucher_no)}</strong><small>${esc(m.booked_on)} · ${esc(m.description)}</small></div><strong class="amount ${m.amount_piasters<0?'bad':'good'}">${fmt(m.amount_piasters)}</strong></div>`).join('');
 const out=new URLSearchParams({period:d.month,fund_id:String(d.fund.id)});
 $('#content').innerHTML=head('مراجعة الحسابات','مطابقة البنك الشهرية','المستند البنكي منفصل تمامًا عن الدفتر المالي؛ لا ينشئ أي سندات جديدة.',b?`<a class="btn btn-secondary" href="/api/bank-reconciliation/export.csv?${out}" download>${ico('download')} تصدير المطابقة</a> <a class="btn btn-secondary" href="/api/bank-reconciliation/${b.id}/source.csv" download>${ico('file')} الكشف الأصلي</a>`:'')+
 `<div class="filter-strip panel bank-toolbar">${periodInput(state.bankMonth,'bankMonth')}${bankSelect}<span class="chip ${b?.status==='approved'?'approved':'pending'}">${esc(statusText)}</span><span class="chip ${canSubmit?'approved':'pending'}">${canSubmit?'إعداد المطابقة متاح':'عرض فقط'}</span><span class="chip ${canApprove?'approved':'pending'}">${canApprove?'حق الاعتماد متاح':'الاعتماد غير مفوض'}</span></div>`+
 `<div class="mini-metrics bank-metrics"><div class="mini-metric"><span>بداية الدفتر</span><strong>${fmt(d.ledger_opening_piasters)}</strong></div><div class="mini-metric"><span>نهاية الدفتر</span><strong>${fmt(d.ledger_closing_piasters)}</strong></div><div class="mini-metric"><span>نهاية كشف البنك</span><strong>${b?fmt(d.bank_closing_piasters):'—'}</strong></div><div class="mini-metric"><span>الفرق البنكي</span><strong class="${d.balance_difference_piasters?'bad':'good'}">${b?fmt(d.balance_difference_piasters):'—'}</strong></div></div>`+
 `<div id="posSettlementPanel" aria-live="polite" class="pos-settlement-area"></div>`+
 (b?`<div class="info-box ${b.status==='approved'?'':'warning'}">${ico('alert')}<div><strong>${esc(statusText)}.</strong> مجموع الحركات: ${integer(d.lines.length)} · المطابق: ${integer(d.matched_count)} · غير المطابق من البنك: ${integer(d.unmatched_bank_count)} · حركات الدفتر غير المطابقة: ${integer(d.unmatched_ledger.length)} · سندات معلقة: ${integer(d.pending_vouchers)}. الرصيد الافتتاحي في كشف البنك ${fmt(d.bank_opening_piasters)} ج.م.</div></div>`:'')+
 (!b&&canSubmit&&!d.month_closed?`<section class="panel panel-pad bank-import"><h2 class="section-title">استيراد كشف البنك بصيغة CSV</h2><p class="section-subtitle">يجب أن يخص الملف شهرًا واحدًا وأن يحتوي على كل الحركات، مع الرصيد الافتتاحي والختامي كما في كشف البنك. إشارة المبلغ الموجبة للإيداع والسالبة للسحب.</p><form id="bankImportForm" class="form-grid"><label>الرصيد الافتتاحي بالجنيه<input name="opening_balance" type="number" step="0.01" min="0" required placeholder="0.00"></label><label>الرصيد الختامي بالجنيه<input name="closing_balance" type="number" step="0.01" min="0" required placeholder="0.00"></label><label class="full">ملف CSV UTF-8<input name="file" type="file" accept=".csv,text/csv" required></label><div class="full"><small>الأعمدة: <code dir="ltr">date,description,amount,reference</code> (المرجع اختياري). كل التواريخ بصيغة YYYY-MM-DD، والحد الأقصى 1500 سطر.</small></div><div class="full"><button type="submit" class="btn btn-primary">${ico('file')} استيراد الكشف للمراجعة</button></div></form></section>`:'')+
 (b?`<section class="panel bank-section"><div class="panel-header"><div><h2>سطور كشف الحساب البنكي</h2><p>طابق السطر مع سند مالي معتمد بنفس الحساب والشهر والقيمة والإشارة، ولا تعتمد كشفًا فيه اختلافات.</p></div></div><div class="bank-lines">${rows.join('')||empty('لا توجد سطور')}</div></section>`:'')+
 (b?`<section class="panel bank-section"><div class="panel-header"><div><h2>حركات دفتر البنك غير المطابقة</h2><p>الحركات المعتمدة التي لا يظهر لها مقابل في كشف البنك.</p></div></div><div class="bank-ledger-list">${unmatched||empty('كل حركات الدفتر مطابقة')}</div></section>`:'')+
 (b&&b.status==='draft'&&!d.month_closed?`<section class="panel panel-pad bank-final"><div><h2 class="section-title">اعتماد المطابقة البنكية</h2><p class="section-subtitle">اعتماد شخص مختلف عن مستورد الكشف، بعد تطابق السطور والحركات.</p></div><div class="row-actions">${canSign?`<button class="btn btn-primary" id="bankApprove">${ico('check')} اعتماد نهائي</button>`:`<span class="text-muted">${signHold}</span>`}${state.me.role==='owner'?`<button class="btn btn-secondary" id="bankVoid">إلغاء هذه المسودة</button>`:''}</div></section>`:'')+
 `<div class="info-box warning">${ico('alert')}<div>${esc(d.warning||'المطابقة لا تُنشئ قيودًا جديدة.')} التحويلات البنكية العابرة بين شهرين غير مدعومة في الاعتماد النهائي في هذه المرحلة، وتحتاج معالجة محاسبية مستقلة.</div></div>`;
 $('#bankFundFilter').onchange=e=>{state.bankFundId=Number(e.target.value);navigate('bank')};
 attachMonth('bankMonth','bankMonth','bank');
 $('#bankImportForm')?.addEventListener('submit',async e=>{
  e.preventDefault();const form=e.currentTarget;const btn=$('button[type=submit]',form);btn.disabled=true;
  const data=new FormData(form);data.set('fund_id',String(d.fund.id));data.set('period',state.bankMonth);
  try{const res=await api('/api/bank-reconciliation/import',{method:'POST',body:data});toast(`تم استيراد ${integer(res.lines)} حركة؛ ابدأ المطابقة`);navigate('bank')}
  catch(err){toast(err.message,true);btn.disabled=false;}
 });
 $$('[data-bank-match]').forEach(button=>button.onclick=async()=>{
  const lineId=Number(button.dataset.bankMatch);const chosen=$(`[data-bank-choice="${lineId}"]`);
  if(!chosen?.value){toast('اختر الحركة المقابلة',true);return}
  button.disabled=true;
  try{await post(`/api/bank-reconciliation/${b.id}/match`,{line_id:lineId,movement_id:Number(chosen.value)});toast('تمت المطابقة وحُفظت في سجل المراجعة');navigate('bank')}
  catch(err){toast(err.message,true);button.disabled=false}
 });
 $$('[data-bank-unmatch]').forEach(button=>button.onclick=async()=>{
  const data=await modal('فك مطابقة بنكية','فك الربط لا يلغي السند، ويحتفظ النظام بسبب الفك في سجل المراجعة.',[{name:'reason',type:'textarea',label:'سبب الفك (8 أحرف على الأقل)',required:true}]);
  if(!data)return;
  try{await post(`/api/bank-reconciliation/${b.id}/unmatch`,{match_id:Number(button.dataset.bankUnmatch),reason:data.reason});toast('تم فك المطابقة وتوثيق السبب');navigate('bank')}
  catch(err){toast(err.message,true)}
 });
 $('#bankApprove')?.addEventListener('click',async()=>{
  const data=await modal('اعتماد المطابقة نهائيًا','بعد الاعتماد لن يمكن تعديل كشف هذا الشهر أو ترحيل سند جديد على حسابه البنكي.',[{name:'note',label:'ملاحظة الاعتماد (اختياري)',placeholder:'تمت مراجعة كشف الحساب بالكامل'}]);
  if(!data)return;
  try{await post(`/api/bank-reconciliation/${b.id}/approve`,data);toast('تم اعتماد المطابقة البنكية وإقفال حركات الحساب للشهر');navigate('bank')}
  catch(err){toast(err.message,true)}
 });
 $('#bankVoid')?.addEventListener('click',async()=>{
  const data=await modal('إلغاء مسودة كشف البنك','سيتم الاحتفاظ بالمستند وحركات المطابقة الملغاة في سجل المراجعة، ويمكن استيراد كشف صحيح بعد الإلغاء.',[{name:'reason',type:'textarea',label:'سبب الإلغاء',required:true}]);
  if(!data)return;
  try{await post(`/api/bank-reconciliation/${b.id}/void`,data);toast('تم إلغاء مسودة الكشف مع الحفاظ على السجل');navigate('bank')}
  catch(err){toast(err.message,true)}
 });
 if(window.renderPOSSettlements)await window.renderPOSSettlements(d.fund.id,d.month);
}

async function renderAccounting(){
 const params='?period='+encodeURIComponent(state.month);
 const data=await api('/api/accounting/trial-balance'+params);
 const journals=await api('/api/accounting/journals'+params);
 const b=data.trial_balance,quality=data.coverage;
 const [integrity,treasury]=await Promise.all([api('/api/accounting/patient-reconciliation'+params),state.me.role==='owner'?api('/api/accounting/treasury-reconciliation'+params):Promise.resolve(null)]);
 const entries=b.accounts.filter(a=>a.debit_total||a.credit_total);
 const hasWarnings=quality.unposted_vouchers||quality.unposted_payroll||quality.unposted_allocations||quality.unverified_opening_funds||quality.pending_journals;
 const canDraft=['owner','reviewer'].includes(state.me.role);
 const statusName={pending:'بانتظار مراجع آخر',posted:'مُرحل',rejected:'مرفوض'};
 const typeName={asset:'أصول',liability:'التزامات',equity:'حقوق ملكية',revenue:'إيرادات',expense:'مصروفات'};
 const top=head('قيد مزدوج · مرحلة تأسيسية','دفتر الأستاذ وميزان المراجعة',
   'القيود المعتمدة تُرحّل تلقائيًا. أرصدة الحسابات هنا جزئية حتى تسوية الأرصدة الافتتاحية والذمم والمخزون.',
   (canDraft?'<button class="btn btn-primary" id="newJournal">'+ico('plus')+' قيد يدوي للمراجعة</button>':'')+
   '<a class="btn btn-secondary" href="/api/accounting/trial-balance.csv?period='+encodeURIComponent(state.month)+'">'+ico('download')+' تصدير CSV</a>');
 const warn=`<section class="accounting-warning panel" aria-live="polite"><strong>${ico('alert')} ميزان مراجعة مبدئي — ليس قائمة أرباح وخسائر معتمدة</strong><p>${esc(quality.readiness_reason)}</p>${hasWarnings?'<p>توجد عناصر غير مسوّاة أو قيود تحت المراجعة. راجع المؤشرات أدناه قبل الاعتماد على النتائج.</p>':''}</section>`;
 const metrics=`<div class="mini-metrics accounting-metrics"><div class="mini-metric"><span>إجمالي المدين المدرج</span><strong>${fmt(b.debit_piasters)}</strong></div><div class="mini-metric"><span>إجمالي الدائن المدرج</span><strong>${fmt(b.credit_piasters)}</strong></div><div class="mini-metric"><span>حالة توازن القيود</span><strong class="${b.balanced?'gl-good':'gl-bad'}">${b.balanced?'متوازن':'غير متوازن'}</strong></div></div>`;
 const checklist=`<div class="accounting-coverage" role="list"><div role="listitem"><span>سندات لم تُرحّل</span><strong>${integer(quality.unposted_vouchers)}</strong></div><div role="listitem"><span>كشوف رواتب غير مرحّلة</span><strong>${integer(quality.unposted_payroll)}</strong></div><div role="listitem"><span>تسويات سلف غير مرحّلة</span><strong>${integer(quality.unposted_allocations)}</strong></div><div role="listitem"><span>خزن لها افتتاحي غير مُدقَّق</span><strong>${integer(quality.unverified_opening_funds)}</strong></div><div role="listitem"><span>قيود تنتظر الاعتماد</span><strong>${integer(quality.pending_journals)}</strong></div><div role="listitem"><span>حركات أرشيف غير مُتحقق منها</span><strong>${integer(quality.historical_unverified)}</strong></div></div>`;
 const integrityRows=integrity.checks.map(x=>`<div class="integrity-line"><div><strong>${esc(x.name)}</strong><small>رقابة ${esc(x.code)} · المستندات مقابل دفتر الأستاذ</small></div><div class="integrity-values"><span>الدفتر <b>${fmt(x.expected_piasters)}</b></span><span>الأستاذ <b>${fmt(x.ledger_piasters)}</b></span><span class="${x.matched?'integrity-match':'integrity-mismatch'}">${x.matched?'متطابق':'فرق '+fmt(x.difference_piasters)}</span></div></div>`).join('');
 const integrityPanel=`<section class="panel integrity-panel" aria-label="مطابقة الدفاتر المساعدة مع الأستاذ"><div class="panel-header"><div><h2>مطابقة حسابات المرضى</h2><p>الفواتير والتحصيل والمقدمات والإشعارات الدائنة والمرتجعات حتى نهاية الشهر المختار.</p></div><span class="chip ${integrity.matched?'approved':'rejected'}">${integrity.matched?'متطابق':'فرق يستوجب التحقيق'}</span></div><div class="integrity-list">${integrityRows}</div><p class="integrity-scope">${esc(integrity.scope)}</p></section>`;
 const treasuryRows=treasury?treasury.funds.map(f=>`<article class="treasury-row" role="listitem"><div class="treasury-row-title"><strong>${esc(f.name)}</strong><small>${esc({cash:'نقدية',wallet:'محفظة إلكترونية',bank:'بنك'}[f.kind]||f.kind)} · رصيد الدفتر ${fmt(f.book_balance_piasters)}</small></div><div class="treasury-row-amounts"><span>حركات السندات <b>${fmt(f.movement_piasters)}</b></span><span>قيود الأستاذ <b>${fmt(f.gl_posted_piasters)}</b></span><span class="${f.matched?'integrity-match':'integrity-mismatch'}">${f.matched?'متطابق':'عدد الملاحظات '+integer(f.issue_count)}</span></div></article>`).join(''):'';
 const treasuryIssues=treasury?treasury.issues.map(x=>`<li>${esc(x.message)}${x.reference!=null?' · مرجع #'+integer(x.reference):''}</li>`).join(''):'';
 const treasuryPanel=treasury?`<section class="panel integrity-panel treasury-panel" aria-label="مطابقة الخزن والبنوك"><div class="panel-header"><div><h2>مطابقة حركة الخزن والبنوك</h2><p>مراجعة السندات وقيود الأستاذ والجرد وكشف البنك المعتمد، حتى نهاية الشهر.</p></div><div class="treasury-heading-actions"><a class="btn btn-secondary btn-small" href="/api/accounting/treasury-reconciliation.csv?period=${encodeURIComponent(state.month)}" download>${ico('download')} CSV</a><span class="chip ${treasury.matched?'approved':'rejected'}">${treasury.matched?'الحركات متطابقة':'توجد فروق: '+integer(treasury.issue_count)}</span></div></div><div role="list" class="treasury-list">${treasuryRows||'<p class="panel-pad">لا توجد حسابات مالية.</p>'}</div>${treasuryIssues?`<div class="treasury-issues"><strong>ملاحظات تستوجب المراجعة</strong><ul>${treasuryIssues}</ul>${treasury.issue_count>treasury.issues.length?`<p>هناك ${integer(treasury.issue_count-treasury.issues.length)} ملاحظة إضافية غير معروضة؛ يلزم التحقيق قبل الإقفال.</p>`:''}</div>`:''}<p class="integrity-scope">${esc(treasury.scope)}${treasury.opening_review_required?' · هناك '+integer(treasury.opening_review_required)+' حساب/خزنة بافتتاحي يتطلب إثباتاً مستقلاً.':''}</p></section>`:'<div class="info-box">مطابقة الخزن الشاملة للمالك فقط؛ قد تظهر فروق عامة تتطلب رفعها لمدير النظام.</div>';
 const rows=entries.map(a=>`<tr><td><strong class="gl-code">${esc(a.code)}</strong><small class="gl-type">${esc(typeName[a.class]||a.class)}</small></td><td>${esc(a.name)}</td><td class="num">${fmt(a.closing_debit_piasters)}</td><td class="num">${fmt(a.closing_credit_piasters)}</td></tr>`).join('');
 const cards=entries.map(a=>`<article class="gl-account-card"><div class="gl-account-head"><div><strong>${esc(a.name)}</strong><small>${esc(typeName[a.class]||a.class)}</small></div><span>${esc(a.code)}</span></div><div class="gl-account-values"><div><span>رصيد مدين</span><strong>${fmt(a.closing_debit_piasters)}</strong></div><div><span>رصيد دائن</span><strong>${fmt(a.closing_credit_piasters)}</strong></div></div></article>`).join('');
 const journalRows=journals.items.map(j=>`<article class="accounting-journal"><div><strong>#${integer(j.id)} · ${esc(j.memo)}</strong><small>${esc(j.entry_date)} · ${esc(j.origin)} · ${esc(statusName[j.status]||j.status)}</small></div><div class="accounting-journal-actions">${j.status==='pending'&&canDraft&&j.created_by!==state.me.id?`<button class="btn btn-primary" data-gl-approve="${j.id}">اعتماد</button><button class="btn btn-secondary" data-gl-reject="${j.id}">رفض</button>`:''}</div></article>`).join('');
 $('#content').innerHTML=top+`<div class="filter-strip panel">${periodInput(state.month,'glMonth')}<span class="helper-note">يُعرض رصيد تراكمي حتى نهاية الشهر المختار، ولا يشمل الأرصدة الافتتاحية غير المدققة.</span></div>`+
 warn+metrics+integrityPanel+treasuryPanel+`<section class="panel accounting-section"><div class="panel-header"><h2>قائمة اكتمال البيانات</h2></div>${checklist}</section>`+
 `<section class="panel accounting-section"><div class="panel-header"><div><h2>ميزان المراجعة الجزئي</h2><p>رصيد كل حساب من القيود المرحلة فقط — بالجنيه المصري</p></div></div><div class="gl-trial-desktop">${table(['الكود','الحساب','رصيد مدين','رصيد دائن'],rows)}</div><div class="gl-trial-mobile">${cards||empty('لا توجد قيود مرحلة للفترة.')}</div></section>`+
 `<section class="panel accounting-section"><div class="panel-header"><h2>سجل القيود (${integer(journals.count)})</h2></div><div class="accounting-journals">${journalRows||empty('لا توجد قيود خلال هذه الفترة.')}</div></section>`;
 attachMonth('glMonth','month','accounting');
 $('#newJournal')?.addEventListener('click',async()=>{
   const protectedCodes=new Set(['1200','2300','2310','2350','1190','2190','2110','1120','4100','4195']);
   const options=b.accounts.filter(x=>x.control!== 'fund'&&!protectedCodes.has(x.code)).map(x=>[x.id,x.code+' · '+x.name]);
   const fields=[{name:'date',type:'date',label:'تاريخ الاستحقاق',value:state.month+'-01',required:true},
     {name:'memo',type:'textarea',label:'بيان محاسبي موثق',required:true},
     {name:'debit_account_id',type:'select',label:'حساب مدين',options,required:true},
     {name:'credit_account_id',type:'select',label:'حساب دائن',options,required:true},
     {name:'amount',type:'number',label:'القيمة بالجنيه',required:true}];
   const form=await modal('قيد يدوي جديد','هذا القيد لا يؤثر على الخزن إلا إذا سُجل سند مالي مستقل. يظل معلقًا حتى مراجعة شخص آخر.',fields);
   if(!form)return;
   const payload={date:form.date,memo:form.memo,lines:[
       {account_id:+form.debit_account_id,debit:form.amount,credit:'0'},
       {account_id:+form.credit_account_id,debit:'0',credit:form.amount}]};
   try{await post('/api/accounting/journals',payload);toast('القيد مسجل بانتظار المراجعة المستقلة');navigate('accounting')}
   catch(err){toast(err.message,true)}
 });
 $$('[data-gl-approve]').forEach(button=>button.addEventListener('click',async()=>{
   const id=+button.dataset.glApprove;
   const answer=await modal('اعتماد قيد محاسبي','يتم تثبيت القيد في دفتر الأستاذ ولا يمكن تعديل أسطره بعد الاعتماد.');
   if(!answer)return;
   try{await post(`/api/accounting/journals/${id}/decision`,{decision:'approve'});toast('تم ترحيل القيد إلى دفتر الأستاذ');navigate('accounting')}
   catch(err){toast(err.message,true)}
 }));
 $$('[data-gl-reject]').forEach(button=>button.addEventListener('click',async()=>{
   const id=+button.dataset.glReject;
   const form=await modal('رفض قيد محاسبي','يظل الرفض في سجل المراجعة.',[{name:'reason',type:'textarea',label:'سبب الرفض',required:true}]);
   if(!form)return;
   try{await post(`/api/accounting/journals/${id}/decision`,{decision:'reject',reason:form.reason});toast('تم رفض القيد');navigate('accounting')}
   catch(err){toast(err.message,true)}
 }));
}

async function renderReports(){
 const d=await api('/api/reports?month='+encodeURIComponent(state.month));
 if(d.scope==='authorized_cash_only'){
   // Viewer has no GL or payroll visibility: do not turn null restricted
   // amounts into misleading displayed zeros or a fabricated profit figure.
   $('#content').innerHTML=head('تقرير محدود','الحركة النقدية المسموح بعرضها',
     'المبالغ من السندات الظاهرة لصلاحياتك فقط؛ ليست إجمالي المستشفى أو نتيجة دفتر الأستاذ.',
     `<button class="btn btn-secondary" id="printReport">طباعة ${ico('file')}</button>`)+
     `<div class="filter-strip panel">${periodInput(state.month,'reportsMonth')}</div>`+
     `<div class="mini-metrics"><div class="mini-metric"><span>المقبوضات المرئية</span><strong>${fmt(d.recognized_cash_service_revenue_piasters)}</strong></div><div class="mini-metric"><span>المدفوعات المرئية</span><strong>${fmt(d.cash_paid_operating_items_piasters)}</strong></div></div>`+
     `<section class="panel"><div class="panel-header"><h2>بنود الصرف المسموح بعرضها</h2></div>${table(['البند','المبلغ'],d.categories.map(x=>`<tr><td>${esc(x.category)}</td><td class="num">${fmt(x.amount_piasters)}</td></tr>`).join(''))}</section>`+
     `<div class="info-box warning">${ico('alert')}<div>${esc(d.note)}</div></div>`;
   $('#printReport')?.addEventListener('click',()=>window.print());
   attachMonth('reportsMonth');return;
 }
 const variance=state.me.role!=='viewer'?await api('/api/reconciliation/variances?month='+encodeURIComponent(state.month)):null;
 $("#content").innerHTML=head('المحاسبة الإدارية','التقارير والتحليل','فصل إيرادات ومصروفات دفتر الأستاذ عن التحصيلات والتحويلات النقدية.',`<button class="btn btn-secondary" id="printReport">طباعة ${ico('file')}</button>`)+
 `<div class="filter-strip panel">${periodInput(state.month,'reportsMonth')}<span class="helper-note">الإيراد والمصروف من الأستاذ المرحّل فقط؛ التحويلات النقدية لا تضاعف الإيراد.</span></div>`+
 `<div class="mini-metrics"><div class="mini-metric"><span>إيراد مُثبت بالأستاذ</span><strong>${fmt(d.recognized_revenue_piasters)}</strong></div><div class="mini-metric"><span>مصروف مُثبت بالأستاذ</span><strong>${fmt(d.recognized_expenses_piasters)}</strong></div><div class="mini-metric"><span>نتيجة دفتر الأستاذ المبدئية</span><strong>${fmt(d.provisional_gl_result_piasters)}</strong></div></div>`+
 `<div class="report-layout"><section class="panel"><div class="panel-header"><h2>إيراد ومصروف الأقسام — دفتر الأستاذ</h2></div>${table(['القسم','إيراد مُثبت','مصروف مُثبت'],(d.gl_departments||[]).map(x=>`<tr><td><b>${esc(x.department)}</b></td><td class="num text-success">${fmt(x.recognized_revenue_piasters)}</td><td class="num">${fmt(x.recognized_expense_piasters)}</td></tr>`).join(''))}</section>`+
 `<section class="panel"><div class="panel-header"><h2>تصنيف المدفوعات النقدية</h2></div>${table(['البند','الطبيعة','المبلغ'],d.categories.map(x=>`<tr><td>${esc(x.category)}</td><td><span class="tiny">${esc(categoryNatures[x.nature]||x.nature)}</span></td><td class="num">${fmt(x.amount_piasters)}</td></tr>`).join(''))}</section></div>`+
 (variance?`<section class="panel" style="margin-top:18px"><div class="panel-header"><div><h2>فروق جرد الخزن قيد المتابعة</h2><p>عهد مؤقتة لا تدخل في الإيرادات أو المصروفات التشغيلية حتى التسوية المحاسبية المستندية.</p></div></div><div class="mini-metrics shift-metrics" style="padding:0 16px 16px"><div class="mini-metric"><span>محاضر تنتظر اعتماد المالك</span><strong>${integer(variance.proposed_count)}</strong></div><div class="mini-metric"><span>عجز عهدة معتمد</span><strong>${fmt(variance.shortage_piasters)} ج.م</strong></div><div class="mini-metric"><span>زيادة عهدة معتمدة</span><strong>${fmt(variance.overage_piasters)} ج.م</strong></div></div>${table(['الوردية','الخزنة','الفرق','الحالة','المسؤول','تفسير التحقيق'],variance.items.map(v=>`<tr><td>${esc(v.business_date)} · ${esc(v.shift)}</td><td>${esc(v.fund_name)}</td><td class="num ${v.variance_piasters<0?'bad':'good'}">${fmt(v.variance_piasters)}</td><td>${esc({proposed:'بانتظار موافقة المالك',approved:'عهدة مؤقتة معتمدة',rejected:'محضر مرفوض'}[v.status]||v.status)}</td><td>${esc(v.proposed_by)}</td><td>${esc(v.explanation)}</td></tr>`).join(''))}</section>`:'')+
 `<div class="info-box warning" style="margin-top:18px">${ico('alert')}<div><strong>تنبيه محاسبي:</strong> ${esc(d.note)} لذلك لم أسمّ الناتج «صافي ربح»؛ نحتاج المصروفات المستحقة، استهلاك المخزون، والإهلاك والتسويات قبل قائمة أرباح وخسائر معتمدة.</div></div>`;
 $('#printReport')?.addEventListener('click',()=>window.print());
 attachMonth('reportsMonth');
}

async function renderLegacy(){
 const f=state.legacy;const query=new URLSearchParams({page:f.page,q:f.q,issues_only:String(f.issues_only)});
 const d=await api('/api/legacy?'+query);const income=d.metrics.find(x=>x.kind==='إيراد')?.amount_piasters||0;
 const expense=d.metrics.find(x=>x.kind==='منصرف')?.amount_piasters||0;
 $("#content").innerHTML=head('بيانات تاريخية منفصلة','أرشيف يونيو 2026','الحركات من ملف الحاج عبد الكريم محفوظة للمطابقة ولا ترحّل للخزن الجديدة.')+
 `<div class="info-box warning">${ico('alert')}<div>هذه الأرقام مأخوذة من ملف إكسل وتحتاج تسوية وفحص. ممنوع دمجها تلقائيًا مع التشغيل حتى لا تتكرر الإيرادات والتحويلات.</div></div>`+
 `<div class="mini-metrics"><div class="mini-metric"><span>إيرادات مؤرخة بالأرشيف</span><strong>${fmt(income)}</strong></div><div class="mini-metric"><span>منصرف مؤرخ بالأرشيف</span><strong>${fmt(expense)}</strong></div><div class="mini-metric"><span>ملاحظات فحص مفتوحة</span><strong>${integer(d.issues.length)}${d.issues.length===100?'+':''}</strong></div></div>`+
 `<section class="panel"><div class="toolbar"><label class="search">بحث في الأرشيف<input id="legacySearch" type="search" placeholder="بيان أو رقم قيد…" value="${esc(f.q)}"></label><label style="align-self:end;display:flex;gap:8px;align-items:center;font-size:12px"><input id="issuesOnly" type="checkbox" ${f.issues_only?'checked':''} style="width:17px;height:17px;min-height:auto"> الحركات التي تحتاج مراجعة فقط</label></div>`+
 table(['صف الملف','التاريخ','النوع','القسم','البيان','المبلغ','الحالة'],d.items.map(v=>`<tr><td class="tiny">${v.source_row}</td><td>${esc(v.transaction_date||'غير محدد')}</td><td>${esc(v.kind)}</td><td>${esc(v.department_raw)}</td><td><div class="desc" title="${esc(v.description)}">${esc(v.description)}</div></td><td class="num">${fmt(v.total_piasters)}</td><td><span class="chip archive">تاريخي غير معتمد</span></td></tr>`).join(''))+
 `<div class="table-footer"><span>${integer(d.count)} حركة بالأرشيف</span><div class="paging"><button class="btn btn-secondary" id="legacyPrev" ${f.page===1?'disabled':''}>السابق</button><button class="btn btn-secondary" id="legacyNext" ${f.page>=d.pages?'disabled':''}>التالي</button></div></div></section>`+
 `<section class="panel" style="margin-top:17px"><div class="panel-header"><div><h2>عينة من ملاحظات الترحيل</h2><p>يتم استكمال تسوية الحالات مع المحاسب المسؤول قبل أي اعتماد.</p></div></div>`+
 table(['صف المصدر','نوع المشكلة','التفاصيل'],d.issues.slice(0,12).map(i=>`<tr><td>${i.source_row}</td><td><span class="chip pending">${esc(i.issue_type)}</span></td><td>${esc(i.details)}</td></tr>`).join(''))+`</section>`;
 let timer;
 $('#legacySearch').oninput=e=>{clearTimeout(timer);timer=setTimeout(()=>{state.legacy.q=e.target.value;state.legacy.page=1;navigate('legacy')},420);};
 $('#issuesOnly').onchange=e=>{state.legacy.issues_only=e.target.checked;state.legacy.page=1;navigate('legacy')};
 $('#legacyPrev').onclick=()=>{state.legacy.page--;navigate('legacy')};$('#legacyNext').onclick=()=>{state.legacy.page++;navigate('legacy')};
}

async function renderAdmin(){
 const [users,periods,audit,sync,grants]=await Promise.all([api('/api/users'),api('/api/periods'),api('/api/audit'),api('/api/sync-status'),api('/api/fund-access')]);
 $("#content").innerHTML=head('الإدارة والحوكمة','إعدادات وصلاحيات النظام','مدير النظام فقط يضيف المستخدمين ويحدد إقفال الفترات ويتابع النسخ إلى Google Sheets.')+
 `<div class="user-grid"><section class="panel"><div class="panel-header"><h2>مستخدمو قسم الحسابات</h2><button class="btn btn-primary btn-small" id="newUser">${ico('plus')} حساب موظف</button></div>`+
 table(['اسم المستخدم','الصلاحية','الحالة','إدارة الحساب'],users.map(u=>`<tr><td><b>${esc(u.username)}</b></td><td>${esc(roleLabels[u.role])}</td><td>${u.active?'<span class="chip approved">نشط</span>':'<span class="chip rejected">معطل</span>'}</td><td><div class="row-actions"><button class="btn btn-small btn-secondary" data-user-password="${u.id}" data-user-name="${esc(u.username)}">تغيير كلمة المرور</button>${['clerk','reviewer'].includes(u.role)?`<button class="btn btn-small btn-secondary" data-user-fund="${u.id}" data-user-name="${esc(u.username)}">تفويض حساب أو خزنة</button>`:''}<button class="btn btn-small btn-outline" data-user-toggle="${u.id}" data-user-name="${esc(u.username)}" data-new-status="${u.active?'0':'1'}" ${u.username===state.me.username?'disabled title="لا يمكنك تعطيل حسابك"':''}>${u.active?'تعطيل':'تفعيل'}</button></div></td></tr>`).join(''))+`</section>`+
 `<section class="panel"><div class="panel-header"><h2>تفويض إثبات الخدمات الطبي (تجريبي)</h2></div><div class="panel-pad"><p>التوثيق منفصل تمامًا عن المالية. أنشئ حسابًا بدور طبي ثم سجّل مراجعة هويته يدويًا قبل تفويض القسم. مراجعة المالك لا تعني التحقق الرسمي من الترخيص أو توقيعًا إلكترونيًا معتمدًا.</p><div class="row-actions"><button class="btn btn-small btn-secondary" id="clinicalIdentitySetup">مراجعة الهوية المهنية</button><button class="btn btn-small btn-secondary" id="clinicalGrantSetup">منح / سحب تفويض طبي</button><button class="btn btn-small btn-outline" id="clinicalActivateSetup">تفعيل شرط الإثبات لقسم</button><button class="btn btn-small btn-secondary" id="clinicalDocumentSetup">إلزام بصمة مصدر طبي</button></div></div></section>`+
 `<section class="panel"><div class="panel-header"><h2>سياسة صلاحيات الخزن النقدية</h2></div><div class="panel-pad"><p>الخزن القديمة تنتقل للحماية بعد تحديد تفويضات الموظفين، والخزن الجديدة تبدأ بالحماية مفعلة. عند التفعيل لا يمكن للموظف العمل أو اعتماد حركة دون تفويض خاص بهذه الخزنة.</p><button class="btn btn-secondary btn-small" type="button" id="configureCashFundPolicy">إدارة حماية الخزنة</button></div></section>`+
 `<section class="panel"><div class="panel-header"><h2>إقفال الفترة المحاسبية</h2><button class="btn btn-secondary btn-small" id="closePeriod">${ico('lock')} إقفال شهر</button></div>`+
 table(['الفترة','تاريخ الإقفال'],periods.map(p=>`<tr><td><b>${esc(p.period)}</b></td><td>${esc(p.closed_at.slice(0,10))}</td></tr>`).join(''))+`<div class="panel-pad"><p class="hint">المحاسبة لا تسمح باعتماد أو إدخال سند جديد في فترة مغلقة، ولا إقفال شهر به سندات معلقة.</p></div></section>`+
 `<section class="panel"><div class="panel-header"><div><h2>مزامنة Google Sheets</h2><p>نسخة متابعة خاصة بمالك المستشفى فقط</p></div><button class="btn btn-primary btn-small" id="syncNow" ${sync.configured?'':'disabled'}>${ico('refresh')} مزامنة الآن</button></div>`+
 `<div class="panel-pad"><p style="margin:0 0 12px">${sync.configured?'<span class="chip approved">تم إعداد الاتصال</span>':'<span class="chip pending">لم يتم ربط Google Sheets بعد</span>'}</p><p class="summary-note">آخر مزامنة: ${esc(sync.last_synced_at||'لم تحدث')} • ${sync.dirty?'هناك تغييرات لم تنسخ بعد':'النسخة محدثة حتى آخر مزامنة'}</p><div class="info-box">${ico('shield')}<div>الموظفون لا يحصلون على صلاحية للشيت. الخادم وحده يتصل باستخدام حساب خدمة، والبيانات الأصلية تظل محفوظة داخل قاعدة النظام.</div></div></div></section>`+
 `<section class="panel"><div class="panel-header"><h2>آخر الأحداث الرقابية</h2></div>${table(['الوقت','المستخدم','الإجراء','المرجع'],audit.slice(0,20).map(a=>`<tr><td class="tiny">${esc(a.created_at.replace('T',' ').slice(0,19))}</td><td>${esc(a.username)}</td><td>${esc(a.action)}</td><td>${esc(a.entity)} #${esc(a.entity_id)}</td></tr>`).join(''))}</section></div>`;
 $('#clinicalIdentitySetup').onclick=async()=>{
   const clinicians=users.filter(u=>u.active&&u.role==='clinician');
   if(!clinicians.length){toast('أنشئ حسابًا بدور طبي أولًا',true);return;}
   const data=await modal('مراجعة هوية مهنية يدوية — اختبار فقط',
      'فحص المرجع المهني مسؤولية بشرية خارج النظام، ولا يعد توقيعًا طبيًا قانونيًا. أعد إدخال كلمة مرور المالك لكل قرار.',[
      {name:'user_id',type:'select',label:'الحساب الطبي',required:true,options:clinicians.map(u=>[String(u.id),u.username])},
      {name:'professional_name',label:'الاسم المهني المسجل (تجريبي)',required:true},
      {name:'registration_reference',label:'مرجع التسجيل المهني (غير معروض في تقارير الحسابات)',required:true},
      {name:'review_note',label:'ملخص مراجعة المستند / سبب السحب',required:true},
      {name:'approved',type:'select',label:'القرار',required:true,options:[['true','مراجعة مكتملة يدويًا - تجربة'],['false','سحب موافقة المراجعة فورًا']]},
      {name:'current_password',type:'password',label:'كلمة مرور المالك للتأكيد',required:true}
   ]);
   if(!data)return;
   try{await post('/api/billing/clinical/identity-review',{...data,user_id:Number(data.user_id),approved:data.approved==='true'});
       toast('تم حفظ قرار مراجعة الهوية دون نشر رقم القيد المهني في سجل الحسابات');}
   catch(error){toast(error.message,true);}
 };
 $('#clinicalGrantSetup').onclick=async()=>{
   const viewers=users.filter(u=>u.active&&u.role==='clinician');
   const departments=state.lookups?.departments||[];
   if(!viewers.length||!departments.length){toast('أنشئ حسابًا طبيًا وراجع هويته وحدد القسم أولًا',true);return;}
   const data=await modal('تفويض مُثبت خدمة مستقل','يُمنح للمستخدم صاحب مهمة طبية تجريبية، وليس للمدير أو المحاسب أو الكاشير.',[
     {name:'user_id',type:'select',label:'حساب المُثبت',required:true,options:viewers.map(u=>[String(u.id),u.username])},
     {name:'department_id',type:'select',label:'القسم',required:true,options:departments.map(d=>[String(d.id),d.name])},
     {name:'active',type:'select',label:'القرار',required:true,options:[['true','تفويض'],['false','سحب التفويض فورًا']]}
   ]);
   if(!data)return;
   try{await post('/api/billing/clinical/grants',{user_id:Number(data.user_id),department_id:Number(data.department_id),active:data.active==='true'});
       toast('حُفظ تفويض التجربة مع سجل التدقيق');}
   catch(error){toast(error.message,true);}
 };
 $('#clinicalActivateSetup').onclick=async()=>{
   const departments=state.lookups?.departments||[];
   const data=await modal('تفعيل إلزام الإثبات الطبي','التفعيل قرار غير قابل للإلغاء تلقائيًا؛ سيمنع فواتير الخدمات غير الموثقة بهذا القسم حتى للطلبات القديمة.',[
     {name:'department_id',type:'select',label:'القسم',required:true,options:departments.map(d=>[String(d.id),d.name])}]);
   if(!data)return;
   try{await post(`/api/billing/clinical/departments/${Number(data.department_id)}/activate`);
       toast('تفعّل الشرط التجريبي، وتجب مطابقة كل خدمة قبل الفوترة');}
   catch(error){toast(error.message,true);}
 };
 $('#clinicalDocumentSetup').onclick=async()=>{
   const departments=state.lookups?.departments||[];
   const data=await modal('إلزام بصمة المستند الطبي — اختبار فقط',
     'هذا قرار دائم لا يُعطّل تلقائيًا. يرفض النظام خدمات بلا بصمة مصدر ويمنع التفعيل مع إثباتات قديمة غير مفوترة. لا تُرفع بيانات مرضى حقيقية؛ تُحفظ البصمة فقط ويجب الاحتفاظ بالأصل في نظام السجلات الطبية.',[
     {name:'department_id',type:'select',label:'القسم الطبي',required:true,options:departments.map(d=>[String(d.id),d.name])},
     {name:'current_password',type:'password',label:'كلمة مرور المالك لتأكيد القرار',required:true}]);
   if(!data)return;
   try{await post(`/api/billing/clinical/departments/${Number(data.department_id)}/require-document`,
                {current_password:data.current_password});
       toast('تم تفعيل شرط بصمة المصدر الطبي لهذا القسم');}
   catch(error){toast(error.message,true);}
 };
 $('#configureCashFundPolicy').onclick=async()=>{
   const all=await api('/api/funds');const cash=all.filter(f=>f.kind==='cash'&&f.active);
   const info=await modal('حماية صلاحيات الخزنة النقدية','تفعيل الرقابة يمنع الموظفين غير المفوضين فورًا. عيّن صلاحيات إنشاء السندات واعتمادها أولًا، خصوصًا للوردية المفتوحة.',[
    {name:'fund_id',type:'select',label:'الخزنة النقدية',required:true,options:cash.map(f=>[String(f.id),f.name+(f.cash_restricted?' — محمية':' — إعدادات قديمة')])},
    {name:'restricted',type:'select',label:'الحماية',required:true,options:[['true','تفعيل — تفويض خاص مطلوب'],['false','إيقاف — تشغيل انتقالي غير مقيد']]},
    {name:'reason',label:'سبب القرار',required:true}]);
   if(!info)return;
   try{await post('/api/funds/'+info.fund_id+'/access-policy',{restricted:info.restricted==='true',reason:info.reason});toast('تم تحديث صلاحيات الخزنة وتوثيق القرار');navigate('admin')}catch(e){toast(e.message,true)}
 };
 $$('[data-user-fund]').forEach(btn=>btn.onclick=async()=>{
   const fundList=(state.lookups?.funds||[]).filter(f=>['bank','wallet','cash'].includes(f.kind));
   if(!fundList.length){toast('لا توجد خزن أو حسابات نشطة',true);return;}
   const assigned=grants.filter(g=>String(g.user_id)===btn.dataset.userFund && (g.can_submit||g.can_approve));
   const data=await modal('تفويض حساب مالي حساس',`الموظف: ${esc(btn.dataset.userName)}. الإنشاء والاعتماد صلاحيتان منفصلتان. لا يجوز للموظف اعتماد سند أنشأه بنفسه. الحالي: ${esc(assigned.map(g=>g.fund_name+': '+(g.can_submit?'إنشاء ':'')+(g.can_approve?'اعتماد':'')).join('، ')||'لا يوجد')}`, [
      {name:'fund_id',type:'select',label:'الخزنة أو الحساب',required:true,options:fundList.map(f=>[String(f.id),f.name])},
      {name:'permission',type:'select',label:'نوع الصلاحية',required:true,options:[['can_submit','إنشاء السندات أو إعداد المطابقة البنكية'],['can_approve','اعتماد السندات والمطابقة (للمراجع فقط)']]},
      {name:'allowed',type:'select',label:'القرار',required:true,options:[['true','منح الصلاحية'],['false','سحب الصلاحية فورًا']]},
      {name:'reason',label:'سبب التفويض أو سحبه',required:true}
   ]);
   if(!data)return;
   try{await post('/api/fund-access',{user_id:Number(btn.dataset.userFund),fund_id:Number(data.fund_id),[data.permission]:data.allowed==='true',reason:data.reason});toast('تم تحديث تفويض الحساب المالي وتسجيله بالمراجعة');navigate('admin')}
   catch(e){toast(e.message,true)}
 });
 $('#newUser').onclick=async()=>{
   const data=await modal('إنشاء حساب موظف','حساب مستقل لكل موظف حتى يظهر اسمه في سجل الاعتماد والمراجعة.',[
    {name:'username',label:'اسم المستخدم بالإنجليزي',required:true,placeholder:'accountant1'},
    {name:'password',type:'password',label:'كلمة مرور قوية (12 حرفًا على الأقل)',required:true},
    {name:'role',type:'select',label:'الصلاحية',options:[['clerk','مدخل بيانات'],['reviewer','مراجع حسابات'],['viewer','مشاهد التقارير'],['clinician','موثّق خدمات طبي - اختبار'],['owner','مدير النظام']]}
   ]);
   if(!data)return;
   try{await post('/api/users',data);toast('تم إنشاء حساب المستخدم');navigate('admin');}catch(e){toast(e.message,true)}
 };
 $$('[data-user-toggle]').forEach(btn=>btn.onclick=async()=>{
   const active=btn.dataset.newStatus==='1';
   const confirmation=await modal(active?'تفعيل حساب':'تعطيل حساب',
     `الحساب: ${esc(btn.dataset.userName)}. ${active?'سيتم السماح للمستخدم بالدخول مجددًا.':'سيتم إلغاء الجلسات المفتوحة فورًا ولن يستطيع المستخدم تسجيل الدخول.'}`,
     [{name:'confirm',type:'select',label:'تأكيد القرار',required:true,options:[['yes','أؤكد القرار']]}]);
   if(!confirmation||confirmation.confirm!=='yes')return;
   try{await post(`/api/users/${btn.dataset.userToggle}/status`,{active});toast(active?'تم تفعيل الحساب':'تم تعطيل الحساب وجلساته');navigate('admin')}
   catch(e){toast(e.message,true)}
 });
 $$('[data-user-password]').forEach(btn=>btn.onclick=async()=>{
   const data=await modal('تغيير كلمة مرور',`الحساب: ${esc(btn.dataset.userName)}. يلزم كلمة مرور المدير الحالية لتأكيد التغيير، وسيتم إنهاء جلسات الحساب فورًا.`,[
     {name:'current_password',type:'password',label:'كلمة مرور المدير الحالية',required:true},
     {name:'password',type:'password',label:'كلمة المرور الجديدة (12 حرفًا على الأقل)',required:true},
     {name:'confirm_password',type:'password',label:'تأكيد كلمة المرور الجديدة',required:true}
   ]);
   if(!data)return;
   if(data.password!==data.confirm_password||data.password.length<12){toast('كلمة المرور قصيرة أو التأكيد غير مطابق',true);return;}
   try{
     const r=await post(`/api/users/${btn.dataset.userPassword}/password`,{password:data.password,current_password:data.current_password});
     if(r.session_revoked){state.csrf='';showLogin();toast('تم تغيير كلمة مرور المدير. سجل الدخول مجددًا')}
     else{toast('تم تحديث كلمة المرور وإلغاء الجلسات القديمة');navigate('admin')}
   }catch(e){toast(e.message,true)}
 });
 $('#closePeriod').onclick=async()=>{
   const data=await modal('إقفال شهر محاسبي','لا يمكن إدخال قيود جديدة أو اعتماد حركات في شهر مغلق. تأكد من التسويات أولًا.',[
     {name:'period',type:'month',label:'الشهر المطلوب إقفاله',value:state.month,required:true}
   ]);
   if(!data)return;
   try{
     const check=await api('/api/periods/preflight?period='+encodeURIComponent(data.period));
     if(!check.ready){toast('لا يمكن الإقفال: '+check.reason,true);return;}
     await post('/api/periods/close',data);
     toast('تم إقفال الشهر بعد اجتياز الفحص المالي والورديات');navigate('admin');
   }catch(e){toast(e.message,true)}
 };
 $('#syncNow').onclick=async()=>{
   $('#syncNow').disabled=true;
   try{const r=await post('/api/sync-google');toast('اكتملت مزامنة بيانات النظام إلى Google Sheets');navigate('admin');}
   catch(e){toast(e.message,true);$('#syncNow').disabled=false;}
 };
}

function modal(title,message,fields=[],setup=null){
 return new Promise(resolve=>{
  const dialog=$('#modal');$('#modalTitle').textContent=title;$('#modalText').innerHTML=message;
  $('#modalError').hidden=true;
  $('#modalFields').innerHTML=fields.map(f=>{
    let field;
    if(f.type==='checkbox')field=`<input type="checkbox" name="${esc(f.name)}">`;
    else if(f.type==='select')field=`<select name="${esc(f.name)}" ${f.required?'required':''}><option value="">اختر</option>${(f.options||[]).map(x=>opt(x[0],x[1])).join('')}</select>`;
    else if(f.type==='textarea')field=`<textarea name="${esc(f.name)}" rows="3" placeholder="${esc(f.placeholder||'')}" ${f.required?'required':''}></textarea>`;
    else field=`<input name="${esc(f.name)}" type="${esc(f.type||'text')}" ${f.type==='file'?'accept=".pdf,.jpg,.jpeg,.png"':`value="${esc(f.value??'')}"`} placeholder="${esc(f.placeholder||'')}" ${f.required?'required':''} ${f.type==='number'?`step="${esc(f.step||'0.01')}" min="0"`:''}>`;
    return `<label>${esc(f.label)}${field}</label>`;
  }).join('');
  const form=$('#modalForm');const cleanup=()=>{form.onsubmit=null;$('#modalCancel').onclick=null;$('#modalClose').onclick=null;dialog.oncancel=null;};
  function cancel(){cleanup();dialog.close();resolve(null);}
  $('#modalCancel').onclick=cancel;$('#modalClose').onclick=cancel;dialog.oncancel=e=>{e.preventDefault();cancel();};
  form.onsubmit=e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form));cleanup();dialog.close();resolve(data);};
  if(setup)setup(form);
  dialog.showModal();
 });
}

async function loadSession(){
 try{const me=await api('/api/me');state.me=me;state.csrf=me.csrf;await bootstrapUI();}
 catch{showLogin();}
}
function initializeEvents(){
 $('#loginForm').addEventListener('submit',login);
 $('#mainNav').addEventListener('click',e=>{const b=e.target.closest('[data-view]');if(b)navigate(b.dataset.view)});
 $$('[data-view]',document).forEach(b=>{if(b.closest('#mainNav'))return;b.addEventListener('click',()=>navigate(b.dataset.view));});
 $('#content').addEventListener('click',e=>{const b=e.target.closest('[data-go]');if(b)navigate(b.dataset.go)});
 $('#showSidebar').onclick=()=>{$('#sidebar').classList.add('open');$('#mobileShade').hidden=false};
 $('#hideSidebar').onclick=hideMenu;$('#mobileShade').onclick=hideMenu;
 const logout=async()=>{try{await post('/api/logout');}catch{}state.me=null;state.csrf='';hideMenu();showLogin();};
 $('#logoutButton').onclick=logout;$('#mobileLogoutButton').onclick=logout;
}
initializeEvents();loadSession();
