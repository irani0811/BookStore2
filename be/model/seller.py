from sqlalchemy import text
from be.model import error
from be.model import db_conn
import sqlalchemy as sa
import json
import logging

# 配置日志记录器
logging.basicConfig(level=logging.INFO)  # 设置最低日志级别为 INFO
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)  # 启用 SQL 语句日志


class Seller(db_conn.DBConn):
    def __init__(self):
        db_conn.DBConn.__init__(self)

    def add_book(self, user_id: str, store_id: str, book_id: str, book_json_str: str, stock_level: int):
        """
        向指定 store_id 的商店添加一本新书。
        """
        try:
            # 检查用户是否存在
            if not self.user_id_exist(user_id):
                # print(f"[ERROR] User ID {user_id} does not exist.")
                return error.error_non_exist_user_id(user_id)

            print(f"[DEBUG] User ID {user_id} exists.")

            # 检查商店是否存在
            if not self.store_id_exist(store_id):
                # print(f"[ERROR] Store ID {store_id} does not exist.")
                return error.error_non_exist_store_id(store_id)

            print(f"[DEBUG] Store ID {store_id} exists.")

            # # 检查书籍是否已存在
            if self.book_id_exist_in_store(store_id, user_id, book_id,stock_level):
                print(f"[ERROR] Book ID {book_id} already exists in store {store_id} for user {user_id}.")
                return error.error_exist_book_id(book_id)


            # 从 book_json_str 中提取书籍详细信息
            try:
                print(f"[DEBUG] Parsing book information JSON: {book_json_str}")
                book_info = json.loads(book_json_str)
                required_fields = [
                    "tags", "picture", "title", "author", "publisher",
                    "original_title", "translator", "pub_year", "pages", "price",
                    "currency_unit", "binding", "isbn", "author_intro", "book_intro", "content"
                ]
                
                # 检查所有必需字段是否存在
                missing_fields = [field for field in required_fields if field not in book_info]
                if missing_fields:
                    print(f"[ERROR] Missing required fields: {missing_fields}")
                    return 400, f"Missing required fields: {', '.join(missing_fields)} in book information."
            except json.JSONDecodeError as e: 
                print(f"[ERROR] Invalid JSON format: {str(e)}")
                return 400, f"Invalid JSON format: {str(e)}"

            print(f"[DEBUG] Book information parsed successfully: {book_info}")

            # 将书籍添加到商店的表中
            insert_store_query = text("""
                INSERT INTO stores (store_id, user_id, book_id, price, stock_level)
                VALUES (:store_id, :user_id, :book_id, :price, :stock_level)
                ON DUPLICATE KEY UPDATE
                    price = VALUES(price),
                    stock_level = stock_level + VALUES(stock_level);
                """)

            # print("[DEBUG] Preparing to insert book into stores table.")
            with self.conn.connect() as conn:
                conn.execute(insert_store_query, {
                    "store_id": store_id,
                    "user_id": user_id,
                    "book_id": book_id,
                    "price": book_info["price"],
                    "stock_level": stock_level
                })
                conn.commit()
            print("[DEBUG] Book successfully inserted into stores table.")
            # 检查并创建 new_books 表全文索引

            
            # 将书籍详细信息添加到 new_books 表中
            insert_book_query = text("""
            INSERT INTO new_books (
                book_id, tags, pictures_path, title, author, publisher, original_title, translator,
                pub_year, pages, price, currency_unit, binding, isbn, author_intro, book_intro, content
            )
            VALUES (
                :book_id, :tags, :pictures_path, :title, :author, :publisher, :original_title, :translator,
                :pub_year, :pages, :price, :currency_unit, :binding, :isbn, :author_intro, :book_intro, :content
            );
            """)
            tags = book_info["tags"]
            if isinstance(tags, list):
                tags = "\n".join(tags)  # 将列表转换为单个字符串，用换行符分隔

            # print(f"[DEBUG] Flattened tags: {tags}")
            with self.conn.connect() as conn:
                conn.execute(insert_book_query, {
                "book_id": book_id,
                "tags": tags,
                "pictures_path": book_info.get("picture", ""),
                "title": book_info.get("title", "Unknown Title"),
                "author": book_info.get("author", "Unknown Author"),
                "publisher": book_info.get("publisher", "Unknown Publisher"),
                "original_title": book_info.get("original_title", ""),
                "translator": book_info.get("translator", ""),
                "pub_year": book_info.get("pub_year", 0),
                "pages": book_info.get("pages", 0),
                "price": book_info.get("price", 0.0),
                "currency_unit": book_info.get("currency_unit", "USD"),
                "binding": book_info.get("binding", ""),
                "isbn": book_info.get("isbn", ""),
                "author_intro": book_info.get("author_intro", ""),
                "book_intro": book_info.get("book_intro", ""),
                "content": book_info.get("content", "")
            })
                conn.commit()
            # print(f"[DEBUG] Book ID {book_id} successfully inserted into new_books.")
            

        except Exception as e: 
            print(f"[ERROR] An error occurred while adding the book: {str(e)}")
            return 528, f"Unexpected error: {str(e)}"

        print(f"[DEBUG] Book ID {book_id} successfully added.")
        return 200, "ok"


    #     return 200, "ok"
    # def add_stock_level(self, user_id: str, store_id: str, book_id: str, add_stock_level: int):
    #     """
    #     增加指定商店中某本书的库存。
    #     """
    #     try:
    #         # 检查用户是否存在
    #         if not self.user_id_exist(user_id):
    #             return error.error_non_exist_user_id(user_id)

    #         # 检查商店是否存在
    #         if not self.store_id_exist(store_id):
    #             return error.error_non_exist_store_id(store_id)

    #         # 检查库存增加量是否合法
    #         if add_stock_level <= 0:
    #             return 400, "Invalid stock level increment. It must be greater than zero."

    #         # 更新库存
    #         with self.conn.connect() as conn:
    #             # 检查书籍是否存在
    #             check_query = text("""
    #             SELECT stock_level
    #             FROM stores
    #             WHERE store_id = :store_id AND book_id = :book_id;
    #             """)
    #             result = conn.execute(check_query, {"store_id": store_id, "book_id": book_id}).fetchone()

    #             if not result:
    #                 return error.error_non_exist_book_id(book_id)

    #             # 获取当前库存
    #             current_stock_level = result[0]

    #             # 更新库存
    #             update_query = text("""
    #             UPDATE stores
    #             SET stock_level = :new_stock_level
    #             WHERE store_id = :store_id AND book_id = :book_id;
    #             """)
    #             conn.execute(update_query, {
    #                 "new_stock_level": current_stock_level + add_stock_level,
    #                 "store_id": store_id,
    #                 "book_id": book_id
    #             })
    #             conn.commit()

    #     except Exception as e: 
    #         return 528, f"添加库存时发生错误：{str(e)}"

    #     return 200, "ok"
    def add_stock_level(self, user_id: str, store_id: str, book_id: str, add_stock_level: int) -> (int, str):
        """
        增加指定商店中某本书的库存。
        """
        try:
            # 1. 检查用户和商店是否存在（事务外）
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)

            # 检查库存增加量是否合法
            if add_stock_level <= 0:
                return 400, "Invalid stock level increment. It must be greater than zero."

            # 2. 查询书籍当前库存（事务外）
            with self.conn.connect() as conn:
                check_query = text("""
                    SELECT stock_level
                    FROM stores
                    WHERE store_id = :store_id AND book_id = :book_id;
                """)
                result = conn.execute(check_query, {"store_id": store_id, "book_id": book_id}).fetchone()

                if not result:
                    return error.error_non_exist_book_id(book_id)

                current_stock_level = result[0]

            # 3. 更新库存（事务内）
            with self.conn.connect() as conn:
                trans = conn.begin()  # 开启事务
                try:
                    update_query = text("""
                        UPDATE stores
                        SET stock_level = stock_level + :add_stock_level
                        WHERE store_id = :store_id AND book_id = :book_id;
                    """)
                    conn.execute(update_query, {
                        "add_stock_level": add_stock_level,
                        "store_id": store_id,
                        "book_id": book_id
                    })
                    trans.commit()
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] 更新库存时发生错误: {str(e)}")
                    return 528, f"更新库存时发生错误: {str(e)}"

        except Exception as e:  # 捕获整体异常
            logging.error(f"[ERROR] 添加库存过程中发生错误: {str(e)}")
            return 528, f"添加库存过程中发生错误: {str(e)}"

        logging.info(f"[INFO] Stock level for book_id {book_id} in store {store_id} successfully updated.")
        return 200, "ok"


    #     return 200, "Store created successfully"
    # def create_store(self, user_id: str, store_id: str) -> tuple:
    #     """
    #     创建商店函数
    #     :param user_id: 用户 ID
    #     :param store_id: 商店 ID
    #     :return: 返回元组 (状态码, 消息)
    #     """
    #     try:
    #         # 检查商店是否已存在
    #         query_exist = sa.text("SELECT COUNT(1) FROM stores WHERE store_id = :store_id")
    #         with self.conn.connect() as connection:
    #             result = connection.execute(query_exist, {"store_id": store_id}).scalar()
    #             if result > 0:
    #                 return 400, f"Store {store_id} already exists"

    #         # 插入新商店
    #         query_insert = sa.text("""
    #         INSERT INTO stores (store_id, user_id)
    #         VALUES (:store_id, :user_id);
    #         """)
    #         with self.conn.connect() as connection:
    #             connection.execute(query_insert, {"store_id": store_id, "user_id": user_id})
    #             connection.commit()

    #     except sa.exc.IntegrityError as e:   
    #         return 400, f"Store {store_id} already exists: {str(e)}"
    #     except sa.exc.SQLAlchemyError as e:   
    #         return 528, f"Database error: {str(e)}"
    #     except Exception as e:   
    #         return 528, f"Unexpected error: {str(e)}"

    #     return 200, "Store created successfully"

    def create_store(self, user_id: str, store_id: str) -> tuple:
        """
        创建商店函数
        :param user_id: 用户 ID
        :param store_id: 商店 ID
        :return: 返回元组 (状态码, 消息)
        """
        try:
            # 1. 检查商店是否已存在（事务外）
            with self.conn.connect() as connection:
                query_exist = sa.text("SELECT COUNT(1) FROM stores WHERE store_id = :store_id")
                result = connection.execute(query_exist, {"store_id": store_id}).scalar()
                if result > 0:
                    logging.info(f"[INFO] Store {store_id} already exists.")
                    return 400, f"Store {store_id} already exists"

            # 2. 插入新商店（事务内）
            with self.conn.connect() as connection:
                trans = connection.begin()  # 显式事务
                try:
                    query_insert = sa.text("""
                    INSERT INTO stores (store_id, user_id)
                    VALUES (:store_id, :user_id);
                    """)
                    connection.execute(query_insert, {"store_id": store_id, "user_id": user_id})
                    trans.commit()
                    logging.info(f"[INFO] Store {store_id} created successfully by user {user_id}.")
                except sa.exc.IntegrityError as e:
                    trans.rollback()
                    logging.error(f"[ERROR] IntegrityError: Store {store_id} already exists: {str(e)}")
                    return 400, f"Store {store_id} already exists: {str(e)}"
                except sa.exc.SQLAlchemyError as e:
                    trans.rollback()
                    logging.error(f"[ERROR] SQLAlchemyError: {str(e)}")
                    return 528, f"Database error: {str(e)}"
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] Unexpected error during store creation: {str(e)}")
                    return 528, f"Unexpected error: {str(e)}"

        except sa.exc.SQLAlchemyError as e:
            logging.error(f"[ERROR] Database connection error: {str(e)}")
            return 528, f"Database error: {str(e)}"
        except Exception as e:
            logging.error(f"[ERROR] Unexpected error outside transaction: {str(e)}")
            return 528, f"Unexpected error: {str(e)}"

        return 200, "Store created successfully"

    # def delivery_order(self, store_id: str, order_id: str) -> (int, str):
    #     """
    #     更新订单状态为待收货 (状态 2)。
    #     """
    #     try:
    #         # 检查商店是否存在
    #         query_store_exist = text("""
    #         SELECT COUNT(1) 
    #         FROM stores 
    #         WHERE store_id = :store_id
    #         """)
    #         with self.conn.connect() as conn:
    #             store_count = conn.execute(query_store_exist, {"store_id": store_id}).scalar()
    #             print(f"[DEBUG] Store existence check: store_id={store_id}, store_count={store_count}")
    #             if store_count == 0:
    #                 return error.error_non_exist_store_id(store_id)

    #         # 查找订单
    #         query_order = text("""
    #         SELECT status, store_id 
    #         FROM history_order 
    #         WHERE order_id = :order_id
    #         """)
    #         with self.conn.connect() as conn:
    #             order = conn.execute(query_order, {"order_id": order_id}).fetchone()
    #             print(f"[DEBUG] Order fetch: order_id={order_id}, order={order}")
    #             if not order:
    #                 return error.error_invalid_order_id(order_id)

    #             # 解析订单结果
    #             order_status, order_store_id = order  # 解包元组值

    #             # 检查订单是否属于商店
    #             if order_store_id != store_id:
    #                 print(f"[DEBUG] Order store mismatch: order_store_id={order_store_id}, expected_store_id={store_id}")
    #                 return error.error_invalid_store_id(store_id)

    #             # 检查订单状态是否为待发货 (状态 1)
    #             print(f"[DEBUG] Order status check: order_status={order_status}")
    #             if order_status != 1:
    #                 return error.error_invalid_order_status(order_id)

    #             # 更新订单状态为待收货 (状态 2)
    #             update_status = text("""
    #             UPDATE history_order
    #             SET status = :new_status
    #             WHERE order_id = :order_id
    #             """)
    #             conn.execute(update_status, {"new_status": 2, "order_id": order_id})
    #             conn.commit()
    #             print(f"[DEBUG] Order status updated: order_id={order_id}, new_status=2")

    #     except Exception as e: 
    #         print(f"[ERROR] Unknown error during delivery: {str(e)}")
    #         return 528, f"发货时发生未知错误: {str(e)}"

    #     print(f"[DEBUG] Delivery success: store_id={store_id}, order_id={order_id}")
    #     return 200, "发货成功"

    def delivery_order(self, store_id: str, order_id: str) -> (int, str):
        """
        更新订单状态为待收货 (状态 2)。
        """
        try:
            # 1. 检查商店是否存在（事务外）
            with self.conn.connect() as conn:
                query_store_exist = text("""
                SELECT COUNT(1) 
                FROM stores 
                WHERE store_id = :store_id
                """)
                store_count = conn.execute(query_store_exist, {"store_id": store_id}).scalar()
                if store_count == 0:
                    logging.info(f"[INFO] Store does not exist: store_id={store_id}")
                    return error.error_non_exist_store_id(store_id)

            # 2. 查询订单状态和归属（事务外）
            with self.conn.connect() as conn:
                query_order = text("""
                SELECT status, store_id 
                FROM history_order 
                WHERE order_id = :order_id
                """)
                order = conn.execute(query_order, {"order_id": order_id}).fetchone()
                if not order:
                    logging.info(f"[INFO] Order does not exist: order_id={order_id}")
                    return error.error_invalid_order_id(order_id)

                # 解包订单信息
                order_status, order_store_id = order

                # 检查订单是否属于商店
                if order_store_id != store_id:
                    logging.warning(f"[WARNING] Order store mismatch: order_store_id={order_store_id}, expected_store_id={store_id}")
                    return error.error_invalid_store_id(store_id)

                # 检查订单状态是否为待发货 (状态 1)
                if order_status != 1:
                    logging.warning(f"[WARNING] Invalid order status for delivery: order_id={order_id}, order_status={order_status}")
                    return error.error_invalid_order_status(order_id)

            # 3. 更新订单状态（事务内）
            with self.conn.connect() as conn:
                trans = conn.begin()
                try:
                    update_status = text("""
                    UPDATE history_order
                    SET status = :new_status
                    WHERE order_id = :order_id
                    """)
                    conn.execute(update_status, {"new_status": 2, "order_id": order_id})
                    trans.commit()
                    logging.info(f"[INFO] Order status updated to 'Pending Receipt': order_id={order_id}, new_status=2")
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] Error updating order status: {str(e)}")
                    return 528, f"发货时发生错误: {str(e)}"

        except Exception as e:  # 捕获所有其他异常
            logging.error(f"[ERROR] Unknown error during delivery: {str(e)}")
            return 528, f"发货时发生未知错误: {str(e)}"

        logging.info(f"[INFO] Delivery success: store_id={store_id}, order_id={order_id}")
        return 200, "发货成功"