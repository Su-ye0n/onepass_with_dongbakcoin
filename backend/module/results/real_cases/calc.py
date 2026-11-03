"""실제 결제 사례 → 원카드(동백전 + BNK 카드 1장) 혜택 재계산 (규칙 기반, 엔진 규칙 단순화판)"""
import json,csv,collections,math
R=json.load(open('raw.json'))
D='/home/claude/syn/dongbaek_onepass_synthetic_v3.3/csv/seed_20261023/'
rules=list(csv.DictReader(open(D+'BENEFIT_RULE.csv',encoding='utf-8-sig')))
tiers=list(csv.DictReader(open(D+'BENEFIT_CAP_TIER.csv',encoding='utf-8-sig')))
PNAME={'BNK_CR_P07':'딩딩 신용','BNK_CR_P09':'팟 신용','BNK_CR_P10':'SK OIL&LPG 신용','BNK_CR_P16':'ZipL 신용','BNK_CK_P19':'빵빵 체크','BNK_CK_P23':'어디로든 그린체크'}
# 화면 업종 → 규칙 대상
RULE_IND={'BR_P07_FOOD':['음식점','배달앱?'],'BR_P07_CAFE':['카페·베이커리'],'BR_P07_ONLINE':['온라인쇼핑'],'BR_P07_FUEL':['주유·자동차'],
 'BR_P09_CVS':['편의점'],'BR_P09_CAFE':['직영카페'],'BR_P09_ONLINE':['온라인쇼핑'],'BR_P10_FUEL':['주유·자동차'],'BR_P10_CAFE':['직영카페'],'BR_P10_CVS':['편의점'],
 'BR_P16_BEAUTY':['미용·여가·스포츠'],'BR_P16_MART':['대형마트(이마트·홈플러스 등)'],'BR_P16_ACAD':['학원·교육'],'BR_P16_MED':['병원·약국'],
 'BR_P19_CB':['*'],'BR_P19_CB2':['*'],'BR_P19_CAFE':['카페·베이커리'],'BR_P19_SHOP':['의류·잡화·뷰티'],'BR_P23_CAFE':['카페·베이커리'],'BR_P23_ALL':['*']}
DIRECT_CAFE=('스타벅스','폴바셋','이디야')
BUSAN={'중구','서구','동구','영도구','부산진구','동래구','남구','북구','해운대구','사하구','금정구','강서구','연제구','수영구','사상구','기장군'}
num=lambda x:float(x) if x not in ('',None) else None
def lane(t):
    m=t['method'] or ''
    if m in('현금·계좌이체',) or t['tool']=='현금·계좌이체': return 'CASH'
    if m in('온라인 결제','자동이체·정기결제') or t['gu']=='온라인' or t['ind'] in('온라인쇼핑','통신·구독','배달앱'): return 'ONLINE'
    return 'OFFLINE'   # 원카드는 실물 태그 결제로 가정 (현장 간편결제·결제방식 미기입 포함)
def ind_key(t):
    if t['ind']=='카페·베이커리' and any(k in (t['store'] or '') for k in DIRECT_CAFE): return '직영카페'
    return t['ind']
def card_month(txs,pid_perf,product):
    """한 사람의 한 달 거래에 BNK 상품 하나를 썼을 때 거래별 혜택 (현금성만, 포인트 0원)"""
    rs=[r for r in rules if r['product_id']==product]
    used_rule=collections.Counter(); used_rule_won=collections.Counter(); used_group=collections.Counter()
    cap_by_group={}
    for tr in tiers:
        if tr['product_id']==product and pid_perf>=float(tr['perf_min_won']):
            g=tr['cap_group']; v=num(tr['monthly_cap_won']); cap_by_group[g]=v if v is not None else 1e18
    out=[]
    for t in txs:
        if t['_lane']=='CASH': out.append((0,None));continue
        best=0;br=None;stack=0
        for r in rs:
            tgt=RULE_IND[r['rule_id']]
            if '*' not in tgt and ind_key(t) not in tgt and not (ind_key(t)=='직영카페' and '카페·베이커리' in tgt): continue
            if r['reward_unit']=='POINT': continue
            if pid_perf < (num(r['perf_threshold_won']) or 0): continue
            if t['amt'] < (num(r['min_amount_won']) or 0): continue
            mc=num(r['monthly_count_cap'])
            if mc is not None and used_rule[r['rule_id']]>=mc: continue
            v=math.floor(t['amt']*float(r['rate']))
            if num(r['per_tx_cap_won']) is not None: v=min(v,num(r['per_tx_cap_won']))
            if num(r['monthly_cap_won']) is not None: v=min(v,num(r['monthly_cap_won'])-used_rule_won[r['rule_id']])
            g=r['shared_cap_group']
            if g:
                gc=cap_by_group.get(g)
                if gc is None and any(tr['cap_group']==g for tr in tiers): gc=0   # 실적 미달
                if gc is not None: v=min(v,gc-used_group[g])
            v=max(int(v),0)
            if r['stack_rule']=='STACKABLE': stack+=v; continue
            if v>best: best=v;br=r
        if br:
            used_rule[br['rule_id']]+=1; used_rule_won[br['rule_id']]+=best
            if br['shared_cap_group']: used_group[br['shared_cap_group']]+=best
        out.append((best+stack, br['rule_id'] if br else ('BR_P19_CB' if stack else None)))
    return out
