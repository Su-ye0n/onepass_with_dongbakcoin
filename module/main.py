from decimal import Decimal
from onepass.engine import Card, CardType, Merchant, BenefitRule, DbPolicy, State, Request, process

cards = [
    Card('DB01', CardType.DONGBAEK_CHECK, account_id='ACC01'),
    Card('CK01', CardType.DEBIT, account_id='ACC01', prev_month_perf=400000,
         rules=(BenefitRule('CAFE5', ('CAFE',), Decimal('0.05'), 300000, 1000, 2000, 10000),)),
    Card('CR01', CardType.CREDIT, credit_limit=1_000_000, prev_month_perf=400000,
         rules=(BenefitRule('FOOD3', ('FOOD',), Decimal('0.03'), 300000, 0, 3000, 10000),)),
]
merchants = {'M1': Merchant('M1', 'FOOD', True, 'LE_10B'),
             'M2': Merchant('M2', 'CAFE', False)}
state = State(accounts={'ACC01': 100_000}, db_charge=60_000)
policy = DbPolicy()
requests = [Request('T001', 'M1', 20000), Request('T002', 'M2', 10000), Request('T003', 'M1', 50000)]
for request in requests:
    result = process(request, merchants[request.merchant_id], cards, state, policy)
    print(f'{request.id}: approved={result.approved} card={result.selected_card_id} '
          f'benefit={result.benefit_won:,}원 reason={result.reason}')
    for c in result.candidates:
        print(f'  {c.card_id:5} eligible={c.eligible} benefit={c.expected_benefit:,} reason={c.reason}')
print('\nFinal state:', state)
