import json
import pytest
import sqlalchemy.exc as sa_exc

from be.model import seller as seller_module
from be.model import error


class ResultStub:
    def __init__(self, fetchone=None, scalar=None):
        self._fetchone = fetchone
        self._scalar = scalar

    def fetchone(self):
        return self._fetchone

    def scalar(self):
        return self._scalar


class TransactionStub:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class ConnectionStub:
    def __init__(self, *, result=None, execute_side_effect=None, begin_side_effect=None):
        self.result = result or ResultStub()
        self.execute_side_effect = execute_side_effect
        self.begin_side_effect = begin_side_effect
        self.transaction = TransactionStub()
        self.commit_count = 0
        self.last_execute = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.last_execute = (query, params)
        if self.execute_side_effect:
            if isinstance(self.execute_side_effect, Exception):
                raise self.execute_side_effect
            return self.execute_side_effect(query, params)
        return self.result

    def commit(self):
        self.commit_count += 1

    def begin(self):
        if self.begin_side_effect:
            if isinstance(self.begin_side_effect, Exception):
                raise self.begin_side_effect
            return self.begin_side_effect()
        return self.transaction


class EngineStub:
    def __init__(self, contexts):
        self._contexts = list(contexts)

    def connect(self):
        if not self._contexts:
            raise AssertionError("No more connection contexts available")
        context = self._contexts.pop(0)
        if isinstance(context, Exception):
            raise context
        return context


@pytest.fixture
def seller_instance():
    instance = seller_module.Seller.__new__(seller_module.Seller)
    instance.user_id_exist = lambda _: True
    instance.store_id_exist = lambda _: True
    instance.book_id_exist_in_store = lambda *args, **kwargs: False
    return instance


def test_add_book_missing_required_fields_returns_400(seller_instance):
    seller_instance.conn = EngineStub([])
    book_info = {"title": "Only title field"}
    code, message = seller_instance.add_book(
        "uid", "sid", "bid", json.dumps(book_info), 5
    )
    assert code == 400
    assert "Missing required fields" in message


def test_add_book_invalid_json_returns_400(seller_instance):
    seller_instance.conn = EngineStub([])
    code, message = seller_instance.add_book(
        "uid", "sid", "bid", "{bad json", 5
    )
    assert code == 400
    assert "Invalid JSON format" in message


def test_add_book_flattens_tag_list(seller_instance):
    context_store = ConnectionStub()
    context_book = ConnectionStub()
    seller_instance.conn = EngineStub([context_store, context_book])

    book_info = {
        "tags": ["tech", "python"],
        "picture": "/cover.png",
        "title": "Test Title",
        "author": "Author",
        "publisher": "Publisher",
        "original_title": "Original",
        "translator": "Translator",
        "pub_year": 2020,
        "pages": 300,
        "price": 99.0,
        "currency_unit": "CNY",
        "binding": "Paperback",
        "isbn": "1234567890",
        "author_intro": "Intro",
        "book_intro": "Book Intro",
        "content": "Content body"
    }

    code, message = seller_instance.add_book(
        "uid", "sid", "bid", json.dumps(book_info), 10
    )
    assert (code, message) == (200, "ok")
    _, params = context_book.last_execute
    assert params["tags"] == "tech\npython"


def test_add_book_handles_unexpected_exception(seller_instance):
    failing_context = ConnectionStub(execute_side_effect=RuntimeError("db down"))
    seller_instance.conn = EngineStub([failing_context])
    code, message = seller_instance.add_book(
        "uid", "sid", "bid",
        json.dumps({
            "tags": [],
            "picture": "",
            "title": "Test",
            "author": "Author",
            "publisher": "Publisher",
            "original_title": "",
            "translator": "",
            "pub_year": 2020,
            "pages": 100,
            "price": 10.0,
            "currency_unit": "CNY",
            "binding": "",
            "isbn": "isbn",
            "author_intro": "",
            "book_intro": "",
            "content": ""
        }),
        5
    )
    assert code == 528
    assert "Unexpected error" in message


def test_add_stock_level_invalid_increment_returns_400(seller_instance):
    seller_instance.conn = EngineStub([])
    code, message = seller_instance.add_stock_level("uid", "sid", "bid", 0)
    assert code == 400
    assert "Invalid stock level" in message


