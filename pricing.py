"""Versioned service tariffs, estimated costs and accepted bundle contracts."""
from __future__ import annotations
import hashlib,json,re,sqlite3
from decimal import Decimal
from typing import Literal
from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field,model_validator
from app import db,get_user,require,fail,audit,stamp,valid_date,c_piasters,lookup
from billing import cairo_today,trim,case_scope,request_key,repeat,remember,require_case_document_period

router=APIRouter(prefix='/api/pricing',tags=['pricing'])
CATEGORIES=('doctor','nurse','technician','other')


class Named(BaseModel):
    code:str=Field(min_length=2,max_length=36)
    name:str=Field(min_length=3,max_length=120)
class Location(Named):department_id:int
class Person(Named):category:Literal['doctor','nurse','technician','other']
class Details(BaseModel):
    unit:str=Field(min_length=1,max_length=40)
    description:str=Field(default='',max_length=1000)
class FeeRule(BaseModel):
    target:Literal['person','category']
    person_id:int|None=None
    category:Literal['doctor','nurse','technician','other']|None=None
    when:Literal['performed','always']
    kind:Literal['percent','fixed']='percent'
    basis:Literal['collected']='collected'
    percentage:Decimal|None=Field(default=None,gt=0,le=100,decimal_places=4)
    fixed_amount:str|None=None
    discount_affects:bool=True
    distribution:Literal['shared']='shared'
    @model_validator(mode='after')
    def validate_rule(self):
        if self.target=='person' and (not self.person_id or self.category is not None):raise ValueError('حدد الشخص وحده')
        if self.target=='category' and (not self.category or self.person_id is not None or self.when=='always'):raise ValueError('الفئة تخص المنفذين الفعليين للخدمة')
        if self.kind=='percent' and (self.percentage is None or self.fixed_amount is not None):raise ValueError('حدد النسبة المئوية فقط')
        if self.kind=='fixed':
            if self.fixed_amount is None or self.percentage is not None:raise ValueError('حدد الأتعاب الثابتة فقط')
            self.discount_affects=False
        return self
class Rate(BaseModel):
    price_list_id:int;location_id:int;service_id:int;valid_from:str;amount:str
    estimated_cost:str|None=None
    rules:list[FeeRule]=Field(default_factory=list,max_length=30)
class Item(BaseModel):
    service_id:int;location_id:int;quantity:int=Field(ge=1,le=1000)
class Package(Named):
    price_list_id:int;valid_from:str
    items:list[Item]=Field(min_length=1,max_length=100)
    final_amount:str|None=None
    discount_amount:str|None=None
    preview_hash:str|None=Field(default=None,min_length=64,max_length=64)
class ServiceLine(BaseModel):
    service_id:int;quantity:int=Field(ge=1,le=1000)
    performer_ids:list[int]=Field(default_factory=list,max_length=30)
    occurrence_performers:list['OccurrencePerformers']=Field(default_factory=list,max_length=1000)
class OccurrencePerformers(BaseModel):
    occurrence_no:int=Field(ge=1,le=1000)
    person_ids:list[int]=Field(default_factory=list,max_length=30)
class Performers(BaseModel):
    service_id:int;location_id:int
    person_ids:list[int]=Field(default_factory=list,max_length=30)
    occurrence_performers:list[OccurrencePerformers]=Field(default_factory=list,max_length=1000)
class Quote(BaseModel):
    case_id:int|None=None
    price_list_id:int
    location_id:int|None=None
    lines:list[ServiceLine]=Field(default_factory=list,max_length=100)
    package_version_id:int|None=None
    performers:list[Performers]=Field(default_factory=list,max_length=100)
class Order(Quote):
    case_id:int
    quote_hash:str=Field(min_length=64,max_length=64)
    request_id:str
class Cancel(BaseModel):reason:str=Field(min_length=8,max_length=400)


