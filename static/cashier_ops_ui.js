"use strict";
/* V8.1E: read-only shift calendar and owner-managed effective dated station plans. */
const cashierStatusName={
  missing:'غير مسجلة إلكترونيًا',unclosed:'تأخر الإقفال',awaiting_review:'تنتظر الاعتماد',
  variance:'فرق جرد معلق',closed:'مقفولة ومعتمدة',open:'مفتوحة',grace:'خلال المهلة',
  upcoming:'قادمة',not_monitored:'قبل بدء الرصد',not_required:'غير مطلوبة'
};
const cashierStatusClass=s=>['closed'].includes(s)?'approved':['missing','unclosed','variance'].includes(s)?'rejected':['awaiting_review','grace'].includes(s)?'pending':'archive';

async function renderCashierCalendar(){
  const month=state.shiftMonth;
  const data=await api('/api/shifts/coverage?month='+encodeURIComponent(month));
  const pointSet=new Map((data.points||[]).map(p=>[p.id,p]));
  const events=new Map();
  (data.items||[]).forEach(item=>{
    if(!events.has(item.business_date))events.set(item.business_date,[]);
    events.get(item.business_date).push(item);
  });
  const first=new Date(month+'-01T12:00:00Z');
  const year=first.getUTCFullYear(),mon=first.getUTCMonth(),count=new Date(Date.UTC(year,mon+1,0)).getUTCDate();
  const offset=(first.getUTCDay()+1)%7;  // Saturday first, Egyptian working week.
  const pointFilter=state.cashierCalendarPoint||'all';
  const defaultFocus=(state.cashierFocusDate||'').startsWith(month)?state.cashierFocusDate:month+'-01';
  const filterLabel=`<label>نقطة التحصيل <select id="calendarPoint"><option value="all">كل نقاط التحصيل</option>${[...pointSet.values()].map(p=>opt(p.id,p.name,pointFilter)).join('')}</select></label>`;
  let cells='';
  for(let i=0;i<offset;i++)cells+='<div class="cashier-day-pad" aria-hidden="true"></div>';
  for(let i=1;i<=count;i++){
    const day=month+'-'+String(i).padStart(2,'0');
    cells+=`<section class="cashier-calendar-day" data-calendar-day="${day}" aria-label="يوم ${i}">
      <div class="cashier-calendar-date"><b>${i}</b><small>${day}</small></div>
      <div class="cashier-calendar-slots"></div></section>`;
  }
  $('#content').innerHTML=head('إدارة حسابات رمسيس','تقويم الورديات',
    'كل فترة مطلوبة تظهر حتى لو لم تُفتح إلكترونيًا. الضغط يعرض حالة الوردية دون إنشاء أي حركة مالية.',
    `<button class="btn btn-secondary" data-go="shifts">${ico('list')} سجل الورديات</button>`)+
    `<section class="panel panel-pad cashier-calendar-shell"><div class="filter-strip">${periodInput(month,'cashierCalendarMonth')}${filterLabel}<label>عرض <select id="cashierCalendarMode"><option value="month">الشهر</option><option value="week">الأسبوع</option><option value="day">اليوم</option></select></label><label>التاريخ <input type="date" id="cashierFocusDate" value="${defaultFocus}" min="${month}-01" max="${month}-${String(count).padStart(2,'0')}"></label><label>الحالة <select id="calendarStatus"><option value="all">كل الحالات</option><option value="attention">تحتاج متابعة</option><option value="closed">مقفولة</option><option value="missing">غير مسجلة</option></select></label></div>
     <div class="cashier-calendar-weekdays">${['السبت','الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة'].map(x=>`<strong>${x}</strong>`).join('')}</div>
     <div class="cashier-calendar-grid" id="cashierMonthGrid">${cells}</div></section>
     <div class="info-box">${ico('alert')} التقويم رقابي فقط. أي يوم غير مكتمل يعرض التحصيل المسجل مؤقتًا، ولا يختلق إيرادات لوردية غير موجودة.</div>`;
  const draw=()=>{
    const point=$('#calendarPoint').value,status=$('#calendarStatus').value;
    const mode=$('#cashierCalendarMode').value, focus=$('#cashierFocusDate').value;
    state.cashierCalendarPoint=point;state.cashierCalendarMode=mode;state.cashierFocusDate=focus;
    const grid=$('#cashierMonthGrid');grid.dataset.mode=mode;
    const anchor=new Date(focus+'T12:00:00Z');
    const startOfWeek=new Date(anchor);startOfWeek.setUTCDate(anchor.getUTCDate()-((anchor.getUTCDay()+1)%7));
    const endOfWeek=new Date(startOfWeek);endOfWeek.setUTCDate(startOfWeek.getUTCDate()+6);
    $$('.cashier-day-pad').forEach(p=>p.hidden=mode!=='month');
    $$('.cashier-calendar-day').forEach(d=>{
       const day=d.dataset.calendarDay;
       d.hidden=mode==='day'?day!==focus:mode==='week'?(day<startOfWeek.toISOString().slice(0,10)||day>endOfWeek.toISOString().slice(0,10)):false;
    });
    $('.cashier-calendar-weekdays').hidden=mode!=='month';
    $$('.cashier-calendar-day').forEach(day=>{
      const host=day.querySelector('.cashier-calendar-slots');const id=day.dataset.calendarDay;
      const slots=(events.get(id)||[]).filter(s=>point==='all'||String(s.point_id)===point).filter(s=>
        status==='all'||(status==='attention'?['missing','unclosed','awaiting_review','variance'].includes(s.status):s.status===status));
      host.innerHTML=slots.map(s=>`<button type="button" class="cashier-calendar-chip ${cashierStatusClass(s.status)}" data-shift-id="${s.session_id||''}" data-slot-name="${esc(s.shift_name)}" data-status="${esc(s.status)}" data-cashier-point="${s.point_id}" data-day="${id}" aria-label="${esc(s.point_name)}: ${esc(s.shift_name)}، ${esc(cashierStatusName[s.status]||s.status)}">
        <b>${esc(s.shift_name)}</b><small>${esc(s.point_name)}</small><span>${esc(cashierStatusName[s.status]||s.status)}</span></button>`).join('')||'<span class="cashier-empty-day">—</span>';
    });
    $$('.cashier-calendar-chip').forEach(btn=>btn.onclick=async()=>{
      const summary=`<p><b>${esc(btn.dataset.day)}</b> — ${esc(btn.dataset.slotName)}</p><p>${esc(cashierStatusName[btn.dataset.status]||btn.dataset.status)}</p><p>تفاصيل المستندات والجرد يتم عرضها من سجل الورديات.</p>`;
      const result=await modal('تفاصيل الوردية',summary,[]);
      if(btn.dataset.shiftId){state.shiftMonth=btn.dataset.day.slice(0,7);navigate('shifts');}
    });
  };
  $('#calendarPoint').addEventListener('change',draw);$('#calendarStatus').addEventListener('change',draw);
  $('#cashierCalendarMode').value=state.cashierCalendarMode||'month';
  $('#cashierCalendarMode').addEventListener('change',draw);
  $('#cashierFocusDate').addEventListener('change',draw);
  $('#cashierCalendarMonth').addEventListener('change',e=>{state.shiftMonth=e.target.value;state.cashierFocusDate=e.target.value+'-01';navigate('calendar')});
  draw();
}

