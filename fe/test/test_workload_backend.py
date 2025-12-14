import json
import threading
from itertools import repeat

import pytest

import fe.bench.workload as workload
from fe import conf

DEFAULT_CONF = {
    "Book_Num_Per_Store": 2,
    "Store_Num_Per_User": 1,
    "Seller_Num": 1,
    "Buyer_Num": 1,
    "Session": 1,
    "Request_Per_Session": 1,
    "Default_Stock_Level": 5,
    "Default_User_Funds": 100,
    "Data_Batch_Size": 1,
    "Use_Large_DB": False,
}


def configure_bench_conf(monkeypatch, **overrides):
    values = DEFAULT_CONF.copy()
    values.update(overrides)
    for key, value in values.items():
        monkeypatch.setattr(conf, key, value, raising=False)


@pytest.fixture
def book_db_factory(monkeypatch):
    def _factory(count=5, infos=None):
        infos = infos or [[{"id": "book-0"}], []]

        class DummyBookDB:
            def __init__(self, use_large_db):
                self.count = count
                self._infos = [list(batch) for batch in infos]
                self._iter_index = 0

            def get_book_count(self):
                return self.count

            def get_book_info(self, start, size):
                if self._iter_index < len(self._infos):
                    batch = self._infos[self._iter_index]
                    self._iter_index += 1
                    return batch
                return []

        monkeypatch.setattr(workload.book, "BookDB", DummyBookDB)
        return DummyBookDB

    return _factory


@pytest.fixture
def stub_registers(monkeypatch):
    sellers = []
    buyers = []

    class DummySeller:
        def __init__(self, user_id):
            self.user_id = user_id
            self.created = []
            self.added = []

        def create_store(self, store_id):
            self.created.append(store_id)
            return 200

        def add_book(self, store_id, stock_level, book_info):
            self.added.append((store_id, book_info["id"]))
            return 200

    class DummyRegisteredBuyer:
        def __init__(self, user_id):
            self.user_id = user_id
            self.funds = 0

        def add_funds(self, amount):
            self.funds += amount

    def fake_register_new_seller(user_id, password):
        seller = DummySeller(user_id)
        sellers.append(seller)
        return seller

    def fake_register_new_buyer(user_id, password):
        buyer = DummyRegisteredBuyer(user_id)
        buyers.append(buyer)
        return buyer

    monkeypatch.setattr(workload, "register_new_seller", fake_register_new_seller)
    monkeypatch.setattr(workload, "register_new_buyer", fake_register_new_buyer)
    return sellers, buyers


@pytest.fixture
def stub_buyer_class(monkeypatch):
    class DummyBuyer:
        def __init__(self, url_prefix, user_id, password):
            self.url_prefix = url_prefix
            self.user_id = user_id
            self.password = password
            self.new_orders = []
            self.payments = []

        def new_order(self, store_id, book_id_and_count):
            self.new_orders.append((store_id, list(book_id_and_count)))
            return 200, f"order-{len(self.new_orders)}"

        def payment(self, order_id):
            self.payments.append(order_id)
            return 200

    monkeypatch.setattr(workload, "Buyer", DummyBuyer)
    return DummyBuyer


@pytest.fixture
def capture_writes(monkeypatch):
    messages = []
    monkeypatch.setattr(workload, "write_to_file", lambda message: messages.append(message))
    return messages


@pytest.fixture
def capture_logging(monkeypatch):
    infos = []
    warnings = []

    def fake_info(msg, *args, **kwargs):
        infos.append(msg % args if args else msg)

    def fake_warning(msg, *args, **kwargs):
        warnings.append(msg % args if args else msg)

    monkeypatch.setattr(workload.logging, "info", fake_info)
    monkeypatch.setattr(workload.logging, "warning", fake_warning)
    return infos, warnings


def make_blank_workload(tmp_path):
    wl = workload.Workload.__new__(workload.Workload)
    wl.cache_path = tmp_path / "workload_cache.json"
    wl._cache_signature = {"marker": "sig"}
    wl.uuid = None
    wl.store_ids = []
    wl.book_ids = {}
    wl.buyer_ids = []
    wl.n_new_order = 0
    wl.n_payment = 0
    wl.n_new_order_ok = 0
    wl.n_payment_ok = 0
    wl.time_new_order = 0
    wl.time_payment = 0
    wl.n_new_order_past = 0
    wl.n_payment_past = 0
    wl.n_new_order_ok_past = 0
    wl.n_payment_ok_past = 0
    wl.lock = threading.Lock()
    return wl


