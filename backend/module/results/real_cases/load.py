import openpyxl,json,csv,collections,warnings
warnings.filterwarnings('ignore')
U='/mnt/user-data/uploads/'
FILES=[('2242cbc1-_____T2.xlsx','T1'),('239c7f87-________.xlsx','T2'),('9f75f3c8-_____________.xlsx','T3'),('54c3d2d1-___________.xlsx','T4'),('a25d3bf4-_______.xlsx','T5'),('5e5f917c-_____T6.xlsx','T6')]
people=[];txs=[]
for fn,code in FILES:
    wb=openpyxl.load_workbook(U+fn,data_only=True)
    ps=wb['참여자 정보']; info={r[0]:r[1] for r in ps.iter_rows(min_row=2,max_row=9,max_col=2,values_only=True) if r[0]}
    cards=[]
    for r in ps.iter_rows(min_row=11,max_row=18,max_col=5,values_only=True):
        if r[0] and str(r[0]).startswith('카드') and r[1]: cards.append(dict(alias=r[0],name=r[1],type=r[2],perf=r[3],benefit=r[4]))
    people.append(dict(code=code,file_code=info.get('참여자 코드'),month=info.get('기준월'),age=info.get('연령대'),gu=info.get('사는 구·군'),db=info.get('동백전 있음'),db_bal=info.get('기준월 1일 동백전 잔액(원)'),db_cb=info.get('기준월 받은 동백전 캐시백(원)'),prev=info.get('전월 카드 결제 총액(원, 대략)'),cards=cards))
    ws=wb['결제 내역']
    for r in ws.iter_rows(min_row=2,max_col=14,values_only=True):
        if not r[0] or r[6] in (None,''): continue
        d=str(r[0])[:10]
        if d in('2026-06-03','2026-06-05') and r[2] in('모모스커피','오늘은 돼지'): continue  # 양식 예시 줄
        txs.append(dict(pid=code,date=d,time=r[1],store=r[2],branch=r[3],gu=r[4],ind=r[5],amt=int(float(r[6])),method=r[7],easy=r[8],tool=r[9],card=r[10],benefit=r[11],dbm=r[12],memo=r[13]))
json.dump(dict(people=people,txs=txs),open('raw.json','w'),ensure_ascii=False,default=str,indent=1)
for p in people: print(p['code'],p['file_code'],p['month'],p['age'],p['gu'],p['db'],p['prev'],[c['name'] for c in p['cards']])
c=collections.Counter(t['pid'] for t in txs);print(c)
for k in['method','easy','tool','dbm','ind','gu']: print(k,collections.Counter(t[k] for t in txs).most_common(25))
print(sum(1 for t in txs if t['benefit'] not in (None,'')), len(txs))
