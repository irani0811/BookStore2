import time
import uuid
import pytest
import random

from fe import conf
from fe.access.auth import Auth
from fe.access.new_buyer import register_new_buyer
from fe.test.gen_book_data import GenBook
from fe.access.book import Book

class TestRecommendBooks:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        # 初始化
        
        # 基本设置
        self.base_url = conf.URL
        self.auth = Auth(self.base_url)


        # 卖家注册
        self.seller_id = "test_recommend_books_seller_id_{}".format(str(uuid.uuid4()))
        self.store_id = "test_recommend_books_store_id_{}".format(str(uuid.uuid4()))
        self.seller_password = self.seller_id
        self.gen_book = GenBook(self.seller_id, self.store_id)
        self.seller = self.gen_book.seller

        # 生成书籍并添加到商店
        common_books_ids = []  # 用于存储所有用户都会购买的书籍
        for _ in range(5):  # 创建5本书作为“公共书籍”
            ok, book_list = self.gen_book.gen(non_exist_book_id=False, low_stock_level=False, max_book_count=100)
            assert ok, "Failed to generate books"
            common_books_ids.extend(book_list)

        # 创建多个买家用户
        self.buyers = []
        self.buyer_ids = []

        # 前两个买家共享部分相同的书籍，但也包含独特书籍
        predefined_books_to_buy = [book_id[0] for book_id in random.sample(common_books_ids, k=2)]  # 选择2本公共书籍

        for i in range(5):  # 创建5个买家用户
            buyer_id = "test_recommend_books_buyer_id_{}_{}".format(i, str(uuid.uuid4()))
            password_buyer = self.seller_id
            buyer = register_new_buyer(buyer_id, password_buyer)
            assert buyer is not None, f"Failed to register buyer {buyer_id}"

            self.total_price = 0
            for item in self.gen_book.buy_book_info_list:
                book = item[0]
                num = item[1]
                self.total_price += book.get("price", 0) * num

            # 给每个买家添加足够的余额
            #buyer.add_funds(self.total_price * 100)
            code = buyer.add_funds(1000000)
            assert code == 200, f"Failed to add funds for buyer {buyer_id}"

            # 创建购买订单
            for _ in range(2):  # 每个买家生成2个订单
                if i < 2:
                    # 前两个买家共享部分书籍，同时加入独有书籍
                    additional_books = [book_id[0] for book_id in random.sample(common_books_ids, k=2)]
                    buy_book_id_list = [(book_id, 2) for book_id in (predefined_books_to_buy + additional_books)]
                else:
                    # 其他买家随机选择不同的书籍
                    unique_books_to_buy = [book_id[0] for book_id in random.sample(common_books_ids, k=random.randint(1, 5))]
                    buy_book_id_list = [(book_id, random.randint(1, 3)) for book_id in unique_books_to_buy]

                code, order_id = buyer.new_order(self.store_id, buy_book_id_list)
                assert code == 200, f"Failed to create order for buyer {buyer_id}"

                # 付款
                code = buyer.payment(order_id)
                assert code == 200, f"Failed to process payment for buyer {buyer_id}"

            self.buyers.append(buyer)
            self.buyer_ids.append(buyer_id)

        yield  # 将测试逻辑交还给测试用例

        

    def test_recommend_books_ok(self):
        # print(self.buyers[0])
        # 选择一个买家并从其购买记录中请求推荐
        buyer_id = self.buyer_ids[1] # 使用第一个买家进行测试
        
        # print(f"测试IDTesting recommendations for buyer {buyer_id}")
        n_recommendations = 5  # 请求推荐的书籍数量
        # print(f"Requesting {n_recommendations} recommendations for buyer {buyer_id}")
        
        # 调用推荐功能
        code, response = self.auth.recommend_books(buyer_id, n_recommendations)

        # 验证返回的状态码和推荐结果的合理性
        assert code == 200, f"Expected status code 200, but got {code}"
        assert response is not None, "Expected response to contain recommendations, but got None"

        # 检查推荐结果中是否包含书籍
        books = response.get('books', [])
        # print(f"Recommendations for buyer {buyer_id}: {books}")
        assert len(books) > 0, "Expected at least one recommended book, but got none"
        

        # 验证推荐书籍的格式是否符合预期
        for book in books:
            assert 'title' in book, "Each recommended book should contain a title field"
            assert 'price' in book, "Each recommended book should contain a price field"







