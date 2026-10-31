"use strict";
/* V8.1C: trial invoices, collections, credits/refunds and advances; cash movements require an open shift. */
const billingState={pointId:null,caseId:null,pending:{}};
const billingKinds={outpatient:"خدمات خارجية",inpatient:"حجز داخلي",operation:"عملية",nicu:"حضانة"};
const billingLineStates={ordered:"بانتظار إثبات تنفيذ الخدمة",fulfilled:"خدمة منفذة",cancelled:"ملغاة"};
function billingCatalog(services){
 if(!services.length)return empty('لم تُسجل أي خدمات بعد. أضف خدمات وأسعارًا وهمية للتجربة.');
 const action=s=>`<button class="btn btn-small btn-outline" data-billing-price="${s.id}">إضافة سعر بتاريخ سريان</button>`;
 return `<div class="billing-catalog-desktop">${table(['كود الخدمة','الخدمة','القسم','السعر الحالي','إجراء'],services.map(s=>`<tr><td>${esc(s.code)}</td><td>${esc(s.name)}</td><td>${esc(s.department_name)}</td><td>${s.current_price_piasters?fmt(s.current_price_piasters)+' ج.م':'غير محدد'}</td><td>${action(s)}</td></tr>`).join(''))}</div>`+
 `<div class="billing-catalog-mobile">${services.map(s=>`<div class="billing-catalog-card"><strong>${esc(s.name)}</strong><small>${esc(s.code)} · ${esc(s.department_name)}</small><span>${s.current_price_piasters?fmt(s.current_price_piasters)+' ج.م':'غير محدد'}</span>${action(s)}</div>`).join('')}</div>`;
}
const billingKey=()=>globalThis.crypto?.randomUUID?.() || (`b${Date.now().toString(36)}${Math.random().toString(36).slice(2,16)}`);
async function billingMutation(group,path,payload){
 const signature=JSON.stringify(payload),cached=billingState.pending[group];
 const key=(cached?.signature===signature?cached.key:billingKey());
 billingState.pending[group]={signature,key};
 const result=await post(path,{...payload,request_id:key});
 delete billingState.pending[group];
 return result;
}
async function billingAction(button,fn){
 if(button.disabled)return;
 button.disabled=true;
 try{await fn();}
 catch(e){toast(e.message,true)}
 finally{button.disabled=false}
}

async function renderBilling(){
 const cfg=await api('/api/billing/config');
 const points=cfg.points||[];
 if(!points.length){
   $('#content').innerHTML=head('الحالات والفواتير','لا توجد نقطة تحصيل مخصصة لحسابك','اطلب من مدير النظام تعيين حسابك إلى الكاشير الخارجي أو خزينة الحسابات الداخلية.')+
      `<div class="info-box warning">${ico('lock')}<div>لن يظهر لك أي ملف مريض أو مبلغ بدون صلاحية رسمية.</div></div>`;
   return;
 }
 if(!points.some(x=>x.id===billingState.pointId))billingState.pointId=points[0].id;
 const point=points.find(x=>x.id===billingState.pointId);
 const list=await api(`/api/billing/cases?point_id=${point.id}`);
 let selected=null, finance=null, adjustments=null, settlement=null;
 if(billingState.caseId){
   try{selected=await api(`/api/billing/cases/${billingState.caseId}`)}
   catch{billingState.caseId=null}
   if(selected&&selected.case.default_point_id!==point.id){selected=null;billingState.caseId=null}
   if(selected)finance=await api(`/api/billing/cases/${billingState.caseId}/finance`);
   if(selected)adjustments=await api(`/api/billing/cases/${billingState.caseId}/adjustments`);
   if(selected&&['inpatient','nicu','operation'].includes(selected.case.kind))settlement=await api(`/api/case-settlement/cases/${billingState.caseId}`);
 }
 const owner=state.me.role==='owner';
 const cashier=['owner','clerk'].includes(state.me.role);
 const canFulfill=['owner','reviewer'].includes(state.me.role);
 const canReview=['owner','reviewer'].includes(state.me.role);
 const services=cfg.services||[];
 $('#content').innerHTML=head('الإدارة المالية للمرضى','الحالات والفواتير','نظام واحد بنقطتي تحصيل مستقلتين، والملف المالي يتبع الحالة وليس الدور الذي أُجريت فيه الخدمة.',
      owner?`<button id="billingCatalog" class="btn btn-secondary">${ico('plus')} خدمة وسعر</button><button id="billingAssign" class="btn btn-secondary">${ico('users')} صلاحيات نقاط التحصيل</button><button id="billingFundsSetup" class="btn btn-secondary">${ico('wallet')} ربط خزنة</button><button id="billingChannelSetup" class="btn btn-secondary">${ico('settings')} إعداد طرق الدفع</button>`:'')+
   `<div class="billing-alert" role="status">${ico('alert')}<div><strong>وضع التجربة G2P — ملفات حالات وفواتير وتسويات مالية وهمية</strong><span>تُرحّل الفواتير التجريبية إلى الذمم، والمدفوعات إلى خزنة الوردية أو حساب المقاصة. لا تستخدم بيانات مرضى حقيقية ولا تعتمد المستندات ضريبيًا قبل الموافقة النهائية.</span></div></div>`+
   `<div class="billing-points" role="group" aria-label="اختر نقطة التحصيل">${points.map(p=>`<button class="billing-point ${p.id===point.id?'selected':''}" data-billing-point="${p.id}" aria-pressed="${p.id===point.id}">${ico(p.kind==='external'?'wallet':'file')}<strong>${esc(p.name)}${p.active?'':' (موقوفة حاليًا)'}</strong><span>${p.kind==='external'?'العيادات والمعمل والأشعة والخدمات الخارجية':'الحالات الداخلية والعمليات والحضانة'}</span><small>${p.fund_id?'الخزنة محددة':'الخزنة غير مرتبطة'}</small></button>`).join('')}</div>`+
   `<div class="billing-shift-state"><span>${point.active_shift?`وردية ${esc(point.active_shift.shift)} — ${esc(point.active_shift.status)}${point.own_open_shift?' · عهدتك الحالية':''}`:'لا توجد وردية مفتوحة'}</span>${cashier&&point.fund_id&&!point.active_shift?`<button id="billingOpenShift" class="btn btn-small btn-outline">فتح وردية الكاشير</button>`:''}</div><div class="billing-two-col"><section class="panel billing-block"><div class="billing-block-head"><div><h2>ملفات الحالات</h2><p>${esc(point.name)} · حالات وخدمات وفواتير وذمم مالية</p></div>${cashier?`<div class="billing-actions"><button id="billingNewCase" class="btn btn-primary">${ico('plus')} حالة جديدة</button><button id="billingExistingCase" class="btn btn-secondary">مريض سابق</button><button id="billingCrossPoint" class="btn btn-secondary">تحصيل حالة من نقطة أخرى</button></div>`:''}</div>`+
   `<div class="billing-case-list">${(list.items||[]).length?list.items.map(k=>`<button type="button" class="billing-case-item ${billingState.caseId===k.id?'selected':''}" data-billing-open-case="${k.id}"><span><strong>${esc(k.case_no)}</strong><small>${esc(k.patient_name)} · ${esc(billingKinds[k.kind]||k.kind)}</small></span><span class="billing-amount">${fmt(k.unbilled_piasters)} ج.م <small>منفذ غير مفوتر</small></span></button>`).join(''):empty('لا توجد حالات في نقطة التحصيل هذه بعد.')}</div></section>`+
   `<section class="panel billing-block" id="billingDetails">${selected?renderBillingCasePanel(selected,cfg,{cashier,canFulfill,canReview,owner},finance,adjustments,settlement):`<div class="billing-blank">${ico('file')}<h2>الملف المالي للحالة</h2><p>اختر حالة من القائمة لعرض خدماتها، ومراجعة السعر، وتجهيز مسودة الفاتورة.</p><small>يمكن إضافة نفس الخدمة إلى حالة داخلية حتى لو أُجريت في المعمل أو الأشعة.</small></div>`}</section></div>`+
   `${owner?`<section class="panel billing-block billing-catalog"><div class="billing-block-head"><div><h2>كتالوج الخدمات والأسعار</h2><p>الأسعار المعتمدة لا تتغير على الخدمات المسجلة سابقًا</p></div></div>${billingCatalog(services)}</section>`:''}`;
 bindBillingActions({point,cfg,selected,owner,cashier,canFulfill,canReview,finance,adjustments});
 bindBillingSettlementActions(selected,settlement,{cashier,canReview,owner,userId:state.me.id});
}

