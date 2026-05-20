import unittest
from payment_processor import DB, process_payment, get_bal, refund, apply_discount

def reset_db():
    DB["users"] = {"u1": {"balance": 500}, "u2": {"balance": 0}}
    DB["transactions"] = []

class TestPaymentProcessor(unittest.TestCase):

    def setUp(self):
        reset_db()

    def test_successful_payment(self):
        r = process_payment("u1", 100, "purchase")
        self.assertTrue(r["s"])
        self.assertIn("tx_id", r)
        self.assertEqual(get_bal("u1"), 400)

    def test_insufficient_balance(self):
        r = process_payment("u2", 50, "purchase")
        self.assertFalse(r["s"])
        self.assertEqual(r["msg"], "low balance")

    def test_unknown_user(self):
        r = process_payment("u99", 10, "purchase")
        self.assertFalse(r["s"])
        self.assertEqual(r["msg"], "no user")

    def test_refund_restores_balance(self):
        r = process_payment("u1", 200, "purchase")
        self.assertTrue(refund(r["tx_id"]))
        self.assertEqual(get_bal("u1"), 500)

    def test_refund_invalid_id(self):
        self.assertFalse(refund("0000"))

    def test_apply_discount(self):
        apply_discount("u1", 10)
        self.assertEqual(get_bal("u1"), 550)

    def test_get_bal_unknown_user(self):
        self.assertIsNone(get_bal("u99"))

if __name__ == "__main__":
    unittest.main()