def test_workload_init_adjusts_book_count_and_sets_uuid(monkeypatch, book_db_factory):
    book_db_factory(count=3)
    configure_bench_conf(monkeypatch, Book_Num_Per_Store=10)
    monkeypatch.setattr(workload.Workload, "_try_load_cache", lambda self: False)
    wl = workload.Workload()
    assert wl.book_num_per_store == 3
    assert isinstance(wl.uuid, str) and wl.uuid


def test_workload_init_respects_existing_cache_uuid(monkeypatch, book_db_factory):
    book_db_factory(count=5)
    configure_bench_conf(monkeypatch)

    def fake_try(self):
        self.uuid = "cached-uuid"
        return True

    monkeypatch.setattr(workload.Workload, "_try_load_cache", fake_try)
    wl = workload.Workload()
    assert wl.uuid == "cached-uuid"
    assert wl.cache_loaded is True


def test_gen_database_populates_and_saves_cache(
    monkeypatch, tmp_path, book_db_factory, stub_registers, capture_writes, capture_logging
):
    sellers, buyers = stub_registers
    infos, _ = capture_logging
    book_db_factory(count=1, infos=[[{"id": "book-1"}], []])
    configure_bench_conf(monkeypatch, Book_Num_Per_Store=1, Buyer_Num=1)
    monkeypatch.setattr(workload.Workload, "_try_load_cache", lambda self: False)
    wl = workload.Workload()
    wl.cache_path = tmp_path / "cache.json"
    wl.gen_database()

    assert wl.cache_loaded is True
    assert sellers[0].created == [wl.store_ids[0]]
    assert wl.book_ids[wl.store_ids[0]] == ["book-1"]
    assert buyers[0].funds == conf.Default_User_Funds
    assert any("seller data loaded" in msg for msg in infos)

    payload = json.load(wl.cache_path.open("r", encoding="utf-8"))
    assert payload["uuid"] == wl.uuid
    assert payload["store_ids"] == wl.store_ids
    assert payload["book_ids"] == wl.book_ids
    assert payload["buyer_ids"] == wl.buyer_ids
    assert any("load data" in msg for msg in capture_writes)


def test_gen_database_skips_when_cache_present(monkeypatch, book_db_factory, capture_writes):
    book_db_factory(count=1)
    configure_bench_conf(monkeypatch)

    def fake_try(self):
        self.cache_loaded = True
        self.uuid = "cached"
        return True

    monkeypatch.setattr(workload.Workload, "_try_load_cache", fake_try)
    monkeypatch.setattr(
        workload,
        "register_new_seller",
        lambda *args, **kwargs: pytest.fail("should not register seller when cache exists"),
    )
    wl = workload.Workload()
    wl.gen_database()
    assert capture_writes == ["benchmark dataset already prepared; skip regenerate"]


def test_get_new_order_and_payment_flow(monkeypatch, book_db_factory, stub_buyer_class):
    book_db_factory(count=2)
    configure_bench_conf(monkeypatch, Buyer_Num=1)
    monkeypatch.setattr(workload.Workload, "_try_load_cache", lambda self: False)
    wl = workload.Workload()
    wl.store_ids = ["store-1"]
    wl.book_ids = {"store-1": ["book-A", "book-B"]}
    wl.buyer_num = 1

    randint_values = iter([1, 2, 2, 2])      # 依次用于买家序号、图书数量、每本书数量...
    uniform_values = iter([0.0, 1.0, 0.0])   # 第二次明确返回 1.0 ⇒ 选中索引 1 的 book-B
    monkeypatch.setattr(workload.random, "randint", lambda a, b: next(randint_values, 1))
    monkeypatch.setattr(workload.random, "uniform", lambda a, b: next(uniform_values, 0.0))

    new_order = wl.get_new_order()
    ok, order_id = new_order.run()
    assert ok is True
    assert order_id == "order-1"
    assert len(new_order.book_id_and_count) == 2
    assert len(new_order.buyer.new_orders) == 1

    payment = workload.Payment(new_order.buyer, order_id)
    assert payment.run() is True
    assert payment.buyer.payments == [order_id]