function renderBillingCasePanel(info,cfg,perms,finance,adjustments,settlement){
 perms={...perms,cashier:perms.cashier&&info.case.status==='open',canFulfill:perms.canFulfill&&info.case.status==='open'};
 const c=info.case;
 const lines=info.services||[];
 const drafts=info.drafts||[];
 const ready=lines.filter(x=>x.state==='fulfilled').length;
 return `<div class="billing-block-head"><div><span class="billing-eyebrow">الملف ${esc(c.case_no)}</span><h2>${esc(c.patient_name)}</h2><p>${esc(c.patient_code)} · ${esc(billingKinds[c.kind]||c.kind)} · ${esc(c.business_date)}</p></div>${perms.cashier?`<button id="billingAddLine" class="btn btn-primary">${ico('plus')} إضافة خدمة</button>`:''}</div>`+
   `<div class="billing-stats"><div><span>خدمات مسجلة</span><strong>${integer(lines.length)}</strong></div><div><span>خدمات منفذة</span><strong>${integer(ready)}</strong></div><div><span>منفذ غير مفوتر</span><strong>${fmt(info.unbilled_piasters)} ج.م</strong></div></div>`+
   `<div class="billing-divider"></div><div class="billing-section-title"><h3>خدمات الحالة</h3><small>الفاتورة بعد إثبات التنفيذ فقط</small></div>`+
   (lines.length?`<div class="billing-services-list">${lines.map(x=>`<div class="billing-service-row"><div class="billing-service-main"><strong>${esc(x.service_name_snapshot)}</strong><span>${fmt(x.unit_price_piasters)} × ${integer(x.quantity)} = ${fmt(x.unit_price_piasters*x.quantity)} ج.م</span><small>${esc(billingLineStates[x.state]||x.state)}</small></div><div class="billing-service-actions">${x.state==='ordered'&&perms.canFulfill?`<button class="btn btn-small btn-outline" data-billing-fulfill="${x.id}">إثبات التنفيذ</button>`:''}${x.state==='ordered'&&perms.cashier?`<button class="btn btn-small btn-secondary" data-billing-cancel="${x.id}">إلغاء الطلب</button>`:''}</div></div>`).join('')}</div>`:empty('لم تُضاف خدمات بعد. أضف خدمة بسعرها المعتمد ثم سجّل تنفيذها قبل إعداد المسودة.'))+
   `<div class="billing-divider"></div><div class="billing-section-title"><h3>مسودات الفواتير</h3>${perms.cashier?`<button class="btn btn-small btn-outline" id="billingDraft" ${info.unbilled_piasters<=0?'disabled':''}>${ico('file')} إنشاء مسودة</button>`:''}</div>`+
   (drafts.length?`<div class="billing-drafts">${drafts.map(d=>`<div class="billing-draft-row"><button class="billing-draft" data-billing-draft="${d.id}"><span>${esc(d.draft_no)}<small>${(info.invoices||[]).some(x=>x.draft_id===d.id)?'تم إصدارها وترحيلها':'مسودة غير مرحلة'}</small></span><strong>${fmt(d.total_piasters)} ج.م</strong></button>${perms.cashier&&!(info.invoices||[]).some(x=>x.draft_id===d.id)?`<button class="btn btn-small btn-primary" data-billing-issue="${d.id}">إصدار فاتورة</button>`:''}</div>`).join('')}</div>`:empty('لم تُنشأ مسودات.'))+
   renderBillingFinance(finance,perms)+renderBillingAdjustments(adjustments,finance,perms)+renderBillingSettlement(settlement,{...perms,userId:state.me.id});
}


