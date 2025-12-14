import time
import uuid
import pytest

from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.buyer import Buyer
from fe.access.book import Book

class TestAutoCancel:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = f"test_auto_cancel_seller_{uuid.uuid1()}"
        self.store_id = f"test_auto_cancel_store_{uuid.uuid1()}"
        self.buyer_id = f"test_auto_cancel_buyer_{uuid.uuid1()}"
        self.password = self.seller_id

        # 生成书籍
        gen_book = GenBook(self.seller_id, self.store_id)
        self.seller = gen_book.seller
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        assert ok

        # 注册买家
        self.buyer = register_new_buyer(self.buyer_id, self.password)

        # 计算总价
        self.total_price = sum(item[0]["price"] * item[1] for item in self.buy_book_info_list)

        # 添加足够的资金
        code = self.buyer.add_funds(self.total_price + 100000)
        assert code == 200

        # 创建订单
        code, self.order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200

        yield
    def test_ok(self):
        # 等待订单超时
        time.sleep(15)
        
        # 检查自动取消功能是否正确执行
        code, _ = self.buyer.auto_cancel(self.order_id)
        assert code == 200

    def test_not_ok(self):
        # 等待时间不足以超时
        time.sleep(5)
        
        # 检查订单未超时的情况下取消是否失败
        code, _ = self.buyer.auto_cancel(self.order_id)
        assert code != 200

    def test_auto_cancel_order_missing(self):
        # 生成一个随机的不存在的订单 ID
        missing_order_id = str(uuid.uuid1())
        
        # 检查不存在的订单自动取消是否失败
        code, _ = self.buyer.auto_cancel(missing_order_id)
        assert code != 200
