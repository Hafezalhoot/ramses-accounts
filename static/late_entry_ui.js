"use strict";
/* G2E: independently approved shortage recovery; G2D cash-only envelopes and mixed envelopes stay separate from a new receipt. */
const lateReasons={outage:'توقف النظام',absence:'غياب الموظف',staff_unavailable:'عدم توفر موظف مؤهل',other:'تعذر التسجيل لسبب آخر'};
const lateLocations={drawer:'درج الكاشير',envelope:'ظرف نقدية',main_safe:'الخزنة الرئيسية',other:'مكان حفظ آخر'};
const lateStatuses={draft:'مسودة',submitted:'بانتظار المطابقة',needs_evidence:'استكمال مستندات',triaged:'تحت المراجعة',resolved:'مستندات مرتبطة ومعتمدة رقابيًا'};
const lateKinds={patient_receipt:'إيصال مريض',expense:'مصروف نقدي',transfer:'تحويل إلى خزنة أخرى'};
const lateNewKey=()=>globalThis.crypto?.randomUUID?.()||('late_'+Date.now().toString(36)+Math.random().toString(36).slice(2,18));
async function proposeLateShortage(id,done){
 const form=await modal('إثبات استلام نقدية لعجز ظرف قديم',
   'أدخل النقدية التي استلمتها فعليًا في وردية الخزنة الرئيسية المفتوحة الآن. الحفظ مسودة فقط؛ لا يزيد الرصيد إلا بعد عد مستقل وموافقة مفوضة.',[
   {name:'receipt_ref',label:'رقم إيصال الاستلام الفعلي (غير مستخدم سابقًا)',required:true},
   {name:'source_type',type:'select',label:'مصدر النقدية',options:[['employee_deposit','إيداع طوعي من موظف — دون افتراض مديونية'],['recovered_cash','نقدية عُثر عليها واستُلمت فعليًا']]},
   {name:'payer_name',label:'اسم الشخص الذي أودع المال — عند إيداع الموظف فقط'},
   {name:'amount',label:'المبلغ النقدي المعدود بالجنيه',required:true},
   {name:'note',type:'textarea',label:'إثبات الاستلام الفعلي وسبب التسوية (24 حرفًا على الأقل)',required:true}
 ]);
 if(!form)return;
 try{const result=await post(`/api/late-entries/${id}/shortage-recoveries`,{...form,request_id:lateNewKey()});
   toast('حُفظ طلب استلام '+fmt(result.amount_piasters)+' جنيه، ولم تُحرك الخزنة قبل الاعتماد');await done();
 }catch(e){toast(e.message,true)}
}
async function proposeLateOverage(id,done){
 const d=await api('/api/late-entries/'+id), proofs=d.evidence||[];
 if(!proofs.length){toast('ارفع مستند ملكية الزيادة أولًا من صفحة الواقعة',true);return}
 const form=await modal('طلب رد زيادة عهدة لصاحب حق',
   'الزيادة مسجلة بالفعل كالتزام وليست إيرادًا. هذا الطلب لا يصرف نقدية؛ يلزم إثبات المطالبة ثم إيصال تسلم مستقل واعتماد محاسب مفوّض.',[
    {name:'claim_ref',label:'رقم مطالبة مستقل غير مستخدم',required:true},
    {name:'claimant_name',label:'اسم صاحب الحق الذي سيستلم المال',required:true},
    {name:'evidence_id',type:'select',label:'مرفق إثبات حق المطالبة',required:true,
      options:proofs.map(x=>[String(x.id),`#${x.id} — ${x.filename}`])},
    {name:'amount',label:'المبلغ المطلوب رده بالجنيه',required:true},
    {name:'note',type:'textarea',label:'كيف ثبتت ملكية النقدية؟ (32 حرفًا على الأقل)',required:true}
   ]);
 if(!form)return;
 try{const out=await post(`/api/late-entries/${id}/overage-refunds`,{
     ...form,evidence_id:Number(form.evidence_id),request_id:lateNewKey()});
   toast('تم حفظ مطالبة '+fmt(out.amount_piasters)+' جنيه دون صرف من الخزنة');await done();
 }catch(e){toast(e.message,true)}
}
async function renderLateEntries(){
  const [result,openShortages,openOverages]=await Promise.all([
    api('/api/late-entries'),api('/api/late-entries/shortage-open'),api('/api/late-entries/overage-open')]);
  const records=result.items||[],shortages=openShortages.items||[],overages=openOverages.items||[];
  const [points,coverage]=await Promise.all([
    api('/api/billing/config').then(d=>d.points||[]),
    api('/api/shifts/coverage?month='+encodeURIComponent(state.shiftMonth)).catch(()=>({items:[]}))
  ]);
  const date=new Date().toLocaleDateString('sv-SE');
  const allowed=state.me.role!=='reviewer';
  const shifts=new Map();(coverage.items||[]).forEach(i=>{
    if(!shifts.has(i.point_id))shifts.set(i.point_id,new Map());
    shifts.get(i.point_id).set(i.shift,i.shift_name);
  });
  const availablePoints=points.filter(p=>p.fund_id);
  const historicalOptions=[...new Set([...Array.from(shifts.values()).flatMap(m=>[...m.keys()]),'treasury','night','morning','evening'])];
  $('#content').innerHTML=head('حالات الطوارئ والاستدراك','سجل المعاملات التي لم تدخل السيستم',
   'وثّق واقعة غياب الموظف أو توقف الكمبيوتر والورق والأظرف، ثم اربطها بالمستندات الإلكترونية الأصلية. لا يسجل النظام نقودًا جديدة من هذا السجل.',
   '<button class="btn btn-secondary" data-go="calendar">تقويم الورديات</button>')+
   `<div class="info-box warning" role="note">${ico('alert')}<div><b>فصل العهدة عن الإيراد:</b> صورة الظرف والمبلغ المكتوب على الورقة لا يُنشئان قبضًا أو مصروفًا. لا يجوز اعتماد الاستدراك المالي إلا بعد تسجيل العمليات الإلكترونية الصحيحة وربطها.</div></div>`+
   (allowed?`<section class="panel panel-pad"><h2>تسجيل واقعة استدراك</h2><form id="lateIncidentForm" class="financial-correction-form">
    <label>نقطة التحصيل<select name="point_id" required>${availablePoints.map(p=>opt(p.id,p.name)).join('')}</select></label>
    <label>تاريخ الوردية الأصلي<input type="date" name="business_date" max="${date}" value="${date}" required></label>
    <label>كود الوردية من التقويم<input name="shift_code" list="lateSlotHints" maxlength="32" required placeholder="night أو treasury"><datalist id="lateSlotHints">${historicalOptions.map(x=>`<option value="${esc(x)}">${esc(shifts.get(availablePoints[0]?.id)?.get(x)||x)}</option>`).join('')}</datalist></label>
    <label>سبب الاستدراك<select name="incident_reason">${Object.entries(lateReasons).map(([k,v])=>opt(k,v)).join('')}</select></label>
    <label>الموظف/المسؤول الذي احتفظ بالنقدية<input name="custodian_name" minlength="3" maxlength="150" required placeholder="الاسم الحقيقي للمستلم أو الحافظ"></label>
    <label>مكان النقدية<select name="cash_location">${Object.entries(lateLocations).map(([k,v])=>opt(k,v)).join('')}</select></label>
    <label>المبلغ المعدود في الظرف/الدرج (إن توفر)<input name="counted_cash" type="number" min="0" step="0.01" placeholder="اتركه فارغًا إذا لم يتم الجرد"></label>
    <label>مرجع الكشف الورقي (اختياري)<input name="source_register_ref" maxlength="120"></label>
    <label class="full">شرح سبب تأخر التسجيل ومكان حفظ المستندات<textarea name="note" rows="3" minlength="16" maxlength="1500" required></textarea></label>
    <button type="submit" class="btn btn-primary">حفظ الواقعة كمسودة دون ترحيل مالي</button>
    </form></section>`:'')+
   `<section class="panel panel-pad"><div class="panel-header"><div><h2>عجز الأظرف القديمة — استلام نقدية جديدة فقط</h2>
       <p>رصيد العجز بعد التحقيق والسداد الفعلي. لا تعرض هذه القائمة تفاصيل أو أسماء المرضى.</p></div></div>
     ${shortages.length?table(['تاريخ الواقعة','المرجع','العجز الأصلي','المسترد','المتبقي','الإجراء'],shortages.map(r=>`<tr>
       <td>${esc(r.business_date)}<div class="tiny">${esc(r.point_name)}</div></td>
       <td>${esc(r.source_register_ref)}</td>
       <td class="num">${fmt(r.original_shortage_piasters)}</td>
       <td class="num">${fmt(r.recovered_piasters)}</td>
       <td class="num"><strong>${fmt(r.outstanding_piasters)}</strong></td>
       <td>${r.outstanding_piasters>0&&['owner','clerk'].includes(state.me.role)?`<button type="button" class="btn btn-primary btn-small" data-late-shortage-quick="${r.incident_id}">إثبات استلام نقدية</button>`:''}
       ${['owner','reviewer'].includes(state.me.role)?`<button type="button" class="btn btn-secondary btn-small" data-late-open="${r.incident_id}">تفاصيل المراجعة</button>`:''}</td>
      </tr>`).join('')):'<p class="tiny">لا توجد حالات عجز ظروف مختلطة مسجلة حاليًا.</p>'}
     </section>`+
   `<section class="panel panel-pad"><div class="panel-header"><div><h2>زيادات الأظرف تحت التحقيق — حقوق أصحابها</h2>
       <p>رصيد مثبت بحساب الالتزامات 2190، ولا يصبح إيرادًا للمستشفى. لا يظهر اسم صاحب المطالبة في القائمة العامة.</p></div></div>
     ${overages.length?table(['تاريخ الواقعة','مرجع الظرف','الزيادة الأصلية','المدفوع لأصحاب الحق','المتبقي','الإجراء'],overages.map(r=>`<tr>
       <td>${esc(r.business_date)}<div class="tiny">${esc(r.point_name)}</div></td>
       <td>${esc(r.source_register_ref)}</td>
       <td class="num">${fmt(r.original_overage_piasters)}</td>
       <td class="num">${fmt(r.refunded_piasters)}</td>
       <td class="num"><strong>${fmt(r.outstanding_piasters)}</strong></td>
       <td>${['owner','clerk'].includes(state.me.role)?`<button type="button" class="btn btn-primary btn-small" data-late-overage-quick="${r.incident_id}">طلب رد مستند</button>`:''}
       <button type="button" class="btn btn-secondary btn-small" data-late-open="${r.incident_id}">التفاصيل</button></td>
      </tr>`).join('')):'<p class="tiny">لا توجد زيادات ظروف مفتوحة للمراجعة في الوقت الحالي.</p>'}
   </section>`+
   `<section class="panel panel-pad"><div class="panel-header"><div><h2>الوقائع السابقة</h2><p>حالة كل وردية وتقدم مطابقة الأوراق بالمستندات الإلكترونية</p></div><span class="chip archive">${integer(records.length)} واقعة</span></div>`+
   table(['التاريخ / النقطة','الوردية','السبب والحيازة','المستندات المرتبطة','الحالة','تفاصيل'],records.map(i=>`<tr>
    <td><b>${esc(i.business_date)}</b><div class="tiny">${esc(i.point_name)}</div></td><td>${esc(i.shift_code)}</td>
    <td>${esc(lateReasons[i.incident_reason]||i.incident_reason)}<div class="tiny">${esc(lateLocations[i.cash_location])} — ${esc(i.custodian_name)}</div></td>
    <td>${integer(i.linked_count)} / ${integer(i.doc_count)}</td>
    <td><span class="chip ${i.status==='resolved'?'approved':'pending'}">${esc(i.status==='resolved'&&i.mixed_variance_piasters?'تمت التسوية بفرق معتمد':lateStatuses[i.status]||i.status)}</span></td>
    <td><button class="btn btn-secondary btn-small" data-late-open="${i.id}">فتح</button></td></tr>`).join(''))+'</section>';
  const form=$('#lateIncidentForm');if(form){
    form.addEventListener('input',()=>delete form.dataset.requestKey);
    form.onsubmit=async ev=>{ev.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
      try{const x=Object.fromEntries(new FormData(form));const request_key=form.dataset.requestKey||(form.dataset.requestKey=lateNewKey());
        const r=await post('/api/late-entries',{...x,point_id:Number(x.point_id),counted_cash:x.counted_cash||null,request_key});
        delete form.dataset.requestKey;toast('تم حفظ الواقعة دون تغيير رصيد الخزنة');await openLateEntry(r.id);
      }catch(e){toast(e.message,true)}finally{button.disabled=false}
    };
  }
  $$('[data-late-shortage-quick]').forEach(btn=>btn.onclick=()=>proposeLateShortage(Number(btn.dataset.lateShortageQuick),renderLateEntries));
  $$('[data-late-overage-quick]').forEach(btn=>btn.onclick=()=>proposeLateOverage(Number(btn.dataset.lateOverageQuick),renderLateEntries));
  $$('[data-late-open]').forEach(btn=>btn.onclick=()=>openLateEntry(Number(btn.dataset.lateOpen)));
}
async function openLateEntry(id){
 const d=await api('/api/late-entries/'+id),i=d.incident;
 state.lateIncidentOpenId=id;
 const canAdd=['draft','needs_evidence'].includes(i.status)&&['owner','clerk'].includes(state.me.role);
 const canReview=['owner','reviewer'].includes(state.me.role)&&i.opened_by!==state.me.id;
 const mayRecover=i.status==='triaged'&&['owner','clerk'].includes(state.me.role)&&i.reviewed_by!==state.me.id;
 const recovered=d.recovered_cases||[];
 const linkedDocuments=new Set(recovered.map(x=>x.paper_document_id));
 const expenseDocs=d.documents.filter(x=>x.kind==='expense'&&!x.linked_id&&!x.mixed_clearance_id);
 const mixedCandidate=canReview&&i.status==='triaged'&&!d.mixed_clearance&&!d.cash_allocations.length&&
   d.point_kind==='internal'&&expenseDocs.length>0&&d.documents.every(x=>x.method==='cash'&&
   ['patient_receipt','expense'].includes(x.kind)&&!x.linked_id&&!x.cash_clearance_id);
 const recoveryRecords=d.mixed_shortage_recovery_requests||[];
 const overageRecords=d.mixed_overage_refund_requests||[],
       overageDue=Number(d.overage_outstanding_piasters||0),
       overageTotal=Number(d.overage_total_piasters||0);
 const canAddOverageEvidence=overageTotal>0&&['owner','reviewer'].includes(state.me.role);
 const recoveryDue=Number(d.shortage_outstanding_piasters||0),
       recoveryTotal=Number(d.shortage_total_piasters||0);
 const patientDocs=d.documents.filter(x=>x.kind==='patient_receipt');
 const gross=patientDocs.reduce((a,x)=>a+Number(x.amount_piasters),0),
       spent=expenseDocs.reduce((a,x)=>a+Number(x.amount_piasters),0),
       expectedNet=gross-spent,
       variance=i.counted_cash_piasters===null?null:Number(i.counted_cash_piasters)-expectedNet;

 $('#content').innerHTML=head('سجل العهدة والورديات','استدراك وردية #'+id,
  i.business_date+' · '+i.shift_code+' · '+(lateStatuses[i.status]||i.status),'<button class="btn btn-secondary" data-go="lateEntries">رجوع للسجل</button>')+
  `<div class="info-box">${ico('shield')}<div><b>حماية النقدية:</b> الفاتورة القديمة تصدر في فترة مفتوحة. إذا كان مبلغ الظرف مثبتًا بالفعل في الخزنة الرئيسية كسند «نقدية غير مخصصة»، يمكن للمراجع تخصيصه للفاتورة دون قبض ثانٍ. لا تُنشئ صورة الظرف رصيدًا، ولا ترحيل مالي تلقائيًا من الورق.</div></div>`+
  `<section class="panel panel-pad"><h2>العهدة والإثباتات</h2><p>الحافظ: <b>${esc(i.custodian_name)}</b> — ${esc(lateLocations[i.cash_location])}</p><p>المبلغ المعدود: <b>${i.counted_cash_piasters===null?'لم يُحدَّد':fmt(i.counted_cash_piasters)+' جنيه'}</b></p><p>${esc(i.note)}</p>
   <h3>المرفقات</h3><div class="row-actions">${d.evidence.map(x=>`<button type="button" class="btn btn-outline btn-small" data-late-proof="${x.id}">${esc(x.filename)}</button>`).join('')||'<span class="tiny">لا توجد صور حتى الآن</span>'}</div>
   ${canAdd||canAddOverageEvidence?'<label>رفع مستند إثبات (PNG أو JPG أو PDF حتى 6 MB)<input type="file" id="lateEvidenceFile" accept="image/jpeg,image/png,application/pdf"></label><button class="btn btn-small btn-secondary" id="lateUploadEvidence" type="button">رفع مرفق إضافي غير قابل للحذف</button>':''}</section>`+
  `<section class="panel panel-pad"><h2>العمليات المذكورة في الورقة</h2>${table(['مرجع الورق','النوع','المبلغ','التسجيل الإلكتروني','الإجراء'],d.documents.map(x=>`<tr>
    <td>${esc(x.paper_ref)}</td><td>${esc(lateKinds[x.kind]||x.kind)}</td><td class="num">${fmt(x.amount_piasters)}</td>
    <td>${x.mixed_clearance_id?'<span class="chip approved">تمت تسوية الظرف المختلط</span>':x.cash_clearance_id?'<span class="chip approved">تمت تسوية النقدية من سند مُرحّل</span>':x.linked_id?'<span class="chip approved">مرتبط بـ'+esc(x.linked_kind)+' #'+integer(x.linked_id)+'</span>':'<span class="chip pending">غير مرتبط</span>'}</td>
    <td><div class="row-actions">${!x.linked_id&&!x.cash_clearance_id&&!x.mixed_clearance_id&&canReview&&['submitted','triaged'].includes(i.status)?`<button class="btn btn-small btn-secondary" data-late-link="${x.id}" data-kind="${x.kind}">ربط بمستند إلكتروني</button>`:''}${mayRecover&&x.kind==='patient_receipt'&&!x.linked_id&&!linkedDocuments.has(x.id)?`<button class="btn btn-small btn-primary" data-late-recover="${x.id}">تسجيل حالة مريض قديمة</button>`:''}${canReview&&i.status==='triaged'&&x.kind==='patient_receipt'&&x.method==='cash'&&!x.linked_id&&!x.cash_clearance_id&&!x.mixed_clearance_id&&!expenseDocs.length&&recovered.some(r=>r.paper_document_id===x.id&&r.issued_invoice_id)?`<button class="btn btn-primary btn-small" data-late-clear="${x.id}" data-invoice-id="${recovered.find(r=>r.paper_document_id===x.id).issued_invoice_id}">تسوية من النقدية المثبتة</button>`:''}${linkedDocuments.has(x.id)?'<span class="chip archive">تم تسجيل ملف الحالة</span>':''}</div></td></tr>`).join(''))}
   ${canAdd?'<button class="btn btn-primary btn-small" id="lateAddDocument">إضافة مستند من الورق كمرجع للمطابقة</button>':''}
   </section>`+
  `<section class="panel panel-pad"><h2>الحالات الطبية المسجلة من هذه الواقعة</h2>
   ${recovered.length?recovered.map(x=>`<div class="billing-draft-row"><div><strong>${esc(x.case_no)}</strong>
     <div class="tiny">تاريخ الخدمة ${esc(x.original_business_date)} · ${esc(x.issued_invoice_no||'فاتورة لم تُصدر بعد')}</div></div>
     <button class="btn btn-secondary btn-small" data-late-case="${x.case_id}">فتح الحالة الإلكترونية</button></div>`).join(''):
     '<p class="tiny">لم تُسجّل حالات جديدة من هذه الواقعة بعد. لا تعتبر أوراقها فواتير أو قبضًا.</p>'}
   <div class="info-box warning">${ico('alert')}<div>إذا لم تُسجّل النقدية في الخزنة بعد، يجب أولًا استلامها وعدها فعليًا في وردية حالية، ثم تسجيل سند «نقدية غير مخصصة» معتمد برقم الظرف؛ لا تعتمد المبلغ المكتوب على الورق وحده.</div></div>
   ${d.cash_allocations?.length?'<h3>تسويات النقدية التاريخية</h3>'+table(['سند الخزنة','الفاتورة','المبلغ','رقم القيد'],d.cash_allocations.map(a=>`<tr><td>${esc(a.voucher_no)}</td><td>#${integer(a.invoice_id)}</td><td class="num">${fmt(a.amount_piasters)}</td><td>#${integer(a.journal_id)}</td></tr>`).join('')):''}${mixedCandidate?`<div class="info-box warning"><div><b>ظرف مختلط (حساب توضيحي):</b>
    إيصالات المرضى ${fmt(gross)} ج، المصروفات ${fmt(spent)} ج، المتوقع في الظرف ${fmt(expectedNet)} ج،
    المعدود ${i.counted_cash_piasters===null?'غير محدد':fmt(i.counted_cash_piasters)+' ج'}،
    الفرق ${variance===null?'غير محدد':fmt(variance)+' ج'}.
    لا تعني هذه الحسابات إثبات قبض أو مصروف؛ المراجع وحده يطلب التسوية.</div></div>
    <button class="btn btn-primary btn-small" data-late-mixed="${id}">مطابقة وتسوية الظرف المختلط</button>`:''}
   ${d.mixed_clearance?`<div class="info-box"><div><b>تسوية ظرف مختلط معتمدة:</b>
     ذمم مرضى ${fmt(d.mixed_clearance.gross_receipts_piasters)} ج، مصروفات تاريخية ${fmt(d.mixed_clearance.expense_piasters)} ج،
     نقدية مُثبتة سابقًا ${fmt(d.mixed_clearance.actual_cash_piasters)} ج،
     ${d.mixed_clearance.variance_piasters?'فرق عهدة معتمد استثنائيًا '+fmt(d.mixed_clearance.variance_piasters)+' ج':'مطابقة كاملة بلا فرق'}.
     قيد #${integer(d.mixed_clearance.journal_id)} — لا توجد نقدية جديدة.</div></div>`:''}
   ${recoveryTotal?`<div class="info-box" role="status"><div><b>متابعة عجز الظرف:</b>
      الأصل ${fmt(recoveryTotal)} ج · النقدية المستردة والمعتمدة ${fmt(d.shortage_recovered_piasters||0)} ج ·
      المتبقي تحت التسوية <b>${fmt(recoveryDue)} ج</b>.
      لا يُعتبر طلب الاستلام قبضًا إلا بعد جرد واعتماد مستقل في الوردية الحالية.</div></div>
      ${recoveryRecords.length?table(['مرجع الاستلام','المبلغ','الحالة','المسؤول','الإجراء'],recoveryRecords.map(r=>`<tr>
        <td>${esc(r.receipt_ref)}</td><td class="num">${fmt(r.amount_piasters)}</td>
        <td><span class="chip ${r.status==='approved'?'approved':r.status==='rejected'?'archive':'pending'}">${r.status==='approved'?'مستلم ومعتمد':r.status==='rejected'?'مرفوض':'بانتظار مراجعة مستقلة'}</span></td>
        <td>${esc(r.proposed_by_name||'')} ${r.voucher_no?'<div class="tiny">سند '+esc(r.voucher_no)+'</div>':''}</td>
        <td>${r.status==='pending'&&['owner','reviewer'].includes(state.me.role)&&r.proposed_by!==state.me.id?`<button class="btn btn-small btn-secondary" data-late-recovery-decision="${r.id}">مراجعة الاستلام</button>`:''}</td>
      </tr>`).join('')):''}
      ${recoveryDue>0&&['owner','clerk'].includes(state.me.role)?`<button class="btn btn-primary btn-small" data-late-recovery-propose="${id}">إثبات استلام مبلغ عجز فعلي</button>`:''}
     `:''}
   ${overageTotal?`<div class="info-box warning" role="status"><div><b>زيادة عهدة تاريخية:</b> الأصل ${fmt(overageTotal)} ج،
       المبالغ المستلمة بمعرفة أصحاب الحقوق ${fmt(d.overage_refunded_piasters||0)} ج،
       <b>المتبقي ${fmt(overageDue)} ج</b> في حساب 2190 كالتزام، وليس إيرادًا. صرفه يتطلب إثبات مطالبة وإيصال تسلم مستقلًا.</div></div>
       ${overageRecords.length?table(['مرجع المطالبة','المستفيد','المبلغ','حالة الرد','الإجراء'],overageRecords.map(r=>`<tr>
         <td>${esc(r.claim_ref)}</td><td>${esc(r.claimant_name)}</td><td class="num">${fmt(r.amount_piasters)}</td>
         <td><span class="chip ${r.status==='approved'?'approved':r.status==='rejected'?'archive':'pending'}">${r.status==='approved'?'مُعاد بإثبات':r.status==='rejected'?'مرفوض':'بانتظار مراجعة'}</span></td>
         <td>${r.voucher_no?'<span class="tiny">سند '+esc(r.voucher_no)+'</span>':''}
         ${r.status==='pending'&&['owner','reviewer'].includes(state.me.role)&&r.proposed_by!==state.me.id?
          `<button type="button" class="btn btn-secondary btn-small" data-late-overage-decision="${r.id}" data-late-overage-claim-proof="${r.evidence_id}">اعتماد / رفض</button>`:''}</td>
        </tr>`).join('')):''}
       ${overageDue>0&&['owner','clerk'].includes(state.me.role)?`<button type="button" class="btn btn-primary btn-small" data-late-overage-propose="${id}">طلب رد لصاحب حق</button>`:''}
       `:''}
   </section>`+
  `<section class="panel panel-pad"><h2>المراجعة والاستكمال</h2>
   <div class="row-actions">${canAdd&&d.documents.length?'<button class="btn btn-primary btn-small" data-late-action="submit">تقديم للمراجعة</button>':''}
   ${canReview&&['submitted','triaged'].includes(i.status)?'<button class="btn btn-secondary btn-small" data-late-action="triage">قبول للفحص</button><button class="btn btn-outline btn-small" data-late-action="needs_evidence">طلب استكمال</button>':''}
   ${canReview&&d.documents.length&&d.documents.every(x=>x.linked_id||x.cash_clearance_id||x.mixed_clearance_id)&&['submitted','triaged'].includes(i.status)?'<button class="btn btn-primary btn-small" data-late-action="resolve">إنهاء مطابقة المستندات</button>':''}</div>
   <h3>السجل غير القابل للتعديل</h3>${d.events.map(e=>`<p class="tiny"><b>${esc(e.username)} · ${esc(e.created_at)}</b> — ${esc(e.note)}</p>`).join('')}</section>`;
 const file=$('#lateEvidenceFile'),submit=$('#lateUploadEvidence');if(submit){submit.onclick=async()=>{
    if(!file.files.length){toast('اختر ملف الإثبات',true);return}const fd=new FormData();fd.append('file',file.files[0]);submit.disabled=true;
    try{await api('/api/late-entries/'+id+'/evidence',{method:'POST',body:fd});toast('تم حفظ الملف الأصلي');openLateEntry(id)}catch(e){toast(e.message,true)}finally{submit.disabled=false}
 }}
 $$('[data-late-proof]').forEach(b=>b.onclick=()=>{window.location.href='/api/late-entries/evidence/'+b.dataset.lateProof+'/download';});
 const add=$('#lateAddDocument');if(add){add.onclick=async()=>{
    const data=await modal('مستند استدراك غير مرحّل','يجب بعده إدخال العملية الأصلية إلكترونيًا بمسار آمن، ثم ربط المستند بها.',[
     {name:'paper_ref',label:'رقم المستند الورقي المميز',required:true},
     {name:'kind',type:'select',label:'نوع العملية',options:Object.entries(lateKinds).map(([k,v])=>[k,v])},
     {name:'amount',label:'القيمة بالجنيه',required:true},
     {name:'method',type:'select',label:'وسيلة الدفع',options:[['cash','نقدي'],['card','بطاقة'],['instapay','إنستاباي'],['wallet','محفظة'],['transfer','تحويل بنكي'],['mixed','مختلط']]},
     {name:'note',label:'بيان أو مرجع الفاتورة'}]);if(!data)return;
    try{await post('/api/late-entries/'+id+'/documents',data);toast('أضيف المستند دون حركة مالية');openLateEntry(id)}catch(e){toast(e.message,true)}
 }}
 $$('[data-late-case]').forEach(b=>b.onclick=()=>{
   billingState.pointId=i.point_id;billingState.caseId=Number(b.dataset.lateCase);navigate('billing');
 });
 $$('[data-late-recover]').forEach(b=>b.onclick=async()=>{
   const form=await modal('تسجيل ملف مريض لخدمة سابقة',
     'سيتم تسجيل تاريخ الخدمة القديم مع تاريخ إدخال اليوم الحقيقي. الفاتورة تصدر في الشهر المفتوح، لكن هذا الإجراء لا يثبت دفع النقدية القديمة.',[
     {name:'patient_code',label:'كود المريض الإلكتروني PT-...',required:true,placeholder:'PT-ABCDEF123456'},
     {name:'kind',type:'select',label:'نوع الحالة',options:i.shift_code==='treasury'?[['inpatient','داخلي'],['operation','عملية'],['nicu','حضانة'],['outpatient','خدمات خارجية']]:[['outpatient','خدمات خارجية'],['inpatient','داخلي'],['operation','عملية'],['nicu','حضانة']]},
     {name:'note',type:'textarea',label:'سبب الاستدراك والدليل على تقديم الخدمة',required:true}]);
   if(!form)return;
   const request_id=lateNewKey();
   try{const res=await post(`/api/late-entries/${id}/documents/${Number(b.dataset.lateRecover)}/recover-case`,{...form,request_id});
      toast('تم تسجيل ملف الحالة '+res.case_no+' دون أي قبض قديم');
      billingState.caseId=res.id;billingState.pointId=i.point_id;navigate('billing');
   }catch(e){toast(e.message,true)}
 });
 $$('[data-late-clear]').forEach(b=>b.onclick=async()=>{
   const docId=Number(b.dataset.lateClear),invoiceId=Number(b.dataset.invoiceId);
   const data=await modal('تسوية نقدية قديمة مثبتة بالخزنة الرئيسية',
    'يجب أن يكون السند قبضًا معتمدًا تحت «نقدية غير مخصصة» بنفس رقم الظرف والمبلغ المعدود. العملية تخصم من الذمم فقط؛ لا تضيف نقدية جديدة ولا تعيد فتح الشهر القديم.',[
    {name:'voucher_id',label:'معرف سند الخزنة الرئيسية المعتمد (ID)',required:true},
    {name:'note',type:'textarea',label:'الدليل على تطابق الظرف والفاتورة والسند',required:true}
   ]);
   if(!data)return;
   try{
     const out=await post(`/api/late-entries/${id}/documents/${docId}/clear-booked-cash`,{
       voucher_id:Number(data.voucher_id),invoice_id:invoiceId,note:data.note,request_id:lateNewKey()
     });
     toast('تمت تسوية '+fmt(out.amount_piasters)+' جنيه من نقدية مثبتة دون قبض جديد');openLateEntry(id);
   }catch(e){toast(e.message,true)}
 });
 $$('[data-late-mixed]').forEach(b=>b.onclick=async()=>{
   const look=await api('/api/lookups');
   const categories=['expense_medical','doctor_fees','lab_external','rent','utilities','maintenance','marketing','hospitality'];
   const expenseCategories=(look.categories||[]).filter(x=>categories.includes(x.code));
   const patients=patientDocs.map(x=>({document_id:x.id,invoice_id:
       recovered.find(r=>r.paper_document_id===x.id)?.issued_invoice_id}));
   if(patients.some(x=>!x.invoice_id)){
     toast('يجب إصدار فواتير المرضى الإلكترونية قبل تسوية الظرف',true);return;
   }
   const top=await modal('تسوية عهدة نقدية تاريخية مختلطة',
     'يُستخدم سند نقدية غير مخصصة معتمد بنفس قيمة الجرد الفعلي. يُرحل مصروف الورق تاريخيًا إلى الأستاذ في شهر مفتوح، ولا توجد حركة نقدية جديدة. أي فرق يحتاج تفويضًا مستقلًا.',[
     {name:'voucher_id',label:'معرّف سند النقدية الصافية المعتمد بالخزنة الرئيسية',required:true},
     {name:'approve_variance',type:'select',label:'قرار فرق العهدة',required:true,
        options:[['no','لا يوجد فرق أو لا أوافق على اعتماده'],['yes','أوافق استثنائيًا على الفرق الظاهر وأُبقيه بحساب تحت التسوية']]},
     {name:'note',type:'textarea',label:'تفسير التسوية والأدلة والتحقق المستقل (24 حرفًا على الأقل)',required:true}]);
   if(!top)return;
   const expenseLines=[];
   for(const doc of expenseDocs){
     const conf=await modal('تصنيف المصروف '+doc.paper_ref+' — '+fmt(doc.amount_piasters)+' جنيه',
       'اختر مركز التكلفة ونوع المصروف الحقيقي. المبلغ ثابت من مستند الوردية؛ لا يتم إنشاء سند صرف نقدي جديد.',[
       {name:'category_code',type:'select',label:'تصنيف المصروف',required:true,
         options:expenseCategories.map(x=>[x.code,x.name])},
       {name:'department_id',type:'select',label:'القسم أو مركز التكلفة',required:true,
         options:(look.departments||[]).map(x=>[String(x.id),x.name])}]);
     if(!conf)return;
     expenseLines.push({document_id:doc.id,category_code:conf.category_code,
                        department_id:Number(conf.department_id)});
   }
   try{
     const data=await post('/api/late-entries/'+id+'/clear-mixed-envelope',{
       request_id:lateNewKey(),voucher_id:Number(top.voucher_id),patients,expenses:expenseLines,
       approve_variance:top.approve_variance==='yes',note:top.note});
     toast(data.variance_piasters?'سُجل فرق عهدة معتمد ضمن حساب مستقل، دون قبض جديد':'تمت تسوية الظرف المختلط دون قبض جديد');
     openLateEntry(id);
   }catch(e){toast(e.message,true)}
 });
 $$('[data-late-recovery-propose]').forEach(b=>b.onclick=()=>proposeLateShortage(id,()=>openLateEntry(id)));
 $$('[data-late-overage-propose]').forEach(b=>b.onclick=()=>proposeLateOverage(id,()=>openLateEntry(id)));
 $$('[data-late-overage-decision]').forEach(b=>b.onclick=async()=>{
   const rid=Number(b.dataset.lateOverageDecision),claimProof=Number(b.dataset.lateOverageClaimProof);
   const signedProofs=(d.evidence||[]).filter(x=>x.id!==claimProof);
   if(!signedProofs.length){toast('ارفع إيصال تسلم موقع مستقلًا قبل اعتماد رد الزيادة',true);return}
   const form=await modal('اعتماد رد زيادة العهدة لصاحب الحق',
       'الاعتماد يسجل صرف نقدية فعلية من الخزنة الرئيسية الآن، ويخفض حساب الالتزامات 2190. تأكد من هوية صاحب الحق وإيصال تسلمه الموقع؛ لا تعتبرها مصروفًا أو إيرادًا.',[
       {name:'decision',type:'select',label:'قرار المراجعة',options:[['approve','تم تسليم المبلغ لصاحب الحق والتحقق من إيصال تسلمه'],['reject','رفض / استكمال أدلة']]},
       {name:'counted_amount',label:'المبلغ الذي تأكدت من صرفه بالجنيه (عند الاعتماد)'},
       {name:'receipt_evidence_id',type:'select',label:'إيصال تسلم موقع مستقل عن دليل المطالبة',options:signedProofs.map(x=>[String(x.id),`#${x.id} — ${x.filename}`])},
       {name:'recipient_receipt_verified',type:'select',label:'هل تحققت بنفسك من هوية المستفيد والتوقيع؟',options:[['false','لا'],['true','نعم، وبعد مطابقة المبلغ']]},
       {name:'reason',type:'textarea',label:'قرارك وأدلة التحقق (24 حرفًا على الأقل)',required:true}
      ]);
   if(!form)return;
   try{const out=await post(`/api/late-entries/${id}/overage-refunds/${rid}/decision`,{
     ...form,receipt_evidence_id:Number(form.receipt_evidence_id)||null,
     recipient_receipt_verified:form.recipient_receipt_verified==='true'});
     toast(out.status==='approved'?'تم رد الزيادة لصاحب الحق وخفض النقدية والالتزام':'رُفض الطلب دون حركة نقدية');
     openLateEntry(id);
   }catch(e){toast(e.message,true)}
 });
 $$('[data-late-recovery-decision]').forEach(b=>b.onclick=async()=>{
   const rid=Number(b.dataset.lateRecoveryDecision);
   const form=await modal('قرار مستقل لاستلام نقدية عجز',
      'راجع الإيصال الأصلي وراقب المبلغ الحقيقي في الخزنة. الموافقة تُنشئ سند قبض واحدًا في الوردية الحالية، وتقلّل حساب العجز فقط؛ لا تُعد إيراد مريض.',[
      {name:'decision',type:'select',label:'قرار المراجعة',options:[['approve','اعتماد الاستلام بعد العد الحقيقي'],['reject','رفض وإرجاع لإعادة الإثبات']]},
      {name:'counted_amount',label:'المبلغ الذي تأكدت من عده بنفسك بالجنيه (عند الاعتماد)'},
      {name:'reason',type:'textarea',label:'سبب القرار وأدلة الجرد (20 حرفًا على الأقل)',required:true}
   ]);
   if(!form)return;
   try{const result=await post(`/api/late-entries/${id}/shortage-recoveries/${rid}/decision`,form);
       toast(result.status==='approved'?'تم تسجيل المبلغ الفعلي في الخزنة وتخفيض العجز المتبقي':'رُفض الطلب دون حركة نقدية');openLateEntry(id);
   }catch(e){toast(e.message,true)}
 });
 $$('[data-late-link]').forEach(b=>b.onclick=async()=>{
   const kind=b.dataset.kind;
   const data=await modal('ربط المستند بحركة إلكترونية موجودة','لا تكتب رقمًا غير مؤكد؛ سيتم التحقق من النوع والتاريخ والنقطة والمبلغ ووسيلة الدفع قبل الربط.',[
    {name:'source_type',type:'select',label:'نوع الحركة الإلكترونية',options:kind==='patient_receipt'?[['collection','إيصال تحصيل مريض']]:[['voucher','سند مالي معتمد']]},
    {name:'source_id',label:'رقم معرف الحركة الإلكتروني (ID)',required:true},
    {name:'note',label:'ملاحظات المطابقة المستقلة',required:true}]);if(!data)return;
   try{await post('/api/late-entries/'+id+'/documents/'+b.dataset.lateLink+'/link',{...data,source_id:Number(data.source_id)});
       toast('تم الربط دون تحصيل جديد');openLateEntry(id)}catch(e){toast(e.message,true)}
 });
 $$('[data-late-action]').forEach(b=>b.onclick=async()=>{
   const action=b.dataset.lateAction;
   const data=await modal('توثيق قرار الاستدراك','القرار الرقابي لا يُنشئ فاتورة ولا إيصالًا أو قيدًا ماليًا.',[
    {name:'note',label:'مبرر القرار',required:true}]);if(!data)return;
   try{await post('/api/late-entries/'+id+'/action',{action,note:data.note});toast('تم حفظ القرار في سجل المراجعة');openLateEntry(id)}catch(e){toast(e.message,true)}
 });
}
window.renderLateEntries=renderLateEntries;
