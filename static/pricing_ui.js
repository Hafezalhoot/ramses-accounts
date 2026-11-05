"use strict";
/* S14: immutable owner tariffs/packages, cashier quotes, and reviewed service fees. */
(() => {
 const categories={doctor:'طبيب',nurse:'تمريض',technician:'فني',other:'أخرى'};
 let selectedList=null,selectedTab='rates';
 const active=items=>(items||[]).filter(x=>x.active!==false&&x.active!==0);
 const options=(items,value,label=x=>x.name)=>items.map(x=>opt(x.id,label(x),value)).join('');
 const find=(items,id)=>(items||[]).find(x=>String(x.id)===String(id));
 const name=(items,id)=>find(items,id)?.name||'غير محدد';
 const amount=v=>v==null?'غير مسجلة':`${fmt(v)} ج.م`;
 const decimal=v=>v==null?'':(Number(v)/100).toFixed(2);
 const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Africa/Cairo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const input=(label,name,value='',type='text',extra='')=>`<label>${esc(label)}<input name="${esc(name)}" type="${type}" value="${esc(value)}" ${extra}></label>`;
 const select=(label,name,html,extra='')=>`<label>${esc(label)}<select name="${esc(name)}" aria-label="${esc(label)}" ${extra}>${html}</select></label>`;
 const moneyInput=(label,name,value='',required=true)=>input(label,name,value,'text',`inputmode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" ${required?'required':''} placeholder="0.00"`);
 const btn=(text,attrs='',variant='secondary')=>`<button type="button" class="btn btn-${variant}" ${attrs}>${text}</button>`;
 function denied(){ $('#content').innerHTML=empty('ليست لديك صلاحية لعرض هذه الصفحة.'); }
 function notice(host,message,bad=false){host.textContent=message;host.hidden=!message;host.className=bad?'form-error':'info-box';}

 // A separate single dialog keeps the common application modal's lifecycle intact.
 function dialog(title,description,fields,onSave,setup,saveText='حفظ',gated=false){
  const previous=$('#pricingDialog');if(previous){previous.close();previous.remove();}
  const el=document.createElement('dialog');el.id='pricingDialog';el.className='modal pricing-dialog';
  el.setAttribute('aria-labelledby','pricingDialogTitle');el.setAttribute('aria-describedby','pricingDialogDescription');
  el.innerHTML=`<form id="pricingDialogForm"><div class="modal-header"><h2 id="pricingDialogTitle">${esc(title)}</h2>${btn('إغلاق','data-dialog-close aria-label="إغلاق النافذة"','secondary')}</div><p id="pricingDialogDescription" class="pricing-help">${esc(description)}</p><div class="pricing-fields">${fields}</div><div id="pricingDialogError" role="alert" class="form-error" hidden></div><div class="modal-buttons">${btn('إلغاء','data-dialog-close')}<button id="pricingDialogSave" type="submit" class="btn btn-primary" ${gated?'disabled':''}>${esc(saveText)}</button></div></form>`;
  document.body.append(el);
  const form=$('form',el),save=$('#pricingDialogSave',el),error=$('#pricingDialogError',el);
  const ui={el,form,save,error,busy:false,allowed:!gated,
   gate(allowed){this.allowed=allowed;save.disabled=this.busy||!allowed;},
   setError(message){notice(error,message,true);},
   close(){if(el.open)el.close();},
   live(){return el.isConnected&&el.open;}
  };
  $$('[data-dialog-close]',el).forEach(b=>b.addEventListener('click',()=>ui.close()));
  el.addEventListener('close',()=>el.remove(),{once:true});
  form.addEventListener('submit',async e=>{
   e.preventDefault();if(ui.busy||!ui.allowed)return;
   ui.busy=true;save.disabled=true;error.hidden=true;
   try{if(await onSave(ui)!==false)ui.close();}
   catch(err){if(ui.live())ui.setError(err.message);}
   finally{ui.busy=false;if(ui.live())save.disabled=!ui.allowed;}
  });
  if(setup)setup(ui);
  el.showModal();return ui;
 }
 const data=ui=>Object.fromEntries(new FormData(ui.form));
 function reloadPricing(){toast('تم حفظ إصدار التسعير');return renderPricing();}
 function section(title,description,body,actions=''){
  return `<section class="panel pricing-section"><div class="panel-header"><div><h2>${title}</h2><p>${description}</p></div><div class="pricing-actions">${actions}</div></div>${body}</section>`;
 }
 function ruleSummary(r,c){
  const who=r.target==='person'?name(c.people,r.person_id):(categories[r.category]||r.category);
  return `${esc(who)} · ${r.kind==='fixed'?amount(r.fixed_piasters??(Number(r.fixed_amount||0)*100)):`${esc(r.percentage??'')}٪ من المحصل`} · ${r.when==='always'?'مستفيد عام':'عند التنفيذ'} · مشتركة`;
 }
 function rateCards(rates,c){
  return `<div class="pricing-mobile-rates">${rates.length?rates.map(r=>`<article class="pricing-mobile-card"><header><h3>${esc(name(c.services,r.service_id))}</h3><span>${esc(find(c.services,r.service_id)?.unit||'وحدة')}</span></header><p class="pricing-mobile-place">${esc(name(c.locations,r.location_id))}</p><div class="pricing-mobile-price"><span>سعر الخدمة</span><strong class="pricing-rate-price">${amount(r.price_piasters)}</strong></div><dl><div><dt>التكلفة الاسترشادية</dt><dd>${amount(r.estimated_cost_piasters)}</dd></div><div><dt>بداية السريان</dt><dd>${esc(r.valid_from)}</dd></div></dl><div class="pricing-mobile-rules"><strong>${(r.rules||[]).length?`قواعد الحصص: ${esc(r.rules.length)}`:'بدون حصص'}</strong>${(r.rules||[]).slice(0,2).map(x=>`<p>${ruleSummary(x,c)}</p>`).join('')}${(r.rules||[]).length>2?'<p>تظهر بقية القواعد عند فتح إصدار جديد.</p>':''}</div>${btn('سعر بتاريخ جديد',`data-rate-copy="${r.id}"`,'outline')}</article>`).join(''):empty('لا توجد تعريفات لهذه القائمة.')}</div>`;
 }
 function packageCards(packages,c){
  return `<div class="pricing-mobile-packages">${packages.length?packages.map(p=>`<article class="pricing-mobile-card"><header><h3>${esc(p.name)}</h3><span>${esc(p.code)}</span></header><div class="pricing-mobile-price"><span>السعر النهائي</span><strong class="pricing-package-net">${amount(p.net_piasters)}</strong></div><dl><div><dt>قبل الخصم</dt><dd>${amount(p.gross_piasters)}</dd></div><div><dt>الخصم</dt><dd class="pricing-package-discount">${amount(p.gross_piasters-p.net_piasters)}</dd></div><div><dt>بداية السريان</dt><dd>${esc(p.valid_from)}</dd></div></dl><div class="pricing-mobile-components"><strong>المكونات وأماكن التنفيذ</strong><ul>${(p.items||[]).map(i=>`<li>${esc(name(c.services,i.service_id))} × ${esc(i.quantity)}<small>${esc(name(c.locations,i.location_id))}</small></li>`).join('')}</ul></div>${btn('إصدار جديد',`data-package-copy="${p.id}"`,'outline')}</article>`).join(''):empty('لا توجد باقات لهذه القائمة.')}</div>`;
 }

 async function renderPricing(){
  if(state.me?.role!=='owner'){denied();return;}
  const identity=state.me.id;
  const c=await api('/api/pricing/catalog');
  if(state.me?.id!==identity||state.me?.role!=='owner')return;
  if(!state.lookups?.departments)state.lookups=await api('/api/lookups');
  if(state.me?.id!==identity||state.me?.role!=='owner')return;
  if(!find(c.lists,selectedList))selectedList=c.lists[0]?.id??null;
  const rates=(c.rates||[]).filter(r=>String(r.price_list_id)===String(selectedList));
  const packages=(c.packages||[]).filter(p=>String(p.price_list_id)===String(selectedList));
  const tabs=[['rates','تعريفات الخدمات'],['packages','الباقات'],['directory','دليل التعريفات']];
  let body;
  if(selectedTab==='rates')body=section('أسعار الخدمات وتاريخ السريان','كل حفظ ينشئ إصدارًا؛ الخدمات المقبولة سابقًا تحتفظ بسعرها.',
   '<div class="pricing-desktop-rates">'+table(['الخدمة / الوحدة','المكان','بداية السريان','السعر','التكلفة الاسترشادية','قواعد الحصص','إصدار'],rates.map(r=>`<tr><td><strong>${esc(name(c.services,r.service_id))}</strong><small class="pricing-small">${esc(find(c.services,r.service_id)?.unit||'وحدة')}</small></td><td>${esc(name(c.locations,r.location_id))}</td><td>${esc(r.valid_from)}</td><td class="num">${amount(r.price_piasters)}</td><td class="num">${amount(r.estimated_cost_piasters)}</td><td class="pricing-wrap">${(r.rules||[]).map(x=>ruleSummary(x,c)).join('<br>')||'بدون حصص'}</td><td>${btn('سعر بتاريخ جديد',`data-rate-copy="${r.id}"`,'outline')}</td></tr>`).join(''))+'</div>'+rateCards(rates,c),
   btn('تعريفة جديدة','id="pricingNewRate"','primary'));
  else if(selectedTab==='packages')body=section('باقات قائمة السعر','السعر الإجمالي يقارن بالمكونات والتكلفة؛ أي تعديل يحفظ إصدارًا جديدًا.',
   '<div class="pricing-desktop-packages">'+table(['الباقة','المكونات','قبل الخصم','الصافي','السريان','إصدار'],packages.map(p=>`<tr><td><strong>${esc(p.name)}</strong><small class="pricing-small">${esc(p.code)}</small></td><td class="pricing-wrap">${(p.items||[]).map(i=>`${esc(name(c.services,i.service_id))} × ${esc(i.quantity)} · ${esc(name(c.locations,i.location_id))}`).join('<br>')}</td><td class="num">${amount(p.gross_piasters)}</td><td class="num">${amount(p.net_piasters)}</td><td>${esc(p.valid_from)}</td><td>${btn('إصدار جديد',`data-package-copy="${p.id}"`,'outline')}</td></tr>`).join(''))+'</div>'+packageCards(packages,c),
   btn('باقة جديدة','id="pricingNewPackage"','primary'));
  else body=directory(c);
  $('#content').innerHTML=head('إدارة التسعير','قوائم الأسعار والخدمات','أسعار بالمكان والقائمة، وتكلفة استرشادية وحصص محفوظة للمالك.')+
   `<div class="info-box"><div>النسب من المحصل الفعلي. المبلغ الثابت كامل لكل مرة منفذة ومفوتَرة ولو لم تُحصّل، ولا يتأثر بالخصم. كل حصة تقدير إلى أن تُراجع وتُعتمد في مستحقات الخدمات.</div></div>`+
   `<div class="panel pricing-toolbar">${select('قائمة السعر','pricing_list',options(c.lists,selectedList), 'id="pricingListFilter"')}<div class="pricing-tabs" role="group" aria-label="أقسام التسعير">${tabs.map(([key,label])=>btn(label,`data-pricing-tab="${key}" aria-pressed="${selectedTab===key}"`,selectedTab===key?'primary':'secondary')).join('')}</div></div>${body}`;
  $('#pricingListFilter').addEventListener('change',e=>{selectedList=e.target.value;renderPricing().catch(e=>toast(e.message,true));});
  $$('[data-pricing-tab]').forEach(b=>b.addEventListener('click',()=>{selectedTab=b.dataset.pricingTab;renderPricing().catch(e=>toast(e.message,true));}));
  $('#pricingNewRate')?.addEventListener('click',()=>rateDialog(c));
  $('#pricingNewPackage')?.addEventListener('click',()=>packageDialog(c));
  $$('[data-rate-copy]').forEach(b=>b.addEventListener('click',()=>rateDialog(c,find(c.rates,b.dataset.rateCopy))));
  $$('[data-package-copy]').forEach(b=>b.addEventListener('click',()=>packageDialog(c,find(c.packages,b.dataset.packageCopy))));
  bindDirectory(c);
 }
 function directory(c){
  return section('الخدمات','الخدمة لها كود وقسم ووحدة ووصف مستقل عن تعريفتها.',
   table(['الكود','الخدمة','القسم','الوحدة','الوصف','تفاصيل'],(c.services||[]).map(s=>`<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td><td>${esc(s.department_name)}</td><td>${esc(s.unit||'—')}</td><td class="pricing-wrap">${esc(s.description||'—')}</td><td>${btn('تعديل التفاصيل',`data-service-details="${s.id}"`,'outline')}</td></tr>`).join('')),btn('خدمة جديدة','id="pricingNewService"','primary'))+
   `<div class="pricing-directory-grid">`+section('قوائم الأسعار','لكل قائمة تعريفاتها وباقاتها.',table(['الكود','القائمة'],(c.lists||[]).map(x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td></tr>`).join('')),btn('قائمة جديدة','id="pricingNewList"'))+
   section('أماكن تنفيذ الخدمة','المكان مستقل عن نقطة التحصيل.',table(['الكود','المكان','القسم'],(c.locations||[]).map(x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${esc(x.department_name||name(state.lookups.departments,x.department_id))}</td></tr>`).join('')),btn('مكان جديد','id="pricingNewLocation"'))+`</div>`+
   section('الأشخاص والمنفذون','تستخدم الفئة لتوزيع الحصة بين المنفذين الفعليين المسجلين للخدمة.',table(['الكود','الاسم','الفئة'],(c.people||[]).map(x=>`<tr><td>${esc(x.code)}</td><td>${esc(x.name)}</td><td>${esc(categories[x.category]||x.category)}</td></tr>`).join('')),btn('شخص جديد','id="pricingNewPerson"'));
 }
 function bindDirectory(c){
  $('#pricingNewList')?.addEventListener('click',()=>dialog('قائمة أسعار جديدة','تُنشأ القوائم دون نقل أسعار من قائمة أخرى.',input('كود القائمة','code','','text','required')+input('اسم القائمة','name','','text','required'),async ui=>{await post('/api/pricing/lists',data(ui));await reloadPricing();}));
  $('#pricingNewLocation')?.addEventListener('click',()=>dialog('مكان تنفيذ جديد','اختر القسم المسؤول عن مكان التنفيذ.',input('كود المكان','code','','text','required')+input('اسم المكان','name','','text','required')+select('القسم','department_id',options(state.lookups.departments), 'required'),async ui=>{const d=data(ui);await post('/api/pricing/locations',{...d,department_id:Number(d.department_id)});await reloadPricing();}));
  $('#pricingNewPerson')?.addEventListener('click',()=>dialog('تسجيل شخص','الأشخاص هنا لأتعاب الخدمات، ولا ينشئ التسجيل حساب دخول أو راتبًا.',input('كود الشخص','code','','text','required')+input('اسم الشخص','name','','text','required')+select('الفئة','category',Object.entries(categories).map(([k,v])=>opt(k,v)).join(''),'required'),async ui=>{await post('/api/pricing/people',data(ui));await reloadPricing();}));
  $('#pricingNewService')?.addEventListener('click',()=>serviceDialog());
  $$('[data-service-details]').forEach(b=>b.addEventListener('click',()=>serviceDialog(find(c.services,b.dataset.serviceDetails))));
 }
 function serviceDialog(service=null){
  let createdId=service?.id;
  dialog(service?'تفاصيل الخدمة':'خدمة جديدة','التعريف مستقل عن السعر. بعد الحفظ أضف تعريفة بالقائمة والمكان.',
   (service?'':input('كود الخدمة','code','','text','required')+input('اسم الخدمة','name','','text','required')+select('قسم الخدمة','department_id',options(state.lookups.departments),'required')+select('نقطة التحصيل المقترحة','suggested_point',opt('either','كلاهما')+opt('external','الخارجي')+opt('internal','الداخلي'),'required'))+
   input('وحدة الخدمة','unit',service?.unit||'وحدة','text','required maxlength="40"')+`<label>وصف الخدمة<textarea name="description" rows="3" maxlength="1000">${esc(service?.description||'')}</textarea></label>`,
   async ui=>{const d=data(ui);if(!createdId){const result=await post('/api/billing/services',{code:d.code,name:d.name,department_id:Number(d.department_id),suggested_point:d.suggested_point});createdId=result.id??result.service?.id;if(!createdId)throw Error('تعذر تحديد الخدمة الجديدة؛ حدّث الدليل قبل المحاولة.');}
    await post(`/api/pricing/services/${createdId}/details`,{unit:d.unit,description:d.description});await reloadPricing();});
 }
 function ruleRow(c,r={}){
  const row=document.createElement('fieldset');row.className='pricing-rule';
  row.innerHTML=`<legend>قاعدة حصة</legend><div class="pricing-form-grid">${select('المستفيد','target',opt('person','شخص معين',r.target||'person')+opt('category','فئة من المنفذين',r.target))}${select('الشخص أو الفئة','beneficiary','')}${select('شرط الاستحقاق','when',opt('performed','عند التنفيذ',r.when||'performed')+opt('always','مستفيد عام',r.when))}${select('نوع الحصة','kind',opt('percent','نسبة من المحصل',r.kind||'percent')+opt('fixed','مبلغ ثابت لكل مرة',r.kind))}${input('قيمة الحصة','value',r.kind==='fixed'?decimal(r.fixed_piasters??(r.fixed_amount==null?null:Number(r.fixed_amount)*100)):(r.percentage??''),'number','required min="0.0001" step="0.0001"')}<label class="pricing-check"><input name="discount_affects" type="checkbox" ${r.discount_affects!==false?'checked':''}> تتأثر بخصم الباقة</label></div><p class="pricing-help">مشتركة بين المنفذين المطابقين لكل مرة. النسبة من المحصل الفعلي؛ والثابت كامل بعد التنفيذ والفاتورة ولو لم تُحصّل، ولا يتأثر بالخصم.</p>${btn('حذف القاعدة','data-remove-rule','secondary')}`;
  const target=$('[name="target"]',row),who=$('[name="beneficiary"]',row),when=$('[name="when"]',row),kind=$('[name="kind"]',row),value=$('[name="value"]',row),discount=$('[name="discount_affects"]',row);
  function targetChanged(){
   who.innerHTML=target.value==='person'?options(active(c.people),r.person_id):Object.entries(categories).map(([k,v])=>opt(k,v,r.category)).join('');
   who.required=true;$('option[value="always"]',when).disabled=target.value==='category';
   if(target.value==='category')when.value='performed';
  }
  function kindChanged(){const fixed=kind.value==='fixed';discount.disabled=fixed;discount.checked=fixed?false:(r.discount_affects!==false);value.step=fixed?'0.01':'0.0001';value.min=fixed?'0.01':'0.0001';if(fixed)value.removeAttribute('max');else value.max='100';}
  target.addEventListener('change',targetChanged);kind.addEventListener('change',kindChanged);
  $('[data-remove-rule]',row).addEventListener('click',()=>row.remove());targetChanged();kindChanged();return row;
 }
 function readRules(form){return $$('.pricing-rule',form).map(row=>{
  const v=n=>$(`[name="${n}"]`,row).value;
  const fixed=v('kind')==='fixed';
  return {target:v('target'),...(v('target')==='person'?{person_id:Number(v('beneficiary'))}:{category:v('beneficiary')}),when:v('when'),kind:v('kind'),...(fixed?{fixed_amount:v('value')}:{percentage:v('value')}),discount_affects:fixed?false:$('[name="discount_affects"]',row).checked,distribution:'shared',basis:'collected'};
 });}
 function rateDialog(c,r={}){
  if(!(c.services||[]).length||!active(c.locations).length||!active(c.lists).length){toast('سجل خدمة وقائمة سعر ومكان تنفيذ من دليل التعريفات أولًا.',true);return;}
  dialog('تعريفة بتاريخ سريان','لن يتغير أي عرض أو خدمة حُفظت سابقًا. الحصص المعروضة تقديرية وتحتاج اعتمادًا مستقلًا.',
   `<div class="pricing-form-grid">${select('قائمة السعر','price_list_id',options(active(c.lists),r.price_list_id??selectedList),'required')}${select('الخدمة','service_id',options(c.services,r.service_id),'required')}${select('مكان التنفيذ','location_id',options(active(c.locations),r.location_id),'required')}${input('بداية السريان','valid_from',r.id?today():(r.valid_from||today()),'date','required')}${moneyInput('سعر الخدمة (ج.م)','amount',decimal(r.price_piasters))}${moneyInput('التكلفة الاسترشادية (ج.م) — اختيارية','estimated_cost',decimal(r.estimated_cost_piasters),false)}</div><div class="pricing-subhead"><h3>قواعد حصص الخدمة</h3>${btn('إضافة قاعدة','data-add-rule','outline')}</div><div data-rule-list class="pricing-stack"></div>`,
   async ui=>{const d=data(ui);await post('/api/pricing/rates',{price_list_id:Number(d.price_list_id),service_id:Number(d.service_id),location_id:Number(d.location_id),valid_from:d.valid_from,amount:d.amount,estimated_cost:d.estimated_cost||null,rules:readRules(ui.form)});await reloadPricing();},
   ui=>{const host=$('[data-rule-list]',ui.form);(r.rules||[]).forEach(rule=>host.append(ruleRow(c,rule)));$('[data-add-rule]',ui.form).addEventListener('click',()=>host.append(ruleRow(c)));});
 }
 function itemRow(c,i={}){
  const row=document.createElement('fieldset');row.className='pricing-package-item';row.innerHTML=`<legend>مكوّن الباقة</legend><div class="pricing-item-grid">${select('خدمة المكوّن','service_id',options(c.services,i.service_id),'required')}${select('مكان المكوّن','location_id',options(active(c.locations),i.location_id),'required')}${input('كمية المكوّن','quantity',i.quantity||1,'number','required min="1" max="1000" step="1"')}${btn('حذف المكوّن','data-remove-item')}</div>`;return row;
 }
 function readItems(form){
  const items=$$('.pricing-package-item',form).map(row=>({service_id:Number($('[name="service_id"]',row).value),location_id:Number($('[name="location_id"]',row).value),quantity:Number($('[name="quantity"]',row).value)}));
  if(!items.length)throw Error('أضف مكوّنًا واحدًا على الأقل.');
  const keys=items.map(x=>`${x.service_id}:${x.location_id}`);
  if(new Set(keys).size!==keys.length)throw Error('الخدمة والمكان مكرران؛ اجمعهما في مكوّن واحد بالكمية المطلوبة.');
  return items;
 }
 function summary(p,owner=false){
  const percent=Number(p.gross_piasters)>0?(Number(p.discount_piasters||0)*100/Number(p.gross_piasters)).toFixed(2):'0.00';
  const fees=(p.lines||[]).flatMap(l=>l.commission_preview||[]),feeTotal=fees.reduce((sum,f)=>sum+Number(f.amount_piasters||0),0);
  const margin=p.cost_complete?Number(p.net_piasters)-Number(p.estimated_cost_piasters)-feeTotal:null;
  const feeSummary=owner&&fees.length?`<div><span>الحصص المقدرة للمستفيدين المحددين</span><strong>${amount(feeTotal)}</strong></div>${margin!=null?`<div><span>فرق تقديري بعد التكلفة والحصص المعروضة</span><strong>${amount(margin)}</strong></div>`:''}<p class="pricing-help pricing-summary-note">هذه تقديرات تفترض التحصيل الكامل؛ حصص المنفذين تعتمد على تعيينهم ومطابقتهم قبل الاعتماد، وليست مبالغ مستحقة.</p>`:'';
  const warning=owner&&(margin<0&&margin!=null||feeTotal>p.net_piasters)?'<p class="pricing-cost-warning">الفرق التقديري سالب: السعر لا يغطي التكلفة والحصص المعروضة. الثابت لا ينخفض مع خصم الباقة؛ راجع التسعير قبل الحفظ.</p>':'';
  return `<div class="pricing-summary" role="status"><div><span>سعر المكونات قبل الخصم</span><strong>${amount(p.gross_piasters)}</strong></div><div><span>الخصم · ${percent}٪</span><strong>${amount(p.discount_piasters)}</strong></div><div><span>السعر النهائي</span><strong>${amount(p.net_piasters)}</strong></div>${owner?(p.cost_complete?`<div><span>التكلفة الاسترشادية</span><strong>${amount(p.estimated_cost_piasters)}</strong></div><div><span>فرق السعر عن التكلفة الاسترشادية</span><strong>${amount(p.net_piasters-p.estimated_cost_piasters)}</strong></div>`:`<p class="pricing-cost-warning">التكلفة غير مكتملة؛ التكلفة المعروفة ${amount(p.known_cost_piasters)}. لا يمكن حساب الفرق الكامل عن التكلفة.</p>`):''}${feeSummary}${warning}</div>`;
 }
 function packageDialog(c,p={}){
  if(!(c.services||[]).length||!active(c.locations).length||!active(c.lists).length){toast('سجل خدمة وقائمة ومكان تنفيذ قبل إنشاء الباقة.',true);return;}
  let previewKey='',previewHash='';
  const payload=form=>{const d=Object.fromEntries(new FormData(form));return {code:d.code,name:d.name,price_list_id:Number(d.price_list_id),valid_from:d.valid_from,items:readItems(form),...(d.price_mode==='final'?{final_amount:d.package_amount}:{discount_amount:d.package_amount})};};
  function invalidatePreview(ui){previewKey='';previewHash='';ui.gate(false);$('[data-package-summary]',ui.form).innerHTML='<p class="pricing-help">يلزم تحديث المعاينة ومراجعتها قبل تأكيد الحفظ.</p>';}
  dialog(p.id?'إصدار جديد للباقة':'باقة جديدة','تتبع الباقة قائمة سعر واحدة، ولكل مكوّن مكانه. احسب المعاينة ثم راجع السعر قبل الحفظ.',
   `<div class="pricing-form-grid">${input('كود الباقة','code',p.code||'','text','required')}${input('اسم الباقة','name',p.name||'','text','required')}${select('قائمة السعر','price_list_id',options(active(c.lists),p.price_list_id??selectedList),'required')}${input('بداية السريان','valid_from',today(),'date','required')}</div><div class="pricing-subhead"><h3>مكونات الباقة</h3>${btn('إضافة مكوّن','data-add-item','outline')}</div><div data-package-items class="pricing-stack"></div><div class="pricing-form-grid">${select('طريقة تسعير الباقة','price_mode',opt('final','قيمة نهائية')+opt('discount','مبلغ خصم'))}<label><span data-price-label>القيمة النهائية (ج.م)</span><input name="package_amount" type="text" inputmode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" value="${esc(decimal(p.net_piasters))}" required></label></div><div class="pricing-preview-action">${btn('معاينة السعر والتكلفة','data-package-preview','outline')}</div><div data-package-summary aria-live="polite"></div>`,
   async ui=>{
    const request=payload(ui.form);if(JSON.stringify(request)!==previewKey||!previewHash)throw Error('أعد معاينة الباقة بعد آخر تعديل.');
    try{await post('/api/pricing/packages',{...request,preview_hash:previewHash});}
    catch(err){if(err.status===409)invalidatePreview(ui);throw err;}
    await reloadPricing();
   },
   ui=>{
    const host=$('[data-package-items]',ui.form),out=$('[data-package-summary]',ui.form);
    function invalidate(){invalidatePreview(ui);}
    function add(i){const row=itemRow(c,i);$('[data-remove-item]',row).addEventListener('click',()=>{row.remove();invalidate();});host.append(row);invalidate();}
    (p.items?.length?p.items:[{}]).forEach(add);
    $('[data-add-item]',ui.form).addEventListener('click',()=>add({}));
    ui.form.addEventListener('input',invalidate);ui.form.addEventListener('change',()=>{const discount=ui.form.elements.price_mode.value==='discount';$('[data-price-label]',ui.form).textContent=discount?'مبلغ الخصم (ج.م)':'القيمة النهائية (ج.م)';invalidate();});
    $('[data-package-preview]',ui.form).addEventListener('click',async e=>{
     if(!ui.form.reportValidity())return;const b=e.currentTarget;b.disabled=true;ui.error.hidden=true;
     try{const request=payload(ui.form),key=JSON.stringify(request),result=await post('/api/pricing/package-preview',request);if(!ui.live()||key!==JSON.stringify(payload(ui.form)))return;if(!/^[a-f0-9]{64}$/i.test(result.preview_hash||''))throw Error('تعذر تأكيد بصمة معاينة الباقة؛ أعد المعاينة.');previewKey=key;previewHash=result.preview_hash;out.innerHTML=summary(result,true);ui.gate(true);}
     catch(err){if(ui.live()){invalidate();ui.setError(err.message);}}finally{b.disabled=false;}
    });
   },'حفظ إصدار الباقة',true);
 }

 async function pricingOrderForCase(caseId){
  if(!['owner','clerk'].includes(state.me?.role)){toast('إضافة الطلب متاحة للكاشير ومدير النظام.',true);return;}
  const identity=state.me.id,role=state.me.role;
  const c=await api('/api/pricing/catalog');
  if(state.me?.id!==identity||state.me?.role!==role)return;
  if(!active(c.lists).length){toast('لا توجد قائمة أسعار متاحة؛ اطلب إعداد الأسعار من مدير النظام.',true);return;}
  let quote=null,quoteKey='',previewSerial=0;
  dialog('إضافة خدمة أو باقة للحالة','طلب الخدمة لا يُثبت تنفيذها ولا يُصدر فاتورة أو يقبض مالًا. الإثبات الطبي مستقل، والباقة لا تُفوتر جزئيًا.',
   `<div class="pricing-form-grid">${select('قائمة السعر','price_list_id',options(active(c.lists)), 'required')}${select('نوع الطلب','order_type',opt('service','خدمة مفردة')+opt('package','باقة'))}</div><div data-order-selection></div><p id="pricingPerformerPolicy" class="pricing-help">منفذون مقترحون للأتعاب — تُراجع مطابقتهم لإثبات التنفيذ قبل الاعتماد. يمكن اختيار أكثر من شخص؛ الحصة مشتركة بينهم لكل مرة، وهذا التعيين لا يُثبت التنفيذ الطبي.</p><div data-order-performers class="pricing-stack"></div><div class="pricing-preview-action">${btn('معاينة الطلب','data-order-preview','outline')}</div><div data-order-summary aria-live="polite"></div>`,
   async ui=>{
    const request=orderPayload(ui,c,caseId);
    if(!quote||JSON.stringify(request)!==quoteKey)throw Error('عاين الطلب بعد آخر تعديل قبل إضافته.');
    try{await billingMutation(`pricing-order-${caseId}`,'/api/pricing/orders',{...request,quote_hash:quote.quote_hash});toast('أضيف الطلب للحالة؛ يلزم إثبات التنفيذ قبل الفاتورة.');billingState.caseId=Number(caseId);await navigate('billing');return true;}
    catch(err){
     if(err.status===409||/quote|stale|تغير|السعر|تعريفة/i.test(err.message)){
      quote=null;quoteKey='';ui.gate(false);
      await refreshQuote(ui);
      ui.setError('لم يُحفظ الطلب لتغير العرض. راجع المعاينة المحدثة واضغط إضافة الطلب مرة أخرى للتأكيد.');return false;
     }
     throw err;
    }
   },
   ui=>{
    const selection=$('[data-order-selection]',ui.form),performers=$('[data-order-performers]',ui.form),out=$('[data-order-summary]',ui.form);
    const invalidate=()=>{++previewSerial;quote=null;quoteKey='';ui.gate(false);out.innerHTML='<p class="pricing-help">عاين السعر قبل إضافة الطلب.</p>';};
    function selectedParts(){
     const d=data(ui);
     if(d.order_type==='package')return find(c.packages,d.package_version_id)?.items||[];
     return d.service_id&&d.location_id?[{service_id:Number(d.service_id),location_id:Number(d.location_id),quantity:Number(d.quantity)||1}]:[];
    }
    function showPerformers(preserve=false){
     const saved=new Map();
     if(preserve)$$('[data-performer-block]',performers).forEach(block=>{
      const assignments={};$$('select[data-occurrence-no]',block).forEach(s=>{assignments[Number(s.dataset.occurrenceNo)]=Array.from(s.selectedOptions).map(o=>Number(o.value));});
      saved.set(block.dataset.performerBlock,{same:$('[data-same-performers]',block).checked,assignments});
     });
     performers.replaceChildren();
     selectedParts().forEach((item,index)=>{
      const qty=Math.max(1,Math.trunc(Number(item.quantity)||1)),key=`${item.service_id}:${item.location_id}`,old=saved.get(key),same=qty>50||qty===1?true:(old?.same??true);
      const service=`${name(c.services,item.service_id)} / ${name(c.locations,item.location_id)}`,toggleLabel=`نفس المنفذين لكل مرات التنفيذ — ${service}`;
      const block=document.createElement('fieldset');block.className='pricing-performer-block';block.dataset.performerBlock=key;
      block.innerHTML=`<legend>${esc(service)}</legend><label class="pricing-check"><input type="checkbox" data-same-performers="${index}" aria-label="${esc(toggleLabel)}" ${same?'checked':''} ${qty===1||qty>50?'disabled':''}>نفس المنفذين لكل مرات التنفيذ</label>${qty>50?'<p class="pricing-help">تحديد منفذين مختلفين لكل مرة متاح حتى 50 مرة للمكوّن؛ هذه الكمية تستخدم مجموعة واحدة لكل المرات.</p>':''}<div class="pricing-stack" data-occurrence-fields></div>`;
      const host=$('[data-occurrence-fields]',block),count=same?1:qty;
      for(let n=0;n<count;n++){
       const occurrence=same?0:n+1,ids=old?.assignments[occurrence]??old?.assignments[0]??old?.assignments[1]??[];
       const label=`منفذون مقترحون — ${service}${same?'':` — المرة ${occurrence}`}`;
       host.insertAdjacentHTML('beforeend',`<label>${esc(label)}<select multiple size="4" data-performer-index="${index}" data-occurrence-no="${occurrence}" aria-label="${esc(label)}" aria-describedby="pricingPerformerPolicy pricingPerformerHelp">${active(c.people).map(p=>opt(p.id,`${p.name} · ${categories[p.category]||p.category}`,ids.includes(Number(p.id))?p.id:null)).join('')}</select></label>`);
      }
      performers.append(block);
     });
     performers.insertAdjacentHTML('beforeend','<small id="pricingPerformerHelp" class="pricing-help">للاختيار المتعدد على الكمبيوتر استخدم Ctrl أو ⌘ مع النقر.</small>');
    }
    function locations(){const d=data(ui);const ids=new Set((c.rates||[]).filter(r=>String(r.price_list_id)===d.price_list_id&&String(r.service_id)===d.service_id).map(r=>Number(r.location_id)));const sel=$('[name="location_id"]',ui.form);if(sel)sel.innerHTML=options(active(c.locations).filter(l=>ids.has(Number(l.id))));showPerformers();}
    function selections(){
     const d=data(ui);
     if(d.order_type==='package')selection.innerHTML=select('الباقة','package_version_id',options((c.packages||[]).filter(p=>String(p.price_list_id)===d.price_list_id),null,p=>`${p.name} · ${amount(p.net_piasters)}`),'required')+'<div data-package-contents class="pricing-help"></div>';
     else{const ids=new Set((c.rates||[]).filter(r=>String(r.price_list_id)===d.price_list_id).map(r=>Number(r.service_id)));selection.innerHTML=`<div class="pricing-form-grid">${select('الخدمة','service_id',options((c.services||[]).filter(s=>ids.has(Number(s.id)))),'required')}${select('مكان التنفيذ','location_id','','required')}${input('الكمية','quantity',1,'number','required min="1" max="50" step="1"')}</div><p class="pricing-help">إدخال الخدمة من هذه الواجهة حتى 50 مرة في الطلب الواحد.</p>`;locations();}
     packageContents();showPerformers();invalidate();
    }
    function packageContents(){const host=$('[data-package-contents]',ui.form);if(host)host.textContent=selectedParts().map(i=>`${name(c.services,i.service_id)} × ${i.quantity} · ${name(c.locations,i.location_id)}`).join('، ');}
    ui.form.addEventListener('input',e=>{if(e.target.name==='quantity')showPerformers(true);invalidate();});
    ui.form.addEventListener('change',e=>{const n=e.target.name;if(n==='price_list_id'||n==='order_type')selections();else if(n==='service_id')locations();else if(n==='location_id'||n==='package_version_id'){packageContents();showPerformers();}else if(e.target.hasAttribute('data-same-performers'))showPerformers(true);invalidate();});
    $('[data-order-preview]',ui.form).addEventListener('click',async e=>{const b=e.currentTarget;b.disabled=true;try{await refreshQuote(ui);}catch(err){if(ui.live())ui.setError(err.message);}finally{b.disabled=false;}});
    ui.refreshOut=out;selections();
   },'إضافة الطلب للحالة',true);
  async function refreshQuote(ui){
   if(!ui.form.reportValidity())return;
   const request=orderPayload(ui,c,caseId),key=JSON.stringify(request),serial=++previewSerial;
   ui.error.hidden=true;ui.gate(false);
   const result=await post('/api/pricing/quote',request);
   if(!ui.live()||serial!==previewSerial||key!==JSON.stringify(orderPayload(ui,c,caseId)))return;
   quote=result;quoteKey=key;
   ui.refreshOut.innerHTML=summary(result,state.me?.role==='owner')+table(['الخدمة','المكان','الكمية','سعر الوحدة','قبل الخصم','الصافي'],(result.lines||[]).map(l=>`<tr><td>${esc(l.service_name||name(c.services,l.service_id))}</td><td>${esc(l.location_name||name(c.locations,l.location_id))}</td><td>${esc(l.quantity)}</td><td>${amount(l.unit_price_piasters)}</td><td>${amount(l.gross_piasters)}</td><td>${amount(l.net_piasters)}</td></tr>`).join(''));
   ui.gate(true);
  }
 }
 function orderPayload(ui,c,caseId){
  const d=data(ui),people=select=>Array.from(select?.selectedOptions||[]).map(x=>Number(x.value));
  const terms=index=>{
   const same=$(`[data-same-performers="${index}"]`,ui.form)?.checked;
   if(same)return {person_ids:people($(`[data-performer-index="${index}"]`,ui.form))};
   return {person_ids:[],occurrence_performers:$$(`[data-performer-index="${index}"]`,ui.form).map(s=>({occurrence_no:Number(s.dataset.occurrenceNo),person_ids:people(s)}))};
  };
  const base={case_id:Number(caseId),price_list_id:Number(d.price_list_id)};
  if(d.order_type==='package'){
   const p=find(c.packages,d.package_version_id);if(!p)throw Error('اختر باقة متاحة لهذه القائمة.');
   return {...base,package_version_id:Number(p.id),performers:(p.items||[]).map((i,index)=>({service_id:Number(i.service_id),location_id:Number(i.location_id),...terms(index)}))};
  }
  if(!d.service_id||!d.location_id)throw Error('لا توجد تعريفة لهذه القائمة والخدمة والمكان.');
  const performers=terms(0);
  return {...base,location_id:Number(d.location_id),lines:[{service_id:Number(d.service_id),quantity:Number(d.quantity),performer_ids:performers.person_ids,...(performers.occurrence_performers?{occurrence_performers:performers.occurrence_performers}:{})}]};
 }

 async function renderServiceFees(){
  if(!['owner','reviewer'].includes(state.me?.role)){denied();return;}
  const identity=state.me.id,role=state.me.role;
  const [queue,balances]=await Promise.all([api('/api/service-fees/queue'),api('/api/service-fees/balances')]);
  if(state.me?.id!==identity||state.me?.role!==role)return;
  const items=queue.items||[],history=balances.decisions||[];
  $('#content').innerHTML=head('مراجعة الأتعاب','مستحقات الخدمات','مراجعة كل مرة تنفيذ ولكل شخص مستقلاً؛ الاعتماد وحده ينشئ مستحقًا.',btn('تحديث القائمة','id="serviceFeesRefresh"','outline'))+
   `<div class="info-box"><div>النسبة من المحصل الفعلي. الثابت كامل لكل مرة منفذة ومفوتَرة ولو لم تُحصّل، ولا يتأثر بالخصم. المقترحات ليست رصيدًا مستحقًا قبل الاعتماد. طابق المنفذين المقترحين مع إثبات التنفيذ قبل اعتماد حصتهم المشتركة.</div></div>`+
   (queue.truncated||balances.truncated?'<div class="info-box warning" role="status">القائمة المعروضة غير مكتملة؛ حدّث بعد مراجعة البنود المعروضة.</div>':'')+
   section('مقترحات للمراجعة','راجع الخدمة والحالة وإثبات التنفيذ والتحصيل قبل اعتماد الحصة.',items.length?`<div class="pricing-fee-grid">${items.map((x,i)=>`<article class="pricing-fee-card"><div class="pricing-fee-heading"><strong>${esc(x.person_name)}</strong><b>${amount(x.amount_piasters)}</b></div><p>${esc(x.service_name)} · المرة ${esc(x.occurrence_no)}</p><small>${esc(x.case_no)} · ${esc(x.invoice_no)}</small><p class="pricing-fee-policy">${x.kind==='fixed'?'مبلغ ثابت كامل بعد التنفيذ والفاتورة، ولو لم تُحصّل؛ لا يتأثر بالخصم.':'نسبة من المحصل الفعلي؛ المقترح يتغير مع التحصيل والتصحيحات.'}</p><dl><div><dt>المحصل من الخدمة</dt><dd>${amount(x.collected_piasters)}</dd></div><div><dt>المعتمد سابقًا</dt><dd>${amount(x.previously_approved_piasters??0)}</dd></div></dl><div class="pricing-actions">${btn('اعتماد',`data-fee-decision="approve" data-fee-index="${i}"`,'primary')}${btn('رفض',`data-fee-decision="reject" data-fee-index="${i}"`,'secondary')}</div></article>`).join('')}</div>`:empty('لا توجد مقترحات حصص تنتظر المراجعة.'))+
   section('أرصدة المستحقات المعتمدة','أرصدة من القرارات المعتمدة بعد عكس أي قرارات مصححة.',table(['الشخص','المستحق المعتمد'],(balances.items||[]).map(x=>`<tr><td>${esc(x.person_name)}</td><td class="num">${amount(x.amount_piasters)}</td></tr>`).join('')))+
   section('سجل القرارات','تصحيح الاعتماد يكون بعكس مستقل مع السبب.',table(['الشخص والخدمة','الحالة / الفاتورة','المرة','المبلغ','القرار','السبب','التاريخ','تصحيح'],history.map(x=>`<tr><td class="pricing-wrap"><strong>${esc(x.person_name)}</strong><br>${esc(x.service_name)}</td><td>${esc(x.case_no)}<br>${esc(x.invoice_no)}</td><td>${esc(x.occurrence_no)}</td><td class="num">${amount(x.amount_piasters)}</td><td>${x.reversed?'معكوس':x.decision==='approved'?'معتمد':'مرفوض'}</td><td class="pricing-wrap">${esc(x.reason)}</td><td>${esc(x.decided_at)}</td><td>${x.decision==='approved'&&!x.reversed?btn('عكس الاعتماد',`data-fee-reverse="${x.id}"`,'outline'):'—'}</td></tr>`).join('')));
  $('#serviceFeesRefresh').addEventListener('click',()=>renderServiceFees().catch(e=>toast(e.message,true)));
  $$('[data-fee-decision]').forEach(b=>b.addEventListener('click',()=>{
   const x=items[Number(b.dataset.feeIndex)],decision=b.dataset.feeDecision;
   dialog(decision==='approve'?'اعتماد حصة خدمة':'رفض حصة خدمة',`${x.person_name} · ${x.service_name} · المرة ${x.occurrence_no} · ${amount(x.amount_piasters)}. اعتماد الحصة ينشئ مستحقًا ماليًا.`,
    input('سبب القرار','reason','','text','required minlength="8" maxlength="500"'),async ui=>{
     await billingMutation(`service-fee-${x.line_id}-${x.occurrence_no}-${x.rule_index}-${x.person_id}`,'/api/service-fees/decisions',{line_id:x.line_id,occurrence_no:x.occurrence_no,rule_index:x.rule_index,person_id:x.person_id,expected_amount_piasters:x.amount_piasters,calculation_hash:x.calculation_hash,decision,reason:data(ui).reason});
     toast(decision==='approve'?'اعتمدت حصة الخدمة':'رُفضت حصة الخدمة');await renderServiceFees();
    },null,decision==='approve'?'اعتماد الحصة':'تسجيل الرفض');
  }));
  $$('[data-fee-reverse]').forEach(b=>b.addEventListener('click',()=>dialog('عكس اعتماد حصة','يسجل العكس تصحيحًا مستقلاً ويخفض المستحق؛ يبقى القرار الأصلي في السجل.',input('سبب العكس','reason','','text','required minlength="8" maxlength="500"'),async ui=>{await billingMutation(`service-fee-reverse-${b.dataset.feeReverse}`,`/api/service-fees/decisions/${b.dataset.feeReverse}/reverse`,{reason:data(ui).reason});toast('تم عكس اعتماد الحصة');await renderServiceFees();},null,'تسجيل العكس')));
 }
 window.renderPricing=renderPricing;
 window.pricingOrderForCase=pricingOrderForCase;
 window.renderServiceFees=renderServiceFees;
})();
