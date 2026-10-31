"use strict";
/* G2T: Central consumables only. Deliberately no pharmacy, payments or auto patient invoices. */
(function(){
  const today=()=>new Date().toLocaleDateString('sv-SE');
  const requestId=()=>globalThis.crypto?.randomUUID?.()||('inventory_'+Date.now()+'_'+Math.random().toString(36).slice(2));
  const unitName={piece:'قطعة',box:'صندوق',pack:'عبوة',bottle:'زجاجة',meter:'متر'};
  const statusName={pending:'تحت المراجعة',approved:'معتمد',rejected:'مرفوض'};
  function field(id,label,input){return `<label class="inv-field">${label}${input}</label>`;}
  const input=(name,type='text',extra='')=>`<input name="${name}" type="${type}" ${extra} required>`;
  function options(rows,placeholder){return `<option value="">${placeholder}</option>`+rows.map(x=>`<option value="${Number(x.id)}">${esc(x.name)}</option>`).join('');}
  async function apply(endpoint,data,message){
    try{await post(endpoint,data);toast(message);await window.renderInventory();}
    catch(error){toast(error.message,true);}
  }
  function docTable(rows,type,canApprove,meId){
    if(!rows.length)return empty('لا توجد مستندات في هذا القسم.');
    return `<div class="table-wrap"><table class="data-table"><thead><tr><th>المستند</th><th>التاريخ</th><th>الحالة</th><th>القيمة</th><th>القرار</th></tr></thead><tbody>${rows.map(row=>{
      const ref=type==='receipts'?row.invoice_ref:row.evidence_ref;
      const date=type==='receipts'?row.received_on:row.used_on;
      const amount=type==='receipts'?row.total_piasters:row.cost_piasters;
      const controls=canApprove&&row.status==='pending'&&Number(row.created_by)!==Number(meId)?
        `<div class="inv-actions"><button class="btn btn-small btn-primary" data-inv-decision="${type}:${row.id}:approve">اعتماد</button><button class="btn btn-small btn-outline" data-inv-decision="${type}:${row.id}:reject">رفض</button></div>`:'—';
      return `<tr><td><strong>${esc(ref)}</strong><small class="inv-muted">رقم ${Number(row.id)}</small></td><td>${esc(date)}</td><td><span class="chip ${esc(row.status)}">${statusName[row.status]||esc(row.status)}</span></td><td class="num">${fmt(amount)}</td><td>${controls}</td></tr>`;
    }).join('')}</tbody></table></div>`;
  }
  window.renderInventory=async function renderInventory(){
    const root=$('#content');
    if(!root)return;
    root.innerHTML=head('إدارة الموارد','المستلزمات والمخزن المركزي','المخزون محسوب من المستندات المعتمدة فقط، وتكلفة الصرف تتبع FIFO.')+'<div class="loading-state" role="status">جاري تحميل سجل المخزون…</div>';
    let d,rec;
    try{
      d=await api('/api/inventory/overview');
      rec=await api('/api/inventory/reconciliation?period='+encodeURIComponent(state.month));
    }catch(error){errorView(error.message);return;}
    const isOwner=state.me.role==='owner';
    const canPrepare=isOwner||!!d.grants.can_prepare;
    const canApprove=isOwner||!!d.grants.can_approve;
    const items=d.items||[],vendors=d.vendors||[];
    const totalValue=items.reduce((sum,x)=>sum+Number(x.value_piasters||0),0);
    const totalUnits=items.reduce((sum,x)=>sum+Number(x.quantity_on_hand||0),0);
    const pending=(d.receipts||[]).filter(x=>x.status==='pending').length+(d.issues||[]).filter(x=>x.status==='pending').length;
    const units=[['piece','قطعة'],['box','صندوق'],['pack','عبوة'],['bottle','زجاجة'],['meter','متر']];
    root.innerHTML=head('المخازن والمشتريات','المخزن المركزي للمستلزمات','قيود مخزون وموردين وتكلفة تشغيل، ولا يحدث صرف من الخزنة تلقائيًا.',isOwner?`<button type="button" class="btn btn-secondary" id="invGrant">${ico('shield')} إدارة تفويضات المخزن</button>`:'')+
      `<div class="info-box warning" role="note">${ico('alert')}<div><strong>تجريبي — مستلزمات غير دوائية فقط.</strong> لا يشمل أدوية المرضى أو الصرف العلاجي أو مطابقة فواتير الموردين مع البنك أو ضريبة القيمة المضافة. التقرير لا يثبت قيمة مخزون افتتاحي تاريخي.</div></div>`+
      `<div class="inv-stats"><div><small>أصناف مسجلة</small><strong>${integer(items.length)}</strong></div><div><small>الكمية المتاحة</small><strong>${integer(totalUnits)}</strong></div><div><small>قيمة المخزون التجريبي</small><strong>${fmt(totalValue)} ج.م</strong></div><div><small>مستندات تنتظر الاعتماد</small><strong>${integer(pending)}</strong></div></div>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>الأرصدة حسب الصنف</h2><p>لا يدخل الرصيد إلا بعد اعتماد الاستلام، ولا ينقص إلا بعد اعتماد الصرف.</p></div>${isOwner?`<div class="inv-actions"><button id="invVendor" class="btn btn-small btn-outline">مورد جديد</button><button id="invItem" class="btn btn-small btn-primary">صنف جديد</button></div>`:''}</div>`+
      (items.length?table(['الكود','الصنف','الوحدة','الرصيد','القيمة'],items.map(x=>`<tr><td>${esc(x.code)}</td><td><strong>${esc(x.name)}</strong></td><td>${esc(unitName[x.unit]||x.unit)}</td><td class="num">${integer(x.quantity_on_hand)}</td><td class="num">${fmt(x.value_piasters)}</td></tr>`).join('')):empty('سجّل موردًا وصنفًا أولًا ثم أنشئ محضر توريد.'))+
      `</section>`+
      (canPrepare?`<div class="inv-grid"><section class="panel panel-pad"><h2 class="section-title">محضر استلام من مورد</h2><p class="section-subtitle">القيد المالي والكمية يترحلان فقط بعد اعتماد موظف آخر.</p><form id="invReceiptForm" class="inv-form">`+
        field('','المورد',`<select name="vendor_id" required>${options(vendors,'اختر المورد')}</select>`)+
        field('','تاريخ الاستلام',input('received_on','date',`value="${today()}"`))+
        field('','مرجع فاتورة المورد',input('invoice_ref','text','minlength="6" maxlength="90" placeholder="رقم فاتورة المورد"'))+
        field('','مرجع محضر استلام المخزن',input('evidence_ref','text','minlength="8" maxlength="180" placeholder="مرجع GRN موقع"'))+
        field('','الصنف',`<select name="item_id" required>${options(items,'اختر صنفًا')}</select>`)+
        field('','الكمية (عدد صحيح)',input('quantity','number','min="1" step="1" max="1000000"'))+
        field('','تكلفة الوحدة بالجنيه',input('unit_cost','number','min="0.01" step="0.01" placeholder="0.00"'))+
        field('','رقم التشغيلة (اختياري)',`<input name="batch_ref" maxlength="90" placeholder="مرجع التشغيلة">`)+
        field('','تاريخ الصلاحية (إن وجد)',`<input name="expiry_date" type="date">`)+
        `<button class="btn btn-primary" type="submit" ${!items.length||!vendors.length?'disabled':''}>إرسال محضر التوريد للمراجعة</button></form></section>`+
        `<section class="panel panel-pad"><h2 class="section-title">إذن صرف مستهلكات</h2><p class="section-subtitle">إثبات تكلفة المستلزمات على القسم أو الحالة، من غير إنشاء فاتورة للمريض.</p><form id="invIssueForm" class="inv-form">`+
        field('','تاريخ الاستخدام',input('used_on','date',`value="${today()}"`))+
        field('','قسم التكلفة',`<select name="department_id" required>${options(state.lookups.departments,'اختر القسم')}</select>`)+
        field('','مرجع إذن الصرف',input('evidence_ref','text','minlength="8" maxlength="180" placeholder="محضر صرف موقع"'))+
        field('','الصنف',`<select name="item_id" required>${options(items,'اختر صنفًا')}</select>`)+
        field('','الكمية',input('quantity','number','min="1" step="1" max="1000000"'))+
        field('','رقم ملف الحالة (اختياري)',`<input name="case_id" type="number" min="1" step="1" placeholder="يتم التحقق من صلاحية الحالة">`)+
        `<button class="btn btn-primary" type="submit" ${!items.length?'disabled':''}>إرسال إذن الصرف للمراجعة</button></form></section></div>`:'')+
      `<div class="inv-grid"><section class="panel inv-panel"><div class="panel-header"><div><h2>فواتير توريد الموردين</h2><p>تثبيت مخزون وموردين بعد مراجعة المستند</p></div></div>${docTable(d.receipts||[],'receipts',canApprove,state.me.id)}</section>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>أذون صرف المستلزمات</h2><p>تكاليف حالة أو قسم، وليس تحصيلًا نقديًا</p></div></div>${docTable(d.issues||[],'issues',canApprove,state.me.id)}</section></div>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>مطابقة مخزون المستلزمات مع الأستاذ</h2><p>حتى شهر ${esc(state.month)} · لا تشمل الرصيد التاريخي غير المُسجل في هذه الدورة</p></div><span class="chip ${rec.matched?'approved':'rejected'}">${rec.matched?'مطابقة مصدر المستندات ناجحة':'فروقات تحتاج مراجعة'}</span></div><div class="inv-recon"><span>رصيد سجل الأصناف: <strong>${fmt(rec.value_piasters)} جنيه</strong></span><span>رصيد القيود المرتبطة: <strong>${fmt(rec.inventory_gl_piasters)} جنيه</strong></span></div>${(rec.errors||[]).map(e=>`<div class="info-box warning" role="alert">${esc(e)}</div>`).join('')}</section>`;
    $('#invReceiptForm')?.addEventListener('submit',async event=>{
      event.preventDefault();const el=event.currentTarget, b=el.querySelector('button[type="submit"]');b.disabled=true;
      const f=Object.fromEntries(new FormData(el));
      const data={vendor_id:Number(f.vendor_id),received_on:f.received_on,invoice_ref:f.invoice_ref,evidence_ref:f.evidence_ref,
        request_id:requestId(),lines:[{item_id:Number(f.item_id),quantity:Number(f.quantity),unit_cost:f.unit_cost,
          batch_ref:f.batch_ref,expiry_date:f.expiry_date||null}]};
      await apply('/api/inventory/receipts',data,'تم إرسال محضر الاستلام للمراجعة؛ لم يُرحّل بعد');b.disabled=false;
    });
    $('#invIssueForm')?.addEventListener('submit',async event=>{
      event.preventDefault();const el=event.currentTarget,b=el.querySelector('button[type="submit"]');b.disabled=true;
      const f=Object.fromEntries(new FormData(el));
      const data={department_id:Number(f.department_id),case_id:f.case_id?Number(f.case_id):null,used_on:f.used_on,
        evidence_ref:f.evidence_ref,request_id:requestId(),lines:[{item_id:Number(f.item_id),quantity:Number(f.quantity)}]};
      await apply('/api/inventory/issues',data,'تم إرسال إذن الصرف للمراجعة؛ المخزون لم ينقص بعد');b.disabled=false;
    });
    $$('#content [data-inv-decision]').forEach(button=>button.addEventListener('click',async()=>{
      const [kind,id,decision]=button.dataset.invDecision.split(':');
      const fields=[{name:'note',label:'سبب الاعتماد أو الرفض (8 أحرف على الأقل)',required:true}];
      const data=await modal(decision==='approve'?'اعتماد مستند المخزن':'رفض مستند المخزن',
        'الاعتماد ينشئ قيدًا ماليًا ويمس كمية المخزون، ويُشترط أن تكون مراجعًا مختلفًا عن مقدم الطلب.',fields);
      if(!data)return;
      await apply(`/api/inventory/${kind}/${Number(id)}/decision`,{decision,note:data.note},'تم تسجيل قرار المراجعة');
    }));
    $('#invVendor')?.addEventListener('click',async()=>{
      const data=await modal('مورد جديد','كتالوج الموردين لا ينشئ مستحقًا ماليًا دون فاتورة معتمدة.',[
        {name:'code',label:'كود المورد',required:true},{name:'name',label:'اسم المورد',required:true}]);
      if(data)await apply('/api/inventory/vendors',data,'تمت إضافة المورد');
    });
    $('#invItem')?.addEventListener('click',async()=>{
      const data=await modal('مستلزم جديد','مستلزمات غير دوائية؛ لا تُستخدم هذه الشاشة لصرف الأدوية.',[
        {name:'code',label:'كود المستلزم',required:true},{name:'name',label:'اسم المستلزم',required:true},
        {name:'unit',type:'select',label:'وحدة القياس',options:units}]);
      if(data)await apply('/api/inventory/items',data,'تمت إضافة الصنف');
    });
    $('#invGrant')?.addEventListener('click',async()=>{
      try{
        const users=(await api('/api/users')).filter(x=>['clerk','reviewer'].includes(x.role)&&x.active);
        if(!users.length){toast('لا توجد حسابات موظفين قابلة للتفويض',true);return;}
        const data=await modal('تفويض المخزن المركزي','صلاحية إعداد المحضر مختلفة عن صلاحية اعتماده؛ لا يمكن لأي مستخدم اعتماد مستنده.',[
          {name:'user_id',type:'select',label:'الموظف',options:users.map(x=>[x.id,x.username+' — '+(roleLabels[x.role]||x.role)])},
          {name:'can_prepare',type:'select',label:'إعداد الطلبات',options:[['false','لا'],['true','نعم']]},
          {name:'can_approve',type:'select',label:'اعتماد الطلبات',options:[['false','لا'],['true','نعم']]},
          {name:'reason',label:'سبب منح أو سحب التفويض',required:true}]);
        if(data)await apply('/api/inventory/access',{user_id:Number(data.user_id),can_prepare:data.can_prepare==='true',
          can_approve:data.can_approve==='true',reason:data.reason},'تم تعديل تفويض المخزن');
      }catch(error){toast(error.message,true)}
    });
  };
})();
