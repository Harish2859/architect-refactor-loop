from payment_processor import process_payment, get_bal, refund, apply_discount

if __name__ == "__main__":
    print("Balance u1:", get_bal("u1"))

    r = process_payment("u1", 100, "purchase")
    print("Payment:", r)

    print("Balance u1 after:", get_bal("u1"))

    if r["s"]:
        refund(r["tx_id"])
        print("Balance u1 after refund:", get_bal("u1"))

    apply_discount("u1", 10)
    print("Balance u1 after discount:", get_bal("u1"))
