import builtins
from types import SimpleNamespace
from typing import Iterable, List, Tuple

import pytest

import be.model.buyer as buyer_module
from be.model import error


class MappingResult:
    def __init__(self, rows):
        self._rows = list(rows or [])

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class ResultStub:
    def __init__(self, *, fetchone=None, scalar=None, mappings=None, fetchall=None, rowcount=None):
        self._fetchone = fetchone
        self._scalar = scalar
        self._mappings = mappings
        self._fetchall = fetchall
        self.rowcount = rowcount

    def fetchone(self):
        return self._fetchone

    def scalar(self):
        return self._scalar

    def fetchall(self):
        if self._fetchall is not None:
            return list(self._fetchall)
        if self._mappings is not None:
            return list(self._mappings)
        return []

    def mappings(self):
        return MappingResult(self._mappings or [])


class TransactionStub:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class ConnectionStub:
    def __init__(
        self,
        *,
        execute_plan: Iterable = None,
        begin_side_effect=None,
        commit_side_effect=None,
        rollback_side_effect=None,
    ):
        self.execute_plan = list(execute_plan or [])
        self.begin_side_effect = begin_side_effect
        self.commit_side_effect = commit_side_effect
        self.rollback_side_effect = rollback_side_effect
        self.executed: List[Tuple[str, object]] = []
        self.transaction = None
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        sql = str(statement).strip()
        self.executed.append((sql, params))
        if not self.execute_plan:
            return ResultStub()
        step = self.execute_plan.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return step(sql, params)
        return step

    def begin(self):
        if isinstance(self.begin_side_effect, Exception):
            raise self.begin_side_effect
        if callable(self.begin_side_effect):
            self.transaction = self.begin_side_effect()
        elif self.begin_side_effect is None:
            self.transaction = TransactionStub()
        else:
            self.transaction = self.begin_side_effect
        return self.transaction

    def commit(self):
        if isinstance(self.commit_side_effect, Exception):
            raise self.commit_side_effect
        if callable(self.commit_side_effect):
            self.commit_side_effect()
        self.committed = True

    def rollback(self):
        if isinstance(self.rollback_side_effect, Exception):
            raise self.rollback_side_effect
        if callable(self.rollback_side_effect):
            self.rollback_side_effect()
        self.rolled_back = True


class EngineStub:
    def __init__(self, connections):
        self._connections = list(connections)

    def connect(self):
        if not self._connections:
            raise AssertionError("No more connections available.")
        conn = self._connections.pop(0)
        if isinstance(conn, Exception):
            raise conn
        return conn


def make_buyer(connections):
    buyer = buyer_module.Buyer.__new__(buyer_module.Buyer)
    buyer.conn = EngineStub(connections)
    return buyer


@pytest.fixture(autouse=True)
def reset_unpaid_orders(monkeypatch):
    monkeypatch.setattr(buyer_module, "unpaid_orders", [])


def test_new_order_aggregates_counts_and_success(monkeypatch):
    monkeypatch.setattr(buyer_module.uuid, "uuid1", lambda: "fake-uuid")

    user_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))])
    store_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))])
    book1_check = ConnectionStub(execute_plan=[ResultStub(fetchone=(10, 5))])
    book1_txn = ConnectionStub(
        execute_plan=[ResultStub(rowcount=1), ResultStub()],
        begin_side_effect=lambda: TransactionStub(),
    )
    book2_check = ConnectionStub(execute_plan=[ResultStub(fetchone=(8, 7))])
    book2_txn = ConnectionStub(
        execute_plan=[ResultStub(rowcount=1), ResultStub()],
        begin_side_effect=lambda: TransactionStub(),
    )
    order_conn = ConnectionStub(
        execute_plan=[ResultStub()],
        begin_side_effect=lambda: TransactionStub(),
    )

    buyer = make_buyer([user_conn, store_conn, book1_check, book1_txn, book2_check, book2_txn, order_conn])
    code, msg, order_id = buyer.new_order(
        "buyer-1",
        "store-1",
        [("book-1", 2), ("book-1", 3), ("book-2", 1), ("book-3", 0), ("book-4", -1), ("book-2", None)],
    )

    assert (code, msg) == (200, "ok")
    assert order_id.startswith("buyer-1_store-1_fake-uuid")
    assert buyer_module.unpaid_orders and buyer_module.unpaid_orders[0][0] == order_id
    assert book1_txn.transaction.committed and book2_txn.transaction.committed
    assert book1_txn.executed[0][1]["count"] == 5
    assert book2_txn.executed[0][1]["count"] == 1


def test_new_order_rolls_back_on_detail_exception(monkeypatch):
    monkeypatch.setattr(buyer_module.uuid, "uuid1", lambda: "uuid")

    buyer = make_buyer(
        [
            ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))]),
            ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))]),
            ConnectionStub(execute_plan=[ResultStub(fetchone=(5, 10))]),
            ConnectionStub(
                execute_plan=[ResultStub(rowcount=1), RuntimeError("detail insert fail")],
                begin_side_effect=lambda: TransactionStub(),
            ),
        ]
    )

    code, msg, order_id = buyer.new_order("buyer", "store", [("book", 1)])

    assert code == 530
    assert "detail insert fail" in msg
    assert order_id == ""