def test_update_stat_computes_metrics(monkeypatch, capture_writes, capture_logging, tmp_path):
    wl = make_blank_workload(tmp_path)
    infos, _ = capture_logging
    wl.update_stat(2, 2, 2, 2, 4.0, 6.0)

    assert wl.n_new_order_past == 2
    assert wl.n_payment_past == 2
    assert wl.n_new_order_ok_past == 2
    assert wl.n_payment_ok_past == 2
    assert capture_writes
    assert any("TPS_C" in msg for msg in infos)


def test_try_load_cache_returns_false_when_file_missing(tmp_path):
    wl = make_blank_workload(tmp_path)
    assert wl._try_load_cache() is False


def test_try_load_cache_returns_false_when_config_mismatch(tmp_path):
    wl = make_blank_workload(tmp_path)
    payload = {
        "uuid": "uid",
        "config": {"different": True},
        "store_ids": ["store-1"],
        "book_ids": {"store-1": ["book-1"]},
        "buyer_ids": ["buyer-1"],
    }
    wl.cache_path.write_text(json.dumps(payload), encoding="utf-8")
    assert wl._try_load_cache() is False


def test_try_load_cache_loads_valid_cache(tmp_path, capture_writes, capture_logging):
    wl = make_blank_workload(tmp_path)
    payload = {
        "uuid": "cached-uuid",
        "config": wl._cache_signature,
        "store_ids": ["store-1"],
        "book_ids": {"store-1": ["book-1"]},
        "buyer_ids": ["buyer-1"],
    }
    wl.cache_path.write_text(json.dumps(payload), encoding="utf-8")
    infos, warnings = capture_logging
    assert wl._try_load_cache() is True
    assert wl.uuid == "cached-uuid"
    assert wl.store_ids == ["store-1"]
    assert wl.book_ids == {"store-1": ["book-1"]}
    assert capture_writes == ["reuse benchmark dataset from cache"]
    assert any("benchmark dataset cache hit" in msg for msg in infos)
    assert not warnings


def test_try_load_cache_handles_corrupt_file(tmp_path, capture_logging):
    wl = make_blank_workload(tmp_path)
    wl.cache_path.write_text("{invalid", encoding="utf-8")
    _, warnings = capture_logging
    assert wl._try_load_cache() is False
    assert warnings


def test_save_cache_persists_payload(tmp_path):
    wl = make_blank_workload(tmp_path)
    wl.uuid = "uuid"
    wl.store_ids = ["store-1"]
    wl.book_ids = {"store-1": ["book-1"]}
    wl.buyer_ids = ["buyer-1"]
    wl._save_cache()

    data = json.load(wl.cache_path.open("r", encoding="utf-8"))
    assert data["uuid"] == "uuid"
    assert data["config"] == wl._cache_signature
    assert data["store_ids"] == ["store-1"]
    assert data["book_ids"] == {"store-1": ["book-1"]}
    assert data["buyer_ids"] == ["buyer-1"]


def test_save_cache_logs_when_write_fails(tmp_path, capture_logging):
    wl = make_blank_workload(tmp_path)
    wl.uuid = "uuid"
    wl.store_ids = ["store-1"]
    wl.book_ids = {"store-1": ["book-1"]}
    wl.buyer_ids = ["buyer-1"]
    wl.cache_path = tmp_path  # directory, open() will fail
    _, warnings = capture_logging
    wl._save_cache()
    assert warnings


def test_identifier_helpers_use_uuid(monkeypatch, book_db_factory):
    book_db_factory(count=1)
    configure_bench_conf(monkeypatch)
    monkeypatch.setattr(workload.Workload, "_try_load_cache", lambda self: False)
    wl = workload.Workload()

    seller_id, seller_pwd = wl.to_seller_id_and_password(5)
    assert str(5) in seller_id and wl.uuid in seller_id
    assert str(5) in seller_pwd and wl.uuid in seller_pwd

    store_id = wl.to_store_id(2, 3)
    assert str(2) in store_id and str(3) in store_id and wl.uuid in store_id