users=[];rows=[]
for p in R['people']:
    p['cards']=[c for c in p['cards'] if c['name']!='카드사·카드 이름']
    T=[t for t in R['txs'] if t['pid']==p['code']]
    T.sort(key=lambda t:(t['date'],str(t['time'] or '')))
    total=sum(t['amt'] for t in T if lane(t)!='CASH')
    perf=float(p['prev']) if p['prev'] else total   # 전월 실적 = 기록값, 없으면 이번 달 카드 결제액으로 대체 [가정]
    for t in T:
        t['_lane']=lane(t)
        t['_busan']=t['gu'] in BUSAN
        t['_db']='Y' if t['dbm']=='예' else ('U' if t['dbm']=='모름' else 'N')
        t['_actual']=int(float(t['benefit'])) if t['benefit'] not in (None,'') else None
    res={}
    for pr in PNAME:
        bn=card_month(T,perf,pr)
        for mode in('safe','wide'):
            cb_base=0; tot=0; per=[]
            for t,(b,rid) in zip(T,bn):
                ok=t['_lane']=='OFFLINE' and t['_busan'] and (t['_db']=='Y' or (mode=='wide' and t['_db']=='U'))
                dbv=0
                if ok and cb_base<500000:
                    base=min(t['amt'],500000-cb_base); dbv=math.floor(base*0.10)
                if dbv>b: cb_base+=min(t['amt'],500000-cb_base); per.append(('동백전',dbv)); tot+=dbv
                else: per.append((PNAME[pr] if b else ('—' if t['_lane']=='CASH' else PNAME[pr]),b)); tot+=b
            res[(pr,mode)]=(tot,per)
    best=max(PNAME,key=lambda pr:(res[(pr,'safe')][0],pr=='BNK_CK_P19'))
    actual=sum(t['_actual'] or 0 for t in T); known=sum(1 for t in T if t['_actual'] is not None)
    ranking=sorted(((PNAME[pr],res[(pr,'safe')][0],res[(pr,'wide')][0]) for pr in PNAME),key=lambda x:-x[1])
    for t,(ins,v),(ins2,v2) in zip(T,res[(best,'safe')][1],res[(best,'wide')][1]):
        rows.append(dict(participant=p['code'],base_month=p['month'],date=t['date'],time=t['time'] or '',store=t['store'],branch=t['branch'] or '',district=t['gu'] or '',industry=t['ind'],amount_won=t['amt'],
          pay_method=t['method'] or '',simple_pay=t['easy'] or '',actual_instrument=t['tool'] or '',actual_card_alias=t['card'] or '',actual_benefit_won='' if t['_actual'] is None else t['_actual'],
          dongbaek_merchant=t['dbm'],lane_norm=t['_lane'],in_busan=int(t['_busan']),
          onecard_instrument=ins,onecard_benefit_won=v,onecard_wide_instrument=ins2,onecard_wide_benefit_won=v2,recommended_bnk=PNAME[best],memo=t['memo'] or ''))
    users.append(dict(code=p['code'],month=p['month'],age=p['age'] or '미입력',gu=p['gu'] or '미입력',db=p['db'] or '미입력',db_bal=p['db_bal'],perf=perf,perf_src='기록' if p['prev'] else '이번 달 결제액으로 대체',
      cards=[[c['name'],c['type'] or ''] for c in p['cards']],n=len(T),amt=total,actual=actual,actual_known=known,
      best=PNAME[best],safe=res[(best,'safe')][0],wide=res[(best,'wide')][0],ranking=ranking,
      db_y=sum(1 for t in T if t['_db']=='Y'),db_u=sum(1 for t in T if t['_db']=='U'),offline_busan=sum(1 for t in T if t['_lane']=='OFFLINE' and t['_busan'])))
with open('real_cases_transactions.csv','w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
json.dump(dict(users=users,tx=[{k:r[k] for k in('participant','date','time','store','district','industry','amount_won','lane_norm','actual_instrument','actual_benefit_won','dongbaek_merchant','onecard_instrument','onecard_benefit_won','onecard_wide_instrument','onecard_wide_benefit_won')} for r in rows]),open('real_cases.json','w'),ensure_ascii=False)
for u in users: print(u['code'],u['n'],u['amt'],'실제',u['actual'],f"({u['actual_known']}건 기록)",'원카드',u['safe'],'확장',u['wide'],'추천',u['best'],u['perf_src'],u['ranking'][:3])