def test_new_order_rolls_back_on_order_insert_failure(monkeypatch):
    monkeypatch.setattr(buyer_module.uuid, "uuid1", lambda: "uuid")

    book_check = ConnectionStub(execute_plan=[ResultStub(fetchone=(3, 12))])
    book_txn = ConnectionStub(
        execute_plan=[ResultStub(rowcount=1), ResultStub()],
        begin_side_effect=lambda: TransactionStub(),
    )
    order_conn = ConnectionStub(
        execute_plan=[RuntimeError("order insert fail")],
        begin_side_effect=lambda: TransactionStub(),
    )

    buyer = make_buyer(
        [
            ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))]),
            ConnectionStub(execute_plan=[ResultStub(fetchone=(1,))]),
            book_check,
            book_txn,
            order_conn,
        ]
    )

    code, msg, order_id = buyer.new_order("buyer", "store", [("book", 1)])

    assert code == 530
    assert "order insert fail" in msg
    assert order_conn.transaction.rolled_back


def test_payment_returns_error_when_total_missing():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(mappings=[{"order_id": "o1", "user_id": "buyer", "store_id": "store-1"}]),
            ResultStub(mappings=[{"user_id": "buyer", "password": "pw", "balance": 100}]),
            ResultStub(scalar=None),
        ],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([conn])

    code, msg = buyer.payment("buyer", "pw", "o1")
    assert (code, msg) == (528, "Error calculating total price")


def test_payment_returns_error_when_seller_missing():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(mappings=[{"order_id": "o1", "user_id": "buyer", "store_id": "store-1"}]),
            ResultStub(mappings=[{"user_id": "buyer", "password": "pw", "balance": 200}]),
            ResultStub(scalar=120),
            ResultStub(),  # update buyer balance
            ResultStub(scalar=None),  # missing seller
        ],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([conn])

    code, msg = buyer.payment("buyer", "pw", "o1")
    assert (code, msg) == (528, "Invalid store_id")


def test_payment_rolls_back_on_update_failure():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(mappings=[{"order_id": "o1", "user_id": "buyer", "store_id": "store-1"}]),
            ResultStub(mappings=[{"user_id": "buyer", "password": "pw", "balance": 500}]),
            ResultStub(scalar=50),
            ResultStub(),  # update buyer
            ResultStub(scalar="seller-1"),
            RuntimeError("seller update fail"),
        ],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([conn])

    code, msg = buyer.payment("buyer", "pw", "o1")
    assert code == 528
    assert "seller update fail" in msg
    assert conn.rolled_back


def test_add_funds_rolls_back_on_update_failure():
    auth_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=("pw",))])
    txn_conn = ConnectionStub(
        execute_plan=[RuntimeError("update fail")],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([auth_conn, txn_conn])

    code, msg = buyer.add_funds("buyer", "pw", 100)
    assert code == 530
    assert "update fail" in msg
    assert txn_conn.transaction.rolled_back


def test_receive_order_returns_error_when_update_fails():
    lookup_conn = ConnectionStub(execute_plan=[ResultStub(mappings=[{"status": 2}])])
    txn_conn = ConnectionStub(
        execute_plan=[RuntimeError("update fail")],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([lookup_conn, txn_conn])

    code, msg = buyer.receive_order("buyer", "order-1")
    assert code == 528
    assert "更新订单状态失败" in msg
    assert txn_conn.transaction.rolled_back


def test_receive_order_handles_outer_exception():
    failing_conn = ConnectionStub(execute_plan=[RuntimeError("db down")])
    buyer = make_buyer([failing_conn])

    code, msg = buyer.receive_order("buyer", "order-1")
    assert code == 528
    assert "收货失败" in msg


def test_cancel_order_rejects_non_pending_status():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(mappings=[{"order_id": "o1", "status": 1, "store_id": "store"}]),
        ]
    )
    buyer = make_buyer([conn])

    expected_code, expected_msg = error.error_order_not_cancelable("o1")
    code, msg = buyer.cancel_order("buyer", "o1")
    assert (code, msg) == (expected_code, expected_msg)


def test_cancel_order_rolls_back_on_failure():
    lookup_conn = ConnectionStub(
        execute_plan=[
            ResultStub(mappings=[{"order_id": "o1", "status": 0, "store_id": "store"}]),
            ResultStub(mappings=[{"book_id": "book-1", "count": 2}]),
        ]
    )
    txn_conn = ConnectionStub(
        execute_plan=[
            ResultStub(),  # update stock
            ResultStub(),  # insert history details
            ResultStub(),  # insert history order
            ResultStub(),  # delete new_order
            RuntimeError("delete fail"),
        ],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([lookup_conn, txn_conn])

    code, msg = buyer.cancel_order("buyer", "o1")
    assert code == 528
    assert "取消订单时发生错误" in msg
    assert txn_conn.transaction.rolled_back


def test_auto_cancel_returns_ok_for_history_cancelled():
    history_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=(3,))])
    buyer = make_buyer([history_conn])

    code, msg = buyer.auto_cancel("order-1")
    assert (code, msg) == (200, "ok")


