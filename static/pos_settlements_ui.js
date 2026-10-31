"use strict";

// POS is a bank-reconciliation companion, not a second cashier-receipt screen.
const POS_TEXT={
 title:"\u062a\u0633\u0648\u064a\u0627\u062a \u0628\u0637\u0627\u0642\u0627\u062a POS",
 desc:"\u062a\u062c\u0645\u064a\u0639 \u0625\u064a\u0635\u0627\u0644\u0627\u062a \u0627\u0644\u0628\u0637\u0627\u0642\u0629 \u0648\u062a\u062d\u0648\u064a\u0644 \u0627\u0644\u0635\u0627\u0641\u064a \u0625\u0644\u0649 \u0627\u0644\u0628\u0646\u0643 \u0628\u0639\u062f \u062e\u0635\u0645 \u0627\u0644\u0639\u0645\u0648\u0644\u0629.",
 missing:"\u0644\u0627 \u062a\u0648\u062c\u062f \u0645\u062d\u0641\u0638\u0629 \u0645\u0642\u0627\u0635\u0629 \u0628\u0637\u0627\u0642\u0627\u062a \u0645\u0647\u064a\u0623\u0629.",
 receipts:"\u0625\u064a\u0635\u0627\u0644\u0627\u062a \u0627\u0644\u0628\u0637\u0627\u0642\u0629 \u0627\u0644\u0645\u062a\u0627\u062d\u0629",
 gross:"\u0625\u062c\u0645\u0627\u0644\u064a \u0627\u0644\u0645\u062d\u062f\u062f",
 fee:"\u0639\u0645\u0648\u0644\u0629 \u0634\u0631\u0643\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644 (\u062c\u0646\u064a\u0647)",
 net:"\u0635\u0627\u0641\u064a \u0627\u0644\u062a\u062d\u0648\u064a\u0644 \u0644\u0644\u0628\u0646\u0643",
 date:"\u062a\u0627\u0631\u064a\u062e \u0627\u0644\u062a\u0633\u0648\u064a\u0629",
 ref:"\u0645\u0631\u062c\u0639 \u0643\u0634\u0641 \u0634\u0631\u0643\u0629 \u0627\u0644\u062a\u062d\u0635\u064a\u0644",
 evidence:"\u0628\u064a\u0627\u0646 \u0627\u0644\u0645\u0633\u062a\u0646\u062f \u0627\u0644\u062f\u0627\u0639\u0645 \u0644\u0644\u062a\u0633\u0648\u064a\u0629",
 submit:"\u0625\u0631\u0633\u0627\u0644 \u0644\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
 history:"\u0633\u062c\u0644 \u0627\u0644\u062a\u0633\u0648\u064a\u0627\u062a",
 pending:"\u0642\u064a\u062f \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
 approved:"\u0645\u0639\u062a\u0645\u062f",
 rejected:"\u0645\u0631\u0641\u0648\u0636",
 approve:"\u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u062a\u0633\u0648\u064a\u0629",
 reject:"\u0631\u0641\u0636 \u0627\u0644\u0637\u0644\u0628",
 bank:"\u0648\u0635\u0648\u0644 \u0627\u0644\u0645\u0628\u0644\u063a \u0644\u0644\u0628\u0646\u0643 \u064a\u062d\u062a\u0627\u062c \u0645\u0637\u0627\u0628\u0642\u0629 \u0643\u0634\u0641 \u0627\u0644\u062d\u0633\u0627\u0628 \u0628\u0634\u0643\u0644 \u0645\u0633\u062a\u0642\u0644.",
 reason:"\u0633\u0628\u0628 \u0642\u0631\u0627\u0631 \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
 sent:"\u062a\u0645 \u062a\u0633\u062c\u064a\u0644 \u0637\u0644\u0628 \u062a\u0633\u0648\u064a\u0629 POS \u0644\u0644\u0645\u0631\u0627\u062c\u0639\u0629",
 accepted:"\u062a\u0645 \u0627\u0639\u062a\u0645\u0627\u062f \u0627\u0644\u062a\u0633\u0648\u064a\u0629\u060c \u0648\u0645\u0627 \u0632\u0627\u0644\u062a \u0627\u0644\u0645\u0637\u0627\u0628\u0642\u0629 \u0627\u0644\u0628\u0646\u0643\u064a\u0629 \u0645\u0637\u0644\u0648\u0628\u0629",
 declined:"\u062a\u0645 \u0631\u0641\u0636 \u0627\u0644\u0637\u0644\u0628 \u0648\u0625\u062a\u0627\u062d\u0629 \u0627\u0644\u0625\u064a\u0635\u0627\u0644\u0627\u062a \u0645\u0631\u0629 \u0623\u062e\u0631\u0649",
 need:"\u0627\u062e\u062a\u0631 \u0625\u064a\u0635\u0627\u0644\u0627 \u0648\u0627\u062d\u062f\u0627 \u0639\u0644\u0649 \u0627\u0644\u0623\u0642\u0644",
 limit:"\u062a\u0638\u0647\u0631 \u0623\u0648\u0644 200 \u0639\u0645\u0644\u064a\u0629 \u063a\u064a\u0631 \u0645\u0633\u0648\u0627\u0629 \u0641\u0642\u0637.",
};