async function renderCashierSettings(){
  if(state.me.role!=='owner')throw new Error('هذه الصفحة لمدير النظام فقط');
  const data=await api('/api/cashier/plans');
  const active=(p)=>p.versions[p.versions.length-1];
  const reviewUsers=await api('/api/cashier/variance-permissions');
  const staffUsers=await api('/api/cashier/staff-access');
  const allFunds=await api('/api/funds');
  const availableFunds=allFunds.filter(f=>f.kind==='cash'&&f.active&&!data.points.some(p=>p.fund_id===f.id));
  function nextDate(day){const x=new Date(day+'T12:00:00Z');x.setUTCDate(x.getUTCDate()+1);return x.toISOString().slice(0,10)}
  const dayNames=['الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت','الأحد'];
  const dayInputs=days=>`<fieldset class="cashier-days"><legend>أيام تشغيل النقطة</legend><div class="cashier-staff-options">${dayNames.map((name,n)=>`<label><input type="checkbox" data-operating-day value="${n}" ${(days||[]).includes(n)?'checked':''}> ${name}</label>`).join('')}</div></fieldset>`;
  $('#content').innerHTML=head('الإعدادات التشغيلية','نقاط التحصيل وجداول الورديات',
    'الجدول الجديد يبدأ من تاريخ سريان مستقبل؛ السجلات والورديات الناقصة القديمة لا تتغير.')+
    `<section class="panel panel-pad" id="cashierCreatePoint"><details class="cashier-admin-details"><summary>إضافة نقطة تحصيل جديدة <span class="cashier-detail-hint">اختياري — عند التوسع فقط</span></summary>
     <p>اختر درجًا نقديًا غير مستخدم، ثم حدد وردياته. الخزنة الرئيسية الحالية تظل مستقلة.</p>
     <form id="newCashierPoint"><div class="cashier-config-fields"><label>كود النقطة بالإنجليزية<input name="code" placeholder="SATELLITE_04" pattern="[A-Za-z][A-Za-z0-9_]{2,31}" maxlength="32" required></label>
      <label>اسم نقطة التحصيل<input name="name" minlength="3" maxlength="100" required placeholder="مثال: كاشير الطوارئ"></label>
      <label>الخزنة المستقلة <select name="fund_id"><option value="">لم يتم ربط خزنة بعد</option>${availableFunds.map(f=>`<option value="${f.id}">${esc(f.name)}</option>`).join('')}</select></label>
      <label>سبب الإنشاء<input name="reason" minlength="8" maxlength="250" required placeholder="سبب إداري واضح لإضافة نقطة تحصيل"></label></div>
      <div class="cashier-config-slotrows" data-new-slotrows><div class="cashier-config-row"><label>الكود<input data-slot-code value="shift_1" pattern="[a-z][a-z0-9_]{1,31}" required maxlength="32"></label><label>اسم الوردية<input data-slot-name value="وردية أولى" required maxlength="70"></label><label>البداية<input data-slot-start value="00:00" type="time" required></label><button type="button" class="btn btn-small btn-outline" data-remove-slot>حذف</button></div></div>
      ${dayInputs([0,1,2,3,4,5,6])}
      <div class="row-actions"><button type="button" class="btn btn-secondary" id="newPointAddSlot">إضافة وردية</button><button type="submit" class="btn btn-primary">إنشاء نقطة التحصيل</button><button type="button" class="btn btn-secondary" data-go="funds">إدارة الخزن</button></div></form>
      <p class="tiny">لا تُنشأ خزنة ضمنيًا؛ إذا أنشأت نقطة بلا خزنة، تبدأ موقوفة بلا تنبيهات ناقصة حتى تربط درجًا وتفعّل تشغيلها بتاريخ سريان.</p>
     </details></section><div class="cashier-settings-grid">${data.points.map((p,index)=>{
      const v=active(p);const policy=p.policy||{grace_minutes:120,require_shift_image:0,require_envelope_image:0};
      const starts=(v?.slots||[]).map(s=>`<div class="cashier-config-row"><label>الكود<input data-slot-code value="${esc(s.code)}" maxlength="32" required pattern="[a-z][a-z0-9_]{1,31}"></label><label>الاسم<input data-slot-name value="${esc(s.name)}" required maxlength="70"></label><label>البداية<input data-slot-start type="time" value="${esc(s.start)}" required></label><button class="btn btn-small btn-outline" type="button" data-remove-slot aria-label="حذف وردية من الجدول الجديد">حذف</button></div>`).join('');
      return `<article class="panel panel-pad cashier-config-card" data-point="${p.id}">
         <div class="panel-header"><div><h2>${esc(p.name)}</h2><p>${p.kind==='internal'?'الخزنة الرئيسية / الحسابات الداخلية':'نقطة التحصيل الخارجي'} · جدول حالي ${v?.slots.length||0} وردية</p></div><span class="chip ${p.active?'approved':'archive'}">${p.active?'نشطة':'موقوفة'}</span></div>
         <details class="cashier-admin-details" ${index===0?'open':''}><summary>تعديل جدول الورديات وتشغيل النقطة والمستندات</summary>
         <div class="cashier-admin-details-body"><form data-cashier-plan><div class="cashier-config-fields"><label>تاريخ سريان الجدول الجديد<input name="effective_from" type="date" min="${esc(nextDate(v?.effective_from>=data.current_date?v.effective_from:data.current_date))}" value="${esc(nextDate(v?.effective_from>=data.current_date?v.effective_from:data.current_date))}" required></label><label>سبب التعديل<input name="reason" placeholder="مثال: تعديل عدد الموظفين" minlength="5" maxlength="250" required></label></div>
         <div class="cashier-config-slotrows" data-slotrows>${starts}</div>
         ${dayInputs(v?.operating_days||[0,1,2,3,4,5,6])}
         <div class="row-actions"><button class="btn btn-secondary" type="button" data-add-slot>إضافة وردية</button><button class="btn btn-primary" type="submit">حفظ جدول جديد</button></div>
         <p class="tiny">آخر جدول يبدأ ${esc(v?.effective_from||'—')}. تاريخ السريان الجديد يجب أن يكون بعده، ولا توجد إعادة كتابة للماضي.</p></form>
         <hr><form data-cashier-status><h3>إيقاف أو إعادة تشغيل النقطة</h3>
         <p class="tiny">يتغيّر التشغيل من التاريخ المحدد فقط، وتظل كل الورديات والفواتير التاريخية ظاهرة في التقارير.</p>
         <div class="cashier-config-fields"><label>التشغيل الجديد<select name="enabled"><option value="true" ${!p.active?'selected':''}>تشغيل النقطة</option><option value="false" ${p.active?'selected':''}>إيقاف النقطة</option></select></label>
         <label>تاريخ السريان<input name="effective_from" type="date" min="${esc(nextDate((p.lifecycle?.at(-1)?.effective_from||data.current_date)>=data.current_date?p.lifecycle.at(-1).effective_from:data.current_date))}" value="${esc(nextDate((p.lifecycle?.at(-1)?.effective_from||data.current_date)>=data.current_date?p.lifecycle.at(-1).effective_from:data.current_date))}" required></label>
         <label>سبب التغيير<input name="reason" required minlength="5" maxlength="250" placeholder="مثال: وقف مؤقت لتجهيز نقطة التحصيل"></label></div>
         <div class="row-actions"><button class="btn btn-secondary" type="submit">حفظ حالة التشغيل</button></div></form>
         <hr><form data-cashier-policy><div class="cashier-config-fields"><label>مهلة التنبيه بالدقائق<input type="number" name="grace_minutes" min="0" max="10080" value="${Number(policy.grace_minutes)}" required></label></div>
         <label class="cashier-config-switch"><input type="checkbox" name="require_shift_image" ${policy.require_shift_image?'checked':''}> إلزام صورة كشف الوردية</label>
         <label class="cashier-config-switch"><input type="checkbox" name="require_envelope_image" ${policy.require_envelope_image?'checked':''}> إلزام صورة الظرف عند وجود ظرف</label>
         <div class="row-actions"><button class="btn btn-secondary" type="submit">حفظ سياسة النقطة</button></div></form></div></details></article>`;
      }).join('')}</div><section class="panel panel-pad" id="cashierPermissionsPanel"><h2>صلاحيات اعتماد فرق العهدة</h2><p>كل تفويض اختياري، والمراجع لا يملك حق اعتماد جرده أو تحقيقه الشخصي.</p>
      ${reviewUsers.map(u=>`<form data-variance-permission="${u.user_id}" class="cashier-permission-row">
        <strong>${esc(u.username)}</strong><label><input type="checkbox" name="can_approve" ${u.can_approve?'checked':''}> السماح باعتماد العجز أو الزيادة</label>
        <input name="reason" required minlength="8" maxlength="400" placeholder="سبب منح أو سحب التفويض">
        <button class="btn btn-secondary" type="submit">حفظ التفويض</button></form>`).join('')||'<p>لا يوجد محاسبون/مراجعون مضافون.</p>'}</section>
      <section class="panel panel-pad" id="cashierStaffPanel"><h2>صلاحيات الموظفين لكل وردية</h2>
      <p>تحديد ورديات كل موظف بنقطة التحصيل؛ أي تغيير يسجله النظام ويمكن سحبه فورًا.</p>
      ${staffUsers.map(u=>{const point=data.points.find(p=>p.id===u.point_id);if(!point)return '';
      const slots=active(point)?.slots||[], allowed=u.allowed_codes;
      return `<form data-staff-access data-point-id="${u.point_id}" data-user-id="${u.user_id}" class="cashier-staff-rule">
      <strong>${esc(u.username)} · ${esc(point.name)}</strong>
      <div class="cashier-staff-options">${slots.map(slot=>`<label><input type="checkbox" value="${esc(slot.code)}" data-staff-slot ${(allowed===null||allowed.includes(slot.code))?'checked':''}> ${esc(slot.name)}</label>`).join('')}</div>
      <label>سبب تعديل الصلاحيات<input name="reason" required minlength="8" maxlength="400" placeholder="سبب التعيين أو السحب"></label>
      <button class="btn btn-secondary" type="submit">حفظ ورديات الموظف</button></form>`;
      }).join('')||'<p>اربط الموظفين بنقاط الكاشير أولًا من صلاحيات التحصيل.</p>'}</section>`;
  const addPointForm=$('#newCashierPoint');
  $('#newPointAddSlot').onclick=()=>addRow($('[data-new-slotrows]',addPointForm));
  addPointForm.addEventListener('click',e=>{if(e.target.closest('[data-remove-slot]'))e.target.closest('.cashier-config-row').remove()});
  addPointForm.addEventListener('submit',async e=>{
    e.preventDefault();const btn=addPointForm.querySelector('[type=submit]');btn.disabled=true;
    const rows=[...addPointForm.querySelectorAll('.cashier-config-row')];
    try{
      if(!rows.length)throw Error('لا بد من وردية واحدة على الأقل');
      const slots=rows.map(x=>({code:x.querySelector('[data-slot-code]').value.trim(),name:x.querySelector('[data-slot-name]').value.trim(),start:x.querySelector('[data-slot-start]').value}));
      const data=Object.fromEntries(new FormData(addPointForm));
      const days=[...addPointForm.querySelectorAll('[data-operating-day]:checked')].map(x=>Number(x.value));
      if(!days.length)throw Error('اختر يوم تشغيل واحدًا على الأقل');
      await post('/api/cashier/points',{code:data.code,name:data.name,fund_id:data.fund_id?Number(data.fund_id):null,
        reason:data.reason,slots,operating_days:days});
      toast('تم إنشاء النقطة وجدول وردياتها دون تعديل اليوميات السابقة');navigate('cashierSettings');
    }catch(err){toast(err.message,true)}finally{btn.disabled=false}
  });
  const panel=$('#cashierPermissionsPanel');
  if(panel){
    panel.querySelectorAll('[data-variance-permission]').forEach(form=>form.addEventListener('submit',async e=>{
      e.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;
      try{await post('/api/cashier/variance-permissions',{user_id:Number(form.dataset.variancePermission),
          can_approve:form.elements.can_approve.checked,reason:form.elements.reason.value});
          toast('تم تحديث تفويض اعتماد فروق العهدة');navigate('cashierSettings')}
      catch(err){toast(err.message,true)}finally{btn.disabled=false}
    }));
  }
  $$('#cashierStaffPanel [data-staff-access]').forEach(form=>form.addEventListener('submit',async e=>{
    e.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;
    try{await post('/api/cashier/staff-access',{
      user_id:Number(form.dataset.userId),point_id:Number(form.dataset.pointId),
      allowed_codes:[...form.querySelectorAll('[data-staff-slot]:checked')].map(x=>x.value),
      reason:form.elements.reason.value
    });toast('تم حفظ صلاحيات ورديات الموظف');navigate('cashierSettings')}
    catch(err){toast(err.message,true)}finally{btn.disabled=false}
  }));
  function addRow(host){
    const index=host.querySelectorAll('.cashier-config-row').length+1;
    const node=document.createElement('div');node.className='cashier-config-row';
    node.innerHTML=`<label>الكود<input data-slot-code required maxlength="32" pattern="[a-z][a-z0-9_]{1,31}" placeholder="shift_${index}"></label><label>الاسم<input data-slot-name required maxlength="70" placeholder="اسم الوردية"></label><label>البداية<input data-slot-start type="time" required></label><button type="button" class="btn btn-small btn-outline" data-remove-slot>حذف</button>`;
    host.append(node);node.querySelector('[data-slot-code]').focus();
  }
  $$('[data-point]').forEach(card=>{
    const id=Number(card.dataset.point);
    card.querySelector('[data-add-slot]').onclick=()=>addRow(card.querySelector('[data-slotrows]'));
    card.addEventListener('click',e=>{if(e.target.closest('[data-remove-slot]'))e.target.closest('.cashier-config-row').remove()});
    card.querySelector('[data-cashier-plan]').onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget;
      const slots=$$('.cashier-config-row',card).map(row=>({code:row.querySelector('[data-slot-code]').value.trim(),name:row.querySelector('[data-slot-name]').value.trim(),start:row.querySelector('[data-slot-start]').value}));
      const data=Object.fromEntries(new FormData(form));
      const btn=form.querySelector('[type=submit]');btn.disabled=true;
      try{
        const days=[...form.querySelectorAll('[data-operating-day]:checked')].map(x=>Number(x.value));
        if(!days.length)throw Error('اختر يوم تشغيل واحدًا على الأقل');
        await post('/api/cashier/plans',{point_id:id,effective_from:data.effective_from,
          slots,operating_days:days,reason:data.reason});
        toast('تم إنشاء نسخة جديدة من جدول الورديات بتاريخ السريان');navigate('cashierSettings')}
      catch(err){toast(err.message,true)}finally{btn.disabled=false}
    };
    card.querySelector('[data-cashier-status]').onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget,btn=form.querySelector('[type=submit]');btn.disabled=true;
      try{
        const values=Object.fromEntries(new FormData(form));
        await post('/api/cashier/points/'+id+'/status',{effective_from:values.effective_from,
          enabled:values.enabled==='true',reason:values.reason});
        toast('تم حفظ تاريخ إيقاف أو تشغيل النقطة دون إخفاء الورديات القديمة');navigate('cashierSettings');
      }catch(err){toast(err.message,true)}finally{btn.disabled=false}
    };
    card.querySelector('[data-cashier-policy]').onsubmit=async e=>{
      e.preventDefault();const form=e.currentTarget,btn=form.querySelector('[type=submit]');btn.disabled=true;
      try{await post('/api/cashier/points/'+id+'/policy',{
        grace_minutes:Number(form.elements.grace_minutes.value),
        require_shift_image:form.elements.require_shift_image.checked,
        require_envelope_image:form.elements.require_envelope_image.checked
      });toast('تم تحديث سياسة النقطة');navigate('cashierSettings')}
      catch(err){toast(err.message,true)}finally{btn.disabled=false}
    };
  });
}


