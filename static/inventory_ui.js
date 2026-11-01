"use strict";
/* G2T: Central consumables only. Deliberately no pharmacy, payments or auto patient invoices. */
(function(){
  const today=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'});
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
      const ref=type==='receipts'||type==='supplier-invoices'?row.invoice_ref:type==='purchase-orders'?row.order_ref:row.evidence_ref;
      const date=type==='receipts'?row.received_on:type==='purchase-orders'?row.ordered_on:type==='supplier-invoices'?row.invoice_date:type==='returns'?row.returned_on:type==='writeoffs'?row.disposed_on:row.used_on;
      const amount=['receipts','purchase-orders'].includes(type)?row.total_piasters:type==='supplier-invoices'?row.amount_piasters:row.cost_piasters;
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
    const approvedOrders=(d.purchase_orders||[]).filter(x=>x.status==='approved');
    const invoiceReceipts=d.purchase_receipts||[];
    const suppliers=d.supplier_summary||{};

    const dueDocs=d.supplier_due_schedules||[];
    const dueLines=d.supplier_due_lines||[];
    const eligibleDue=d.supplier_due_eligible_invoices||[];
    const aging=d.supplier_aging||{};
    const paymentRequests=d.supplier_payment_requests||[];
    const paymentEligible=(d.supplier_payment_eligible_lines||[]).filter(x=>Number(x.available_to_request_piasters)>0);
    const installmentRow=(minimum=today())=>`<div class="inv-match-row inv-due-line">`+
      field('','تاريخ الاستحقاق',input('due_on','date',`min="${esc(minimum)}" value="${today()}"`))+
      field('','قيمة القسط بالجنيه',input('amount','number','min="0.01" step="0.01"'))+
      `</div>`;
    const dueRows=dueDocs.map(doc=>{
      const parts=dueLines.filter(line=>Number(line.schedule_id)===Number(doc.id));
      const trusted=parts.length>0&&parts.length<=12&&
        parts.every(line=>Number.isInteger(Number(line.amount_piasters))&&Number(line.amount_piasters)>0&&/^\d{4}-\d{2}-\d{2}$/.test(String(line.due_on)))&&
        parts.reduce((sum,line)=>sum+Number(line.amount_piasters),0)===Number(doc.amount_piasters);
      const review=canApprove&&doc.status==='pending'&&trusted&&
        ![doc.created_by,doc.invoice_creator,doc.receipt_creator].some(id=>Number(id)===Number(state.me.id))?
        `<div class="inv-actions"><button class="btn btn-small btn-primary" data-inv-due-decision="${Number(doc.id)}:approve">اعتماد</button>`+
        `<button class="btn btn-small btn-outline" data-inv-due-decision="${Number(doc.id)}:reject">رفض</button></div>`:'—';
      const details=trusted?parts.map(line=>`<span class="inv-muted">القسط ${integer(line.line_no)}: ${esc(line.due_on)} — ${fmt(line.amount_piasters)} جنيه</span>`).join(' ؛ '):
        '<strong>تفاصيل الأقساط ناقصة — ممنوع الاعتماد</strong>';
      return `<tr data-inv-due-schedule="${Number(doc.id)}"><td><strong>${esc(doc.invoice_ref)}</strong>`+
        `<small class="inv-muted">${esc(doc.vendor_name)} / ${esc(doc.terms_ref)}</small></td>`+
        `<td>${esc(doc.scheduled_on)}</td><td class="num">${fmt(doc.amount_piasters)}</td>`+
        `<td>${details}</td><td><span class="chip ${esc(doc.status)}">${statusName[doc.status]||esc(doc.status)}</span></td>`+
        `<td>${review}</td></tr>`;
    }).join('');
    const duePanel=`<section class="panel inv-panel"><div class="panel-header"><div><h2>جدولة استحقاقات الموردين — إجمالي قبل السداد</h2>`+
      `<p>مواعيد أقساط الفواتير المطابقة، وليست رصيدًا غير مدفوع ولا إذنًا بصرف النقدية.</p></div></div>`+
      `<div class="inv-stats"><div><small>فواتير معتمدة بالقيمة الإجمالية</small><strong>${fmt(aging.approved_invoice_total_piasters)} جنيه</strong></div>`+
      `<div><small>إجمالي أقساط معتمدة</small><strong>${fmt(aging.scheduled_total_piasters)} جنيه</strong></div>`+
      `<div><small>فواتير بدون جدول معتمد</small><strong>${fmt(aging.unscheduled_total_piasters)} جنيه</strong></div>`+
      `<div><small>مستقبلية</small><strong>${fmt(aging.future_piasters)} جنيه</strong></div>`+
      `<div><small>مستحقة اليوم</small><strong>${fmt(aging.due_today_piasters)} جنيه</strong></div>`+
      `<div><small>متأخرة 1–30 يومًا</small><strong>${fmt(aging.over_1_30_piasters)} جنيه</strong></div>`+
      `<div><small>متأخرة 31–60</small><strong>${fmt(aging.over_31_60_piasters)} جنيه</strong></div>`+
      `<div><small>متأخرة 61–90</small><strong>${fmt(aging.over_61_90_piasters)} جنيه</strong></div>`+
      `<div><small>متأخرة أكثر من 90</small><strong>${fmt(aging.over_90_piasters)} جنيه</strong></div></div>`+
      `<p class="section-subtitle">التقرير مبني على الجداول المعتمدة حاليًا بتاريخ ${esc(aging.as_of||today())}، ولا يخصم سدادًا تاريخيًا أو أرصدة افتتاحية أو ضرائب.</p>`+
      (dueDocs.length?table(['فاتورة المورد','تاريخ التسجيل','القيمة','تواريخ ومبالغ كل قسط','الحالة','القرار'],dueRows):empty('لم تُسجّل جداول استحقاق بعد.'))+
      `</section>`+
      (canPrepare?`<section class="panel panel-pad"><h2 class="section-title">تسجيل شروط سداد فاتورة مورد</h2>`+
        `<p class="section-subtitle">يجب أن يساوي مجموع الأقساط فاتورة المورد كاملةً بالقروش. لا ينشأ قيد إضافي.</p>`+
        (eligibleDue.length?`<form id="invDueScheduleForm" class="inv-form">`+
          field('','فاتورة مطابقة ومستحقة للجدولة',`<select name="invoice_match_id" required>${eligibleDue.map(x=>`<option value="${Number(x.id)}">${esc(x.vendor_name)} — ${esc(x.invoice_ref)} — ${fmt(x.amount_piasters)} جنيه</option>`).join('')}</select>`)+
          field('','تاريخ تسجيل الشروط',input('scheduled_on','date',`value="${today()}"`))+
          field('','مرجع شروط السداد المتفق عليها',input('terms_ref','text','minlength="8" maxlength="180"'))+
          `<div id="invDueLines">${installmentRow(eligibleDue[0].invoice_date)}</div>`+
          `<div class="inv-actions"><button id="invAddInstallment" type="button" class="btn btn-outline">إضافة قسط (حد أقصى 12)</button>`+
          `<button type="submit" class="btn btn-primary">إرسال شروط السداد لمراجع مستقل</button></div></form>`:
          empty('لا توجد فاتورة مطابقة ثلاثيًا بدون جدول استحقاق نشط.'))+
        `</section>`:'');

    const paymentPanel=`<section class="panel inv-panel"><div class="panel-header"><div><h2>طلبات اعتماد صرف الموردين — غير منفذة</h2>`+
      `<p>الموافقة هنا تمهيدية فقط، وليست دفعًا نقديًا أو تحويلًا بنكيًا، ولا تخصم من حساب المورد.</p></div></div>`+
      `<div class="info-box warning" role="note">المبالغ المحجوزة أدناه هي سعة موافقات مقترحة، وليست مبالغ مدفوعة. يلزم إثبات سند صرف مستقل ومطابقة البنك قبل إثبات السداد.</div>`+
      (paymentRequests.length?table(['فاتورة المورد وقسطها','قيمة الطلب المرجعية','مرجع الطلب','حالة المراجعة','القرار'],paymentRequests.map(row=>{
        const amount=Number(row.amount_piasters);
        const trusted=Number.isSafeInteger(amount)&&amount>0&&amount<=Number(row.installment_piasters)&&
          /^\d{4}-\d{2}-\d{2}$/.test(String(row.due_on))&&!!row.invoice_ref&&!!row.vendor_name;
        const review=canApprove&&row.status==='pending'&&trusted&&
          ![row.created_by,row.schedule_creator,row.invoice_creator,row.receipt_creator].some(id=>Number(id)===Number(state.me.id))?
          `<div class="inv-actions">${Number(row.vendor_active)===1?
            `<button type="button" class="btn btn-small btn-primary" data-inv-payment-decision="${Number(row.id)}:approve">اعتماد تمهيدي</button>`:
            `<span class="chip rejected">المورد موقوف — الرفض فقط</span>`}`+
          `<button type="button" class="btn btn-small btn-outline" data-inv-payment-decision="${Number(row.id)}:reject">رفض</button></div>`:'—';
        return `<tr data-inv-payment-id="${Number(row.id)}"><td><strong>${esc(row.invoice_ref)}</strong>`+
          `<small class="inv-muted">${esc(row.vendor_name)} — قسط يستحق ${esc(row.due_on)}</small></td>`+
          `<td class="num">${fmt(amount)} جنيه</td><td>${esc(row.evidence_ref)}</td>`+
          `<td><span class="chip ${esc(row.status)}">${statusName[row.status]||esc(row.status)}</span></td><td>${review}</td></tr>`;
      }).join('')):empty('لا توجد طلبات اعتماد صرف تمهيدية.'))+
      `</section>`+
      (canPrepare?`<section class="panel panel-pad"><h2 class="section-title">طلب إذن صرف مبدئي لمورد</h2>`+
        `<p class="section-subtitle">اختر قسطًا معتمدًا. الطلب ليس إثبات دفع، ولا يصدر سند خزنة أو قيد أستاذ.</p>`+
        (paymentEligible.length?`<form id="invPaymentRequestForm" class="inv-form">`+
          field('','القسط والفاتورة',`<select name="due_line_id" required>${paymentEligible.map(x=>
            `<option value="${Number(x.id)}">${esc(x.vendor_name)} — ${esc(x.invoice_ref)} — ${esc(x.due_on)} (متاح للموافقة ${fmt(x.available_to_request_piasters)} جنيه)</option>`).join('')}</select>`)+
          field('','تاريخ تقديم طلب الصرف',input('requested_on','date',`value="${today()}"`))+
          field('','مبلغ الطلب بالجنيه',input('amount','number',`min="0.01" step="0.01" max="${(Number(paymentEligible[0].available_to_request_piasters)/100).toFixed(2)}"`))+
          field('','مرجع مستند طلب الصرف',input('evidence_ref','text','minlength="8" maxlength="180"'))+
          `<button type="submit" class="btn btn-primary">إرسال الطلب للمراجعة — بدون دفع</button></form>`:
          empty('لا توجد أقساط معتمدة ذات سعة متبقية لطلب الصرف التمهيدي.'))+
        `</section>`:'');

    const totalValue=items.reduce((sum,x)=>sum+Number(x.value_piasters||0),0);
    const totalUnits=items.reduce((sum,x)=>sum+Number(x.quantity_on_hand||0),0);
    const totalQuarantine=items.reduce((sum,x)=>sum+Number(x.quarantined_quantity||0),0);
    const totalAvailable=items.reduce((sum,x)=>sum+Number(x.available_quantity||0),0);
    const pending=(d.receipts||[]).filter(x=>x.status==='pending').length+(d.issues||[]).filter(x=>x.status==='pending').length+(d.returns||[]).filter(x=>x.status==='pending').length;
    const units=[['piece','قطعة'],['box','صندوق'],['pack','عبوة'],['bottle','زجاجة'],['meter','متر']];
    root.innerHTML=head('المخازن والمشتريات','المخزن المركزي للمستلزمات','قيود مخزون وموردين وتكلفة تشغيل، ولا يحدث صرف من الخزنة تلقائيًا.',isOwner?`<button type="button" class="btn btn-secondary" id="invGrant">${ico('shield')} إدارة تفويضات المخزن</button>`:'')+
      `<div class="info-box warning" role="note">${ico('alert')}<div><strong>تجريبي — مستلزمات غير دوائية فقط.</strong> لا يشمل أدوية المرضى أو الصرف العلاجي أو سداد الموردين أو المطابقة البنكية أو ضريبة القيمة المضافة. التقرير لا يثبت قيمة مخزون افتتاحي تاريخي.</div></div>`+
      `<div class="inv-stats"><div><small>أصناف مسجلة</small><strong>${integer(items.length)}</strong></div><div><small>الرصيد الدفتري (يشمل الحجر)</small><strong>${integer(totalUnits)}</strong></div><div><small>الحجر الطبي</small><strong>${integer(totalQuarantine)}</strong></div><div><small>المتاح بعد الحجر*</small><strong>${integer(totalAvailable)}</strong></div><div><small>قيمة المخزون (تشمل الحجر)</small><strong>${fmt(totalValue)} ج.م</strong></div></div>`+
      `<div class="info-box warning" role="note">الموافقة المحاسبية على المرتجع لا تعني صلاحية إعادة الاستخدام. الكمية المحجوزة طبيًا لا تدخل FIFO إلا بقرار طبي مستقل، والرصيد غير المحجوز لا يضمن الصلاحية أو سلامة العبوة؛ يتم فحصهما عند الصرف. لا يجوز استخدام هذه الدورة مع مرضى حقيقيين قبل اعتماد مكافحة العدوى.</div>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>مشتريات الموردين — أوامر ومطابقة ثلاثية</h2><p>أمر شراء معتمد ← استلام جزئي معتمد ← فاتورة بنفس الأصناف والسعر والكمية. الاستلام هو وحده الذي يُسجّل دين المورد.</p></div></div>`+
      `<div class="inv-stats"><div><small>استحقاق موردين من محاضر الاستلام فقط</small><strong>${fmt(suppliers.total_grn_accrued_piasters)} ج.م</strong></div><div><small>مطابق مع فاتورة مورد</small><strong>${fmt(suppliers.confirmed_piasters)} ج.م</strong></div><div><small>غير مطابق / قديم خارج دورة الشراء</small><strong>${fmt(suppliers.unmatched_piasters)} ج.م</strong></div></div>`+
      (suppliers.vendors?.length?table(['المورد','محاضر معتمدة','استحقاق محاضر الاستلام','مطابق','غير مطابق'],suppliers.vendors.map(v=>`<tr><td>${esc(v.vendor_name)}</td><td class="num">${integer(v.approved_grns)}</td><td class="num">${fmt(v.grn_accrued_piasters)}</td><td class="num">${fmt(v.confirmed_piasters)}</td><td class="num">${fmt(v.unmatched_piasters)}</td></tr>`).join('')):empty('لا توجد استلامات مورّدين معتمدة بعد.'))+
      `<p class="section-subtitle">هذه قيم مستندات GRN فقط، وليست رصيد المورد بعد المدفوعات أو ضريبة القيمة المضافة. المطابقة لا تُنشئ قيدًا ماليًا ثانيًا.</p></section>`+
      duePanel+
      paymentPanel+
      `<div class="inv-grid"><section class="panel inv-panel"><div class="panel-header"><div><h2>أوامر الشراء</h2><p>مراجعة مستقلة قبل بدء استلام الكميات</p></div></div>${docTable(d.purchase_orders||[],'purchase-orders',canApprove,state.me.id)}</section>`+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>مطابقات فواتير الموردين</h2><p>الرفض لا يغيّر قيود الاستلام، ويمكن إعادة التقديم بمستند صحيح</p></div></div>${docTable(d.supplier_invoice_matches||[],'supplier-invoices',canApprove,state.me.id)}</section></div>`+
      (canPrepare?`<div class="inv-grid"><section class="panel panel-pad"><h2 class="section-title">طلب أمر شراء</h2><p class="section-subtitle">لا يصرف أموالًا ولا ينشئ مخزونًا. مثال الواجهة لصنف واحد؛ الـAPI يقبل عدة أصناف.</p><form id="invPurchaseOrderForm" class="inv-form">`+
        field('','المورد',`<select name="vendor_id" required>${options(vendors,'اختر المورد')}</select>`)+
        field('','تاريخ الأمر',input('ordered_on','date',`value="${today()}"`))+
        field('','رقم أمر الشراء',input('order_ref','text','minlength="6" maxlength="90" placeholder="PO-001"'))+
        field('','مرجع اعتماد الاحتياج',input('evidence_ref','text','minlength="8" maxlength="180" placeholder="مرجع طلب القسم المعتمد"'))+
        field('','الصنف',`<select name="item_id" required>${options(items,'اختر صنفًا')}</select>`)+
        field('','الكمية',input('quantity','number','min="1" step="1" max="1000000"'))+
        field('','السعر المتفق عليه / وحدة بالجنيه',input('unit_cost','number','min="0.01" step="0.01"'))+
        `<button type="submit" class="btn btn-primary" ${!vendors.length||!items.length?'disabled':''}>إرسال أمر الشراء لاعتماد مستقل</button></form></section>`+
        `<section class="panel panel-pad"><h2 class="section-title">مطابقة فاتورة مورد مع الاستلام</h2><p class="section-subtitle">بعد اعتماد محضر الاستلام المرتبط بأمر شراء. لا يضاف قيد جديد للموردين.</p>`+
        (invoiceReceipts.length?`<form id="invSupplierInvoiceForm" class="inv-form">`+
          field('','محضر الاستلام المرتبط',`<select name="receipt_id" required>${invoiceReceipts.map(x=>`<option value="${Number(x.id)}">${esc(x.invoice_ref)} — ${esc(x.vendor_name)} (GRN #${integer(x.id)})</option>`).join('')}</select>`)+
          `<p class="section-subtitle">أدخل كمية وسعر <strong>كل بند من فاتورة المورد الأصلية</strong> بنفسك؛ لا تفترض صحة بيانات المخزن.</p><div id="invInvoiceLines"></div>`+
          field('','تاريخ فاتورة المورد',input('invoice_date','date',`value="${today()}"`))+
          field('','رقم الفاتورة',input('invoice_ref','text','minlength="6" maxlength="90"'))+
          field('','إجمالي الفاتورة بالجنيه',input('amount','number','min="0.01" step="0.01"'))+
          field('','مرجع أصل الفاتورة',input('evidence_ref','text','minlength="8" maxlength="180"'))+
          `<button type="submit" class="btn btn-primary">إرسال للمطابقة المستقلة</button></form>`:empty('لا توجد محاضر استلام مرتبطة بأوامر شراء ومعتمدة تنتظر مطابقة فاتورة.'))+
        `</section></div>`:'')+
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>الأرصدة حسب الصنف</h2><p>الرصيد الدفتري يشمل المرتجعات بالحجر حتى اعتماد تسويتها؛ لا يساوي جردًا ماديًا.</p></div>${isOwner?`<div class="inv-actions"><button id="invVendor" class="btn btn-small btn-outline">مورد جديد</button><button id="invItem" class="btn btn-small btn-primary">صنف جديد</button></div>`:''}</div>`+
      (items.length?table(['الكود','الصنف','الوحدة','المملوك','بالحجر','غير محجوز*','القيمة'],items.map(x=>`<tr><td>${esc(x.code)}</td><td><strong>${esc(x.name)}</strong></td><td>${esc(unitName[x.unit]||x.unit)}</td><td class="num">${integer(x.quantity_on_hand)}</td><td class="num">${integer(x.quarantined_quantity)}</td><td class="num">${integer(x.available_quantity)}</td><td class="num">${fmt(x.value_piasters)}</td></tr>`).join('')):empty('سجّل موردًا وصنفًا أولًا ثم أنشئ محضر توريد.'))+
      `</section>`+
      (canPrepare?`<div class="inv-grid"><section class="panel panel-pad"><h2 class="section-title">محضر استلام من مورد</h2><p class="section-subtitle">القيد المالي والكمية يترحلان فقط بعد اعتماد موظف آخر.</p><form id="invReceiptForm" class="inv-form">`+
        field('','المورد',`<select name="vendor_id" required>${options(vendors,'اختر المورد')}</select>`)+
        field('','أمر الشراء المعتمد (اختياري للترحيل التاريخي فقط)',`<select name="purchase_order_id"><option value="">قديم / غير مرتبط بأمر شراء</option>${approvedOrders.map(x=>`<option value="${Number(x.id)}">${esc(x.order_ref)} — ${esc(x.vendor_name)}</option>`).join('')}</select>`)+
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
      `<section class="panel inv-panel"><div class="panel-header"><div><h2>تسويات تلف وإعدام المستلزمات</h2><p>تسوية مستقلة للوحدات المرتجعة المرفوضة طبيًا فقط. الاعتماد يخصم من أصل المخزون ويثبت خسارة، ولا يغير تكلفة الحالة.</p></div></div>${docTable(d.writeoffs||[],'writeoffs',canApprove,state.me.id)}</section>`+
      (canPrepare?`<section class="panel panel-pad"><h2 class="section-title">طلب شطب مستلزم محجوز</h2>`+
      `<p class="section-subtitle">يجب توثيق الفحص الطبي الرافض والإزالة المادية. لن تتغير قيمة المخزون قبل اعتماد مراجع مستقل.</p>`+
      ((d.writeoff_candidates||[]).length?`<form id="invWriteoffForm" class="inv-form">`+
        field('','دفعة المرتجع المرفوض',`<select name="return_line_id" required>${(d.writeoff_candidates||[]).map(row=>`<option value="${Number(row.return_line_id)}">${esc(row.item_code)} — ${esc(row.item_name)} / ${esc(row.batch_ref)} (متبقي ${integer(row.remaining_quantity)})</option>`).join('')}</select>`)+
        field('','كمية الشطب',`<input name="quantity" type="number" min="1" max="${Number(d.writeoff_candidates[0].remaining_quantity)}" step="1" required>`)+
        field('','تاريخ الإزالة المادية',`<input name="disposed_on" type="date" value="${today()}" required>`)+
        field('','سبب التلف',`<select name="reason" required><option value="damaged">تلف أو كسر</option><option value="contaminated">تلوث</option><option value="expired">انتهاء صلاحية</option><option value="other">سبب موثق آخر</option></select>`)+
        field('','مرجع محضر الإعدام أو التلف',`<input name="evidence_ref" minlength="8" maxlength="180" placeholder="محضر إزالة مادي موقع" required>`)+
        `<label class="inv-field"><span><input name="physical_disposal_confirmed" type="checkbox" required> أؤكد أن الكمية أُزيلت فعليًا من العهدة وفق محضر الإثبات</span></label>`+
        `<button type="submit" class="btn btn-primary">إرسال التسوية للمراجع المالي</button></form>`:
        empty('لا توجد حاليًا مستلزمات مرفوضة طبيًا بكمية غير مسوّاة.'))+
      `</section>`:'')+
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
    $('#invWriteoffForm')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const form=event.currentTarget,button=form.querySelector('button[type="submit"]');
      const selected=(d.writeoff_candidates||[]).find(x=>Number(x.return_line_id)===Number(form.elements.return_line_id.value));
      const quantity=Number(form.elements.quantity.value);
      if(!selected||!Number.isSafeInteger(quantity)||quantity<1||quantity>Number(selected.remaining_quantity)){
        toast('كمية التسوية لا تطابق رصيد المرتجع المرفوض',true);return;
      }
      if(!form.elements.physical_disposal_confirmed.checked){
        toast('يجب تأكيد الإزالة المادية قبل تقديم المحضر',true);return;
      }
      button.disabled=true;
      try{await apply('/api/inventory/writeoffs',{
        return_line_id:Number(form.elements.return_line_id.value),quantity,
        disposed_on:form.elements.disposed_on.value,reason:form.elements.reason.value,
        evidence_ref:form.elements.evidence_ref.value,physical_disposal_confirmed:true,
        request_id:requestId()},'أُرسل طلب تسوية التلف للمراجع؛ لا يوجد خصم أو قيد قبل الاعتماد');}
      finally{button.disabled=false;}
    });
    $('#invWriteoffForm [name="return_line_id"]')?.addEventListener('change',event=>{
      const selected=(d.writeoff_candidates||[]).find(x=>Number(x.return_line_id)===Number(event.target.value));
      const qty=$('#invWriteoffForm [name="quantity"]');if(qty&&selected)qty.max=Number(selected.remaining_quantity);
    });
    $('#invDueScheduleForm [name="invoice_match_id"]')?.addEventListener('change',event=>{
      const inv=eligibleDue.find(x=>Number(x.id)===Number(event.target.value));
      if(!inv)return;
      $$('#invDueLines [name="due_on"]').forEach(field=>{
        field.min=inv.invoice_date;
        if(field.value<inv.invoice_date)field.value=inv.invoice_date;
      });
    });
    $('#invAddInstallment')?.addEventListener('click',()=>{
      const holder=$('#invDueLines');
      if(holder.querySelectorAll('.inv-due-line').length>=12){toast('حد أقصى 12 قسطًا',true);return;}
      const inv=eligibleDue.find(x=>Number(x.id)===Number($('#invDueScheduleForm').elements.invoice_match_id.value));
      holder.insertAdjacentHTML('beforeend',installmentRow(inv?.invoice_date));
    });
    $('#invDueScheduleForm')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const el=event.currentTarget,button=el.querySelector('button[type="submit"]');
      const lines=[...el.querySelectorAll('.inv-due-line')].map(row=>({
        due_on:row.querySelector('[name="due_on"]').value,
        amount:row.querySelector('[name="amount"]').value}));
      if(lines.length<1||lines.length>12||lines.some(line=>!line.due_on||!line.amount)){
        toast('أكمل تاريخ ومبلغ كل قسط',true);return;
      }
      const fields=Object.fromEntries(new FormData(el));
      const invoice=eligibleDue.find(x=>Number(x.id)===Number(fields.invoice_match_id));
      const total=lines.reduce((sum,line)=>sum+Math.round(Number(line.amount)*100),0);
      if(!invoice||!lines.every(line=>Number(line.amount)>0)||total!==Number(invoice.amount_piasters)){
        toast('مجموع الأقساط لا يساوي القيمة الأصلية لفاتورة المورد',true);return;
      }
      button.disabled=true;
      try{await apply('/api/inventory/supplier-due-schedules',{
        invoice_match_id:Number(fields.invoice_match_id),scheduled_on:fields.scheduled_on,
        terms_ref:fields.terms_ref,lines,request_id:requestId()},
        'تم إرسال مواعيد الاستحقاق للمراجعة؛ لم يجر أي دفع أو قيد جديد');}
      finally{button.disabled=false;}
    });
    $$('#content [data-inv-due-decision]').forEach(button=>button.addEventListener('click',async()=>{
      const [id,decision]=button.dataset.invDueDecision.split(':');
      const data=await modal(decision==='approve'?'اعتماد شروط السداد':'رفض شروط السداد',
        'راجع تواريخ ومبالغ كل قسط بالمستند قبل الاعتماد؛ لا يعتبر القرار إذن صرف.',
        [{name:'note',label:'مبرر القرار (8 أحرف على الأقل)',required:true}]);
      if(data)await apply(`/api/inventory/supplier-due-schedules/${Number(id)}/decision`,
        {decision,note:data.note},'تم حفظ مراجعة شروط المورد دون حركة نقدية');
    }));
    $('#invPaymentRequestForm [name="due_line_id"]')?.addEventListener('change',event=>{
      const line=paymentEligible.find(x=>Number(x.id)===Number(event.target.value));
      const amount=$('#invPaymentRequestForm [name="amount"]');
      if(line&&amount)amount.max=(Number(line.available_to_request_piasters)/100).toFixed(2);
    });
    $('#invPaymentRequestForm')?.addEventListener('submit',async event=>{
      event.preventDefault();
      const form=event.currentTarget,btn=form.querySelector('button[type="submit"]');
      const fields=Object.fromEntries(new FormData(form));
      const source=paymentEligible.find(x=>Number(x.id)===Number(fields.due_line_id));
      const amount=Math.round(Number(fields.amount)*100);
      if(!source||!Number.isSafeInteger(amount)||amount<=0||amount>Number(source.available_to_request_piasters)){
        toast('المبلغ أكبر من الحد المتاح للموافقة أو غير صالح',true);return;
      }
      btn.disabled=true;
      try{await apply('/api/inventory/supplier-payment-requests',{
        due_line_id:Number(fields.due_line_id),requested_on:fields.requested_on,
        amount:fields.amount,evidence_ref:fields.evidence_ref,request_id:requestId()},
        'تم إرسال طلب الموافقة التمهيدي؛ لا يوجد صرف نقدي أو تحويل أو قيد جديد');}
      finally{btn.disabled=false;}
    });
    $$('#content [data-inv-payment-decision]').forEach(button=>button.addEventListener('click',async()=>{
      const [id,decision]=button.dataset.invPaymentDecision.split(':');
      const data=await modal(decision==='approve'?'اعتماد طلب صرف تمهيدي':'رفض طلب صرف تمهيدي',
        'راجع اسم المورد ورقم الفاتورة وتاريخ القسط والمبلغ؛ اعتمادك لا يسدد الفاتورة ولا يخرج أموالًا.',
        [{name:'note',label:'مبرر المراجعة (8 أحرف على الأقل)',required:true}]);
      if(data)await apply(`/api/inventory/supplier-payment-requests/${Number(id)}/decision`,
        {decision,note:data.note},'تم تسجيل قرار المراجعة دون أي حركة مالية');
    }));
    $('#invPurchaseOrderForm')?.addEventListener('submit',async event=>{
      event.preventDefault();const el=event.currentTarget,b=el.querySelector('button[type="submit"]');b.disabled=true;
      const f=Object.fromEntries(new FormData(el));
      await apply('/api/inventory/purchase-orders',{
        vendor_id:Number(f.vendor_id),ordered_on:f.ordered_on,order_ref:f.order_ref,
        evidence_ref:f.evidence_ref,request_id:requestId(),
        lines:[{item_id:Number(f.item_id),quantity:Number(f.quantity),unit_cost:f.unit_cost}]},
        'أُرسل أمر الشراء لاعتماد مستقل؛ لم يتم تسجيل دين أو مخزون');b.disabled=false;
    });
    const invoiceMatchForm=$('#invSupplierInvoiceForm');
    function syncInvoiceSource(){
      if(!invoiceMatchForm)return;
      const r=invoiceReceipts.find(x=>Number(x.id)===Number(invoiceMatchForm.elements.receipt_id.value));
      if(r){
        invoiceMatchForm.elements.invoice_ref.value=r.invoice_ref;
        invoiceMatchForm.elements.amount.value='';
        const lines=(d.purchase_receipt_lines||[]).filter(x=>Number(x.receipt_id)===Number(r.id));
        const holder=$('#invInvoiceLines');
        holder.innerHTML=lines.length?lines.map(x=>`<div class="inv-match-row" data-item-id="${Number(x.item_id)}">`+
          `<p class="section-subtitle">${esc(x.item_code)} — ${esc(x.item_name)} (محضر الاستلام: ${integer(x.quantity)} × ${fmt(x.unit_cost_piasters)} جنيه)</p>`+
          field('','كمية البند من فاتورة المورد',input('quantity','number','min="1" step="1" max="1000000"'))+
          field('','سعر الوحدة في فاتورة المورد',input('unit_cost','number','min="0.01" step="0.01"'))+
          `</div>`).join(''):empty('لم تتوفر تفاصيل الأصناف لهذا الاستلام؛ لا يمكن تقديم مطابقة موثوقة.');
      }
    }
    invoiceMatchForm?.elements.receipt_id.addEventListener('change',syncInvoiceSource);
    syncInvoiceSource();
    invoiceMatchForm?.addEventListener('submit',async event=>{
      event.preventDefault();const el=event.currentTarget,b=el.querySelector('button[type="submit"]');b.disabled=true;
      const f=Object.fromEntries(new FormData(el));
      const lines=[...el.querySelectorAll('#invInvoiceLines .inv-match-row')].map(row=>({
        item_id:Number(row.dataset.itemId),quantity:Number(row.querySelector('[name="quantity"]').value),
        unit_cost:row.querySelector('[name="unit_cost"]').value}));
      if(!lines.length||lines.some(x=>!Number.isSafeInteger(x.item_id)||!Number.isSafeInteger(x.quantity)||x.quantity<1||!x.unit_cost)){
        toast('أدخل بنود فاتورة المورد الأصلية بالكامل قبل المطابقة',true);b.disabled=false;return;
      }
      await apply('/api/inventory/supplier-invoices',{
        receipt_id:Number(f.receipt_id),invoice_date:f.invoice_date,invoice_ref:f.invoice_ref,
        amount:f.amount,evidence_ref:f.evidence_ref,lines,request_id:requestId()},
        'أُرسلت فاتورة المورد للمطابقة المستقلة دون أي قيد إضافي');b.disabled=false;
    });
    $('#invReceiptForm')?.addEventListener('submit',async event=>{
      event.preventDefault();const el=event.currentTarget, b=el.querySelector('button[type="submit"]');b.disabled=true;
      const f=Object.fromEntries(new FormData(el));
      const data={vendor_id:Number(f.vendor_id),received_on:f.received_on,
        purchase_order_id:f.purchase_order_id?Number(f.purchase_order_id):null,
        invoice_ref:f.invoice_ref,evidence_ref:f.evidence_ref,
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
      const procurement=['purchase-orders','supplier-invoices'].includes(kind);
      const data=await modal(decision==='approve'?'اعتماد مستند المخزن':'رفض مستند المخزن',
        procurement?'الاعتماد هنا إداري ومطابقة مستندات فقط: لا تنشأ قيود نقدية أو ديون جديدة، ويُشترط مراجع مستقل.':
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