window.renderPOSSettlements=async function(bankId,month){
 const host=document.querySelector('#posSettlementPanel');if(!host)return;
 const t=POS_TEXT;
 let r;
 try{r=await api('/api/pos/settlements?'+new URLSearchParams({period:month,bank_fund_id:String(bankId)}))}
 catch(e){host.innerHTML=`<div class="info-box warning" role="alert">${esc(e.message)}</div>`;return}
 if(state.view!=='bank'||state.bankMonth!==month||state.bankFundId!==bankId)return;
 const last=new Date(Number(month.slice(0,4)),Number(month.slice(5,7)),0).getDate();
 const settlementDate=month===new Date().toLocaleDateString('sv-SE').slice(0,7)?new Date().toLocaleDateString('sv-SE'):`${month}-${String(last).padStart(2,'0')}`;
 const history=r.settlements.map(s=>`<article class="bank-line pos-history"><div class="bank-line-top"><div><strong>#${s.id} · ${esc(s.settlement_ref)}</strong><p>${esc(s.settlement_date)} · ${esc(s.maker)} · ${s.part_ids.length} POS</p><small>${esc(s.evidence_note)}</small></div><div class="bank-line-status"><strong>${fmt(s.gross_piasters)} / -${fmt(s.fee_piasters)} / ${fmt(s.net_piasters)}</strong><span class="chip ${esc(s.status)}">${t[s.status]||esc(s.status)}</span></div></div><div class="pos-actions"><span class="text-muted">${s.reviewed_at?esc(s.reviewer)+' · '+esc(s.reviewed_at):''}</span>${r.permissions?.can_approve===true&&s.status==='pending'&&s.maker!==state.me.username?`<button type="button" class="btn btn-small btn-primary" data-posdecision="approve" data-posid="${s.id}">${t.approve}</button><button type="button" class="btn btn-small btn-secondary" data-posdecision="reject" data-posid="${s.id}">${t.reject}</button>`:''}</div></article>`).join('');
 const receipts=r.candidates.map(p=>`<label class="pos-receipt"><input type="checkbox" data-pospart="${p.id}" value="${p.id}"><span><strong>${esc(p.collection_no)}</strong><small dir="ltr">${esc(p.business_date)}</small></span><strong dir="ltr">${fmt(p.amount_piasters)}</strong></label>`).join('');
 host.innerHTML=`<section class="panel bank-section pos-panel" aria-label="${t.title}"><div class="panel-header"><div><h2>${t.title}</h2><p>${t.desc}</p></div><span class="chip pending">G2O · TEST</span></div><div class="panel-pad"><p class="info-box warning">${t.bank}</p>${!r.clearing_fund_id?`<p role="status">${esc(r.note||t.missing)}</p>`:`<h3 class="section-title">${t.receipts} · ${esc(r.clearing_name)}</h3><div class="pos-receipts">${receipts||'<p class="empty">0</p>'}</div>${r.candidate_limit_reached?`<p class="text-muted">${t.limit}</p>`:''}${r.bank_sealed||r.period_closed?`<div class="info-box warning">كشف البنك أو الشهر معتمد ومقفل؛ لا يمكن تسجيل تسويات POS جديدة.</div>`:''}${receipts&&r.permissions?.can_submit===true&&!r.bank_sealed&&!r.period_closed?`<form id="posSettlementForm" class="form-grid pos-form"><div class="pos-totals full"><span>${t.gross}: <strong id="posGross">0.00</strong></span><span>${t.net}: <strong id="posNet">0.00</strong></span></div><label>${t.fee}<input name="fee_amount" id="posFee" type="number" min="0" step="0.01" value="0" required></label><label>${t.date}<input name="settlement_date" type="date" value="${settlementDate}" required></label><label class="full">${t.ref}<input name="settlement_ref" maxlength="90" minlength="6" required placeholder="POS-SETTLEMENT-REF" autocomplete="off"></label><label class="full">${t.evidence}<textarea name="evidence_note" minlength="12" maxlength="500" required rows="2" placeholder="POS acquiring statement number, bank reference, fee calculation"></textarea></label><div class="full"><button class="btn btn-primary" type="submit">${t.submit}</button></div></form>`:''}`}</div><div class="panel-header pos-history-heading"><h2>${t.history}</h2></div><div class="bank-lines">${history||'<p class="empty">0</p>'}</div></section>`;
 const form=host.querySelector('#posSettlementForm');
 if(form){
   const key=globalThis.crypto?.randomUUID?.()||('POS_'+Date.now()+'_'+Math.random().toString(36).slice(2));
   const chosen=()=>r.candidates.filter(x=>host.querySelector(`[data-pospart="${x.id}"]`)?.checked);
   const update=()=>{
     const gross=chosen().reduce((s,p)=>s+p.amount_piasters,0);
     const fee=Math.round(Number(host.querySelector('#posFee')?.value||0)*100);
     host.querySelector('#posGross').textContent=fmt(gross);
     host.querySelector('#posNet').textContent=gross-fee>0?fmt(gross-fee):'--';
   };
   host.querySelectorAll('[data-pospart]').forEach(x=>x.onchange=update);
   host.querySelector('#posFee').oninput=update;update();
   form.onsubmit=async e=>{
     e.preventDefault();const parts=chosen();const fee=Number(form.elements.fee_amount.value);
     if(!parts.length){toast(t.need,true);return}
     const gross=parts.reduce((s,p)=>s+p.amount_piasters,0);
     if(!Number.isFinite(fee)||fee<0||Math.round(fee*100)>=gross){toast(t.net,true);return}
     const btn=form.querySelector('[type=submit]');btn.disabled=true;
     try{await post('/api/pos/settlements',{bank_fund_id:bankId,
       clearing_fund_id:r.clearing_fund_id,settlement_date:form.elements.settlement_date.value,
       payment_part_ids:parts.map(p=>p.id),fee_amount:form.elements.fee_amount.value,
       settlement_ref:form.elements.settlement_ref.value,evidence_note:form.elements.evidence_note.value,
       request_key:key});toast(t.sent);navigate('bank')}
     catch(err){toast(err.message,true);btn.disabled=false}
   };
 }
 host.querySelectorAll('[data-posdecision]').forEach(btn=>btn.onclick=async()=>{
   const id=Number(btn.dataset.posid),decision=btn.dataset.posdecision;
   const details=await modal(decision==='approve'?t.approve:t.reject,t.bank,
     [{name:'note',type:'textarea',label:t.reason,required:true,placeholder:'Reviewer evidence and signoff'}]);
   if(!details)return;
   if(details.note.trim().length<8){toast(t.reason,true);return}
   btn.disabled=true;
   try{await post(`/api/pos/settlements/${id}/decision`,{decision,note:details.note});
     toast(decision==='approve'?t.accepted:t.declined);navigate('bank')}
   catch(err){toast(err.message,true);btn.disabled=false}
 });
};
