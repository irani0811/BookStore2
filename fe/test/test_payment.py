import pytest

from fe.access.buyer import Buyer
from fe.test.gen_book_data import GenBook
from fe.access.new_buyer import register_new_buyer
from fe.access.book import Book
import uuid


class TestPayment:
    seller_id: str
    store_id: str
    buyer_id: str
    password: str
    buy_book_info_list: [Book]
    total_price: int
    order_id: str
    buyer: Buyer

    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_payment_seller_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_payment_store_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_payment_buyer_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id

        print("[DEBUG] Initializing test setup...")
        
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=5
        )
        assert ok, "Failed to generate books"
        
        # 转换字典为 Book 对象
        self.buy_book_info_list = []
        for book_info, num in gen_book.buy_book_info_list:
            if isinstance(book_info, dict):
                book_obj = Book()
                # 确保所有必要字段都被正确设置
                book_obj.id = book_info.get('id', '')
                book_obj.title = book_info.get('title', '')
                book_obj.author = book_info.get('author', '')
                book_obj.publisher = book_info.get('publisher', '')
                book_obj.price = book_info.get('price', 0)  # 确保价格字段存在
                book_obj.tags = book_info.get('tags', [])
                book_obj.picture = book_info.get('picture', '')
                self.buy_book_info_list.append((book_obj, num))
            # else:
            #     self.buy_book_info_list.append((book_info, num))

        print(f"[DEBUG] Created {len(self.buy_book_info_list)} book objects")

        b = register_new_buyer(self.buyer_id, self.password)
        self.buyer = b
        code, self.order_id = b.new_order(self.store_id, buy_book_id_list)
        assert code == 200, f"Failed to create order, code: {code}"

        # 计算总价
        self.total_price = 0
        for book, num in self.buy_book_info_list:
            if hasattr(book, 'price') and isinstance(book.price, (int, float)) and book.price > 0:
                print(f"[DEBUG] Adding to total: {book.price} * {num}")
                self.total_price += book.price * num
            else:
                print(f"[WARNING] Invalid price for book: {book.__dict__}")

        print(f"[DEBUG] Total price calculated: {self.total_price}")
        
        yield  # 这允许测试运行
        
        # 清理代码（如果需要）
        print("[DEBUG] Cleaning up test setup...")

    def test_ok(self):
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code == 200

    def test_authorization_error(self):
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        self.buyer.password = self.buyer.password + "_x"
        code = self.buyer.payment(self.order_id)
        assert code != 200

    def test_not_suff_funds(self):
        code = self.buyer.add_funds(self.total_price - 1)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code != 200

    def test_repeat_pay(self):
        code = self.buyer.add_funds(self.total_price)
        assert code == 200
        code = self.buyer.payment(self.order_id)
        assert code == 200

        code = self.buyer.payment(self.order_id)
        assert code != 200