def test_add_stock_level_transaction_failure_rolls_back(seller_instance):
    fetch_context = ConnectionStub(result=ResultStub(fetchone=(5,)))
    update_context = ConnectionStub(execute_side_effect=RuntimeError("write fail"))
    seller_instance.conn = EngineStub([fetch_context, update_context])

    code, message = seller_instance.add_stock_level("uid", "sid", "bid", 3)
    assert code == 528
    assert "更新库存时发生错误" in message
    assert update_context.transaction.rolled_back


def test_add_stock_level_outer_exception(seller_instance):
    fetch_context = ConnectionStub(result=ResultStub(fetchone=(5,)))
    seller_instance.conn = EngineStub([fetch_context, RuntimeError("connect fail")])
    code, message = seller_instance.add_stock_level("uid", "sid", "bid", 3)
    assert code == 528
    assert "添加库存过程中发生错误" in message


def test_create_store_integrity_error(seller_instance):
    exist_context = ConnectionStub(result=ResultStub(scalar=0))
    insert_context = ConnectionStub(
        execute_side_effect=sa_exc.IntegrityError(
            "stmt", {}, Exception("duplicate")
        )
    )
    seller_instance.conn = EngineStub([exist_context, insert_context])

    code, message = seller_instance.create_store("uid", "sid")
    assert code == 400
    assert "already exists" in message
    assert insert_context.transaction.rolled_back


def test_create_store_sqlalchemy_error(seller_instance):
    exist_context = ConnectionStub(result=ResultStub(scalar=0))
    insert_context = ConnectionStub(
        execute_side_effect=sa_exc.SQLAlchemyError("db error")
    )
    seller_instance.conn = EngineStub([exist_context, insert_context])

    code, message = seller_instance.create_store("uid", "sid")
    assert code == 528
    assert "Database error" in message
    assert insert_context.transaction.rolled_back


def test_create_store_outer_sqlalchemy_error(seller_instance):
    seller_instance.conn = EngineStub([sa_exc.SQLAlchemyError("connect error")])
    code, message = seller_instance.create_store("uid", "sid")
    assert code == 528
    assert "Database error" in message


def test_create_store_outer_unexpected_error(seller_instance):
    seller_instance.conn = EngineStub([RuntimeError("boom")])
    code, message = seller_instance.create_store("uid", "sid")
    assert code == 528
    assert "Unexpected error" in message


def test_delivery_order_store_mismatch(seller_instance):
    store_context = ConnectionStub(result=ResultStub(scalar=1))
    order_context = ConnectionStub(result=ResultStub(fetchone=(1, "other_store")))
    seller_instance.conn = EngineStub([store_context, order_context])

    code, message = seller_instance.delivery_order("sid", "oid")
    expected_code, _ = error.error_invalid_store_id("sid")
    assert code == expected_code
    assert "invalid_store_id" in message or message == error.error_invalid_store_id("sid")[1]


def test_delivery_order_invalid_status(seller_instance):
    store_context = ConnectionStub(result=ResultStub(scalar=1))
    order_context = ConnectionStub(result=ResultStub(fetchone=(3, "sid")))
    seller_instance.conn = EngineStub([store_context, order_context])

    code, message = seller_instance.delivery_order("sid", "oid")
    expected_code, _ = error.error_invalid_order_status("oid")
    assert code == expected_code
    assert "invalid_order_status" in message or message == error.error_invalid_order_status("oid")[1]


def test_delivery_order_update_error_rolls_back(seller_instance):
    store_context = ConnectionStub(result=ResultStub(scalar=1))
    order_context = ConnectionStub(result=ResultStub(fetchone=(1, "sid")))
    update_context = ConnectionStub(execute_side_effect=RuntimeError("update fail"))
    seller_instance.conn = EngineStub([store_context, order_context, update_context])

    code, message = seller_instance.delivery_order("sid", "oid")
    assert code == 528
    assert "发货时发生错误" in message
    assert update_context.transaction.rolled_back


def test_delivery_order_outer_exception(seller_instance):
    store_context = ConnectionStub(result=ResultStub(scalar=1))
    order_context = ConnectionStub(result=ResultStub(fetchone=(1, "sid")))
    seller_instance.conn = EngineStub([store_context, order_context, RuntimeError("connect fail")])

    code, message = seller_instance.delivery_order("sid", "oid")
    assert code == 528
    assert "发货时发生未知错误" in message