function renderBillingSettlement(state,perms){
 if(!state)return '';
 const p=state.preflight, reqs=state.requests||[];
 const latest=reqs[0],pending=reqs.find(r=>r.status==='pending'),approved=reqs.find(r=>r.status==='approved');
 const overview=`<div class="billing-stats"><div><span>فواتير صادرة</span><strong>${integer(p.invoice_count)}</strong></div><div><span>المتبقي</span><strong>${fmt(p.outstanding_piasters)} ج.م</strong></div><div><span>مقدم غير مخصص</span><strong>${fmt(p.advance_available_piasters)} ج.م</strong></div></div>`;
 const blockers=p.no_charge_ready?'<p class="billing-clearance-ready">لم تُسجل خدمات منفذة أو فواتير أو مدفوعات. يمكن للمالك طلب إلغاء مالي بدون رسوم مع اعتماد مستقل.</p>':
   p.blockers.length?`<ul class="billing-clearance-checks">${p.blockers.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:
   `<p class="billing-clearance-ready">كل الفواتير والخدمات والذمم الحالية مستوفية لشروط التصفية المالية.</p>`;
 const noCharge=perms.owner&&p.no_charge_ready;
 const action=p.status==='closed'?`<strong class="billing-clearance-status">${approved?.clearance_mode==='no_charge'?'أُلغيت الحالة بلا رسوم بعد اعتماد مستقل':'تم إغلاق الملف المالي بعد اعتماد مستقل'}</strong>`:
   pending?`<div class="billing-clearance-status">${pending.clearance_mode==='no_charge'?'طلب إلغاء حجز بلا رسوم':'طلب التصفية المالية'} #${integer(pending.id)} بانتظار مراجع مختلف عن مقدم الطلب</div>`+
     (perms.canReview&&Number(pending.requested_by)!==Number(perms.userId)?`<div class="billing-actions"><button class="btn btn-primary btn-small" data-case-clearance="${pending.id}" data-clearance-decision="approve">${pending.clearance_mode==='no_charge'?'اعتماد إلغاء الحجز':'اعتماد الإغلاق المالي'}</button><button class="btn btn-outline btn-small" data-case-clearance="${pending.id}" data-clearance-decision="reject">رفض الطلب</button></div>`:''):
   p.ready&&perms.cashier?'<button id="billingClearanceRequest" class="btn btn-primary btn-small">طلب تصفية مالية نهائية</button>':
   noCharge?'<button id="billingClearanceNoCharge" class="btn btn-outline btn-small">إلغاء حالة بلا خدمات أو معاملات مالية</button>':
   '<p class="billing-clearance-hint">عالج البنود غير المكتملة قبل إرسال التصفية للمراجعة.</p>';
 return `<div class="billing-divider"></div><section class="billing-clearance" aria-labelledby="billingClearanceHeading">
   <div class="billing-section-title"><h3 id="billingClearanceHeading">التصفية المالية للحالة</h3><small>الداخلي / العمليات / الحضانة</small></div>
   <p class="billing-clearance-notice">الاعتماد المالي لا يُعد خروجًا طبيًا، ولا إثباتًا لمطابقة البنك أو جرد الخزنة.</p>
   ${overview}${blockers}${action}
   ${approved?`<p class="billing-clearance-meta">مرجع الإثبات: ${esc(approved.evidence_reference)} · تاريخ الإغلاق المالي: ${esc(approved.closed_on||'')}</p>`:''}
   ${latest?.status==='rejected'?`<p class="billing-clearance-meta">آخر طلب مرفوض: ${esc(latest.decision_note||'')}</p>`:''}
 </section>`;
}

async function bindBillingSettlementActions(selected,settlement,perms){
 if(!selected||!settlement)return;
 $$('#billingClearanceRequest,#billingClearanceNoCharge').forEach(button=>button.addEventListener('click',async()=>{
   const zeroCharge=button.id==='billingClearanceNoCharge';
   const form=await modal(zeroCharge?'إلغاء حالة بلا رسوم':'طلب إقفال الملف المالي',
    'الطلب لا يثبت خروج المريض طبيًا، ولا ينشئ تحصيلًا. مرجع إثبات مستقل مطلوب.',[
      {name:'evidence_reference',label:zeroCharge?'مرجع محضر إلغاء الحجز (لا تكتب تشخيصًا)':'مرجع مستند استكمال الخدمة / الخروج (لا تكتب تشخيصًا)',required:true,placeholder:zeroCharge?'ADMISSION-CANCEL-001':'IPD-CLEARANCE-0001'},
      {name:'note',label:'ملاحظات التصفية المالية',required:true,placeholder:'تمت مراجعة الخدمات والفواتير والذمم دون أرصدة معلقة'}]);
   if(!form)return;
   try{await billingMutation('financial-clearance-'+selected.case.id,
      `/api/case-settlement/cases/${selected.case.id}/request`,{...form,mode:zeroCharge?'no_charge':'settled'});
      toast('تم إرسال طلب التصفية لمراجع مستقل');navigate('billing');}
   catch(e){toast(e.message,true)}
 }));
 $$('[data-case-clearance]').forEach(b=>b.addEventListener('click',async()=>{
   const decision=b.dataset.clearanceDecision;
   const form=await modal(decision==='approve'?'اعتماد التصفية المالية':'رفض التصفية المالية',
      'تتم مراجعة الأرصدة والخدمات مرة أخرى لحظة الاعتماد؛ لا توجد حركة نقدية أو إذن خروج طبي.',[
      {name:'note',label:'مبرر القرار (12 حرفًا على الأقل)',required:true}]);
   if(!form)return;
   await billingAction(b,async()=>{
      await post(`/api/case-settlement/requests/${Number(b.dataset.caseClearance)}/decision`,
        {decision,note:form.note});
      toast(decision==='approve'?'تم إغلاق الملف المالي فقط':'تم رفض التصفية مع الاحتفاظ بالمحضر');navigate('billing');
   });
 }));
}

