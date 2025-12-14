import pytest
import uuid
import random

from fe.access.new_buyer import register_new_buyer
from fe.test.gen_book_data import GenBook

class TestRecommendOne:
    @pytest.fixture(autouse=True)
    def pre_run_initialization(self):
        self.seller_id = "test_recommend_seller_one_id_{}".format(str(uuid.uuid1()))
        self.store_id = "test_recommend_store_one_id_{}".format(str(uuid.uuid1()))
        self.buyer_id = "test_recommend_buyer_one_id_{}".format(str(uuid.uuid1()))
        self.password = self.seller_id
        self.count = 5  # 推荐的书籍数量
        
        # 生成书籍数据
        gen_book = GenBook(self.seller_id, self.store_id)
        ok, buy_book_id_list = gen_book.gen(
            non_exist_book_id=False, low_stock_level=False, max_book_count=100
        )
        self.buy_book_info_list = gen_book.buy_book_info_list
        self.buy_book_id_list = [book for book in gen_book.buy_book_id_list if book[1] > 7] 
        assert ok

        # 注册买家
        b = register_new_buyer(self.buyer_id, self.password)
        self.buyer = b

        # 增加资金并创建一个订单购买两本书
        self.buyer.add_funds(100000)
        order_items = [(book_id[0], 1) for book_id in self.buy_book_id_list[:2]]  # 每本书数量为1
        # print(f"尝试创建订单，订单内容: {order_items}")  # 调试信息
        code, order_id = self.buyer.new_order(self.store_id, order_items)
        assert code == 200
        payment_code = self.buyer.payment(order_id)
        # print(f"主买家付款返回代码: {payment_code}")  # 调试信息

        # 获取主买家已购买书籍的ID集合，用于排除重复书籍
        purchased_books_set = set(book_id[0] for book_id in order_items)
        
        # 生成与主买家购买不同的书籍列表
        unique_books = [book for book in self.buy_book_id_list if book[0] not in purchased_books_set]

        # 生成相似买家并注册
        self.similar_buyers = []
        for i in range(5):  # 生成5个相似的买家
            similar_buyer_id = f"test_similar_buyer_{i+1}_{uuid.uuid1()}"
            new_buyer = register_new_buyer(similar_buyer_id, self.password)
            self.similar_buyers.append(new_buyer)

            # 每个相似买家购买与主买家相同的两本书
            for book_id in self.buy_book_id_list[:2]:
                new_buyer.add_funds(100000)
                new_order_code, new_order_id = new_buyer.new_order(
                    self.store_id, [(book_id[0], 1)]
                )
                # print(f"相似买家 {similar_buyer_id} 尝试相同下单书籍 {book_id[0]}，返回代码: {new_order_code}, 订单 ID: {new_order_id}")  # 调试信息
                assert new_order_code == 200
                payment_code = new_buyer.payment(new_order_id)
                # print(f"相似买家 {similar_buyer_id} 对订单 {new_order_id} 的付款返回代码: {payment_code}")  # 调试信息

            # 每个相似买家从 unique_books 中选择不同的书籍
            selected_books = random.sample(unique_books, k=min(len(unique_books), 3))
            new_buyer.add_funds(100000)

            for book_id in selected_books:
                new_order_code, new_order_id = new_buyer.new_order(
                    self.store_id, [(book_id[0], 1)]
                )
                # print(f"相似买家 {similar_buyer_id} 尝试下单独特书籍 {book_id[0]}，返回代码: {new_order_code}, 订单 ID: {new_order_id}")  # 调试信息
                assert new_order_code == 200
                payment_code = new_buyer.payment(new_order_id)
                # print(f"相似买家 {similar_buyer_id} 对订单 {new_order_id} 的付款返回代码: {payment_code}")  # 调试信息

        yield  # 结束测试

    def test_recommend_books_success(self):
        # 测试推荐书籍功能的正常情况
        code, recommendations = self.buyer.get_recommendations_one(count=self.count)
        assert code == 200

    def test_recommend_books_no_purchases(self):
        # 测试没有购买记录的买家推荐情况
        buyer_id = f"test_no_purchases_buyer_{uuid.uuid1()}"
        new_buyer = register_new_buyer(buyer_id, self.password)
        code, recommendations = new_buyer.get_recommendations_one(count=self.count)
        assert code == 528
        assert len(recommendations) == 0

    def test_recommend_books_invalid_user(self):
        # 测试不存在的用户推荐情况
        self.buyer.user_id = self.buyer.user_id + "_x"
        code, recommendations = self.buyer.get_recommendations_one(count=self.count)
        assert code == 404
        assert len(recommendations) == 0