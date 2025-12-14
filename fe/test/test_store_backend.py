import pytest

import be.model.store as store_module


class DummyResult:
    def __init__(self, scalar_value=None):
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value


class ConnectionStub:
    """
    既可作为上下文管理器配合 init_tables 使用，
    也可直接传递给 index_exists。
    """
    def __init__(self, scalar_values, recorder):
        self._scalar_iter = iter(scalar_values)
        self.recorder = recorder

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params=None):
        sql = str(statement).strip()
        self.recorder.append((sql, params))
        if "INFORMATION_SCHEMA.STATISTICS" in sql:
            return DummyResult(next(self._scalar_iter, 0))
        return DummyResult()


class EngineStub:
    def __init__(self, connection):
        self._connection = connection

    def connect(self):
        return self._connection


INDEX_NAMES = [
    "idx_users_user_id",
    "unique_store_user_book",
    "idx_new_order_order_id",
    "idx_new_order_detail_order_id_book_id",
    "idx_history_order_order_id",
    "idx_history_order_detail_order_id_book_id",
    "idx_new_books_title_tags",
]


def test_init_tables_creates_missing_indexes(monkeypatch):
    executed = []
    connection = ConnectionStub([0] * len(INDEX_NAMES), executed)
    engine = EngineStub(connection)

    monkeypatch.setattr(store_module, "create_engine", lambda *args, **kwargs: engine)
    store_module.Store("sqlite:///dummy")

    created_indexes = [
        sql for sql, _ in executed if "CREATE" in sql and "INDEX" in sql
    ]
    for name in INDEX_NAMES:
        assert any(name in sql for sql in created_indexes)


def test_init_tables_skips_existing_indexes(monkeypatch):
    executed = []
    connection = ConnectionStub([1] * len(INDEX_NAMES), executed)
    engine = EngineStub(connection)

    monkeypatch.setattr(store_module, "create_engine", lambda *args, **kwargs: engine)
    store_module.Store("sqlite:///dummy")

    created_indexes = [
        sql for sql, _ in executed if "CREATE" in sql and "INDEX" in sql
    ]
    assert created_indexes == []


def test_index_exists_returns_boolean(monkeypatch):
    executed = []
    connection = ConnectionStub([1], executed)
    store_obj = store_module.Store.__new__(store_module.Store)

    result = store_module.Store.index_exists(
        store_obj, connection, "users", "idx_users_user_id"
    )

    assert result is True
    sql, params = executed[0]
    assert "INFORMATION_SCHEMA.STATISTICS" in sql
    assert params == {"table_name": "users", "index_name": "idx_users_user_id"}