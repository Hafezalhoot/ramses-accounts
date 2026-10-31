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
      const date=type==='receipts'?row.received_on:type==='returns'?row.returned_on:row.used_on;
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
    const totalQuarantine=items.reduce((sum,x)=>sum+Number(x.quarantined_quantity||0),0);
    const totalAvailable=items.reduce((sum,x)=>sum+Number(x.available_quantity||0),0);
    const pending=(d.receipts||[]).filter(x=>x.status==='pending').length+(d.issues||[]).filter(x=>x.status==='pending').length+(d.returns||[]).filter(x=>x.status==='pending').length;
    const units=[['piece','قطعة'],['box','صندوق'],['pack','عبوة'],['bottle','زجاجة'],['meter','متر']];
    root.innerHTML=head('المخازن والمشتريات','المخزن المركزي للمستلزمات','قيود مخزون وموردين وتكلفة تشغيل، ولا يحدث صرف من الخزنة تلقائيًا.',isOwner?`<button type="button" class="btn btn-secondary" id="invGrant">${ico('shield')} إدارة تفويضات المخزن</button>`:'')+
      `<div class="info-box warning" role="note">${ico('alert')}<div><strong>تجريبي — مستلزمات غير دوائية فقط.</strong> لا يشمل أدوية المرضى أو الصرف العلاجي أو مطابقة فواتير الموردين مع البنك أو ضريبة القيمة المضافة. التقرير لا يثبت قيمة مخزون افتتاحي تاريخي.</div></div>`+
      `<div class="inv-stats"><div><small>أصناف مسجلة</small><strong>${integer(items.length)}</strong></div><div><small>المملوك فعليًا (يشمل الحجر)</small><strong>${integer(totalUnits)}</strong></div><div><small>الحجر الطبي</small><strong>${integer(totalQuarantine)}</strong></div><div><small>المتاح بعد الحجر*</small><strong>${integer(totalAvailable)}</strong></div><div><small>قيمة المخزون (تشمل الحجر)</small><strong>${fmt(totalValue)} ج.م</strong></div></div>`+
      `<div class="info-box warning" role="note">الموافقة المحاسبية على المرتجع لا تعني صلاحية إعادة الاستخدام. الكمية المحجوزة طبيًا لا تدخل FIFO إلا بقرار طبي مستقل، والرصيد غير المحجوز لا يضمن الصلاحية أو سلامة العبوة؛ يتم فحصهما عند الصرف. لا يجوز استخدام هذه الدورة مع مرضى حقيقيين قبل اعتماد مكافحة العدوى.</div>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>الأرصدة حسب الصنف</h2><p>المملوك يشمل المستلزمات المرتجعة داخل الحجر؛ قيد المرتجع المالي مستقل عن الإفراج الطبي.</p></div>${isOwner?`<div class="inv-actions"><button id="invVendor" class="btn btn-small btn-outline">مورد جديد</button><button id="invItem" class="btn btn-small btn-primary">صنف جديد</button></div>`:''}</div>`+
      (items.length?table(['الكود','الصنف','الوحدة','المملوك','بالحجر','غير محجوز*','القيمة'],items.map(x=>`<tr><td>${esc(x.code)}</td><td><strong>${esc(x.name)}</strong></td><td>${esc(unitName[x.unit]||x.unit)}</td><td class="num">${integer(x.quantity_on_hand)}</td><td class="num">${integer(x.quarantined_quantity)}</td><td class="num">${integer(x.available_quantity)}</td><td class="num">${fmt(x.value_piasters)}</td></tr>`).join('')):empty('سجّل موردًا وصنفًا أولًا ثم أنشئ محضر توريد.'))+
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
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>مرتجعات مستلزمات</h2><p>الاعتماد المالي يعيد الملكية إلى المخزون المحجوز، ولا يجعل المرتجع متاحًا حتى يجيزه طبيب مفوض مستقل.</p></div></div>${docTable(d.returns||[],'returns',canApprove,state.me.id)}</section>`+
      (canPrepare?`<section class="panel panel-pad"><h2 class="section-title">إرجاع مستلزمات غير مستخدمة</h2>`+
      `<p class="section-subtitle">إرجاع فعلي لإذن معتمد. كل كمية تعتمد ماليًا تدخل الحجر الطبي تلقائيًا، ولا يُسمح بالصرف منها حتى فحص مستقل.</p>`+
      `<form id="invReturnLookupForm" class="inv-form">`+
        field('','رقم إذن الصرف الأصلي',`<input name="issue_id" type="number" min="1" step="1" required aria-label="رقم إذن الصرف الأصلي">`)+
        `<button type="submit" class="btn btn-secondary">عرض الدفعات القابلة للإرجاع</button></form>`+
      `<div id="invReturnSource" role="status" aria-live="polite"></div></section>`:'')+
      `<section class="panel panel-pad"><h2 class="section-title">تكلفة مستهلكات الحالة</h2>`+
      `<p class="section-subtitle">استعلام مقيد بتفويض المخزن ونقطة تحصيل الحالة. يعرض أذون الصرف المعتمدة فقط؛ لا يشمل الأدوية أو أتعاب الأطباء أو ربح الحالة.</p>`+
      `<form id="invCaseCostForm" class="inv-form">`+
      field('','رقم ملف الحالة',`<input name="case_id" type="number" min="1" step="1" required aria-label="رقم ملف الحالة">`)+
      `<button type="submit" class="btn btn-primary">عرض المستهلكات المعتمدة</button></form>`+
      `<div id="invCaseCostResult" role="status" aria-live="polite"></div></section>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>مطابقة مخزون المستلزمات مع الأستاذ</h2><p>حتى شهر ${esc(state.month)} · لا تشمل الرصيد التاريخي غير المُسجل في هذه الدورة</p></div><span class="chip ${rec.matched?'approved':'rejected'}">${rec.matched?'مطابقة مصدر المستندات ناجحة':'فروقات تحتاج مراجعة'}</span></div><div class="inv-recon"><span>رصيد سجل الأصناف: <strong>${fmt(rec.value_piasters)} جنيه</strong></span><span>رصيد القيود المرتبطة: <strong>${fmt(rec.inventory_gl_piasters)} جنيه</strong></span></div>${(rec.errors||[]).map(e=>`<div class="info-box warning" role="alert">${esc(e)}</div>`).join('')}</section>`;
    $('#invCaseCostForm')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const form=event.currentTarget, button=form.querySelector('button[type="submit"]');
      const result=$('#invCaseCostResult');
      const caseId=Number(form.elements.case_id.value);
      if(!Number.isSafeInteger(caseId)||caseId<1){result.textContent='يرجى إدخال رقم حالة صحيح';return;}
      result.textContent='جاري قراءة أذون الصرف المعتمدة…';
      button.disabled=true;
      try{
        const report=await api('/api/inventory/cases/'+caseId+'/cost');
        if(Number(form.elements.case_id.value)!==caseId)return;
        const rows=report.lines||[];
        result.innerHTML=`<div class="inv-stats"><div><small>تكلفة المستلزمات المعتمدة فقط</small><strong>${fmt(report.total_cost_piasters)} ج.م</strong></div>`+
          `<div><small>تكلفة مرتجعات معتمدة</small><strong>${fmt(report.total_returned_piasters||0)} ج.م</strong></div>`+
          `<div><small>أذون معتمدة</small><strong>${integer(report.approved_issue_count)}</strong></div>`+
          `<div><small>أذون تنتظر الاعتماد، غير محتسبة</small><strong>${integer(report.pending_issue_count)}</strong></div></div>`+
          (rows.length?table(['إذن الصرف','تاريخ الاستخدام','المستلزم','صافي الكمية','المرتجع','صافي التكلفة'],rows.map(x=>
            `<tr><td>${integer(x.issue_id)}</td><td>${esc(x.used_on)}</td><td>${esc(x.item_code)} — ${esc(x.item_name)}</td><td class="num">${integer(x.net_quantity??x.quantity)}</td><td class="num">${integer(x.returned_quantity||0)}</td><td class="num">${fmt(x.cost_piasters)}</td></tr>`).join('')):empty('لا توجد أذون صرف معتمدة مربوطة بهذه الحالة.'))+
          `<p class="section-subtitle">هذا تقرير تكلفة جزئي من مخزون المستلزمات المركزي؛ ليس فاتورة للمريض ولا هامش ربح.</p>`;
      }catch(error){result.innerHTML=`<p role="alert">${esc(error.message)}</p>`;}
      finally{button.disabled=false;}
    });
    $('#invReturnLookupForm')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const form=event.currentTarget, issueId=Number(form.elements.issue_id.value);
      const source=$('#invReturnSource'), button=form.querySelector('button[type="submit"]');
      source.textContent='جاري التحقق من صلاحية إذن الصرف ودفعاته…';
      if(!Number.isSafeInteger(issueId)||issueId<1){source.textContent='ادخل رقم إذن صرف صحيح';return;}
      button.disabled=true;
      try{
        const info=await api('/api/inventory/issues/'+issueId+'/returnable');
        if(Number(form.elements.issue_id.value)!==issueId)return;
        const lots=(info.allocations||[]).filter(a=>Number(a.returnable_quantity)>0);
        if(!lots.length){source.textContent='لا توجد دفعات قابلة للإرجاع لهذا الإذن';return;}
        source.innerHTML=`<p class="section-subtitle">إذن رقم ${integer(issueId)}؛ اختر الدفعة الأصلية والكمية الفعلية غير المستخدمة.</p>`+
          `<form id="invReturnForm" class="inv-form">`+
          field('','الدفعة الأصلية',`<select name="issue_allocation_id" required>${lots.map(a=>
            `<option value="${Number(a.issue_allocation_id)}">${esc(a.item_code)} — ${esc(a.item_name)} | متاح للرد ${integer(a.returnable_quantity)} | ${fmt(a.unit_cost_piasters)} ج.م</option>`).join('')}</select>`)+
          field('','الكمية المرتجعة',`<input name="quantity" type="number" min="1" step="1" max="${Number(lots[0].returnable_quantity)}" required>`)+
          field('','تاريخ المرتجع',`<input name="returned_on" type="date" value="${today()}" required>`)+
          field('','محضر الاستلام العكسي',`<input name="evidence_ref" minlength="8" maxlength="180" required placeholder="مرجع مستند مرتجع موقع">`)+
          `<button type="submit" class="btn btn-primary">إرسال المرتجع للمراجعة المستقلة</button></form>`;
        const ret=source.querySelector('#invReturnForm');
        ret.elements.issue_allocation_id.addEventListener('change',()=>{
          const lot=lots.find(a=>Number(a.issue_allocation_id)===Number(ret.elements.issue_allocation_id.value));
          if(lot)ret.elements.quantity.max=Number(lot.returnable_quantity);
        });
        ret.addEventListener('submit',async submit=>{
          submit.preventDefault();const button=ret.querySelector('button[type="submit"]');
          button.disabled=true;
          const data={issue_id:issueId,returned_on:ret.elements.returned_on.value,
            evidence_ref:ret.elements.evidence_ref.value,request_id:requestId(),
            lines:[{issue_allocation_id:Number(ret.elements.issue_allocation_id.value),
                    quantity:Number(ret.elements.quantity.value)}]};
          await apply('/api/inventory/returns',data,'تم إرسال طلب المرتجع ماليًا؛ إذا اعتمد فسيبقى في الحجر حتى فحص طبي مستقل');
          button.disabled=false;
        });
      }catch(error){source.innerHTML=`<p role="alert">${esc(error.message)}</p>`;}
      finally{button.disabled=false;}
    });
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
