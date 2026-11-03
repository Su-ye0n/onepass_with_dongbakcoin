"""원카드 개인화 추천 ML (보정 데이터 240명 학습 → 실제 사례 T1·T4 적용)
- 모델 1: 예상 월 혜택 증가액 회귀 (원패스+충전 상한, S11-S00)
- 모델 2: 연결 추천 카드 분류 (원패스 기준 혜택이 가장 큰 BNK 카드)
- 모델 3: 비슷한 고객 묶기 (K-means)
"""
import csv, json, collections, numpy as np, pandas as pd
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import cross_val_predict, KFold, StratifiedKFold
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_error, r2_score, accuracy_score
import sys, math
RULE_DIR=sys.argv[6]
rules=list(csv.DictReader(open(RULE_DIR+'/BENEFIT_RULE.csv',encoding='utf-8-sig')))
tiers=list(csv.DictReader(open(RULE_DIR+'/BENEFIT_CAP_TIER.csv',encoding='utf-8-sig')))
RULE_IND={'BR_P07_FOOD':['FOOD'],'BR_P07_CAFE':['CAFE'],'BR_P07_ONLINE':['ONLINE'],'BR_P07_FUEL':['FUEL'],'BR_P09_CVS':['CVS'],'BR_P09_CAFE':['DCAFE'],'BR_P09_ONLINE':['ONLINE'],
 'BR_P10_FUEL':['FUEL'],'BR_P10_CAFE':['DCAFE'],'BR_P10_CVS':['CVS'],'BR_P16_BEAUTY':['LEISURE'],'BR_P16_MART':['BIGMART'],'BR_P16_ACAD':['ACAD'],'BR_P16_MED':['MED'],
 'BR_P19_CB':['*'],'BR_P19_CB2':['*'],'BR_P19_CAFE':['CAFE','DCAFE'],'BR_P19_SHOP':['CLOTH'],'BR_P23_CAFE':['CAFE','DCAFE'],'BR_P23_ALL':['*']}
num=lambda x:float(x) if x not in ('',None) else None
def card_total(txs,perf,product):
    """규칙표로 BNK 상품 하나를 썼을 때 한 달 현금성 혜택 (포인트 0원, 동백전 제외 결제만)"""
    rs=[r for r in rules if r['product_id']==product]; ur=collections.Counter(); uw=collections.Counter(); ug=collections.Counter(); cap={}
    for tr in tiers:
        if tr['product_id']==product and perf>=float(tr['perf_min_won']): v=num(tr['monthly_cap_won']); cap[tr['cap_group']]=v if v is not None else 1e18
    tot=0
    for t in txs:
        best=0;br=None;st=0
        for r in rs:
            tg=RULE_IND[r['rule_id']]
            if '*' not in tg and t['rk'] not in tg: continue
            if r['reward_unit']=='POINT' or perf<(num(r['perf_threshold_won']) or 0) or t['amt']<(num(r['min_amount_won']) or 0): continue
            if num(r['monthly_count_cap']) is not None and ur[r['rule_id']]>=num(r['monthly_count_cap']): continue
            v=math.floor(t['amt']*float(r['rate']))
            if num(r['per_tx_cap_won']) is not None: v=min(v,num(r['per_tx_cap_won']))
            if num(r['monthly_cap_won']) is not None: v=min(v,num(r['monthly_cap_won'])-uw[r['rule_id']])
            g=r['shared_cap_group']
            if g:
                gc=cap.get(g)
                if gc is None and any(tr['cap_group']==g for tr in tiers): gc=0
                if gc is not None: v=min(v,gc-ug[g])
            v=max(int(v),0)
            if r['stack_rule']=='STACKABLE': st+=v; continue
            if v>best: best=v;br=r
        if br: ur[br['rule_id']]+=1; uw[br['rule_id']]+=best; ug[br['shared_cap_group']]+=best
        tot+=best+st
    return tot
def best_card(txs):
    perf=sum(t['amt'] for t in txs)
    nd=[t for t in txs if not (t['lane']=='OFFLINE' and t['reg'])]   # 동백전으로 갈 결제는 빼고 비교
    sc={p:card_total(nd,perf,p) for p in CARDN}
    return max(sc,key=lambda p:(sc[p],p=='BNK_CK_P19')), sc
RES=sys.argv[1]; MER=sys.argv[2]; PROFILE=sys.argv[3]; CASES=sys.argv[4]; OUT=sys.argv[5]
GROUP={'RESTAURANT':'FOOD','FRANCHISE_DIRECT_FOOD':'FOOD','CAFE_BAKERY':'CAFE','FRANCHISE_DIRECT_CAFE':'CAFE','CONVENIENCE_STORE':'CVS',
 'SUPERMARKET':'MART','LARGE_MART_SSM':'MART','DEPARTMENT_STORE':'MART','HOSPITAL_PHARMACY':'MED','ACADEMY':'ACAD','BEAUTY_LEISURE_ETC':'LEISURE',
 'FUEL_AUTO':'FUEL','CLOTHING_GOODS':'CLOTH','ONLINE_MALL':'ONLINE'}