def test_auto_cancel_returns_error_when_new_order_pending():
    history_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=None)])
    new_order_conn = ConnectionStub(execute_plan=[ResultStub(fetchone=(0,))])
    buyer = make_buyer([history_conn, new_order_conn])

    code, msg = buyer.auto_cancel("order-1")
    assert code == 600
    assert error.error_not_cancel_order("order-1")[1] in msg[1]


def test_auto_cancel_returns_missing_order():
    buyer = make_buyer(
        [
            ConnectionStub(execute_plan=[ResultStub(fetchone=None)]),
            ConnectionStub(execute_plan=[ResultStub(fetchone=None)]),
        ]
    )
    code, msg = buyer.auto_cancel("order-1")
    assert (code, msg) == (518, error.error_missing_order("order-1"))


def test_auto_cancel_handles_exception():
    buyer = make_buyer([RuntimeError("db fail")])
    code, msg = buyer.auto_cancel("order-1")
    assert code == 528
    assert "Unexpected error" in msg


def test_recommend_books_one_no_orders():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(fetchone=(1,)),
            ResultStub(fetchall=[]),
        ]
    )
    buyer = make_buyer([conn])

    code, msg, books = buyer.recommend_books_one("buyer", 5)
    assert (code, msg, books) == (528, "User has no orders", [])


def test_recommend_books_one_no_purchased_books():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(fetchone=(1,)),
            ResultStub(fetchall=[("order-1",)]),
            ResultStub(fetchall=[]),
        ]
    )
    buyer = make_buyer([conn])

    code, msg, books = buyer.recommend_books_one("buyer", 5)
    assert (code, msg, books) == (528, "User has not purchased any books", [])


def test_recommend_books_one_no_similar_users():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(fetchone=(1,)),
            ResultStub(fetchall=[("order-1",)]),
            ResultStub(fetchall=[("book-1",)]),
            ResultStub(fetchall=[]),
        ]
    )
    buyer = make_buyer([conn])

    code, msg, books = buyer.recommend_books_one("buyer", 5)
    assert (code, msg, books) == (528, "No similar users found", [])


def test_recommend_books_one_no_recommendations():
    conn = ConnectionStub(
        execute_plan=[
            ResultStub(fetchone=(1,)),
            ResultStub(fetchall=[("order-1",)]),
            ResultStub(fetchall=[("book-1",)]),
            ResultStub(fetchall=[("user-x", "order-x", "book-1")]),
            ResultStub(mappings=[]),
        ]
    )
    buyer = make_buyer([conn])

    code, msg, books = buyer.recommend_books_one("buyer", 3)
    assert (code, msg, books) == (200, "No recommended books found", [])


def test_recommend_books_one_handles_exception():
    buyer = make_buyer([RuntimeError("db down")])
    code, msg, books = buyer.recommend_books_one("buyer", 3)
    assert code == 528
    assert "Error in recommendation" in msg


def test_generate_titles_rejects_empty_input():
    buyer = make_buyer([])
    code, msg, titles = buyer.generate_and_extract_titles("")
    assert (code, msg, titles) == (540, "输入文本不能为空", [])


def test_generate_titles_successful_flow(monkeypatch):
    class DummyTensor:
        def __init__(self, data):
            self.data = data

        def to(self, device):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self.data

    class DummyTokenizer:
        def __call__(self, texts):
            return {"input_ids": [[1, 2]], "attention_mask": [[1, 1]]}

        def batch_decode(self, outputs, skip_special_tokens=True, clean_up_tokenization_spaces=True):
            return ["《推荐书》"]

    class DummyModel:
        def to(self, device):
            return self

        def my_generate(self, **kwargs):
            return DummyTensor([[0, 1]])

    monkeypatch.setattr(buyer_module.AutoTokenizer, "from_pretrained", lambda *args, **kwargs: DummyTokenizer())
    monkeypatch.setattr(
        buyer_module.AutoModelForSeq2SeqLM,
        "from_pretrained",
        lambda *args, **kwargs: DummyModel(),
    )
    monkeypatch.setattr(buyer_module.torch.cuda, "is_available", lambda: False)
    monkeypatch.setattr(buyer_module.torch, "device", lambda name: name)
    monkeypatch.setattr(buyer_module.torch, "LongTensor", lambda data: DummyTensor(data))

    insert_conn = ConnectionStub(
        execute_plan=[ResultStub()],
        begin_side_effect=lambda: TransactionStub(),
    )
    buyer = make_buyer([insert_conn])

    code, titles = buyer.generate_and_extract_titles("一些文本")
    assert code == 200
    assert titles == ["推荐书"]
    assert insert_conn.committed or insert_conn.transaction.committed


def test_generate_titles_handles_generation_exception(monkeypatch):
    monkeypatch.setattr(
        buyer_module.AutoTokenizer,
        "from_pretrained",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("load fail")),
    )
    buyer = make_buyer([])
    code, titles = buyer.generate_and_extract_titles("内容")
    assert code == 528
    assert titles == []