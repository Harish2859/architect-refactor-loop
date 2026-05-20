import time
import random
import uuid
import threading

DB = {
    "users": {"u1": {"balance": 500}, "u2": {"balance": 0}},
    "transactions": []
}

class PaymentProcessor:
    def __init__(self, db):
        self._validate_db(db)
        self._db = db
        self._tx_map = {tx["id"]: tx for tx in db["transactions"]}
        self._lock = threading.Lock()
        self._user_balances = {uid: user["balance"] for uid, user in db["users"].items()}

    def _validate_db(self, db):
        self._validate_db_structure(db)
        self._validate_db_types(db)
        self._validate_db_values(db)

    def _validate_db_structure(self, db):
        if "users" not in db or "transactions" not in db:
            raise ValueError("Invalid database structure")

    def _validate_db_types(self, db):
        if not isinstance(db["users"], dict) or not isinstance(db["transactions"], list):
            raise ValueError("Invalid database structure")

    def _validate_db_values(self, db):
        for user_id, user in db["users"].items():
            if not isinstance(user_id, str) or not isinstance(user, dict) or "balance" not in user:
                raise ValueError("Invalid database values")
            if not isinstance(user["balance"], (int, float)) or user["balance"] < 0:
                raise ValueError("Invalid database values")
        for tx in db["transactions"]:
            if not isinstance(tx, dict) or "id" not in tx or "uid" not in tx or "amt" not in tx or "type" not in tx or "ts" not in tx:
                raise ValueError("Invalid database values")

    def process_payment(self, uid, amt, t):
        try:
            if not isinstance(uid, str) or not isinstance(amt, (int, float)) or not isinstance(t, str):
                raise ValueError("Invalid input: uid, amt, and t must be of type str, int/float, and str respectively")
            if amt <= 0:
                raise ValueError("Invalid amount: amount must be greater than zero")
            with self._lock:
                if uid not in self._db["users"]:
                    raise ValueError("User not found")
                if self._db["users"][uid]["balance"] < amt:
                    raise ValueError("Insufficient balance")
                tx_id = str(uuid.uuid4())
                new_balance = self._db["users"][uid]["balance"] - amt
                new_tx = {"id": tx_id, "uid": uid, "amt": amt, "type": t, "ts": time.time()}
                self._update_user_balance(uid, new_balance)
                self._db["transactions"].append(new_tx)
                self._tx_map[tx_id] = new_tx
            return {"s": True, "tx_id": tx_id}
        except ValueError as e:
            return {"s": False, "msg": str(e).lower().replace("insufficient balance", "low balance").replace("user not found", "no user")}
        except Exception as e:
            return {"s": False, "msg": "An unexpected error occurred: " + str(e)}

    def get_bal(self, uid):
        try:
            if not isinstance(uid, str):
                raise ValueError("Invalid user id: user id must be of type str")
            with self._lock:
                if uid not in self._db["users"]:
                    raise ValueError("User not found")
                return {"s": True, "balance": self._db["users"][uid]["balance"]}
        except ValueError as e:
            return {"s": False, "msg": str(e).lower().replace("user not found", "no user")}
        except Exception as e:
            return {"s": False, "msg": "An unexpected error occurred: " + str(e)}

    def refund(self, tx_id):
        try:
            if not isinstance(tx_id, str):
                raise ValueError("Invalid transaction id: transaction id must be of type str")
            with self._lock:
                if tx_id not in self._tx_map:
                    raise ValueError("Transaction not found")
                tx = self._tx_map[tx_id]
                if tx["uid"] not in self._db["users"]:
                    raise ValueError("User not found")
                new_balance = self._db["users"][tx["uid"]]["balance"] + tx["amt"]
                if new_balance < 0:
                    raise ValueError("Refund amount exceeds user balance")
                self._update_user_balance(tx["uid"], new_balance)
                self._db["transactions"] = [t for t in self._db["transactions"] if t["id"] != tx_id]
                del self._tx_map[tx_id]
            return {"s": True, "msg": "Refund successful"}
        except ValueError as e:
            return {"s": False, "msg": str(e).lower().replace("transaction not found", "no transaction").replace("user not found", "no user")}
        except Exception as e:
            return {"s": False, "msg": "An unexpected error occurred: " + str(e)}

    def apply_discount(self, uid, pct):
        try:
            if not isinstance(uid, str) or not isinstance(pct, (int, float)):
                raise ValueError("Invalid input: uid and pct must be of type str and int/float respectively")
            if pct < 0 or pct > 100:
                raise ValueError("Invalid discount percentage: discount percentage must be between 0 and 100")
            with self._lock:
                if uid not in self._db["users"]:
                    raise ValueError("User not found")
                if pct == 0:
                    return {"s": True}
                if self._db["users"][uid]["balance"] == 0:
                    raise ValueError("Cannot apply discount to zero balance")
                discount_amount = self._db["users"][uid]["balance"] * (pct / 100)
                new_balance = self._db["users"][uid]["balance"] + discount_amount
                self._update_user_balance(uid, new_balance)
            return {"s": True}
        except ValueError as e:
            return {"s": False, "msg": str(e)}
        except Exception as e:
            return {"s": False, "msg": "An unexpected error occurred: " + str(e)}

    def _update_user_balance(self, uid, new_balance):
        self._db["users"][uid]["balance"] = new_balance
        self._user_balances[uid] = new_balance

processor = PaymentProcessor(DB)

def process_payment(uid, amt, t):
    return processor.process_payment(uid, amt, t)

def get_bal(uid):
    result = processor.get_bal(uid)
    if isinstance(result, dict) and result.get("s") is False:
        return None
    return result.get("balance")

def refund(tx_id):
    result = processor.refund(tx_id)
    if result["s"] is False and result["msg"] == "no transaction":
        return False
    return result

def apply_discount(uid, pct):
    return processor.apply_discount(uid, pct)