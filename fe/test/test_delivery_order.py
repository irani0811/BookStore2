import pytest
import uuid

from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer
from fe.test.gen_book_data import GenBook
from fe.access.book import Book

class TestdeliveryOrder:
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

        # 遍历 buy_book_info_list，将字典手动赋值到 Book 对象
        for item in self.buy_book_info_list:
            book_data = item[0]  # book_data 是字典
            book = Book()  # 初始化 Book 对象

            # 手动赋值字段
            book.id = book_data.get("id", "")
            book.title = book_data.get("title", "")
            book.author = book_data.get("author", "")
            book.publisher = book_data.get("publisher", "")
            book.original_title = book_data.get("original_title", "")
            book.translator = book_data.get("translator", "")
            book.pub_year = book_data.get("pub_year", "")
            book.pages = book_data.get("pages", 0)
            book.price = book_data.get("price", 0)
            book.currency_unit = book_data.get("currency_unit", "")
            book.binding = book_data.get("binding", "")
            book.isbn = book_data.get("isbn", "")
            book.author_intro = book_data.get("author_intro", "")
            book.book_intro = book_data.get("book_intro", "")
            book.content = book_data.get("content", "")
            book.tags = book_data.get("tags", [])
            book.picture_path = book_data.get("picture_path", "")

            num = item[1]
            # if book.price is None:
            #     continue
            # else:
            self.total_price += book.price * num

        self.buyer.add_funds(self.total_price)
        for i in range(1):
            self.buyer.payment(self.order_id[i])
        yield

    # 测试发货成功
    def test_ok(self):
        code = self.seller.delivery_order(self.store_id, self.order_id[0])
        assert code == 200

    # 测试错误的商店 ID
    def test_error_store_id(self):
        code = self.seller.delivery_order(self.store_id + "_x", self.order_id[0])
        assert code != 200

    # 测试错误的订单 ID
    def test_error_order_id(self):
        code = self.seller.delivery_order(self.store_id, self.order_id[0] + "_x")
        assert code != 200
        
    # 测试订单不属于商店
    def test_order_not_belong_to_store(self):
        another_store_id = "test_delivery_store_id_another"
        code = self.seller.delivery_order(another_store_id, self.order_id[0])
        assert code != 200
        
    # 测试订单状态不为待发货
    def test_order_not_in_pending_delivery_status(self):
        # 使用一个已付款但未在待发货状态的订单进行测试
        code = self.seller.delivery_order(self.store_id, self.order_id[1])
        assert code != 200