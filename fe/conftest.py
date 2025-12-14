import requests
import threading
from urllib.parse import urljoin
from be import serve
from be.model.store import init_completed_event
from fe import conf

import uuid
import random
from types import SimpleNamespace
import pytest
from fe.access import auth
from fe.access.new_seller import register_new_seller
from fe.test.gen_book_data import GenBook

thread: threading.Thread = None


# 修改这里启动后端程序，如果不需要可删除这行代码
def run_backend():
    # rewrite this if rewrite backend
    serve.be_run()

@pytest.fixture(scope="session")
def search_env():
    auth_client = auth.Auth(conf.URL)
    user_id = f"test_search_user_{uuid.uuid4()}"
    password = f"pwd_{uuid.uuid4()}"
    assert auth_client.register(user_id, password) == 200
    seller_id = f"test_search_seller_{uuid.uuid4()}"
    store_id = f"test_search_store_{uuid.uuid4()}"
    # seller = register_new_seller(seller_id, seller_id)
    # assert seller.create_store(store_id) == 200
    gen_book = GenBook(seller_id, store_id)
    ok, _ = gen_book.gen(non_exist_book_id=False, low_stock_level=False, max_book_count=3)
    assert ok
    # for book_info, _ in gen_book.buy_book_info_list:
    #     assert seller.add_book(store_id=store_id, stock_level=10, book_info=book_info) == 200
    first_book = gen_book.buy_book_info_list[0][0]
    tag = random.choice(first_book["tags"])
    return SimpleNamespace(auth=auth_client, store_id=store_id, title=first_book["title"], tag=tag)

def pytest_configure(config):
    global thread
    print("frontend begin test")
    thread = threading.Thread(target=run_backend)
    thread.start()

    if not init_completed_event.wait(timeout=20):
        raise RuntimeError("Backend initialization timed out or failed (check logs/console for errors).")



def pytest_unconfigure(config):
    url = urljoin(conf.URL, "shutdown")
    requests.get(url)
    thread.join()
    print("frontend end test")
