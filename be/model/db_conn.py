from pymongo import MongoClient
from be.model import store


class DBConn:
    def __init__(self):
        self.conn = store.get_db_conn()

    def user_id_exist(self, user_id):
        # 在MongoDB中查找用户ID是否存在
        result = self.conn['users'].find_one({"user_id": user_id})
        return result is not None

    def book_id_exist(self, store_id, book_id):
        # 在MongoDB中查找指定store_id下的书籍
        # 使用 stores 集合中的 books 数组来查找 book_id
        result = self.conn['stores'].find_one({
            "store_id": store_id,
            "books.book_id": book_id  # 查找 books 数组中的 book_id
        })
        return result is not None

    def store_id_exist(self, store_id):
        # 在MongoDB中查找商店ID是否存在
        result = self.conn['stores'].find_one({"store_id": store_id})
        return result is not None