function renderBillingAdjustments(adjustments,finance,perms){
 if(!adjustments||!finance)return '';
 const credits=adjustments.credits||[],refunds=adjustments.refunds||[];
 const labels={pending:'\u0628\u0627\u0646\u062a\u0638\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629',
  approved:'\u0645\u0639\u062a\u0645\u062f',rejected:'\u0645\u0631\u0641\u0648\u0636',paid:'\u062a\u0645 \u0627\u0644\u0635\u0631\u0641'};
 const eligible=perms.cashier&&(finance.invoices||[]).length;
 return `<div class="billing-divider"></div><div class="billing-section-title"><h3>\u0627\u0644\u0625\u0634\u0639\u0627\u0631\u0627\u062a \u0627\u0644\u062f\u0627\u0626\u0646\u0629 \u0648\u0627\u0644\u0645\u0631\u062a\u062c\u0639\u0627\u062a</h3><small>\u0628\u0645\u0648\u0627\u0641\u0642\u0629 \u0645\u0633\u062a\u0642\u0644\u0629 \u0641\u0642\u0637</small></div>`+
  `<div class="billing-stats"><div><span>\u0631\u0635\u064a\u062f \u0631\u062f \u0627\u0644\u0625\u0634\u0639\u0627\u0631\u0627\u062a</span><strong>${fmt(adjustments.credit_refundable_piasters||0)} \u062c.\u0645</strong></div><div><span>\u0645\u0642\u062f\u0645 \u0642\u0627\u0628\u0644 \u0644\u0644\u0631\u062f</span><strong>${fmt(adjustments.advance_refundable_piasters||0)} \u062c.\u0645</strong></div></div>`+
  (perms.cashier?`<div class="billing-actions">${eligible?'<button id="billingCreditRequest" class="btn btn-small btn-outline">\u0637\u0644\u0628 \u0625\u0634\u0639\u0627\u0631 \u062f\u0627\u0626\u0646</button>':''}<button id="billingRefundRequest" class="btn btn-small btn-outline">\u0637\u0644\u0628 \u0631\u062f \u0645\u0628\u0644\u063a</button></div>`:'')+
  [...credits.map(x=>`<div class="billing-invoice-card"><div><strong>${esc(x.credit_no)}</strong><small>${fmt(x.amount_piasters)} \u062c.\u0645 · ${esc(labels[x.status]||x.status)}</small></div>${perms.canReview&&x.status==='pending'?`<div class="billing-actions"><button class="btn btn-small btn-primary" data-billing-credit-decision="${x.id}" data-decision="approve">\u0642\u0628\u0648\u0644</button><button class="btn btn-small btn-outline" data-billing-credit-decision="${x.id}" data-decision="reject">\u0631\u0641\u0636</button></div>`:''}</div>`),
   ...refunds.map(x=>`<div class="billing-invoice-card"><div><strong>${esc(x.refund_no)}</strong><small>${fmt(x.amount_piasters)} \u062c.\u0645 · ${esc(x.method)} · ${esc(labels[x.status]||x.status)}</small></div><div class="billing-actions">${perms.canReview&&x.status==='pending'?`<button class="btn btn-small btn-primary" data-billing-refund-decision="${x.id}" data-decision="approve">\u0642\u0628\u0648\u0644</button><button class="btn btn-small btn-outline" data-billing-refund-decision="${x.id}" data-decision="reject">\u0631\u0641\u0636</button>`:''}${perms.cashier&&x.status==='approved'?`<button class="btn btn-small btn-primary" data-billing-refund-pay="${x.id}">\u0635\u0631\u0641 \u0627\u0644\u0631\u062f</button>`:''}</div></div>`)
  ].join('');
}

function renderBillingFinance(finance,perms){
 if(!finance)return '';
 const invs=finance.invoices||[],collections=finance.collections||[];
 const isLate=!!finance.late_recovery;
 const settledLate=Number(finance.late_cash_settlement?.settled_piasters||0);
 return `<div class="billing-divider"></div><div class="billing-section-title"><h3>التحصيل والذمم</h3><small>تجريبي فقط · غير صالح للاستخدام الحقيقي</small></div>`+
  (isLate?`<div class="info-box ${settledLate?'':'warning'}">${ico(settledLate?'check':'alert')}<div><strong>حالة مستدركة من يوم سابق</strong>
     <p>تاريخ الخدمة الأصلي: ${esc(finance.late_recovery.original_business_date)}. ${settledLate?`تم تخصيص ${fmt(settledLate)} جنيه من نقدية مثبتة سابقًا بالخزنة، دون إنشاء قبض جديد. راجع المتبقي قبل اعتبار الحالة مسددة.`:'التحصيل النقدي القديم ممنوع من هذه الشاشة إلى أن يطابق المحاسب الظرف والخزنة؛ إصدار الفاتورة لا يعني استلام المال.'} (بلاغ #${integer(finance.late_recovery.incident_id)}).</p></div></div>`:'')+
  `<div class="billing-stats"><div><span>الفواتير الصادرة</span><strong>${fmt(finance.total_invoiced_piasters)} ج.م</strong></div><div><span>المتبقي</span><strong>${fmt(finance.outstanding_piasters)} ج.م</strong></div><div><span>المقدم المتاح</span><strong>${fmt(finance.advance_available_piasters)} ج.م</strong></div></div>`+
  (invs.length?`<div class="billing-invoices">${invs.map(i=>`<div class="billing-invoice-card"><div><strong>${esc(i.invoice_no)}</strong><small>${fmt(i.total_piasters)} ج.م — المتبقي ${fmt(i.due_piasters)} ج.م</small></div><div class="billing-actions">${i.due_piasters>0&&perms.cashier&&!isLate?`<button class="btn btn-small btn-primary" data-billing-collect="${i.id}">تحصيل</button>${finance.advance_available_piasters?`<button class="btn btn-small btn-outline" data-billing-apply="${i.id}">تخصيص مقدم</button>`:''}`:''}<button class="btn btn-small btn-outline" data-billing-correction="invoice:${i.id}">الإبلاغ عن خطأ</button></div></div>`).join('')}</div>`:empty('لم تُصدر فاتورة بعد.'))+
  (perms.cashier&&!isLate?`<button id="billingAdvance" class="btn btn-secondary">تسجيل مقدم حالة (بدون فاتورة)</button>`:'')+
  `<div class="billing-divider"></div><div class="billing-section-title"><h3>الإيصالات المسجلة</h3><small>كل تحصيل مرتبط بالوردية</small></div>`+
  (collections.length?`<div class="billing-invoices">${collections.map(x=>{
    const moved=!!x.reallocation_id, incoming=moved&&x.original_case_id!==x.effective_case_id;
    const label=moved?(incoming?'مخصص لهذه الحالة بعد تصحيح مستقل':'الإيصال الأصلي — نُقل تخصيصه لحالة أخرى'):(x.kind==='advance'?'مقدم مريض':'سداد فاتورة');
    const receipt=`<span>${esc(x.collection_no)}<small>${esc(label)} · ${esc(x.business_date)}</small></span><strong>${fmt(x.total_piasters)} ج.م</strong>`;
    return `<div class="billing-draft-row">${incoming?`<div class="billing-draft">${receipt}</div>`:`<button class="billing-draft" data-billing-receipt="${x.id}">${receipt}</button>`}${!moved?`<button class="btn btn-small btn-outline" data-billing-correction="collection:${x.id}">الإبلاغ عن خطأ</button>`:''}</div>`;
  }).join('')}</div>`:empty('لا توجد مدفوعات مسجلة.'));
}