KO={'음식점':'FOOD','배달앱':'FOOD','카페·베이커리':'CAFE','편의점':'CVS','슈퍼·마트(SSM 포함)':'MART','대형마트(이마트·홈플러스 등)':'MART','백화점':'MART',
 '병원·약국':'MED','학원·교육':'ACAD','미용·여가·스포츠':'LEISURE','주유·자동차':'FUEL','의류·잡화·뷰티':'CLOTH','온라인쇼핑':'ONLINE'}
GROUPS=['FOOD','CAFE','CVS','MART','MED','ACAD','LEISURE','FUEL','CLOTH','ONLINE','OTHER']
CARDN={'BNK_CR_P07':'딩딩 신용','BNK_CR_P09':'팟 신용','BNK_CR_P10':'SK OIL&LPG 신용','BNK_CR_P16':'ZipL 신용','BNK_CK_P19':'빵빵 체크','BNK_CK_P23':'어디로든 그린체크'}
AGE={'20대':25,'30대':35,'40대':45,'50대':55,'60대':65,'70대+':75}
def feats(txs, wallet_active, card_count, age):
    n=len(txs); amt=sum(t['amt'] for t in txs) or 1
    f={'n_tx':n,'amt_total':amt,'amt_avg':amt/max(n,1),'wallet_active':wallet_active,'card_count':card_count,'age':age}
    g=collections.Counter(); ln=collections.Counter(); dbo=0
    for t in txs:
        g[t['grp']]+=t['amt']; ln[t['lane']]+=t['amt']
        if t['lane']=='OFFLINE' and t['reg']: dbo+=t['amt']
    for k in GROUPS: f['sh_'+k]=g[k]/amt
    for k in ['OFFLINE','ONLINE','SIMPLE_PAY']: f['lane_'+k]=ln[k]/amt
    f['db_offline_share']=dbo/amt
    return f
M={r['merchant_id']:r for r in csv.DictReader(open(MER,encoding='utf-8-sig'))}
U={r['user_id']:r for r in csv.DictReader(open(RES+'/users.csv',encoding='utf-8-sig'))}
P=json.load(open(PROFILE))  # 대시보드 사용자 프로필 (연령·지갑·카드)
P={p['id']:p for p in P}
T=collections.defaultdict(list); cardben=collections.defaultdict(collections.Counter)
for r in csv.DictReader(open(RES+'/transactions.csv',encoding='utf-8-sig')):
    m=M[r['merchant_id']]
    ic=m['industry_code'];T[r['user_id']].append(dict(amt=int(r['amount_won']),lane=r['lane'],grp=GROUP.get(ic,'OTHER'),reg=m['dongbaek_status']=='REGISTERED',rk={'FRANCHISE_DIRECT_CAFE':'DCAFE','LARGE_MART_SSM':'BIGMART'}.get(ic,GROUP.get(ic,'OTHER'))))
    c=r['S01_selected_card']
    if c in CARDN: cardben[r['user_id']][c]+=int(r['S01_benefit_won'])+1  # +1: 같은 혜택이면 많이 쓰인 카드
rows=[];ids=sorted(U)
for uid in ids:
    p=P[uid]; f=feats(T[uid], int(p['ws']=='활성'), p['cc'], AGE.get(p['age'],50))
    u=U[uid]; f['y_gain']=int(u['S11_benefit_won'])-int(u['S00_benefit_won']); f['y_op']=int(u['S01_benefit_won'])-int(u['S00_benefit_won'])
    f['y_card']=best_card(T[uid])[0]
    rows.append(f)
df=pd.DataFrame(rows,index=ids)
X_cols=[c for c in df.columns if not c.startswith('y_')]
X=df[X_cols].values
# 1) 회귀
kf=KFold(5,shuffle=True,random_state=7)
reg=RandomForestRegressor(n_estimators=400,min_samples_leaf=3,random_state=7)
pred_gain=cross_val_predict(reg,X,df.y_gain,cv=kf); reg.fit(X,df.y_gain)
reg_op=RandomForestRegressor(n_estimators=400,min_samples_leaf=3,random_state=7)
pred_op=cross_val_predict(reg_op,X,df.y_op,cv=kf); reg_op.fit(X,df.y_op)
base_mae=mean_absolute_error(df.y_gain,[df.y_gain.mean()]*len(df))
# 2) 분류
yc=df.y_card; keep=yc!='NONE'
clf=RandomForestClassifier(n_estimators=400,min_samples_leaf=2,random_state=7,class_weight='balanced')
skf=StratifiedKFold(5,shuffle=True,random_state=7)
pred_card=pd.Series('NONE',index=df.index)
pred_card[keep]=cross_val_predict(clf,X[keep.values],yc[keep],cv=skf)
clf.fit(X[keep.values],yc[keep])
maj=yc[keep].value_counts(normalize=True).iloc[0]
# 3) 군집
sc=StandardScaler().fit(df[[c for c in X_cols if c.startswith('sh_') or c.startswith('lane_') or c in('db_offline_share','amt_avg')]])
CL=[c for c in X_cols if c.startswith('sh_') or c.startswith('lane_') or c in('db_offline_share','amt_avg')]
km=KMeans(5,n_init=20,random_state=7).fit(sc.transform(df[CL]))
cl=km.labels_
# 군집 이름: 가장 큰 업종 비중
names={}
for k in range(5):
    sub=df[cl==k]; shc=[c for c in CL if c.startswith('sh_')]; top=(sub[shc].mean()-df[shc].mean()).sort_values(ascending=False)
    lab={'sh_FOOD':'음식점','sh_CAFE':'카페','sh_CVS':'편의점','sh_MART':'마트','sh_MED':'병원·약국','sh_ACAD':'학원','sh_LEISURE':'미용·여가','sh_FUEL':'주유','sh_CLOTH':'의류','sh_ONLINE':'온라인','sh_OTHER':'기타'}
    names[k]=f"{lab[top.index[0]]}·{lab[top.index[1]]} 많이 쓰는 고객"
