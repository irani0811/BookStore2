import pytest
from fe.access.new_buyer import register_new_buyer
from fe.test.gen_book_data import GenBook
import uuid

class TestCancelOrder:    
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_cancel_order_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_cancel_order_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_cancel_order_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        self.buyer = register_new_buyer(self.buyer_id, self.password)
        yield

    def test_cancel_order_ok(self):
        # 下单
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False
        )
        assert ok
        code, order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200

        # 取消订单
        code, message = self.buyer.cancel_order(order_id)
        assert code == 200
        assert message == "ok"

    def test_cancel_non_exist_order(self):
        # 尝试取消不存在的订单
        code, _ = self.buyer.cancel_order("non_exist_order_id")
        assert code != 200
    
    def test_cancel_order_not_zero_status(self):
        # 下单
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(non_exist_book_id=False, low_stock_level=False)
        assert ok
        self.book_list = gen_book.buy_book_info_list

        # 输出调试信息，检查 book_list 数据结构
        print("[DEBUG] book_list content:", self.book_list)

        # 买家创建订单并支付
        code, order_id = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200

        # 增加资金并支付订单
        total_price = sum(book['price'] * num for book, num in self.book_list)  # 使用字典键访问
        print("[DEBUG] Calculated total_price:", total_price)

        self.buyer.add_funds(total_price)
        code = self.buyer.payment(order_id)
        assert code == 200

        # 调用取消订单的函数
        code, _ = self.buyer.cancel_order(order_id)
        assert code != 200  # 确保取消失败