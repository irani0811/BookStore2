
from sqlalchemy import text
from be.model import store  # 从 store.py 中获取全局数据库连接
import json
import logging
from sqlalchemy.sql import text
import mysql.connector as mysql


class DBConn:
    def __init__(self):
        # 使用 store.py 中的全局数据库连接
        self.conn = store.get_db_conn()

    def user_id_exist(self, user_id):
        """
        检查用户 ID 是否存在
        """
        query = text("SELECT user_id FROM users WHERE user_id = :user_id;")
        with self.conn.connect() as conn:
            result = conn.execute(query, {"user_id": user_id}).fetchone()
        return result is not None

    def book_id_exist_in_store(self, store_id: str, user_id: str, book_id: str, stock_level: int) -> bool:
        print(f"[DEBUG] Checking if book ID {book_id} exists in store {store_id} for user {user_id} with stock level {stock_level}")
        query = """
            SELECT stock_level
            FROM stores
            WHERE store_id = :store_id AND user_id = :user_id AND book_id = :book_id
            LIMIT 1
        """
        with self.conn.connect() as conn:
            result = conn.execute(
                text(query),
                {"store_id": store_id, "user_id": user_id, "book_id": book_id}
            ).fetchone()
        print(f"[DEBUG] Query result: {result}")

        if result:
            # 如果结果是元组，则通过索引访问
            existing_stock_level = result[0]  # `stock_level` 是结果的第一个字段
            print(f"[DEBUG] Existing stock level: {existing_stock_level}")
            if existing_stock_level == stock_level:
                print(f"[DEBUG] Book ID {book_id} with stock level {stock_level} matches.")
                return True  # 书籍ID和库存数量完全匹配
            else:
                print(f"[DEBUG] Book ID {book_id} exists in store {store_id} for user {user_id}, "
                    f"but stock_level differs: {existing_stock_level} != {stock_level}")
                return False  # 书籍ID存在但库存不同
        else:
            print(f"[DEBUG] Book ID {book_id} does not exist in store {store_id}.")
            return False  # 书籍不存在


    def store_id_exist(self, store_id):
        """
        检查商店 ID 是否存在
        """
        query = text("SELECT store_id FROM stores WHERE store_id = :store_id;")
        with self.conn.connect() as conn:
            result = conn.execute(query, {"store_id": store_id}).fetchone()
        return result is not None
