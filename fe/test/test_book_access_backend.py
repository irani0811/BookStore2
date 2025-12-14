# fe/test/test_book_access_backend.py
import builtins
from types import SimpleNamespace
from typing import Iterable, List, Tuple

import pytest

from fe.access import book as book_module


class CursorStub:
    def __init__(
        self,
        *,
        fetchone=None,
        fetchall=None,
        execute_side_effect=None,
    ):
        self.fetchone_result = fetchone
        self.fetchall_result = fetchall
        self.execute_side_effect = execute_side_effect
        self.executed: List[Tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        if self.execute_side_effect:
            raise self.execute_side_effect
        self.executed.append((query.strip(), params))

    def fetchone(self):
        return self.fetchone_result

    def fetchall(self):
        return self.fetchall_result or []


class ConnectionStub:
    def __init__(self, cursors: Iterable[CursorStub]):
        self._cursor_iter = iter(cursors)

    def cursor(self, dictionary=False):
        cursor = next(self._cursor_iter)
        cursor.dictionary = dictionary
        return cursor


@pytest.fixture
def mysql_connect(monkeypatch):
    """允许在测试中为每个场景注入不同的连接替身。"""
    holders = SimpleNamespace(conn=None)

    def fake_connect(*args, **kwargs):
        if holders.conn is None:
            raise RuntimeError("connection stub not set")
        return holders.conn

    monkeypatch.setattr(book_module.mysql, "connect", fake_connect)
    return holders


def test_init_mysql_error(monkeypatch):
    monkeypatch.setattr(
        book_module.mysql,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(book_module.mysql.Error("boom")),
    )
    with pytest.raises(book_module.mysql.Error):
        book_module.BookDB(use_large_db=False)


def test_init_unexpected_error(monkeypatch):
    monkeypatch.setattr(
        book_module.mysql,
        "connect",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("oops")),
    )
    with pytest.raises(ValueError):
        book_module.BookDB(use_large_db=False)


def test_get_book_count_success(mysql_connect):
    mysql_connect.conn = ConnectionStub(
        [CursorStub(fetchone=(23,))]
    )
    db = book_module.BookDB(use_large_db=False)
    assert db.get_book_count() == 23


def test_get_book_count_mysql_error(mysql_connect):
    mysql_connect.conn = ConnectionStub(
        [CursorStub(execute_side_effect=book_module.mysql.Error("bad query"))]
    )
    db = book_module.BookDB(use_large_db=False)
    with pytest.raises(book_module.mysql.Error):
        db.get_book_count()


def test_get_book_count_unexpected_error(mysql_connect):
    mysql_connect.conn = ConnectionStub(
        [CursorStub(execute_side_effect=RuntimeError("cursor broken"))]
    )
    db = book_module.BookDB(use_large_db=False)
    with pytest.raises(RuntimeError):
        db.get_book_count()


def test_get_book_info_handles_tags_and_pictures(
    mysql_connect, monkeypatch, tmp_path
):
    valid_pic = tmp_path / "valid.jpg"
    valid_pic.write_bytes(b"img")

    rows = [
        {
            "id": "bk-valid",
            "title": "Valid Book",
            "tags": "tech, python",
            "picture_path": str(valid_pic),
        },
        {
            "id": "bk-missing",
            "title": "Missing Pic",
            "tags": "lost",
            "picture_path": str(tmp_path / "missing.jpg"),
        },
        {
            "id": "bk-error",
            "title": "Error Pic",
            "tags": "error",
            "picture_path": str(tmp_path / "error.jpg"),
        },
        {
            "id": "bk-nopic",
            "title": "No Pic",
            "tags": "",
            "picture_path": "",
        },
    ]

    base_open = builtins.open

    def fake_open(path, mode="r", *args, **kwargs):
        if "error" in path:
            raise RuntimeError("decode failure")
        return base_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    mysql_connect.conn = ConnectionStub(
        [CursorStub(fetchall=rows)]
    )

    db = book_module.BookDB(use_large_db=False)
    books = db.get_book_info(0, 10)

    assert len(books) == 4
    assert books[0]["tags"] == ["tech", "python"]
    assert books[0]["picture"] == str(valid_pic)
    assert books[1]["picture"] == ""
    assert books[2]["picture"] == ""
    assert books[3]["picture"] == ""


def test_get_book_info_mysql_error(mysql_connect):
    mysql_connect.conn = ConnectionStub(
        [CursorStub(execute_side_effect=book_module.mysql.Error("fail info"))]
    )
    db = book_module.BookDB(use_large_db=False)
    assert db.get_book_info(0, 5) == []


def test_get_book_info_unexpected_error(mysql_connect):
    mysql_connect.conn = ConnectionStub(
        [CursorStub(execute_side_effect=RuntimeError("boom info"))]
    )
    db = book_module.BookDB(use_large_db=False)
    assert db.get_book_info(0, 5) == []