"""Read-only, authenticated documents using the existing billing/shift readers."""
from html import escape
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from app import db, get_user, fail, require, shift_daily_report
from billing import case_scope, collection_receipt, draft_detail, invoice_due

router=APIRouter(tags=['print'])
METHODS={'cash':'نقدي','card':'بطاقة POS','wallet':'محفظة','instapay':'InstaPay','transfer':'تحويل تحت التسوية'}
STATES={'open':'مفتوحة — الجرد لم يُرسل', 'submitted':'بانتظار الاستلام والاعتماد', 'closed':'مقفلة ومعتمدة'}


def text(value):
    return escape(str(value if value is not None else ''),quote=True)


def money(value):
    if value is None:return 'محجوب حتى إرسال الجرد'
    sign='-' if value<0 else ''
    amount=abs(value)
    return f'{sign}{amount//100:,}.{amount%100:02d}'


def fields(items):
    return '<dl>'+''.join(f'<div><dt>{text(label)}</dt><dd>{text(value)}</dd></div>' for label,value in items)+'</dl>'


def table(headings,rows):
    return '<div class="table-scroll"><table><thead><tr>'+''.join(f'<th>{text(x)}</th>' for x in headings)+\
        '</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{text(x)}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def document(title,number,content,paper):
    return HTMLResponse(f'''<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{text(title)} · {text(number)}</title>
<link rel="stylesheet" href="/static/fonts/cairo.css"><link rel="stylesheet" href="/static/print.css"><script src="/static/print.js" defer></script></head>
<body class="{'narrow' if paper=='80mm' else 'a4'}"><nav aria-label="إعدادات الطباعة"><button id="printDocument" type="button">طباعة أو حفظ PDF</button>
<a href="?paper=a4">A4</a><a href="?paper=80mm">إيصال 80 مم</a><span>اختر مقاس الورق والطابعة من نافذة الطباعة</span></nav>
<main><header><p class="brand">مستشفى رمسيس · نظام الحسابات</p><h1>{text(title)}</h1><p class="number">{text(number)}</p></header>
<p class="test-notice">نسخة اختبار — بيانات تجريبية؛ لا تُستخدم للتحصيل الفعلي أو كمستند ضريبي.</p>
{content}<footer>جميع المبالغ بالجنيه المصري · الطباعة نسخة للعرض ولا تنشئ قيدًا أو تحصيلًا جديدًا.</footer></main></body></html>''')


