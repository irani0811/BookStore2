import pytest
import uuid
from fe.access.new_buyer import register_new_buyer
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.book import Book
import uuid

class TestReceiveOrder:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_payment_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_payment_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_payment_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id

        b = register_new_buyer(self.buyer_id, self.password)
        self.buyer = b
        gen_book = GenBook(self.seller_id, self.store_id)
        self.seller = gen_book.seller
        self.buy_book_info_list = []
        self.order_id = []

        for i in range(2):
            ok, buy_book_id_list = gen_book.gen(
                non_exist_book_id=False, low_stock_level=False, max_book_count=2
            )
            self.buy_book_info_list.extend(gen_book.buy_book_info_list)
            assert ok

            code, order_id = b.new_order(self.store_id, buy_book_id_list)
            self.order_id.append(order_id)
            assert code == 200

        self.total_price = 0

        # 修复：遍历 buy_book_info_list，正确处理字典
        for item in self.buy_book_info_list:
            book_data = item[0]  # book_data 是字典
            num = item[1]


            # 计算总价格
            self.total_price += book_data['price'] * num

        # 添加用户资金以支付订单
        self.buyer.add_funds(self.total_price)

        # 支付订单
        for i in range(1):
            self.buyer.payment(self.order_id[i])

        yield

    def test_ok(self):
        code = self.seller.delivery_order(self.store_id, self.order_id[0])
        assert code == 200
        # 假设订单已经发货，可以进行收货操作
        code = self.buyer.receive_order(self.order_id[0])
        assert code == 200

    def test_error_order_id(self):
        wrong_order_id = self.order_id[0] + "_x"
        code = self.buyer.receive_order(wrong_order_id)
        assert code != 200

    def test_error_user_id(self):
        self.buyer.user_id = self.buyer.user_id[0] + "_x"
        
        code = self.buyer.receive_order(self.order_id[0])
        assert code != 200
        
    def test_error_not_delivery(self):
        code = self.buyer.receive_order(self.order_id[0])
        assert code != 200
    