async function billingPaymentForm({caseId,point,invoiceId,patientCode,cfg}){
 if(!point.own_open_shift){toast('افتح ورديتك الحالية أولًا لتسجيل مدفوعات باسمها',true);return;}
 const methods=[['cash','نقدي'],...(cfg.payment_channels||[]).map(x=>[x.method,{card:'بطاقة POS',instapay:'InstaPay',wallet:'محفظة',transfer:'تحويل تحت التسوية'}[x.method]])];
 const form=await modal(invoiceId?'تحصيل فاتورة تجريبية':'تسجيل مقدم تجريبي','اختر وسيلة أو وسيلتين؛ المبالغ الإلكترونية تذهب لحساب مقاصة وليس حساب بنك مباشر.',[
   {name:'method_1',type:'select',label:'طريقة الدفع الأولى',options:methods,required:true},
   {name:'amount_1',type:'number',label:'المبلغ الأول بالجنيه',required:true,step:'0.01'},
   {name:'method_2',type:'select',label:'طريقة دفع ثانية (اختياري)',options:methods},
   {name:'amount_2',type:'number',label:'مبلغ الدفع الثاني (اختياري)',step:'0.01'}]);
 if(!form)return;
 const parts=[{method:form.method_1,amount:form.amount_1}];
 if(form.method_2&&form.amount_2)parts.push({method:form.method_2,amount:form.amount_2});
 if((form.method_2&&!form.amount_2)||(!form.method_2&&form.amount_2)){
   toast('أكمل طريقة الدفع الثانية والمبلغ معًا',true);return;
 }
 const data=await billingMutation('cashier-collect-'+caseId,`/api/billing/cases/${caseId}/collect`,
   {point_id:point.id,invoice_id:invoiceId||null,patient_code:patientCode||'',parts});
 toast('سُجل التحصيل التجريبي '+data.collection_no+'؛ راجع اليومية قبل أي اعتماد');
 if(patientCode){
   try{
     const receipt=await api(`/api/billing/collections/${data.id}`);
     await modal('إيصال كاشير عن حالة من نقطة أخرى',`<strong>${esc(receipt.collection_no)}</strong><p>${esc(receipt.case_no)}</p>`+
       receipt.parts.map(x=>`<p>${esc(x.method)}: ${fmt(x.amount_piasters)} ج.م</p>`).join('')+
       `<strong>الإجمالي: ${fmt(receipt.total_piasters)} ج.م</strong><p>${esc(receipt.watermark)}</p>`);
   }catch(e){toast('تم حفظ التحصيل، لكن تعذر عرض الإيصال: '+e.message,true)}
 }
 await navigate('billing');
}