@router.get('/api/billing/invoices/{invoice_id}/print',response_class=HTMLResponse)
def print_invoice(invoice_id:int,paper:Literal['a4','80mm']='a4',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    invoice=c.execute('SELECT * FROM billing_invoices WHERE id=?',(invoice_id,)).fetchone()
    if not invoice:fail('الفاتورة غير موجودة',404)
    case_scope(c,user,invoice['case_id'])
    detail=draft_detail(invoice['draft_id'],user,c)
    content=fields([('تاريخ الإصدار',invoice['issued_date']),('الحالة',detail['case_no']),
                    ('كود المريض',detail['patient_code']),('اسم المريض',detail['patient_name'])])
    content+=table(['الخدمة','الكمية','سعر الوحدة','خصم الباقة','الصافي'],[
        (line['service_name_snapshot']+(' · '+line['location_name'] if line.get('location_name') else '')+
         (' / '+line['unit'] if line.get('unit') else ''),line['quantity'],money(line['unit_price_piasters']),
         money(line['unit_price_piasters']*line['quantity']-line['total_piasters']),money(line['total_piasters']))
        for line in detail['lines']])
    content+=fields([('إجمالي الفاتورة الأصلية',money(invoice['total_piasters'])),
                     ('المتبقي الحالي بعد المدفوعات والتسويات',money(invoice_due(c,invoice_id)))])
    lists=sorted({x['price_list_name'] for x in detail['lines'] if x.get('price_list_name')})
    if lists:content+=fields([('قوائم الأسعار','، '.join(lists))])
    content+='<p class="notice">إصدار الفاتورة يثبت المبلغ المستحق؛ إثبات القبض يكون بإيصال التحصيل المستقل.</p>'
    return document('فاتورة خدمات',invoice['invoice_no'],content,paper)


@router.get('/api/billing/collections/{collection_id}/print',response_class=HTMLResponse)
def print_collection(collection_id:int,paper:Literal['a4','80mm']='a4',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    receipt=collection_receipt(collection_id,user,c)  # Includes current station/reviewer/own-receipt checks.
    recorded=c.execute('''SELECT u.username,p.name point_name,s.shift,s.business_date,s.point_id,
        i.invoice_no FROM billing_collections b JOIN users u ON u.id=b.created_by
        JOIN billing_points p ON p.id=b.point_id JOIN shift_sessions s ON s.id=b.shift_session_id
        LEFT JOIN billing_invoices i ON i.id=b.invoice_id WHERE b.id=?''',(collection_id,)).fetchone()
    import cashier_ops
    shift_name=cashier_ops.historical_shift_name(c,recorded['point_id'],recorded['business_date'],recorded['shift'])
    content=fields([('تاريخ التحصيل',receipt['date']),('الحالة الأصلية',receipt['case_no']),
                    ('كود المريض',receipt['patient_code']),('نوع التحصيل','مقدم مريض' if receipt['kind']=='advance' else 'سداد فاتورة'),
                    ('الفاتورة الأصلية',recorded['invoice_no'] or 'مقدم دون فاتورة'),('نقطة التحصيل',recorded['point_name']),
                    ('الكاشير',recorded['username']),('الوردية',shift_name)])
    content+=table(['وسيلة الدفع','المبلغ'],[(METHODS.get(p['method'],p['method']),money(p['amount_piasters'])) for p in receipt['parts']])
    content+=f'<p class="total">إجمالي المقبوض: <strong>{money(receipt["total_piasters"])}</strong> ج.م</p>'
    if receipt['allocation_corrected']:
        content+='<p class="notice">هذا هو الإيصال التاريخي الأصلي؛ تغير تخصيصه بتصحيح مستقل. لم يُقبض المال مرة ثانية.</p>'
    content+='<p>البطاقات والمحافظ والتحويلات ليست نقدية داخل درج الكاشير.</p>'
    return document('إيصال تحصيل',receipt['collection_no'],content,paper)


@router.get('/api/shifts/{shift_id}/daily-report/print',response_class=HTMLResponse)
def print_shift(shift_id:int,paper:Literal['a4','80mm']='a4',user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    report=shift_daily_report(shift_id,user,c)  # Reuses current fund scope and blind-count redaction.
    responsible=c.execute('SELECT u.username FROM shift_sessions s JOIN users u ON u.id=s.responsible_id WHERE s.id=?',(shift_id,)).fetchone()[0]
    content=fields([('تاريخ العمل',report['business_date']),('نقطة التحصيل',report['point_name']),
        ('الصندوق',report['fund_name']),('الكاشير',responsible),('الوردية',report['shift_name']),
        ('الحالة',STATES.get(report['status'],report['status']))])
    content+='<h2>جرد النقدية</h2>'+fields([('رصيد البداية',money(report['opening_piasters'])),
        ('إضافات نقدية',money(report['cash_credited_piasters'])),('سحب نقدي',money(report['cash_debited_piasters']))])
    content+=f'<dl><div><dt>النقدية المتوقعة</dt><dd data-field="expected">{money(report["expected_piasters"])}</dd></div></dl>'
    content+=fields([('النقدية المعدودة',money(report['counted_piasters']))])
    if report['expected_piasters'] is not None and report['counted_piasters'] is not None:
        content+=fields([('فرق الجرد',money(report['counted_piasters']-report['expected_piasters']))])
    content+='<h2>التحصيل حسب وسيلة الدفع</h2>'+table(['الوسيلة','عدد الأجزاء','المبلغ'],[
        (METHODS.get(x['method'],x['method']),x['parts'],money(x['total_piasters'])) for x in report['payment_methods']])
    content+='<p class="notice">المدفوعات الإلكترونية خارج درج النقدية. إرسال الجرد لا يعني اعتماد إقفال الوردية.</p>'
    content+=fields([('الاستلام المستقل',{'accepted':'تم الاستلام','rejected':'أُعيد الجرد'}.get(report['handoff_status'],'لم يُستلم بعد')),
                     ('المستلم',report['handoff_receiver'] or '—')])
    content+='<h2>حركات النقدية المثبتة</h2>'+table(['السند','البيان','الأثر النقدي'],[
        (x['voucher_no'],x['description'],money(x['amount_piasters'])) for x in report['cash_movements']])
    return document('ملخص الوردية',f'#{shift_id}',content,paper)