imp=sorted(zip(X_cols,reg.feature_importances_),key=lambda x:-x[1])[:6]
FN={'wallet_active':'동백전 활성 지갑','db_offline_share':'동백전 가맹 오프라인 비중','amt_total':'월 결제액','n_tx':'결제 건수','amt_avg':'건당 금액','card_count':'보유 카드 수','age':'연령','lane_OFFLINE':'오프라인 비중','lane_ONLINE':'온라인 비중','lane_SIMPLE_PAY':'간편결제 비중'}
for g in GROUPS: FN['sh_'+g]={'FOOD':'음식점','CAFE':'카페','CVS':'편의점','MART':'마트','MED':'병원·약국','ACAD':'학원','LEISURE':'미용·여가','FUEL':'주유','CLOTH':'의류','ONLINE':'온라인몰','OTHER':'기타'}[g]+' 비중'
# 실제 사례 적용
C=json.load(open(CASES)); real={}
PROF={'T1':dict(wallet=1,cc=3,age=25),'T4':dict(wallet=1,cc=2,age=25)}
for code in ('T1','T4'):
    txs=[]
    for t in C:
        if t['c']!=code: continue
        ind=t['ind']; online=ind in('온라인쇼핑','통신·구독','배달앱') or any(k in t['m'] for k in('NICE','네이버페이','AGODA','ANTHROPIC','자동납부','우아한','땡겨요','쿠팡','버스타고'))
        if t['tool']=='현금·계좌이체': continue
        g=KO.get(ind,'OTHER'); txs.append(dict(amt=t['amt'],lane='ONLINE' if online else 'OFFLINE',grp=g,reg=t['dbm']=='예',rk={'대형마트(이마트·홈플러스 등)':'BIGMART'}.get(ind,g)))
    f=feats(txs,PROF[code]['wallet'],PROF[code]['cc'],PROF[code]['age']); x=np.array([[f[c] for c in X_cols]])
    proba=clf.predict_proba(x)[0]; order=np.argsort(-proba)
    trees=np.array([e.predict(x)[0] for e in reg.estimators_])
    real[code]=dict(gain=int(reg.predict(x)[0]),gain_lo=int(np.percentile(trees,20)),gain_hi=int(np.percentile(trees,80)),op=int(reg_op.predict(x)[0]),
      card=[[CARDN[clf.classes_[i]],round(float(proba[i]),2)] for i in order[:3]],cluster=names[int(km.predict(sc.transform(pd.DataFrame([f])[CL]))[0])],
      rule_card=CARDN[best_card(txs)[0]],other_share=round(f['sh_OTHER'],2),db_offline_share=round(f['db_offline_share'],3),n=len(txs))
out=dict(
  metrics=dict(n=len(df),gain_mae=int(mean_absolute_error(df.y_gain,pred_gain)),gain_base_mae=int(base_mae),gain_r2=round(r2_score(df.y_gain,pred_gain),2),
    op_mae=int(mean_absolute_error(df.y_op,pred_op)),op_r2=round(r2_score(df.y_op,pred_op),2),
    card_acc=round(accuracy_score(yc[keep],pred_card[keep]),2),card_base=round(float(maj),2),card_n=int(keep.sum())),
  importance=[[FN.get(k,k),round(float(v),3)] for k,v in imp],
  clusters={str(k):dict(name=names[k],n=int((cl==k).sum()),gain=int(df.y_gain[cl==k].mean())) for k in range(5)},
  users={uid:dict(pg=int(pred_gain[i]),po=int(pred_op[i]),pc=CARDN.get(pred_card.iloc[i],'—'),tc=CARDN.get(yc.iloc[i],'—'),cl=int(cl[i])) for i,uid in enumerate(ids)},
  real=real)
json.dump(out,open(OUT,'w'),ensure_ascii=False)
print(json.dumps(out['metrics'],ensure_ascii=False)); print(out['importance']); print(out['clusters']); print(json.dumps(real,ensure_ascii=False))