function bindBillingActions({point,cfg,selected,owner,cashier,canFulfill,finance}){
 $('#billingOpenShift')?.addEventListener('click',async()=>{
   const suggested=cfg.suggested_shift||{business_date:new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'}),shift:'morning'};
   const choices=(cfg.shift_schedule||[]).map(x=>[x.code,`${({night:'\u0633\u0647\u0631',morning:'\u0635\u0628\u0627\u062d\u064a',evening:'\u0645\u0633\u0627\u0626\u064a'})[x.code]} ${x.start}-${x.end}`]);
   choices.sort((a,b)=>Number(b[0]===suggested.shift)-Number(a[0]===suggested.shift));
   const form=await modal('فتح وردية الكاشير','\u064a\u062a\u0628\u0639 \u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0633\u0647\u0631 \u064a\u0648\u0645 \u0628\u062f\u0627\u064a\u062a\u0647 \u0639\u0646\u062f \u0645\u0646\u062a\u0635\u0641 \u0627\u0644\u0644\u064a\u0644.',[
      {name:'business_date',type:'date',label:'\u062a\u0627\u0631\u064a\u062e \u0628\u062f\u0627\u064a\u0629 \u0627\u0644\u0648\u0631\u062f\u064a\u0629',value:suggested.business_date,required:true},
      {name:'shift',type:'select',label:'نوع الوردية',required:true,options:choices.length?choices:[['night','\u0633\u0647\u0631'],['morning','\u0635\u0628\u0627\u062d\u064a'],['evening','\u0645\u0633\u0627\u0626\u064a']]}]);
   if(!form)return;
   await billingAction($('#billingOpenShift'),async()=>{
     await post('/api/shifts/open',{business_date:form.business_date,
       shift:form.shift,fund_id:point.fund_id});toast('وردية جديدة على خزنة الكاشير');navigate('billing');
   });
 });
 $('#billingFundsSetup')?.addEventListener('click',async()=>{
   const funds=(state.lookups.funds||[]);
   const cash=funds.filter(f=>f.kind==='cash');
   const form=await modal('ربط خزنة الكاشير','اختر نقطة التحصيل وخزنتها النقدية. لا يتم تغييرها بعد تسجيل أول قبض.',[
      {name:'point_id',type:'select',label:'النقطة',options:cfg.points.map(x=>[x.id,x.name]),required:true},
      {name:'fund_id',type:'select',label:'الخزنة النقدية',options:cash.map(x=>[x.id,x.name]),required:true}]);
   if(form)await billingAction($('#billingFundsSetup'),async()=>{
      await post(`/api/billing/points/${Number(form.point_id)}/cash-fund`,{fund_id:Number(form.fund_id)});
      toast('تم ربط الخزنة بالنقطة');navigate('billing');
   });
 });
 $('#billingChannelSetup')?.addEventListener('click',async()=>{
   const form=await modal('إعداد طريقة دفع إلكتروني','سنسجل التحصيل في حساب مقاصة مستقل، لا في البنك قبل تسويته.',[
     {name:'method',type:'select',label:'طريقة الدفع',required:true,
       options:[['card','بطاقات POS'],['instapay','InstaPay'],['wallet','محافظ'],['transfer','تحويل تحت التسوية']]},
     {name:'fund_name',label:'اسم حساب مقاصة جديد',required:true,placeholder:'مقاصة POS - تجريبي'}]);
   if(!form)return;
   await billingAction($('#billingChannelSetup'),async()=>{
     const code='bclear_'+form.method;
     const existing=(state.lookups.funds||[]).find(x=>x.code===code);
     const fund=existing||await post('/api/funds',{code,name:form.fund_name,kind:'wallet'});
     await post('/api/billing/channels',{method:form.method,fund_id:fund.id});
     toast('تم تجهيز حساب مقاصة منفصل لهذه الطريقة؛ التحويل للبنك يتطلب مطابقة لاحقًا');
     navigate('billing');
   });
 });
 $('#billingCrossPoint')?.addEventListener('click',async()=>{
   if(!point.own_open_shift){toast('افتح ورديتك أولًا ثم اطلب تحصيل حالة من نقطة أخرى',true);return;}
   const form=await modal('تحصيل لحالة تابعة لنقطة أخرى',
      'أدخل رقم الحالة وكود المريض الكاملين للتأكد من التطابق دون كشف بيانات ملف المريض.',[
     {name:'case_no',label:'رقم الحالة',required:true,placeholder:'CASE-2026-000001'},
     {name:'patient_code',label:'كود المريض',required:true,placeholder:'PT-ABCDEF123456'}]);
   if(!form)return;
   try{
     const res=await api(`/api/billing/crosscase/resolve?case_no=${encodeURIComponent(form.case_no)}&patient_code=${encodeURIComponent(form.patient_code)}&point_id=${point.id}`);
     const invoices=res.unpaid_invoices||[];
     const choice=await modal('اختيار التحصيل','الملف يتبع نقطة أخرى، لكن عهدة القبض ستُسجل باسم ورديتك الحالية.',[
       {name:'invoice_id',label:'الفاتورة أو مقدم',type:'select',required:true,
          options:[['advance','مقدم على الحالة'],...invoices.map(i=>[i.id,`${i.invoice_no} — المتبقي ${fmt(i.due_piasters)} ج.م`])]}]);
     if(!choice)return;
     await billingPaymentForm({caseId:res.case_id,point,invoiceId:choice.invoice_id==='advance'?null:Number(choice.invoice_id),
                              patientCode:form.patient_code,cfg});
   }catch(e){toast(e.message,true)}
 });
 $('#billingCreditRequest')?.addEventListener('click',async()=>{
   const invoices=finance.invoices||[];
   const form=await modal('\u0637\u0644\u0628 \u0625\u0634\u0639\u0627\u0631 \u062f\u0627\u0626\u0646','\u0627\u0644\u0625\u064a\u0631\u0627\u062f \u0648\u0627\u0644\u0630\u0645\u0629 \u064a\u064f\u0635\u062d\u062d\u0627\u0646 \u0628\u0642\u064a\u062f \u0645\u0646\u0641\u0635\u0644.',[
      {name:'invoice_id',label:'\u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629',type:'select',required:true,options:invoices.map(i=>[i.id,i.invoice_no+' · '+fmt(i.total_piasters-(i.credited_piasters||0))])},
      {name:'amount',label:'\u0627\u0644\u0645\u0628\u0644\u063a',type:'number',step:'0.01',required:true},
      {name:'reason',label:'\u0627\u0644\u0633\u0628\u0628',required:true}]);
   if(!form)return;
   try{await billingMutation('credit-request-'+selected.case.id,`/api/billing/cases/${selected.case.id}/credits`,
      {invoice_id:Number(form.invoice_id),amount:form.amount,reason:form.reason});toast('Credit request saved for independent approval');navigate('billing');}
   catch(e){toast(e.message,true)}
 });
 $('#billingRefundRequest')?.addEventListener('click',async()=>{
   const form=await modal('\u0637\u0644\u0628 \u0631\u062f \u0645\u0628\u0644\u063a','\u0627\u0644\u0631\u062f \u064a\u062a\u0637\u0644\u0628 \u0645\u0648\u0627\u0641\u0642\u0629 \u0645\u0633\u062a\u0642\u0644\u0629.',[
      {name:'source',label:'\u0645\u0635\u062f\u0631 \u0627\u0644\u0631\u0635\u064a\u062f',required:true,type:'select',options:[['credit','\u0625\u0634\u0639\u0627\u0631 \u062f\u0627\u0626\u0646'],['advance','\u0645\u0642\u062f\u0645 \u0645\u0631\u064a\u0636']]},
      {name:'method',label:'\u0637\u0631\u064a\u0642\u0629 \u0627\u0644\u0631\u062f',required:true,type:'select',options:[['cash','\u0646\u0642\u062f\u064a'],...(cfg.payment_channels||[]).map(p=>[p.method,p.method])]},
      {name:'amount',label:'\u0627\u0644\u0645\u0628\u0644\u063a',type:'number',step:'0.01',required:true},
      {name:'reason',label:'\u0627\u0644\u0633\u0628\u0628',required:true}]);
   if(!form)return;
   try{await billingMutation('refund-request-'+selected.case.id,`/api/billing/cases/${selected.case.id}/refunds`,
      {point_id:point.id,source:form.source,method:form.method,amount:form.amount,reason:form.reason});toast('Refund request saved for independent approval');navigate('billing');}
   catch(e){toast(e.message,true)}
 });
 $$('[data-billing-credit-decision]').forEach(b=>b.onclick=async()=>{
   const id=Number(b.dataset.billingCreditDecision),decision=b.dataset.decision;
   try{await post(`/api/billing/credits/${id}/decision`,{decision});toast('Credit decision recorded');navigate('billing');}
   catch(e){toast(e.message,true)}
 });
 $$('[data-billing-refund-decision]').forEach(b=>b.onclick=async()=>{
   const id=Number(b.dataset.billingRefundDecision),decision=b.dataset.decision;
   try{await post(`/api/billing/refunds/${id}/decision`,{decision});toast('Refund decision recorded');navigate('billing');}
   catch(e){toast(e.message,true)}
 });
 $$('[data-billing-refund-pay]').forEach(b=>b.onclick=async()=>{
   if(!point.own_open_shift){toast('Open your assigned cashier shift first',true);return;}
   const confirmation=await modal('\u0635\u0631\u0641 \u0627\u0644\u0631\u062f','\u0633\u064a\u062e\u0631\u062c \u0627\u0644\u0645\u0628\u0644\u063a \u0645\u0646 \u0639\u0647\u062f\u0629 \u0627\u0644\u0643\u0627\u0634\u064a\u0631.',[{name:'confirm',label:'\u062a\u0623\u0643\u064a\u062f',type:'select',required:true,options:[['yes','\u0646\u0639\u0645'],['no','\u0644\u0627']]}]);
   if(!confirmation||confirmation.confirm!=='yes')return;
   try{await billingMutation('refund-pay-'+b.dataset.billingRefundPay,`/api/billing/refunds/${Number(b.dataset.billingRefundPay)}/pay`,{});toast('Approved refund posted');navigate('billing');}
   catch(e){toast(e.message,true)}
 });
 $('#billingAdvance')?.addEventListener('click',()=>billingPaymentForm({caseId:selected.case.id,point,invoiceId:null,cfg}));
 $$('[data-billing-correction]').forEach(b=>b.onclick=()=>{
   const [source_type,source_id]=b.dataset.billingCorrection.split(':');
   state.financialCorrectionPrefill={source_type,source_id:Number(source_id)};
   navigate('cashierCorrections');
 });
 $$('[data-billing-collect]').forEach(b=>b.onclick=()=>billingPaymentForm({caseId:selected.case.id,point,invoiceId:Number(b.dataset.billingCollect),cfg}));
 $$('[data-billing-apply]').forEach(b=>b.onclick=async()=>{
   const form=await modal('تخصيص مقدم إلى فاتورة','التخصيص يخفض المقدم والذمم فقط، ولا يحرك الخزنة مرة ثانية.',[
     {name:'amount',type:'number',step:'0.01',label:'المبلغ بالجنيه',required:true}]);
   if(!form)return;
   await billingAction(b,async()=>{
      await billingMutation('apply-advance-'+selected.case.id,`/api/billing/cases/${selected.case.id}/apply-advance`,
           {invoice_id:Number(b.dataset.billingApply),amount:form.amount});
      toast('خُصص المقدم؛ لم يُقبض مبلغ جديد');navigate('billing');
   });
 });
 $$('[data-billing-issue]').forEach(b=>b.onclick=()=>billingAction(b,async()=>{
   const result=await billingMutation('issue-'+b.dataset.billingIssue,`/api/billing/drafts/${Number(b.dataset.billingIssue)}/issue`,{});
   toast('أُصدرت فاتورة تجريبية '+result.invoice_no+'؛ المبلغ الآن مستحق وليس مقبوضًا');navigate('billing');
 }));
 $$('[data-billing-receipt]').forEach(b=>b.onclick=async()=>{
   try{
     const r=await api(`/api/billing/collections/${Number(b.dataset.billingReceipt)}`);
     await modal('إيصال تحصيل تجريبي',`<strong>${esc(r.collection_no)}</strong><p>${esc(r.case_no)}</p>`+
       r.parts.map(x=>`<p>${esc(x.method)}: ${fmt(x.amount_piasters)} ج.م</p>`).join('')+
       `<strong>الإجمالي: ${fmt(r.total_piasters)} ج.م</strong>`+
       (r.allocation_corrected?'<p><b>تنبيه:</b> هذا هو الإيصال التاريخي الأصلي؛ رُبطت ذمته بفـاتورة أخرى بتصحيح مستقل، ولم يُقبض المال ثانية.</p>':'')+
       `<p>${esc(r.watermark)}</p>`);
   }catch(e){toast(e.message,true)}
 });
 $$('[data-billing-point]').forEach(b=>b.onclick=()=>{billingState.pointId=Number(b.dataset.billingPoint);billingState.caseId=null;navigate('billing')});
 $$('[data-billing-open-case]').forEach(b=>b.onclick=()=>{billingState.caseId=Number(b.dataset.billingOpenCase);navigate('billing')});
 $('#billingNewCase')?.addEventListener('click',async()=>{
   const kindopts=point.kind==='external'?[['outpatient',billingKinds.outpatient]]:
       [['inpatient',billingKinds.inpatient],['operation',billingKinds.operation],['nicu',billingKinds.nicu]];
   const form=await modal('فتح حالة مالية جديدة','استخدم بيانات اختبار فقط. لا تسجل تشخيصات أو تفاصيل طبية.',[
      {name:'patient',label:'اسم مريض افتراضي للتجربة',required:true,placeholder:'مريض تجريبي ١'},
      {name:'kind',label:'نوع الملف المالي',type:'select',options:kindopts,required:true}]);
   if(!form)return;
   const button=$('#billingNewCase');await billingAction(button,async()=>{
       const patient=await billingMutation('patient-new','/api/billing/patients',{display_name:form.patient});
       const c=await billingMutation('case-new','/api/billing/cases',{
          patient_id:patient.id,point_id:point.id,kind:form.kind,
          business_date:new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})});
       billingState.caseId=c.id;toast('فُتح الملف المالي التجريبي');await navigate('billing');
   });
 });
 $('#billingAddLine')?.addEventListener('click',async()=>{
   const priced=cfg.services.filter(s=>s.current_price_piasters>0);
   if(!priced.length){toast('أضف أسعار خدمات معتمدة تجريبيًا من لوحة المالك أولًا',true);return;}
   const form=await modal('تسجيل خدمة على الحالة','الخدمة تُسجّل مطلوبة أولًا. إتمام التنفيذ يُوثّقه مسؤول مختلف.',[
      {name:'service_id',label:'الخدمة',type:'select',options:priced.map(s=>[s.id,`${s.name} — ${fmt(s.current_price_piasters)} ج.م`]),required:true},
      {name:'quantity',label:'الكمية',type:'number',value:'1',required:true,step:'1'}]);
   if(!form)return;
   const b=$('#billingAddLine');await billingAction(b,async()=>{
      await billingMutation('service-new-'+selected.case.id,`/api/billing/cases/${selected.case.id}/services`,
          {service_id:Number(form.service_id),quantity:Number(form.quantity)});
      toast('تم تسجيل الخدمة على الحالة، بانتظار إثبات التنفيذ');await navigate('billing');
   });
 });
 $$('[data-billing-fulfill]').forEach(b=>b.onclick=()=>billingAction(b,async()=>{
      await post(`/api/billing/lines/${Number(b.dataset.billingFulfill)}/fulfill`);
      toast('تم إثبات تنفيذ الخدمة دون إنشاء إيراد نقدي');await navigate('billing');
 }));
 $$('[data-billing-cancel]').forEach(b=>b.onclick=async()=>{
      const data=await modal('إلغاء طلب خدمة','الإلغاء متاح للخدمة قبل التنفيذ فقط.',[
        {name:'reason',label:'سبب الإلغاء',required:true,placeholder:'تم إدخال الخدمة بالخطأ'}]);
      if(!data)return;
      await billingAction(b,async()=>{
        await post(`/api/billing/lines/${Number(b.dataset.billingCancel)}/cancel`,{reason:data.reason});
        toast('أُلغي الطلب مع حفظ السبب');await navigate('billing');
      });
 });
 $('#billingDraft')?.addEventListener('click',async()=>{
    const b=$('#billingDraft');await billingAction(b,async()=>{
      const r=await billingMutation('draft-'+selected.case.id,`/api/billing/cases/${selected.case.id}/drafts`,{});
      toast('تم إنشاء المسودة؛ إصدارها خطوة مستقلة بعد إثبات تنفيذ الخدمات.');await navigate('billing');
    });
 });
 $$('[data-billing-draft]').forEach(b=>b.onclick=async()=>{
    try{
     const data=await api('/api/billing/drafts/'+Number(b.dataset.billingDraft));
     const preview=`<strong>${esc(data.draft.draft_no)}</strong><p>${esc(data.patient_name)} — ${esc(data.case_no)}</p>`+
       `<div class="billing-draft-lines">${data.lines.map(l=>`<div><span>${esc(l.service_name_snapshot)} × ${integer(l.quantity)}</span><strong>${fmt(l.total_piasters)} ج.م</strong></div>`).join('')}</div>`+
       `<p><strong>الإجمالي: ${fmt(data.draft.total_piasters)} ج.م</strong></p>`+
       `<div class="billing-alert">${ico('alert')} ${esc(data.watermark)}</div>`;
     await modal('تفاصيل مسودة الفاتورة',preview);
    }catch(e){toast(e.message,true)}
 });
 $('#billingExistingCase')?.addEventListener('click',async()=>{
   const form=await modal('فتح حالة لمريض مسجل','يمكن للكاشير البحث بكود المريض الكامل فقط؛ المالك يستطيع أيضًا البحث بالاسم.',[
     {name:'query',label:'كود المريض الكامل أو الاسم (للإدارة)',required:true,placeholder:'PT-...'},
     {name:'kind',type:'select',label:'نوع الحالة',required:true,options:point.kind==='external'?[["outpatient",billingKinds.outpatient]]:
       [["inpatient",billingKinds.inpatient],["operation",billingKinds.operation],["nicu",billingKinds.nicu]]}]);
   if(!form)return;
   try{
     const results=await api('/api/billing/patients?q='+encodeURIComponent(form.query));
     if(results.items.length!==1){toast('لا يوجد مريض واحد مطابق؛ استخدم الكود الكامل',true);return;}
     const person=results.items[0];
     const newCase=await billingMutation('previous-patient-case','/api/billing/cases',{
       patient_id:person.id,patient_code:person.code,kind:form.kind,point_id:point.id,
       business_date:new Date().toLocaleDateString('sv-SE',{timeZone:'Africa/Cairo'})});
     billingState.caseId=newCase.id;toast('تم إنشاء حالة مستقلة للمريض المسجل');navigate('billing');
   }catch(e){toast(e.message,true)}
 });
 $('#billingAssign')?.addEventListener('click',async()=>{
   try{
     const users=await api('/api/users');
     const clerks=users.filter(u=>['clerk','reviewer'].includes(u.role)&&u.active);
     if(!clerks.length){toast('أنشئ حساب كاشير أو مراجع نشط أولًا من إدارة المستخدمين',true);return;}
     const form=await modal('صلاحيات ملفات المرضى','يحتاج الكاشير والمراجع تفويضًا محددًا لكل نقطة. سحب التفويض يوقف الوصول فورًا.',[
       {name:'user_id',type:'select',label:'الموظف / المراجع',required:true,options:clerks.map(u=>[u.id,`${u.username} (${u.role==='reviewer'?'مراجع':'كاشير'})`])},
       {name:'point_id',type:'select',label:'نقطة التحصيل',required:true,options:cfg.points.map(p=>[p.id,p.name])},
       {name:'active',type:'select',label:'الإجراء',required:true,options:[['true','تعيين / تفعيل'],['false','سحب التصريح']]}
     ]);
     if(!form)return;
     await post(`/api/billing/points/${Number(form.point_id)}/assign`,{user_id:Number(form.user_id),active:form.active==='true'});
     toast('تم تحديث تصريح نقطة التحصيل مع سجل مراجعة');navigate('billing');
   }catch(e){toast(e.message,true)}
 });
 $('#billingCatalog')?.addEventListener('click',async()=>{
   const form=await modal('خدمة جديدة في الكتالوج','سجل خدمة افتراضية للتجربة، ثم أدخل سعرها بتاريخ السريان.',[
     {name:'code',label:'كود الخدمة (إنجليزي)',required:true,placeholder:'LAB_TEST'},
     {name:'name',label:'اسم الخدمة',required:true,placeholder:'تحليل تجريبي'},
     {name:'department_id',label:'القسم',type:'select',required:true,options:(state.lookups.departments||[]).map(d=>[d.id,d.name])},
     {name:'suggested_point',label:'نقطة التحصيل المقترحة',type:'select',required:true,options:[['either','كلاهما'],['external','الخارجي'],['internal','الداخلي']]}
   ]);
   if(!form)return;
   await billingAction($('#billingCatalog'),async()=>{
      const r=await post('/api/billing/services',{...form,department_id:Number(form.department_id)});
      toast('تم حفظ الخدمة؛ أدخل سعرها من الكتالوج');await navigate('billing');
   });
 });
 $$('[data-billing-price]').forEach(b=>b.onclick=async()=>{
   const data=await modal('إضافة سعر جديد','تاريخ السريان يحدد السعر عند تسجيل الخدمة؛ لا يتم تعديل السعر التاريخي.',[
     {name:'valid_from',label:'بداية سريان السعر',type:'date',value:new Date().toLocaleDateString('sv-SE'),required:true},
     {name:'amount',label:'السعر بالجنيه',type:'number',required:true,step:'0.01',placeholder:'0.00'}]);
   if(!data)return;
   await billingAction(b,async()=>{await post(`/api/billing/services/${Number(b.dataset.billingPrice)}/prices`,data);
       toast('حُفظ إصدار سعر جديد دون تغيير الأسعار السابقة');await navigate('billing')});
 });
}
window.renderBilling=renderBilling;