def encoded(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def code(value):
    value=value.strip().upper()
    if not re.fullmatch(r'[A-Z][A-Z0-9_-]{1,35}',value):fail('كود غير صالح')
    return value
def active(c,table,ident):
    row=c.execute('SELECT * FROM '+table+' WHERE id=? AND active=1',(ident,)).fetchone()
    if not row:fail('عنصر تسعير غير موجود أو متوقف',409)
    return row
def allocation(total,weights):
    """Largest remainder, deterministic input-order tie break, no floating point."""
    denominator=sum(weights)
    if total<0 or denominator<=0:fail('مبالغ التوزيع غير صالحة')
    values=[total*w//denominator for w in weights]
    remaining=total-sum(values)
    for i in sorted(range(len(weights)),key=lambda i:(-(total*weights[i]%denominator),i))[:remaining]:values[i]+=1
    return values
def rate_for(c,price_list_id,location_id,service_id,day):
    price_list=active(c,'pricing_lists',price_list_id);location=active(c,'pricing_locations',location_id)
    service=active(c,'billing_services',service_id)
    row=c.execute('''SELECT * FROM pricing_rate_versions WHERE price_list_id=? AND location_id=?
        AND service_id=? AND valid_from<=? ORDER BY valid_from DESC,id DESC LIMIT 1''',
        (price_list_id,location_id,service_id,day)).fetchone()
    if not row:fail('لا توجد تعريفة سارية للخدمة في هذا المكان والقائمة',409)
    profile=c.execute('SELECT unit FROM pricing_service_details WHERE service_id=?',(service_id,)).fetchone()
    return {'rate_id':row['id'],'price_list_id':price_list_id,'price_list_name':price_list['name'],
            'service_id':service_id,'service_name':service['name'],'service_code':service['code'],
            'department_id':service['department_id'],'location_id':location_id,'location_name':location['name'],
            'unit':profile['unit'] if profile else 'خدمة','unit_price_piasters':row['price_piasters'],
            'unit_cost_piasters':row['estimated_cost_piasters'],'rules':json.loads(row['rules_json'])}
def line_from_rate(rate,quantity):
    line=dict(rate,quantity=quantity)
    line['gross_piasters']=line['net_piasters']=line['unit_price_piasters']*quantity
    line['estimated_cost_piasters']=None if line['unit_cost_piasters'] is None else line['unit_cost_piasters']*quantity
    return line
def summarize(lines):
    complete=all(x['estimated_cost_piasters'] is not None for x in lines)
    known=sum(x['estimated_cost_piasters'] or 0 for x in lines)
    gross=sum(x['gross_piasters'] for x in lines);net=sum(x['net_piasters'] for x in lines)
    return {'lines':lines,'gross_piasters':gross,'net_piasters':net,'discount_piasters':gross-net,
            'cost_complete':complete,'known_cost_piasters':known,'estimated_cost_piasters':known if complete else None,
            'estimated_margin_before_fees_piasters':net-known if complete else None}
def package_preview(c,body):
    day=valid_date(body.valid_from).isoformat()
    pairs=[(i.service_id,i.location_id) for i in body.items]
    if len(set(pairs))!=len(pairs):fail('اجمع كمية الخدمة في نفس المكان في سطر واحد')
    lines=[line_from_rate(rate_for(c,body.price_list_id,i.location_id,i.service_id,day),i.quantity) for i in body.items]
    gross=sum(x['gross_piasters'] for x in lines)
    if body.final_amount is not None and body.discount_amount is not None:fail('حدد السعر النهائي أو الخصم، وليس الاثنين')
    net=c_piasters(body.final_amount) if body.final_amount is not None else gross-c_piasters(body.discount_amount or '0',allow_zero=True)
    if not 0<net<=gross:fail('صافي الباقة يجب أن يكون موجبًا ولا يزيد عن أسعار مكوناتها')
    for line,amount in zip(lines,allocation(net,[x['gross_piasters'] for x in lines])):
        if not amount:fail('سعر الباقة صغير جدًا لتوزيع قرش على كل مكون')
        line['net_piasters']=amount
    result=summarize(lines)
    public_lines=[{k:v for k,v in line.items() if k not in ('rules','unit_cost_piasters','estimated_cost_piasters')} for line in lines]
    result['preview_hash']=hashlib.sha256(encoded({'day':day,'price_list_id':body.price_list_id,'lines':public_lines}).encode()).hexdigest()
    return result
def validate_people(c,ids):
    if len(set(ids))!=len(ids):fail('منفذ الخدمة مكرر')
    for person_id in ids:active(c,'pricing_people',person_id)
def full_quote(c,body,user):
    if body.case_id is not None:case_scope(c,user,body.case_id)
    elif user['role']!='owner':fail('اختر حالة مصرحًا بها أولًا',403)
    active(c,'pricing_lists',body.price_list_id)
    day=cairo_today()
    if body.package_version_id is not None:
        if body.lines or body.location_id is not None:fail('اختر باقة أو خدمات منفردة')
        version=c.execute('''SELECT v.*,p.price_list_id,p.name FROM pricing_package_versions v
          JOIN pricing_packages p ON p.id=v.package_id WHERE v.id=?''',(body.package_version_id,)).fetchone()
        if not version or version['price_list_id']!=body.price_list_id or version['valid_from']>day:fail('نسخة باقة غير سارية في هذه القائمة',409)
        latest=c.execute('SELECT id FROM pricing_package_versions WHERE package_id=? AND valid_from<=? ORDER BY valid_from DESC,id DESC LIMIT 1',(version['package_id'],day)).fetchone()
        if latest['id']!=version['id']:fail('تغيرت نسخة الباقة؛ حدّث العرض',409)
        lines=json.loads(version['items_json'])
        assignments={(a.service_id,a.location_id):a for a in body.performers}
        if len(assignments)!=len(body.performers) or set(assignments)-{(x['service_id'],x['location_id']) for x in lines}:fail('توزيع منفذي الباقة لا يطابق مكوناتها')
        for line in lines:
            active(c,'billing_services',line['service_id']);active(c,'pricing_locations',line['location_id'])
            assignment=assignments.get((line['service_id'],line['location_id']))
            line['performer_ids']=assignment.person_ids if assignment else []
            line['occurrence_performers']=[x.model_dump() for x in assignment.occurrence_performers] if assignment else []
    else:
        if not body.lines or body.location_id is None or body.performers:fail('حدد المكان والخدمات المطلوبة')
        if len({x.service_id for x in body.lines})!=len(body.lines):fail('اجمع تكرار الخدمة في الكمية')
        lines=[dict(line_from_rate(rate_for(c,body.price_list_id,body.location_id,x.service_id,day),x.quantity),
                    performer_ids=x.performer_ids,occurrence_performers=[a.model_dump() for a in x.occurrence_performers]) for x in body.lines]
    for line in lines:
        validate_people(c,line['performer_ids'])
        occurrences=line.get('occurrence_performers',[])
        if occurrences:
            if len(occurrences)!=line['quantity'] or {x['occurrence_no'] for x in occurrences}!=set(range(1,line['quantity']+1)):
                fail('سجل مجموعة منفذين لكل مرة تنفيذ بالضبط')
            for occurrence in occurrences:validate_people(c,occurrence['person_ids'])
    result=summarize(lines)
    # Immutable tariff/version IDs bind the private terms. Hash only public
    # terms: hashing a low-entropy hidden cost would expose a guessing oracle.
    public_lines=[{k:v for k,v in line.items() if k not in ('rules','unit_cost_piasters','estimated_cost_piasters')} for line in lines]
    result['quote_hash']=hashlib.sha256(encoded({'day':day,'price_list_id':body.price_list_id,'package_version_id':body.package_version_id,'lines':public_lines}).encode()).hexdigest()
    return result
def public_quote(c,result,user):
    if user['role']=='owner':
        from service_fees import calculate_rule_shares
        for line in result['lines']:
            previews=[]
            for index,rule in enumerate(line['rules']):
                base=line['net_piasters'] if rule.get('discount_affects',True) else line['gross_piasters']
                assignments=line.get('occurrence_performers',[])
                if assignments:
                    bases=allocation(base,[1]*line['quantity'])
                    totals={}
                    for assignment in assignments:
                        for share in calculate_rule_shares(c,rule,assignment['person_ids'],bases[assignment['occurrence_no']-1],1):
                            entry=totals.setdefault(share['person_id'],dict(share,amount_piasters=0))
                            entry['amount_piasters']+=share['amount_piasters']
                    shares=list(totals.values())
                else:shares=calculate_rule_shares(c,rule,line.get('performer_ids',[]),base,line['quantity'])
                previews.extend(dict(share,rule_index=index,projection_only=True) for share in shares)
            line['commission_preview']=previews
        result['fees_projection_notice']='تقدير الأتعاب يفترض تحصيل الصافي كاملًا؛ لا استحقاق أو صرف قبل المراجعة والاعتماد.'
        return result
    private={'rules','unit_cost_piasters','estimated_cost_piasters','known_cost_piasters','cost_complete','estimated_margin_before_fees_piasters'}
    return {k:([{a:b for a,b in x.items() if a not in private} for x in value] if k=='lines' else value)
            for k,value in result.items() if k not in private}


@router.get('/catalog')
def catalog(user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk')
    data={key:[dict(r) for r in c.execute(query)] for key,query in {
        'lists':'SELECT id,code,name,active FROM pricing_lists ORDER BY id',
        'locations':'SELECT l.id,l.code,l.name,l.department_id,l.active,d.name department_name FROM pricing_locations l JOIN departments d ON d.id=l.department_id ORDER BY l.id',
        'people':'SELECT id,code,name,category,active FROM pricing_people ORDER BY id',
        'services':'''SELECT s.id,s.code,s.name,s.department_id,d.name department_name,
          COALESCE(p.unit,'خدمة') unit,COALESCE(p.description,'') description,
          EXISTS(SELECT 1 FROM pricing_rate_versions r WHERE r.service_id=s.id) managed_pricing
          FROM billing_services s JOIN departments d ON d.id=s.department_id LEFT JOIN pricing_service_details p ON p.service_id=s.id WHERE s.active=1 ORDER BY s.id''',
        'rates':'SELECT * FROM pricing_rate_versions ORDER BY valid_from DESC,id DESC'}.items()}
    for r in data['rates']:
        rules=json.loads(r.pop('rules_json'))
        if user['role']=='owner':r['rules']=rules
        else:r.pop('estimated_cost_piasters',None)
        r.pop('created_by',None);r.pop('created_at',None)
    data['packages']=[]
    for r in c.execute('''SELECT v.*,p.code,p.name,p.price_list_id FROM pricing_package_versions v JOIN pricing_packages p ON p.id=v.package_id
          WHERE v.id=(SELECT x.id FROM pricing_package_versions x WHERE x.package_id=p.id AND x.valid_from<=? ORDER BY x.valid_from DESC,x.id DESC LIMIT 1) ORDER BY p.id''',(cairo_today(),)):
        package=dict(r);items=json.loads(package.pop('items_json'))
        if user['role']!='owner':items=[{k:v for k,v in x.items() if k not in ('rules','unit_cost_piasters','estimated_cost_piasters')} for x in items]
        package['items']=items;package.pop('created_by',None);package.pop('created_at',None);data['packages'].append(package)
    return data


def create_named(c,user,table,body):
    values={'code':code(body.code),'name':trim(body.name,'الاسم',3,120),'created_by':user['id'],'created_at':stamp()}
    if isinstance(body,Location):lookup(c,'departments',body.department_id);values['department_id']=body.department_id
    if isinstance(body,Person):values['category']=body.category
    try:cur=c.execute('INSERT INTO '+table+'('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')',list(values.values()))
    except sqlite3.IntegrityError:fail('الكود مسجل بالفعل',409)
    audit(c,user['id'],'pricing_create',table,cur.lastrowid,{'code':values['code']});return {'id':cur.lastrowid}
@router.post('/lists')
def create_list(body:Named,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:c.execute('BEGIN IMMEDIATE');return create_named(c,user,'pricing_lists',body)
@router.post('/locations')
def create_location(body:Location,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:c.execute('BEGIN IMMEDIATE');return create_named(c,user,'pricing_locations',body)
@router.post('/people')
def create_person(body:Person,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:c.execute('BEGIN IMMEDIATE');return create_named(c,user,'pricing_people',body)
@router.post('/services/{service_id}/details')
def service_details(service_id:int,body:Details,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner')
    with c:
        c.execute('BEGIN IMMEDIATE');lookup(c,'billing_services',service_id)
        unit=trim(body.unit,'الوحدة',1,40)
        previous=c.execute('SELECT unit FROM pricing_service_details WHERE service_id=?',(service_id,)).fetchone()
        if unit!=(previous['unit'] if previous else 'خدمة') and c.execute('SELECT 1 FROM pricing_rate_versions WHERE service_id=?',(service_id,)).fetchone():
            fail('وحدة الفوترة مرتبطة بتعريفات منشورة؛ أنشئ خدمة بوحدة أخرى بدل تغيير معناها المالي',409)
        c.execute('INSERT INTO pricing_service_details VALUES (?,?,?,?,?) ON CONFLICT(service_id) DO UPDATE SET unit=excluded.unit,description=excluded.description,changed_by=excluded.changed_by,changed_at=excluded.changed_at',
                  (service_id,unit,body.description.strip(),user['id'],stamp()))
        audit(c,user['id'],'pricing_service_details','billing_service',service_id)
    return {'id':service_id}
@router.post('/rates')
def create_rate(body:Rate,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner');day=valid_date(body.valid_from).isoformat();amount=c_piasters(body.amount)
    cost=c_piasters(body.estimated_cost,allow_zero=True) if body.estimated_cost is not None else None
    rules=[r.model_dump(mode='json') for r in body.rules]
    with c:
        c.execute('BEGIN IMMEDIATE');active(c,'pricing_lists',body.price_list_id);active(c,'pricing_locations',body.location_id);active(c,'billing_services',body.service_id)
        if c.execute('SELECT 1 FROM bed_catalog WHERE service_id=?',(body.service_id,)).fetchone():
            fail('تعريفة الأسرة لها مسارها المؤرخ؛ لا تخلطها بتعريفة خدمات عامة',409)
        for r in rules:
            if r['target']=='person':active(c,'pricing_people',r['person_id'])
            if r['kind']=='fixed':c_piasters(r['fixed_amount'])
        signatures=[(r['target'],r['person_id'],r['category'],r['when'],r['kind']) for r in rules]
        if len(set(signatures))!=len(signatures):fail('قاعدة أتعاب مكررة')
        cur=c.execute('''INSERT INTO pricing_rate_versions(price_list_id,location_id,service_id,valid_from,price_piasters,
            estimated_cost_piasters,rules_json,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?)''',
            (body.price_list_id,body.location_id,body.service_id,day,amount,cost,encoded(rules),user['id'],stamp()))
        # Compatibility FK for existing lines. Actual tariff identity and agreed
        # prices live in pricing_line_terms; old tariffs are never overwritten.
        if not c.execute('SELECT 1 FROM billing_service_prices WHERE service_id=? AND valid_from=?',(body.service_id,day)).fetchone():
            c.execute('INSERT INTO billing_service_prices(service_id,valid_from,price_piasters,created_by,created_at) VALUES (?,?,?,?,?)',(body.service_id,day,amount,user['id'],stamp()))
        audit(c,user['id'],'pricing_rate_version','pricing_rate',cur.lastrowid,{'price_list_id':body.price_list_id,'location_id':body.location_id,'amount_piasters':amount})
    return {'id':cur.lastrowid}
@router.post('/package-preview')
def preview_package(body:Package,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner');return public_quote(c,package_preview(c,body),user)
@router.post('/packages')
def create_package(body:Package,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner');name=trim(body.name,'اسم الباقة',3,120);key=code(body.code);day=valid_date(body.valid_from).isoformat()
    with c:
        c.execute('BEGIN IMMEDIATE');preview=package_preview(c,body)
        if body.preview_hash!=preview['preview_hash']:
            fail('تغيرت تعريفة مكونات الباقة؛ أعد معاينة السعر ثم أكده',409)
        package=c.execute('SELECT * FROM pricing_packages WHERE price_list_id=? AND code=?',(body.price_list_id,key)).fetchone()
        if package and package['name']!=name:fail('لتحديث نسخة الباقة استخدم نفس كودها واسمها',409)
        pid=package['id'] if package else c.execute('INSERT INTO pricing_packages(price_list_id,code,name,created_by,created_at) VALUES (?,?,?,?,?)',(body.price_list_id,key,name,user['id'],stamp())).lastrowid
        cur=c.execute('INSERT INTO pricing_package_versions(package_id,valid_from,gross_piasters,net_piasters,items_json,created_by,created_at) VALUES (?,?,?,?,?,?,?)',
             (pid,day,preview['gross_piasters'],preview['net_piasters'],encoded(preview['lines']),user['id'],stamp()))
        audit(c,user['id'],'pricing_package_version','pricing_package',cur.lastrowid,{'total_piasters':preview['net_piasters']})
    return {'id':cur.lastrowid,'package_id':pid}
@router.post('/quote')
def quote(body:Quote,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','reviewer','clerk');return public_quote(c,full_quote(c,body,user),user)
@router.post('/orders')
def create_order(body:Order,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk');key=request_key(body.request_id);payload=body.model_dump(mode='json');payload.pop('request_id')
    with c:
        c.execute('BEGIN IMMEDIATE')
        case_scope(c,user,body.case_id)  # Replays never retain a revoked point grant.
        previous,fingerprint=repeat(c,key,'priced_order',user['id'],payload)
        if previous:
            ids=[r[0] for r in c.execute('SELECT case_line_id FROM pricing_line_terms WHERE order_id=? ORDER BY case_line_id',(previous,))]
            return {'id':previous,'line_ids':ids,'replayed':True}
        case=case_scope(c,user,body.case_id,write=True)
        if case['status']!='open':fail('الحالة مقفلة',409)
        require_case_document_period(c,case,cairo_today())
        result=full_quote(c,body,user)
        if result['quote_hash']!=body.quote_hash:fail('تغير عرض التسعير؛ اعرض السعر الحالي ثم أكده',409)
        order=c.execute('INSERT INTO pricing_orders(case_id,price_list_id,package_version_id,total_piasters,created_by,created_at) VALUES (?,?,?,?,?,?)',
           (body.case_id,body.price_list_id,body.package_version_id,result['net_piasters'],user['id'],stamp())).lastrowid
        ids=[]
        for line in result['lines']:
            legacy=c.execute('SELECT id FROM billing_service_prices WHERE service_id=? AND valid_from<=? ORDER BY valid_from DESC,id DESC LIMIT 1',(line['service_id'],cairo_today())).fetchone()
            if not legacy:fail('أصل التعريفة غير متاح',409)
            ident=c.execute('''INSERT INTO billing_case_lines(case_id,service_id,price_version_id,service_name_snapshot,
                department_id,unit_price_piasters,quantity,added_by,added_at) VALUES (?,?,?,?,?,?,?,?,?)''',
                (body.case_id,line['service_id'],legacy['id'],line['service_name'],line['department_id'],line['unit_price_piasters'],line['quantity'],user['id'],stamp())).lastrowid
            c.execute('INSERT INTO pricing_line_terms VALUES (?,?,?,?,?,?,?)',(ident,order,line['rate_id'],line['gross_piasters'],line['net_piasters'],line['estimated_cost_piasters'],encoded(line)))
            ids.append(ident)
        remember(c,key,'priced_order',user['id'],fingerprint,order)
        audit(c,user['id'],'pricing_accept_quote','pricing_order',order,{'case_id':body.case_id,'line_ids':ids,'net_piasters':result['net_piasters'],'quote_hash':body.quote_hash})
    return {'id':order,'line_ids':ids,'total_piasters':result['net_piasters'],'replayed':False}
@router.post('/orders/{order_id}/cancel')
def cancel_order(order_id:int,body:Cancel,user=Depends(get_user),c:sqlite3.Connection=Depends(db)):
    require(user,'owner','clerk')
    with c:
        c.execute('BEGIN IMMEDIATE');order=c.execute('SELECT * FROM pricing_orders WHERE id=?',(order_id,)).fetchone()
        if not order:fail('عرض التسعير غير موجود',404)
        case=case_scope(c,user,order['case_id'],write=True);require_case_document_period(c,case,cairo_today())
        if case['status']!='open':fail('الحالة مقفلة',409)
        lines=c.execute('SELECT l.* FROM billing_case_lines l JOIN pricing_line_terms t ON t.case_line_id=l.id WHERE t.order_id=?',(order_id,)).fetchall()
        if not lines or any(x['state']!='ordered' for x in lines):fail('يمكن إلغاء الطلب كله فقط قبل تنفيذ أي مكون',409)
        for line in lines:c.execute("UPDATE billing_case_lines SET state='cancelled',cancelled_by=?,cancelled_at=?,reason=? WHERE id=?",(user['id'],stamp(),body.reason,line['id']))
        audit(c,user['id'],'pricing_cancel_order','pricing_order',order_id,{'reason':body.reason})
    return {'id':order_id,'status':'cancelled'}


def line_net(c,line):
    row=c.execute('SELECT net_piasters FROM pricing_line_terms WHERE case_line_id=?',(line['id'],)).fetchone()
    return row['net_piasters'] if row else int(line['unit_price_piasters'])*int(line['quantity'])
def require_complete_packages(c,lines):
    selected={x['id'] for x in lines}
    for line in lines:
        order=c.execute('SELECT o.id FROM pricing_line_terms t JOIN pricing_orders o ON o.id=t.order_id WHERE t.case_line_id=? AND o.package_version_id IS NOT NULL',(line['id'],)).fetchone()
        if order and c.execute("SELECT 1 FROM pricing_line_terms t JOIN billing_case_lines l ON l.id=t.case_line_id WHERE t.order_id=? AND l.state!='fulfilled'",(order['id'],)).fetchone():fail('لا تفوتر الباقة جزئيًا؛ أكمل إثبات جميع مكوناتها أولًا',409)
        if order and not {x[0] for x in c.execute('SELECT case_line_id FROM pricing_line_terms WHERE order_id=?',(order['id'],))}<=selected:
            fail('كل مكونات الباقة يجب أن تكون في نفس المسودة والفترة',409)