async function renderCashierRecoveries(){
  const data=await api('/api/cashier/shortage-repayments');
  const cases=data.cases||[], recoverable=cases.filter(x=>x.outstanding_piasters>0);
  $('#content').innerHTML=head('متابعة العهدة','سداد فروق الخزنة المعتمدة',
    'سداد نقدية حقيقية من الموظف بعد اعتماد العجز. لا يدخل السداد في إيرادات المرضى ولا يغيّر جرد الوردية القديمة.',
    `<button class="btn btn-secondary" data-go="shifts">${ico('arrow')} الورديات والجرد</button>`)+
    `<section class="panel panel-pad"><h2>أرصدة العجز الموافق عليها</h2><p class="tiny">هذه المبالغ لم تُحمّل على راتب الموظف تلقائيًا. يجب التحقق من سداد نقدية فعلية قبل تسجيل الإيصال.</p>
     <div class="table-wrap"><table class="data-table"><thead><tr><th>المحضر</th><th>تاريخ الوردية</th><th>العجز الأصلي</th><th>المسدّد</th><th>المتبقي</th></tr></thead><tbody>${cases.map(c=>`<tr><td>#${c.case_id}</td><td>${esc(c.business_date)}</td><td>${fmt(-c.variance_piasters)}</td><td>${fmt(c.repaid_piasters)}</td><td class="num">${fmt(c.outstanding_piasters)}</td></tr>`).join('')||'<tr><td colspan="5">لا يوجد عجز معتمد في السجل.</td></tr>'}</tbody></table></div></section>`+
    `<section class="panel panel-pad"><h2>تسجيل استلام سداد نقدي</h2><p>لا يسجل هذا النموذج شيئًا إلا إذا كان المستخدم صاحب وردية الخزنة الرئيسية المفتوحة اليوم، وشخصًا مختلفًا عن صاحب العجز.</p>
     ${recoverable.length?`<form id="shortageRepayment" class="cashier-repayment-form">
       <label>محضر العجز المعتمد<select name="variance_case_id" required>${recoverable.map(c=>`<option value="${c.case_id}">#${c.case_id} — وردية ${esc(c.business_date)} — متبقّي ${fmt(c.outstanding_piasters)} ج</option>`).join('')}</select></label>
       <label>المبلغ المستلم فعليًا بالجنيه<input name="amount" required type="number" min="0.01" step="0.01" inputmode="decimal" placeholder="0.00"></label>
       <label>بيان إثبات الاستلام<input name="evidence_note" required minlength="12" maxlength="500" placeholder="من سلّم النقدية، ومن عدّها، ومرجع الإثبات"></label>
       <button type="submit" class="btn btn-primary">تسجيل إيصال نقدي مرتبط بالعجز</button></form>`:'<p>لا توجد حالات عجز متبقية يمكن سدادها.</p>'}</section>`+
    `<section class="panel panel-pad"><h2>إيصالات السداد المحفوظة</h2>
      <div class="table-wrap"><table class="data-table"><thead><tr><th>رقم الإيصال</th><th>محضر الفرق</th><th>المبلغ</th><th>تاريخ التسجيل</th></tr></thead><tbody>${(data.receipts||[]).map(r=>`<tr><td>${esc(r.voucher_no)}</td><td>#${r.variance_case_id}</td><td>${fmt(r.amount_piasters)}</td><td>${esc(r.recorded_at)}</td></tr>`).join('')||'<tr><td colspan="4">لم تُسجل أي تسويات نقدية بعد.</td></tr>'}</tbody></table></div></section>`;
  const form=$('#shortageRepayment');if(!form)return;
  const clearKey=()=>{delete form.dataset.receiptKey};
  form.addEventListener('input',clearKey);
  form.addEventListener('submit',async e=>{
    e.preventDefault();const btn=form.querySelector('[type=submit]');btn.disabled=true;
    try{
      const values=Object.fromEntries(new FormData(form));
      const receipt_key=form.dataset.receiptKey||(form.dataset.receiptKey=globalThis.crypto.randomUUID());
      await post('/api/cashier/shortage-repayments',{variance_case_id:Number(values.variance_case_id),
        amount:values.amount,evidence_note:values.evidence_note,receipt_key});
      delete form.dataset.receiptKey;toast('سُجل السداد النقدي وخُفّض العجز المعلّق');navigate('cashierRecoveries');
    }catch(err){toast(err.message,true)}finally{btn.disabled=false}
  });
}
window.renderCashierRecoveries=renderCashierRecoveries;
