import unittest
from decimal import Decimal
from onepass.engine import *

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.policy = DbPolicy()
        self.shop = Merchant('M', 'FOOD', True, 'LE_10B')
        self.cards = [Card('DB', CardType.DONGBAEK_CHECK, account_id='A'),
                      Card('CR', CardType.CREDIT, credit_limit=100000,
                           prev_month_perf=300000, rules=(BenefitRule('R', ('FOOD',), Decimal('0.03')),))]
        self.state = State(accounts={'A': 100000}, db_charge=50000)
    def test_max_benefit(self):
        d = process(Request('T', 'M', 10000), self.shop, self.cards, self.state, self.policy)
        self.assertEqual((d.selected_card_id, d.benefit_won), ('DB', 1000))
        self.assertEqual((self.state.db_charge, self.state.db_cashback), (40000,1000))
    def test_fallback_has_zero_cashback(self):
        self.state.db_charge = 0
        d = process(Request('T','M',10000), self.shop, self.cards, self.state, self.policy)
        self.assertEqual((d.selected_card_id, d.benefit_won), ('CR', 300))
    def test_shared_account(self):
        d = process(Request('T','M',60000), self.shop,
                    [self.cards[0], Card('CK', CardType.DEBIT, account_id='A')], self.state, self.policy)
        self.assertEqual(d.selected_card_id, 'CK')
        self.assertEqual(self.state.accounts['A'], 40000)
    def test_credit_limit(self):
        self.state.credit_used['CR'] = 99000
        c = evaluate(self.cards[1], self.shop, 2000, self.state, self.policy)
        self.assertFalse(c.eligible)
    def test_onecard_block(self):
        d = process(Request('T','M',1000,False),self.shop,self.cards,self.state,self.policy)
        self.assertFalse(d.approved)
        self.assertEqual(len(self.state.ledger),0)
    def test_not_registered(self):
        m = Merchant('M2','FOOD',False)
        self.assertEqual(evaluate(self.cards[0],m,500,self.state,self.policy).reason,'NOT_DB_MERCHANT')
    def test_duplicate(self):
        req = Request('T','M',1000)
        process(req,self.shop,self.cards,self.state,self.policy)
        again=process(req,self.shop,self.cards,self.state,self.policy)
        self.assertEqual(again.reason,'DUPLICATE_REQUEST')
        self.assertEqual(len(self.state.ledger),1)
    def test_cashback_funding_buckets(self):
        self.state.db_grant = 3000
        self.state.db_cashback = 2000
        d=process(Request('T','M',10000), self.shop,self.cards,self.state,self.policy)
        self.assertEqual(next(c for c in d.candidates if c.card_id=='DB').expected_benefit,500)
        self.assertEqual(self.state.db_charge,45000)
    def test_month_cap(self):
        self.state.db_month_applied=499000
        d=process(Request('T','M',10000),self.shop,self.cards,self.state,self.policy)
        self.assertEqual(next(c for c in d.candidates if c.card_id=='DB').expected_benefit,100)

class DirectPaymentTests(unittest.TestCase):

    def test_direct_payment_with_blocked_onecard(self):
        from onepass.engine import (
            Card, CardType, Merchant, State,
            Request, DbPolicy, process
        )

        cards = [
            Card(
                "CK01",
                CardType.DEBIT,
                account_id="ACC01"
            )
        ]

        merchant = Merchant(
            "M01", "FOOD", False
        )

        state = State(
            accounts={"ACC01": 50000}
        )

        request = Request(
            id="DIRECT001",
            merchant_id="M01",
            amount=10000,
            onecard_active=False,
            payment_path="DIRECT",
            direct_card_id="CK01"
        )

        result = process(
            request, merchant, cards, state, DbPolicy()
        )

        self.assertTrue(result.approved)
        self.assertEqual(result.selected_card_id, "CK01")
        self.assertEqual(state.accounts["ACC01"], 40000)

    def test_onecard_blocked(self):
        from onepass.engine import (
            Card, CardType, Merchant, State,
            Request, DbPolicy, process
        )

        cards = [
            Card(
                "CK01",
                CardType.DEBIT,
                account_id="ACC01"
            )
        ]

        request = Request(
            id="AUTO001",
            merchant_id="M01",
            amount=10000,
            onecard_active=False,
            payment_path="ONECARD"
        )

        result = process(
            request,
            Merchant("M01", "FOOD", False),
            cards,
            State(accounts={"ACC01": 50000}),
            DbPolicy()
        )

        self.assertFalse(result.approved)
        self.assertEqual(result.reason, "ONECARD_BLOCKED")


if __name__=='__main__': unittest.main()
