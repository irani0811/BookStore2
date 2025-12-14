import pytest
import uuid

from fe.access.new_buyer import register_new_buyer
from fe.access.new_seller import register_new_seller
from fe.test.gen_book_data import GenBook

class TestQueryOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        # 初始化 seller, store, buyer
        self.seller_id = "test_query_order_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_query_order_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_query_order_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id

        # 注册 buyer
        self.buyer = register_new_buyer(self.buyer_id, self.password)

        # 注册 seller 并创建店铺和书籍
        self.gen_book = GenBook(self.seller_id, self.store_id)
        yield

    # 测试查询存在的订单
    def test_order_history_ok(self):
        # 生成书籍并下单
        ok, buy_book_id_list = self.gen_book.gen(
            non_exist_book_id=False, low_stock_level=False
        )
        assert ok
        code, _ = self.buyer.new_order(self.store_id, buy_book_id_list)
        assert code == 200

        # 查询订单历史
        code, orders = self.buyer.query_order()
        assert code == 200

    # 测试查询不存在的订单
    def test_order_history_non_exist(self):
        # 使用不存在的用户 ID 查询订单历史
        self.buyer.user_id = self.buyer.user_id + "_x"
        code, orders = self.buyer.query_order()
        assert code != 200  # 预期查询失败

    def test_order_history_non_exist_store(self):
        # 生成书籍并下单
        ok, buy_book_id_list = self.gen_book.gen(
            non_exist_book_id=False, low_stock_level=False
        )
        assert ok

        # 使用不存在的 store_id 创建订单
        code, _ = self.buyer.new_order(self.store_id + "_x", buy_book_id_list)
        assert code != 200  # 预期创建订单失败

        # 查询订单历史，验证该订单不存在
        code, orders = self.buyer.query_order()
        assert code == 529  # 预期查询订单失败，返回 529 错误码
