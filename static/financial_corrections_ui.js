"use strict";
/* G2G credit and G2H full wrong-patient receipt reassignment; immutable sources. */
const correctionTypeLabels={invoice:'فاتورة صادرة',collection:'إيصال تحصيل',voucher:'سند مالي',shift:'وردية وجرد'};
const correctionIssueLabels={wrong_patient:'مريض أو حالة غير صحيحة',wrong_service:'خدمة أو سعر غير صحيح',wrong_amount:'مبلغ غير صحيح',wrong_method:'وسيلة دفع غير صحيحة',duplicate:'عملية متكررة',wrong_cash_fund:'خزنة غير صحيحة',missing_document:'مستند ناقص',other:'خطأ آخر'};
const correctionStatusLabels={open:'بلاغ جديد',needs_evidence:'مطلوب استكمال',triaged:'قيد المعالجة المالية',dismissed:'مغلق دون تسوية'};
const correctionNewKey=()=>globalThis.crypto?.randomUUID?.()||('corr_'+Date.now().toString(36)+Math.random().toString(36).slice(2,18));

async function renderFinancialCorrections(){
  const d=await api('/api/corrections');
  const records=d.tickets||[];
  const canReview=['owner','reviewer'].includes(state.me.role);
  const selected=state.financialCorrectionPrefill||{};
  state.financialCorrectionPrefill=null;
  const types=['invoice','collection','shift',...(canReview?['voucher']:[])];
  const ticketActions=t=>`<div class="row-actions">
    <button type="button" class="btn btn-small btn-outline" data-correction-history="${t.id}">السجل</button>
    ${t.status==='open'&&canReview&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-secondary" data-correction-review="${t.id}">مراجعة</button>`:''}
    ${t.status==='triaged'&&canReview&&t.source_type==='invoice'&&t.issue_type==='wrong_amount'&&!t.resolved_credit_id&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-primary" data-correction-credit="${t.id}">تخفيض فاتورة غير محصلة</button>`:''}
    ${t.status==='triaged'&&canReview&&t.source_type==='collection'&&t.issue_type==='wrong_patient'&&!t.resolved_reallocation_id&&t.opened_by!==state.me.id?`<button type="button" class="btn btn-small btn-primary" data-correction-reassign="${t.id}">نقل تخصيص إيصال</button>`:''}
    ${['open','needs_evidence'].includes(t.status)?`<button type="button" class="btn btn-small btn-outline" data-correction-note="${t.id}">إضافة إفادة</button>`:''}
    </div>`;
  const ticketStatus=t=>t.resolved_credit_id?'تخفيض معتمد':t.resolved_reallocation_id?'إعادة تخصيص معتمدة':correctionStatusLabels[t.status]||t.status;
  $('#content').innerHTML=head('رقابة المستندات','بلاغات تصحيح العمليات السابقة',
    'اختر المستند الأصلي. البلاغ لا يرحّل نقدية؛ تصحيح الفاتورة أو ربط إيصال بمريض آخر يتطلب مراجعة مستقلة.',
    '<button class="btn btn-secondary" data-go="billing">الحالات والفواتير</button>')+
    '<div class="info-box">'+ico('shield')+'<div><b>حماية البيانات المالية:</b> قبول البلاغ للمراجعة لا يغيّر القيود. تخفيض الفاتورة غير المحصلة يتم بإشعار دائن، ونقل تحصيل سُجّل على مريض غلط يتم بإعادة تخصيص <b>الإيصال كاملًا</b> دون قبض جديد أو تعديل وردية الكاشير.</div></div>'+
    `<section class="panel panel-pad"><h2>إنشاء بلاغ تصحيح</h2>
       <form class="financial-correction-form" id="financialCorrectionForm">
        <label>نوع المستند<select name="source_type" required>${types.map(type=>`<option value="${type}" ${type===selected.source_type?'selected':''}>${correctionTypeLabels[type]}</option>`).join('')}</select></label>
        <label>رقم المستند الداخلي (ID)<input name="source_id" type="number" step="1" min="1" required value="${Number(selected.source_id)||''}" placeholder="مثال: 25"></label>
        <label>نوع المشكلة<select name="issue_type" required>${Object.entries(correctionIssueLabels).map(([value,label])=>`<option value="${value}">${label}</option>`).join('')}</select></label>
        <label class="full">شرح الواقعة والمستندات المتاحة<textarea name="reason" rows="3" minlength="20" maxlength="2000" required placeholder="ما الخطأ بالتحديد؟ ما تاريخ الواقعة؟ وما الدليل؟"></textarea></label>
        <label class="full">الإجراء المطلوب مراجعته<textarea name="proposed_resolution" rows="2" minlength="12" maxlength="2000" required placeholder="مثلًا: تصحيح ربط الإيصال بالمريض بعد التحقق"></textarea></label>
        <button class="btn btn-primary" type="submit">إرسال البلاغ للمراجعة</button>
       </form><p class="tiny">المستند المعتمد يظل كما هو. لا تستخدم البلاغ بدل إيصال قبض أو مصروف.</p></section>`+
    `<section class="panel panel-pad financial-corrections-records"><div class="panel-header"><div><h2>سجل بلاغات التصحيح</h2><p>مستند أصلي · سبب البلاغ · مراجعة مستقلة · سجل تغييرات لا يُمسح</p></div><span class="chip archive">${integer(records.length)} بلاغ</span></div>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>رقم</th><th>المستند الأصلي</th><th>المشكلة</th><th>الحالة</th><th>المُبلّغ</th><th>الإجراء</th></tr></thead><tbody>${records.map(t=>
        `<tr><td data-label="رقم البلاغ">#${t.id}</td><td data-label="المستند"><strong>${esc(t.source_ref)}</strong><div class="tiny">${esc(correctionTypeLabels[t.source_type]||t.source_type)}</div></td>
         <td data-label="المشكلة">${esc(correctionIssueLabels[t.issue_type]||t.issue_type)}</td>
         <td data-label="الحالة"><span class="chip ${t.resolved_credit_id||t.resolved_reallocation_id?'approved':t.status==='open'?'pending':t.status==='triaged'?'approved':'archive'}">${esc(t.resolved_credit_id?'تخفيض معتمد':t.resolved_reallocation_id?'إعادة تخصيص معتمدة':correctionStatusLabels[t.status]||t.status)}</span></td>
         <td data-label="المُبلّغ">${esc(t.opened_by_name)}</td>
         <td data-label="الإجراء">${ticketActions(t)}</td></tr>`).join('')||'<tr><td colspan="6">لا توجد بلاغات تصحيح حتى الآن.</td></tr>'}</tbody></table></div>
      </section>`;
  const form=$('#financialCorrectionForm');
  form.addEventListener('input',()=>{delete form.dataset.requestKey});
  form.addEventListener('submit',async e=>{
    e.preventDefault();const button=form.querySelector('button[type=submit]');button.disabled=true;
    try{
      const info=Object.fromEntries(new FormData(form));
      const request_key=form.dataset.requestKey||(form.dataset.requestKey=correctionNewKey());
      await post('/api/corrections',{source_type:info.source_type,source_id:Number(info.source_id),
        issue_type:info.issue_type,reason:info.reason,proposed_resolution:info.proposed_resolution,request_key});
      delete form.dataset.requestKey;toast('سُجّل البلاغ للمراجعة دون أي حركة مالية');navigate('cashierCorrections');
    }catch(err){toast(err.message,true)}finally{button.disabled=false}
  });
  $$('[data-correction-history]').forEach(btn=>btn.onclick=async()=>{
    try{
      const data=await api('/api/corrections/'+btn.dataset.correctionHistory+'/history');
      const t=data.ticket;
      const html=`<p><b>${esc(t.source_ref)}</b> — ${esc(correctionStatusLabels[t.status]||t.status)}</p>`+
        (data.financial_execution?`<p><b>تصحيح مالي معتمد:</b> إشعار دائن #${integer(data.financial_execution.credit_id)} · خفض ${esc((data.financial_execution.amount_piasters/100).toFixed(2))} جنيه · الرصيد بعده ${esc((data.financial_execution.new_due_piasters/100).toFixed(2))} جنيه</p>`:'')+
        (data.collection_reallocation?`<p><b>نقل تخصيص معتمد:</b> إيصال #${integer(data.collection_reallocation.collection_id)} · من فاتورة #${integer(data.collection_reallocation.from_invoice_id)} إلى #${integer(data.collection_reallocation.to_invoice_id)} · ${esc((data.collection_reallocation.amount_piasters/100).toFixed(2))} جنيه · تاريخ التصحيح ${esc(data.collection_reallocation.effective_date)}. <b>لم يتم قبض أو صرف أي مبلغ جديد.</b></p>`:'')+
        `<p>${esc(t.reason)}</p>`+(data.events||[]).map(x=>`<p><b>${esc(x.username)} · ${esc(x.created_at)}</b><span class="tiny"> ${esc(x.note)}</span></p>`).join('');
      await modal('سجل بلاغ التصحيح #'+t.id,html);
    }catch(err){toast(err.message,true)}
  });
  $$('[data-correction-review]').forEach(btn=>btn.onclick=async()=>{
    const decision=await modal('قرار مراجعة البلاغ',
      'هذا قرار بشأن قبول البلاغ للفحص فقط، وليس موافقة على ترحيل محاسبي.',[
        {name:'decision',type:'select',label:'قرار المراجعة',required:true,options:[['triage','قبول للفحص المالي'],['needs_evidence','طلب مستندات إضافية'],['dismiss','إغلاق البلاغ دون تسوية']]},
        {name:'note',type:'textarea',label:'مبرر القرار',required:true,placeholder:'شرح مستقل لا يقل عن 16 حرفًا'}]);
    if(!decision)return;
    try{await post('/api/corrections/'+btn.dataset.correctionReview+'/review',decision);
      toast('تم حفظ مراجعة البلاغ دون المساس برصيد الخزنة');navigate('cashierCorrections')}
    catch(err){toast(err.message,true)}
  });
  $$('[data-correction-credit]').forEach(btn=>btn.onclick=async()=>{
    const ticket=Number(btn.dataset.correctionCredit);btn.disabled=true;
    try{
      const preview=await api('/api/corrections/'+ticket+'/invoice-credit-preview');
      if(!preview.eligible){toast(preview.reason||'الفاتورة غير مؤهلة لهذا التصحيح',true);return;}
      const form=await modal('تخفيض ذمة فاتورة صادرة',
        'الفاتورة الأصلية '+esc(preview.invoice_no)+' · المبلغ غير المحصل '+esc((preview.before_due_piasters/100).toFixed(2))+' جنيه. <b>التخفيض بإشعار دائن نهائي، لا يحرك النقدية ولا يعدل أصل الفاتورة.</b> أوقف العملية لو فيه أي تحصيل أو تسوية ظرف.',[
          {name:'amount',type:'number',step:'0.01',required:true,label:'قيمة التخفيض بالجنيه (حد أقصى '+(preview.max_reduction_piasters/100).toFixed(2)+')'},
          {name:'evidence_reference',type:'text',required:true,label:'مرجع كشف الخدمة أو مستند الإثبات',placeholder:'مثال: LAB-REPORT-2026-152'},
          {name:'decision_note',type:'textarea',required:true,label:'سبب الاعتماد المالي المستقل'}]);
      if(!form)return;
      if(!Number.isFinite(Number(form.amount))||Number(form.amount)<=0||Number(form.amount)*100>preview.max_reduction_piasters){
        toast('قيمة التخفيض غير صحيحة أو تتجاوز الذمة',true);return;
      }
      await post('/api/corrections/'+ticket+'/execute-invoice-credit',{
        amount:form.amount,expected_due_piasters:preview.before_due_piasters,
        evidence_reference:form.evidence_reference,decision_note:form.decision_note,
        request_key:correctionNewKey()});
      toast('اعتُمد إشعار دائن مرتبط بالفاتورة دون قبض أو حركة خزنة');navigate('cashierCorrections');
    }catch(err){toast(err.message,true)}finally{btn.disabled=false}
  });
  $$('[data-correction-reassign]').forEach(btn=>btn.onclick=async()=>{
    const ticket=Number(btn.dataset.correctionReassign);btn.disabled=true;
    try{
      const target=await modal('تحديد الفاتورة الصحيحة',
        'سيبقى إيصال القبض الأصلي مسجلًا في ورديته وخزنته. أدخل رقم الفاتورة الصحيحة وكود المريض الكامل للتأكد من هوية المستفيد، دون كشف بيانات المرضى بالبحث.',[
         {name:'target_invoice_id',type:'number',label:'الرقم الداخلي للفاتورة الصحيحة (ID)',required:true,step:'1',min:'1'},
         {name:'target_patient_code',label:'كود المريض الصحيح كاملًا',required:true,placeholder:'PT-XXXXXXXXXXXX'}]);
      if(!target)return;
      const targetInvoiceId=Number(target.target_invoice_id);
      if(!Number.isSafeInteger(targetInvoiceId)||targetInvoiceId<1){toast('رقم الفاتورة غير صالح',true);return;}
      const preview=await post('/api/corrections/'+ticket+'/collection-reassign-preview',{
        target_invoice_id:targetInvoiceId,target_patient_code:target.target_patient_code.trim()});
      if(!preview.eligible){toast(preview.reason||'لا يمكن إعادة تخصيص الإيصال',true);return;}
      const form=await modal('اعتماد إعادة تخصيص إيصال كامل',
        'من الإيصال <b>'+esc(preview.source_receipt_no)+'</b> إلى الفاتورة <b>'+esc(preview.target_invoice_no)+
        '</b> للحالة <b>'+esc(preview.target_case_no)+'</b>. المبلغ <b>'+
        esc((preview.amount_piasters/100).toFixed(2))+
        ' جنيه</b> كاملًا. الذمة الصحيحة قبل النقل '+esc((preview.before_target_due_piasters/100).toFixed(2))+
        ' جنيه، وبعد النقل '+esc(((preview.before_target_due_piasters-preview.amount_piasters)/100).toFixed(2))+
        ' جنيه. ذمة فاتورة المصدر قبل النقل '+esc((preview.before_source_due_piasters/100).toFixed(2))+
        ' جنيه، وبعده '+esc(((preview.before_source_due_piasters+preview.amount_piasters)/100).toFixed(2))+
        ' جنيه. <b>لن يتحرك أي مال أو يتغير سند القبض القديم.</b> يُمنع التنفيذ إن كان المستند الأصلي غير صحيح.',[
         {name:'evidence_reference',label:'مرجع مستند التحقيق أو إثبات المريض',required:true},
         {name:'decision_note',type:'textarea',label:'سبب قرار المراجع المستقل',required:true},
         {name:'confirm',type:'select',label:'تأكيد نقل الإيصال كاملًا',required:true,
          options:[['no','لا، إلغاء'],['yes','نعم، البيانات والمستندات متطابقة']]}]);
      if(!form||form.confirm!=='yes')return;
      await post('/api/corrections/'+ticket+'/execute-collection-reassign',{
        target_invoice_id:targetInvoiceId,target_patient_code:target.target_patient_code.trim(),
        expected_source_due_piasters:preview.before_source_due_piasters,
        expected_target_due_piasters:preview.before_target_due_piasters,
        evidence_reference:form.evidence_reference,decision_note:form.decision_note,
        request_key:correctionNewKey()});
      toast('تم نقل تخصيص الإيصال كاملًا دون حركة خزنة جديدة');navigate('cashierCorrections');
    }catch(err){toast(err.message,true)}finally{btn.disabled=false}
  });
  $$('[data-correction-note]').forEach(btn=>btn.onclick=async()=>{
    const info=await modal('إضافة إفادة للبلاغ','سيتم الاحتفاظ بالنص مع اسم المستخدم ووقت التسجيل دون حذف السابق.',[
      {name:'note',type:'textarea',label:'الإفادة أو مرجع المستند',required:true}]);
    if(!info)return;
    try{await post('/api/corrections/'+btn.dataset.correctionNote+'/note',info);
      toast('تم تسجيل الإفادة وإضافتها للسجل');navigate('cashierCorrections')}
    catch(err){toast(err.message,true)}
  });
}
window.renderFinancialCorrections=renderFinancialCorrections;
