import pymysql
import uuid
import logging
from be.model import db_conn
from be.model import error
from sqlalchemy.sql import text
from sqlalchemy.exc import SQLAlchemyError
import json
from fe.access.book import Book
from be.model.times import unpaid_orders
from datetime import datetime
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from collections import defaultdict
import torch
import re
import logging

# 配置日志记录器
logging.basicConfig(level=logging.INFO)  # 设置最低日志级别为 INFO
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)  # 启用 SQL 语句日志


class Buyer(db_conn.DBConn):
    def __init__(self):
        db_conn.DBConn.__init__(self)


    # def new_order(self, user_id: str, store_id: str, id_and_count: [(str, int)]) -> (int, str, str):
    #     order_id = ""
    #     try:
    #         with self.conn.connect() as conn:
    #             # 检查用户是否存在
    #             # print(f"[DEBUG] Checking if user exists: user_id={user_id}")
    #             user_check_query = "SELECT 1 FROM users WHERE user_id = :user_id"
    #             user_result = conn.execute(text(user_check_query), {"user_id": user_id}).fetchone()
    #             # print(f"[DEBUG] User check result: {user_result}")
    #             if user_result is None:
    #                 return error.error_non_exist_user_id(user_id) + (order_id,)

    #             # 检查商店是否存在
    #             # print(f"[DEBUG] Checking if store exists: store_id={store_id}")
    #             store_check_query = "SELECT 1 FROM stores WHERE store_id = :store_id"
    #             store_result = conn.execute(text(store_check_query), {"store_id": store_id}).fetchone()
    #             # print(f"[DEBUG] Store check result: {store_result}")
    #             if store_result is None:
    #                 return error.error_non_exist_store_id(store_id) + (order_id,)

    #             # 生成订单ID
    #             uid = f"{user_id}_{store_id}_{str(uuid.uuid1())}"
    #             # print(f"[DEBUG] Generated order_id: {uid}")

    #             for book_id, count in id_and_count:
    #                 # print(f"[DEBUG] Processing book_id={book_id}, count={count}")

    #                 # 查询书籍信息和库存
    #                 get_book_query = """
    #                 SELECT 
    #                     s.stock_level,
    #                     b.price
    #                 FROM stores s
    #                 JOIN new_books b ON s.book_id = b.book_id
    #                 WHERE s.store_id = :store_id
    #                 AND s.book_id = :book_id;
    #                 """
    #                 # print(f"[DEBUG] Executing get_book_query for book_id={book_id}")
    #                 book_result = conn.execute(
    #                     text(get_book_query),
    #                     {"store_id": store_id, "book_id": book_id}
    #                 ).fetchone()
    #                 # print(f"[DEBUG] get_book_query result for book_id={book_id}: {book_result}")

    #                 if not book_result:
    #                     return error.error_non_exist_book_id(book_id) + (order_id,)

    #                 # 提取书籍库存和价格
    #                 stock_level, price = book_result[0], book_result[1]
    #                 # print(f"[DEBUG] stock_level={stock_level}, price={price} for book_id={book_id}")
    #                 if stock_level < count:
    #                     return error.error_stock_level_low(book_id) + (order_id,)

    #                 # 更新库存
    #                 update_stock_query = """
    #                 UPDATE stores
    #                 SET stock_level = stock_level - :count
    #                 WHERE store_id = :store_id
    #                 AND book_id = :book_id
    #                 AND stock_level >= :count;
    #                 """
    #                 # print(f"[DEBUG] Executing update_stock_query for book_id={book_id}, count={count}")
    #                 update_result = conn.execute(text(update_stock_query), {
    #                     "store_id": store_id,
    #                     "book_id": book_id,
    #                     "count": count
    #                 })
    #                 # print(f"[DEBUG] update_stock_query result rowcount={update_result.rowcount}")
    #                 if update_result.rowcount == 0:
    #                     return error.error_stock_level_low(book_id) + (order_id,)

    #                 # 插入订单详细信息
    #                 insert_order_detail_query = """
    #                 INSERT INTO new_order_detail (order_id, book_id, count, price)
    #                 VALUES (:order_id, :book_id, :count, :price)
    #                 """
    #                 # print(f"[DEBUG] Inserting order details for book_id={book_id}")
    #                 conn.execute(text(insert_order_detail_query), {
    #                     "order_id": uid,
    #                     "book_id": book_id,
    #                     "count": count,
    #                     "price": price
    #                 })

    #             # 插入订单
    #             insert_order_query = """
    #             INSERT INTO new_order (order_id, store_id, user_id, status, commit_time)
    #             VALUES (:order_id, :store_id, :user_id, 0, NOW())
    #             """
    #             # print(f"[DEBUG] Inserting new order with order_id={uid}")
    #             conn.execute(text(insert_order_query), {
    #                 "order_id": uid,
    #                 "store_id": store_id,
    #                 "user_id": user_id
    #             })

    #             conn.commit()
    #             order_id = uid
    #             # print(f"[DEBUG] Order committed successfully: order_id={order_id}")
    #             unpaid_orders.append((order_id, datetime.now()))
    #             print(f"[DEBUG] Appending order to unpaid_orders: {order_id}")
    #             print(f"[DEBUG] Current unpaid_orders: {unpaid_orders}")
                
    #         print(f"[DEBUG] unpaid_orders before auto_cancel: {unpaid_orders}")
    #     except Exception as e: 
    #         conn.rollback()  # 回滚事务
    #         print(f"[ERROR] An error occurred while creating the order: {str(e)}")
    #         return 530, str(e), ""

    #     return 200, "ok", order_id

    def new_order(self, user_id: str, store_id: str, id_and_count: [(str, int)]) -> (int, str, str):
        order_id = ""
        try:
            # 1. 检查用户是否存在（事务外）
            with self.conn.connect() as conn:
                user_check_query = "SELECT 1 FROM users WHERE user_id = :user_id"
                user_result = conn.execute(text(user_check_query), {"user_id": user_id}).fetchone()
                if user_result is None:
                    return error.error_non_exist_user_id(user_id) + (order_id,)

            # 2. 检查商店是否存在（事务外）
            with self.conn.connect() as conn:
                store_check_query = "SELECT 1 FROM stores WHERE store_id = :store_id"
                store_result = conn.execute(text(store_check_query), {"store_id": store_id}).fetchone()
                if store_result is None:
                    return error.error_non_exist_store_id(store_id) + (order_id,)

            # 3. 生成订单ID
            uid = f"{user_id}_{store_id}_{str(uuid.uuid1())}"
            aggregated_items = defaultdict(int)
            for book_id, count in id_and_count:
                if count is None or count <= 0:
                    continue
                aggregated_items[book_id] += count
            id_and_count = list(aggregated_items.items())

            # 4. 逐步处理每本书
            for book_id, count in id_and_count:
                # 查询书籍信息和库存（事务外）
                with self.conn.connect() as conn:
                    get_book_query = """
                    SELECT 
                        s.stock_level,
                        b.price
                    FROM stores s
                    JOIN new_books b ON s.book_id = b.book_id
                    WHERE s.store_id = :store_id
                    AND s.book_id = :book_id
                    """
                    book_result = conn.execute(
                        text(get_book_query),
                        {"store_id": store_id, "book_id": book_id}
                    ).fetchone()

                    if not book_result:
                        return error.error_non_exist_book_id(book_id) + (order_id,)

                    stock_level, price = book_result[0], book_result[1]
                    if stock_level < count:
                        return error.error_stock_level_low(book_id) + (order_id,)

                # 执行更新库存和插入订单详情（事务内）
                with self.conn.connect() as conn:
                    trans = conn.begin()  # 开启事务
                    try:
                        # 更新库存
                        update_stock_query = """
                        UPDATE stores
                        SET stock_level = stock_level - :count
                        WHERE store_id = :store_id
                        AND book_id = :book_id
                        """
                        conn.execute(text(update_stock_query), {
                            "store_id": store_id,
                            "book_id": book_id,
                            "count": count
                        })

                        # 插入订单详细信息
                        insert_order_detail_query = """
                        INSERT INTO new_order_detail (order_id, book_id, count, price)
                        VALUES (:order_id, :book_id, :count, :price)
                        """
                        conn.execute(text(insert_order_detail_query), {
                            "order_id": uid,
                            "book_id": book_id,
                            "count": count,
                            "price": price
                        })

                        trans.commit()  # 提交事务
                    except Exception as e:
                        trans.rollback()  # 回滚事务
                        raise e

            # 5. 插入订单表（事务内）
            with self.conn.connect() as conn:
                trans = conn.begin()  # 开启事务
                try:
                    insert_order_query = """
                    INSERT INTO new_order (order_id, store_id, user_id, status, commit_time)
                    VALUES (:order_id, :store_id, :user_id, 0, NOW())
                    """
                    conn.execute(text(insert_order_query), {
                        "order_id": uid,
                        "store_id": store_id,
                        "user_id": user_id
                    })
                    trans.commit()  # 提交事务
                    order_id = uid
                except Exception as e:
                    trans.rollback()  # 回滚事务
                    raise e

            # 6. 更新未支付订单列表（事务外）
            unpaid_orders.append((order_id, datetime.now()))
            print(f"[DEBUG] Appending order to unpaid_orders: {order_id}")
            print(f"[DEBUG] Current unpaid_orders: {unpaid_orders}")

        except Exception as e:
            print(f"[ERROR] An error occurred while creating the order: {str(e)}")
            return 530, str(e), ""

        return 200, "ok", order_id



    def payment(self, user_id: str, password: str, order_id: str) -> (int, str):
        try:
            with self.conn.connect() as conn:
                conn.begin()  # 开启事务
                print("[DEBUG] Transaction started.")

                # 查询订单
                query_order = text("SELECT * FROM new_order WHERE order_id = :order_id AND user_id = :user_id")
                order = conn.execute(query_order, {"order_id": order_id, "user_id": user_id}).mappings().fetchone()
                if not order:
                    return error.error_invalid_order_id(order_id)

                # 验证用户密码
                query_user = text("SELECT * FROM users WHERE user_id = :user_id")
                user = conn.execute(query_user, {"user_id": user_id}).mappings().fetchone()
                if not user or user['password'] != password:
                    return error.error_authorization_fail()

                # 计算订单总金额
                query_total_price = text("""
                    SELECT SUM(price * count) as total_price 
                    FROM new_order_detail 
                    WHERE order_id = :order_id
                """)
                total_price = conn.execute(query_total_price, {"order_id": order_id}).scalar()
                if total_price is None:
                    return 528, "Error calculating total price"

                # 验证余额是否充足
                if user['balance'] < total_price:
                    return error.error_not_sufficient_funds(order_id)

                # 扣除买家余额
                update_buyer_balance = text("""
                    UPDATE users SET balance = balance - :total_price 
                    WHERE user_id = :user_id AND balance >= :total_price
                """)
                conn.execute(update_buyer_balance, {"total_price": total_price, "user_id": user_id})

                # 增加卖家余额
                query_store = text("SELECT user_id FROM stores WHERE store_id = :store_id")
                seller_user_id = conn.execute(query_store, {"store_id": order['store_id']}).scalar()
                if not seller_user_id:
                    return 528, "Invalid store_id"
                update_seller_balance = text("""
                    UPDATE users SET balance = balance + :total_price 
                    WHERE user_id = :user_id
                """)
                conn.execute(update_seller_balance, {"total_price": total_price, "user_id": seller_user_id})

                global unpaid_orders  # 声明为全局变量 
                unpaid_orders = [order for order in unpaid_orders if order[0] != order_id]
                print(f"[DEBUG] unpaid_orders after update: {unpaid_orders}")

                # 查询订单详情
                query_order_details = text("""
                    SELECT book_id, count, price 
                    FROM new_order_detail 
                    WHERE order_id = :order_id
                """)
                order_details = conn.execute(query_order_details, {"order_id": order_id}).mappings().fetchall()

                # 将订单详情移至历史订单详情表
                for detail in order_details:
                    insert_history_detail = text("""
                        INSERT INTO history_order_detail (book_id, count, order_id, price, sales)
                        VALUES (:book_id, :count, :order_id, :price, :sales)
                    """)
                    conn.execute(insert_history_detail, {
                        "book_id": detail['book_id'],  # 使用列名访问
                        "count": detail['count'],
                        "order_id": order_id,
                        "price": detail['price'],
                        "sales": detail['count'],  # 假设销量等于数量
                    })

                # 查询订单数据
                query_order_data = text("""
                    SELECT order_id, store_id, user_id, commit_time 
                    FROM new_order 
                    WHERE order_id = :order_id
                """)
                order_data = conn.execute(query_order_data, {"order_id": order_id}).mappings().fetchone()

                # 插入订单至历史订单表
                insert_history_order = text("""
                    INSERT INTO history_order (order_id, store_id, user_id, status, commit_time)
                    VALUES (:order_id, :store_id, :user_id, :status, :commit_time)
                """)
                conn.execute(insert_history_order, {
                    "order_id": order_data['order_id'],
                    "store_id": order_data['store_id'],
                    "user_id": order_data['user_id'],
                    "status": 1,  # 更新状态为已支付
                    "commit_time": order_data['commit_time'],
                })

                # 删除新订单及其详情
                delete_new_order = text("DELETE FROM new_order WHERE order_id = :order_id")
                conn.execute(delete_new_order, {"order_id": order_id})

                delete_new_order_details = text("DELETE FROM new_order_detail WHERE order_id = :order_id")
                conn.execute(delete_new_order_details, {"order_id": order_id})

                conn.commit()  # 提交事务
                print("[DEBUG] Transaction committed.")

        except Exception as e: 
            conn.rollback()  # 出现异常回滚事务
            print("[ERROR] Exception occurred:", e)
            return 528, str(e)

        return 200, "ok"

    

    # def add_funds(self, user_id: str, password: str, add_value: int) -> (int, str):
    #     try:
    #         # 使用 SQLAlchemy 的 Engine 获取连接
    #         with self.conn.connect() as connection:
    #             # 验证用户密码
    #             result = connection.execute(
    #                 text("SELECT password FROM users WHERE user_id = :user_id"),
    #                 {"user_id": user_id}  # 参数用字典形式
    #             ).fetchone()

    #             if result is None or result[0] != password:
    #                 return error.error_authorization_fail()

    #             # 更新余额
    #             connection.execute(
    #                 text("UPDATE users SET balance = balance + :add_value WHERE user_id = :user_id"),
    #                 {"add_value": add_value, "user_id": user_id}  # 参数用字典形式
    #             )
    #             connection.commit()

    #     except pymysql.MySQLError as e: 
    #         logging.error(f"MySQL error: {e}")
    #         return 528, str(e)
    #     except Exception as e: 
    #         logging.error(f"Unexpected error: {e}")
    #         return 530, str(e)

    #     return 200, "ok"
    
    def add_funds(self, user_id: str, password: str, add_value: int) -> (int, str):
        try:
            # 1. 验证用户密码（事务外）
            with self.conn.connect() as connection:
                result = connection.execute(
                    text("SELECT password FROM users WHERE user_id = :user_id"),
                    {"user_id": user_id}
                ).fetchone()

                if result is None or result[0] != password:
                    return error.error_authorization_fail()

            # 2. 更新余额（事务内）
            with self.conn.connect() as connection:
                trans = connection.begin()  # 显式开启事务
                try:
                    connection.execute(
                        text("UPDATE users SET balance = balance + :add_value WHERE user_id = :user_id"),
                        {"add_value": add_value, "user_id": user_id}
                    )
                    trans.commit()  # 提交事务
                except Exception as e:
                    trans.rollback()  # 回滚事务
                    raise e

        except pymysql.MySQLError as e:  # pragma: no cover
            logging.error(f"MySQL error: {e}")
            return 528, str(e)
        except Exception as e:  # pragma: no cover
            logging.error(f"Unexpected error: {e}")
            return 530, str(e)

        return 200, "ok"

    # def query_order(self, user_id: str) -> (int, str, dict):
    #     """
    #     查询用户的订单信息，包括新订单和历史订单。
    #     """
    #     try:
    #         with self.conn.connect() as conn:
    #             # 查询 new_order 表中的订单
    #             query_new_orders = text("""
    #             SELECT 
    #                 order_id, store_id, status, commit_time 
    #             FROM new_order
    #             WHERE user_id = :user_id
    #             """)
    #             new_orders = conn.execute(query_new_orders, {"user_id": user_id}).mappings().fetchall()
    #             new_orders_list = [dict(order) for order in new_orders]
    #             print(f"[DEBUG] New orders for user_id={user_id}: {new_orders_list}")  # 调试信息

    #             # 查询 history_order 表中的订单
    #             query_history_orders = text("""
    #             SELECT 
    #                 order_id, store_id, status, commit_time 
    #             FROM history_order
    #             WHERE user_id = :user_id
    #             """)
    #             history_orders = conn.execute(query_history_orders, {"user_id": user_id}).mappings().fetchall()
    #             history_orders_list = [dict(order) for order in history_orders]
    #             print(f"[DEBUG] History orders for user_id={user_id}: {history_orders_list}")  # 调试信息

    #             # 如果两个表都没有找到订单，返回错误信息
    #             if not new_orders_list and not history_orders_list:
    #                 print(f"[DEBUG] No orders found for user_id={user_id}.")
    #                 return error.error_non_exist_order(user_id)

    #     except SQLAlchemyError as e: 
    #         logging.error(f"[ERROR] Database error during query_order for user_id={user_id}: {str(e)}")
    #         return 528, str(e), {}
    #     except Exception as e: 
    #         logging.error(f"[ERROR] Unexpected error during query_order for user_id={user_id}: {str(e)}")
    #         return 530, str(e), {}

    #     # 返回订单信息
    #     return 200, "ok", {"new_orders": new_orders_list, "history_orders": history_orders_list}

    def query_order(self, user_id: str) -> (int, str, dict):
        """
        查询用户的订单信息，包括新订单和历史订单。
        """
        try:
            new_orders_list = []
            history_orders_list = []

            # 查询 new_order 表中的订单（事务外）
            with self.conn.connect() as conn:
                query_new_orders = text("""
                SELECT 
                    order_id, store_id, status, commit_time 
                FROM new_order
                WHERE user_id = :user_id
                """)
                new_orders = conn.execute(query_new_orders, {"user_id": user_id}).mappings().fetchall()
                new_orders_list = [dict(order) for order in new_orders]
                print(f"[DEBUG] New orders for user_id={user_id}: {new_orders_list}")  # 调试信息

            # 查询 history_order 表中的订单（事务外）
            with self.conn.connect() as conn:
                query_history_orders = text("""
                SELECT 
                    order_id, store_id, status, commit_time 
                FROM history_order
                WHERE user_id = :user_id
                """)
                history_orders = conn.execute(query_history_orders, {"user_id": user_id}).mappings().fetchall()
                history_orders_list = [dict(order) for order in history_orders]
                print(f"[DEBUG] History orders for user_id={user_id}: {history_orders_list}")  # 调试信息

            # 如果两个表都没有找到订单，返回错误信息
            if not new_orders_list and not history_orders_list:
                print(f"[DEBUG] No orders found for user_id={user_id}.")
                return error.error_non_exist_order(user_id)

        except SQLAlchemyError as e:  # pragma: no cover
            logging.error(f"[ERROR] Database error during query_order for user_id={user_id}: {str(e)}")
            return 528, str(e), {}
        except Exception as e:  # pragma: no cover
            logging.error(f"[ERROR] Unexpected error during query_order for user_id={user_id}: {str(e)}")
            return 530, str(e), {}

        # 返回订单信息
        return 200, "ok", {"new_orders": new_orders_list, "history_orders": history_orders_list}


    # def receive_order(self, user_id: str, order_id: str) -> (int, str):
    #     try:
    #         with self.conn.connect() as conn:
    #             # 查询订单
    #             query_order = text("""
    #                 SELECT status 
    #                 FROM history_order 
    #                 WHERE order_id = :order_id AND user_id = :user_id
    #             """)
    #             order = conn.execute(query_order, {"order_id": order_id, "user_id": user_id}).mappings().fetchone()

    #             # 检查订单是否存在
    #             if not order:
    #                 return error.error_invalid_order_id(order_id)

    #             # 检查订单状态是否为 "待收货" (状态 2)
    #             order_status = order['status']  # 使用字典键访问
    #             if order_status != 2:
    #                 return error.error_not_delivery(order_id)

    #             # 更新订单状态为 "交易成功" (状态 4)
    #             update_order = text("""
    #                 UPDATE history_order
    #                 SET status = :new_status
    #                 WHERE order_id = :order_id AND user_id = :user_id
    #             """)
    #             conn.execute(update_order, {"new_status": 4, "order_id": order_id, "user_id": user_id})
    #             conn.commit()

    #     except Exception as e: 
    #         logging.error(f"收货过程中出现错误: {str(e)}")
    #         return 528, f"收货失败: {str(e)}"

    #     return 200, "收货成功"
    
    def receive_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            # 查询订单信息（事务外）
            with self.conn.connect() as conn:
                query_order = text("""
                    SELECT status 
                    FROM history_order 
                    WHERE order_id = :order_id AND user_id = :user_id
                """)
                order = conn.execute(query_order, {"order_id": order_id, "user_id": user_id}).mappings().fetchone()

                # 检查订单是否存在
                if not order:
                    return error.error_invalid_order_id(order_id)

                # 检查订单状态是否为 "待收货" (状态 2)
                order_status = order['status']
                if order_status != 2:
                    return error.error_not_delivery(order_id)

            # 更新订单状态（事务内）
            with self.conn.connect() as conn:
                trans = conn.begin()
                try:
                    update_order = text("""
                        UPDATE history_order
                        SET status = :new_status
                        WHERE order_id = :order_id AND user_id = :user_id
                    """)
                    conn.execute(update_order, {
                        "new_status": 4,  # 交易成功状态
                        "order_id": order_id,
                        "user_id": user_id
                    })
                    trans.commit()
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] 更新订单状态失败: {str(e)}")
                    return 528, f"更新订单状态失败: {str(e)}"

        except Exception as e:
            logging.error(f"收货过程中出现错误: {str(e)}")
            return 528, f"收货失败: {str(e)}"

        return 200, "收货成功"

    
    # def cancel_order(self, user_id: str, order_id: str) -> (int, str):
    #     try:
    #         with self.conn.connect() as conn:
    #             # 查找订单
    #             query_order = text("""
    #                 SELECT order_id, status, store_id
    #                 FROM new_order
    #                 WHERE order_id = :order_id AND user_id = :user_id
    #             """)
    #             order = conn.execute(query_order, {"order_id": order_id, "user_id": user_id}).mappings().fetchone()

    #             # 检查订单是否存在
    #             if not order:
    #                 return error.error_invalid_order_id(order_id)

    #             # 检查订单是否为待付款状态 (状态 0)
    #             if order['status'] != 0:
    #                 return error.error_order_not_cancelable(order_id)

    #             # 获取订单详情
    #             query_order_details = text("""
    #                 SELECT book_id, count
    #                 FROM new_order_detail
    #                 WHERE order_id = :order_id
    #             """)
    #             order_details = conn.execute(query_order_details, {"order_id": order_id}).mappings().fetchall()

    #             # 恢复库存
    #             for detail in order_details:
    #                 update_stock = text("""
    #                     UPDATE stores
    #                     SET stock_level = stock_level + :count
    #                     WHERE store_id = :store_id AND book_id = :book_id
    #                 """)
    #                 conn.execute(update_stock, {
    #                     "count": detail['count'],
    #                     "store_id": order['store_id'],
    #                     "book_id": detail['book_id']
    #                 })

    #             # 将订单详情插入到历史订单详情表
    #             insert_history_details = text("""
    #                 INSERT INTO history_order_detail (book_id, count, order_id, price, sales)
    #                 SELECT book_id, count, order_id, price, 0
    #                 FROM new_order_detail
    #                 WHERE order_id = :order_id
    #             """)
    #             conn.execute(insert_history_details, {"order_id": order_id})

    #             # 将订单插入到历史订单表，并设置状态为 3 (已取消)
    #             insert_history_order = text("""
    #                 INSERT INTO history_order (order_id, store_id, status, user_id, commit_time)
    #                 SELECT order_id, store_id, 3 AS status, user_id, commit_time
    #                 FROM new_order
    #                 WHERE order_id = :order_id
    #             """)
    #             conn.execute(insert_history_order, {"order_id": order_id})
    #             print(f"[DEBUG] Successfully moved order {order_id} to history_order")

    #             # 删除新订单及其详情
    #             delete_new_order = text("DELETE FROM new_order WHERE order_id = :order_id")
    #             conn.execute(delete_new_order, {"order_id": order_id})

    #             delete_new_order_details = text("DELETE FROM new_order_detail WHERE order_id = :order_id")
    #             conn.execute(delete_new_order_details, {"order_id": order_id})
    #             print(f"[DEBUG] Deleted order {order_id} from new_order and new_order_detail")

    #             # 提交事务
    #             conn.commit()

    #     except Exception as e: 
    #         conn.rollback()  # 回滚事务以防止部分操作成功
    #         return 528, f"取消订单时发生错误: {str(e)}"

    #     return 200, "ok"

    def cancel_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            # 1. 查找订单信息（事务外）
            with self.conn.connect() as conn:
                query_order = text("""
                    SELECT order_id, status, store_id
                    FROM new_order
                    WHERE order_id = :order_id AND user_id = :user_id
                """)
                order = conn.execute(query_order, {"order_id": order_id, "user_id": user_id}).mappings().fetchone()

                # 检查订单是否存在
                if not order:
                    return error.error_invalid_order_id(order_id)

                # 检查订单是否为待付款状态 (状态 0)
                if order['status'] != 0:
                    return error.error_order_not_cancelable(order_id)

                # 获取订单详情
                query_order_details = text("""
                    SELECT book_id, count
                    FROM new_order_detail
                    WHERE order_id = :order_id
                """)
                order_details = conn.execute(query_order_details, {"order_id": order_id}).mappings().fetchall()

            # 2. 执行恢复库存和插入历史订单等操作（事务内）
            with self.conn.connect() as conn:
                trans = conn.begin()
                try:
                    # 恢复库存
                    for detail in order_details:
                        update_stock = text("""
                            UPDATE stores
                            SET stock_level = stock_level + :count
                            WHERE store_id = :store_id AND book_id = :book_id
                        """)
                        conn.execute(update_stock, {
                            "count": detail['count'],
                            "store_id": order['store_id'],
                            "book_id": detail['book_id']
                        })

                    # 将订单详情插入到历史订单详情表
                    insert_history_details = text("""
                        INSERT INTO history_order_detail (book_id, count, order_id, price, sales)
                        SELECT book_id, count, order_id, price, 0
                        FROM new_order_detail
                        WHERE order_id = :order_id
                    """)
                    conn.execute(insert_history_details, {"order_id": order_id})

                    # 将订单插入到历史订单表，并设置状态为 3 (已取消)
                    insert_history_order = text("""
                        INSERT INTO history_order (order_id, store_id, status, user_id, commit_time)
                        SELECT order_id, store_id, 3 AS status, user_id, commit_time
                        FROM new_order
                        WHERE order_id = :order_id
                    """)
                    conn.execute(insert_history_order, {"order_id": order_id})

                    # 删除新订单及其详情
                    delete_new_order = text("DELETE FROM new_order WHERE order_id = :order_id")
                    conn.execute(delete_new_order, {"order_id": order_id})

                    delete_new_order_details = text("DELETE FROM new_order_detail WHERE order_id = :order_id")
                    conn.execute(delete_new_order_details, {"order_id": order_id})

                    trans.commit()
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] 取消订单时发生错误: {str(e)}")
                    return 528, f"取消订单时发生错误: {str(e)}"

        except Exception as e:
            logging.error(f"[ERROR] 取消订单过程中出现错误: {str(e)}")
            return 528, f"取消订单时发生错误: {str(e)}"

        return 200, "ok"


    
    # def auto_cancel(self, order_id: str) -> (int, str):
    #     try:
    #         with self.conn.connect() as conn:
    #             print(f"[DEBUG] unpaid_orders before auto_cancel: {unpaid_orders}")
    #             # 检查历史订单状态
    #             query_history_order = text("""
    #             SELECT status FROM history_order WHERE order_id = :order_id
    #             """)
    #             print(f"[DEBUG] Querying history_order table for order_id={order_id}")
    #             result = conn.execute(query_history_order, {"order_id": order_id}).fetchone()
    #             print(f"[DEBUG] Query result: {result}")
    #             print(f"[DEBUG] Using order_id: {order_id}")
    #             if result:
    #                 history_status = result[0]
    #                 print(f"[DEBUG] History order status: {history_status}")
    #                 if history_status == 3:  # 状态为3，表示已取消成功
    #                     return 200, "ok"

    #             # 如果历史订单中没有找到，再检查新订单状态
    #             query_new_order = text("""
    #             SELECT status FROM new_order WHERE order_id = :order_id
    #             """)
    #             result = conn.execute(query_new_order, {"order_id": order_id}).fetchone()
    #             print(f"[DEBUG] New order query result: {result}")
    #             if result:
    #                 new_status = result[0]
    #                 print(f"[DEBUG] New order status: {new_status}")
    #                 if new_status == 0:  # 状态为0，表示未付款取消失败
    #                     return 600, error.error_not_cancel_order(order_id)

    #             # 如果在两个表中都找不到订单
    #             print("[DEBUG] Order not found in both history_order and new_order tables.")
    #             return 518, error.error_missing_order(order_id)

    #     except Exception as e: 
    #         print(f"[ERROR] auto_cancel exception: {str(e)}")
    #         return 528, f"Unexpected error: {str(e)}"
    def auto_cancel(self, order_id: str) -> (int, str):
        try:
            # 检查历史订单状态（事务外）
            with self.conn.connect() as conn:
                query_history_order = text("""
                    SELECT status FROM history_order WHERE order_id = :order_id
                """)
                print(f"[DEBUG] Querying history_order table for order_id={order_id}")
                history_result = conn.execute(query_history_order, {"order_id": order_id}).fetchone()
                print(f"[DEBUG] History order query result: {history_result}")

                if history_result:
                    history_status = history_result[0]
                    print(f"[DEBUG] History order status: {history_status}")
                    if history_status == 3:  # 状态为3，表示已取消成功
                        return 200, "ok"

            # 检查新订单状态（事务外）
            with self.conn.connect() as conn:
                query_new_order = text("""
                    SELECT status FROM new_order WHERE order_id = :order_id
                """)
                print(f"[DEBUG] Querying new_order table for order_id={order_id}")
                new_order_result = conn.execute(query_new_order, {"order_id": order_id}).fetchone()
                print(f"[DEBUG] New order query result: {new_order_result}")

                if new_order_result:
                    new_status = new_order_result[0]
                    print(f"[DEBUG] New order status: {new_status}")
                    if new_status == 0:  # 状态为0，表示未付款取消失败
                        return 600, error.error_not_cancel_order(order_id)

            # 如果在两个表中都找不到订单
            print(f"[DEBUG] Order with order_id={order_id} not found in both history_order and new_order tables.")
            return 518, error.error_missing_order(order_id)

        except Exception as e:
            print(f"[ERROR] Exception in auto_cancel: {str(e)}")
            return 528, f"Unexpected error: {str(e)}"       

    def recommend_books_one(self, user_id: str, count: int) -> (int, str, list):
        try:
            with self.conn.connect() as conn:
                # 检查用户是否存在
                user_check_query = "SELECT 1 FROM users WHERE user_id = :user_id"
                user_exists = conn.execute(text(user_check_query), {"user_id": user_id}).fetchone()
                print(f"[DEBUG] 检查用户是否存在: user_id={user_id}, user_exists={user_exists}")
                if not user_exists:
                    print(f"[ERROR] 用户 {user_id} 不存在。")
                    return 404, "User does not exist", []

                # 第一步：找到当前用户的订单
                user_orders_query = "SELECT order_id FROM history_order WHERE user_id = :user_id"
                user_orders = conn.execute(text(user_orders_query), {"user_id": user_id}).fetchall()
                print(f"[DEBUG] 用户 {user_id} 的订单：{user_orders}")
                user_order_ids = [record[0] for record in user_orders]  # 确保使用元组索引提取数据
                print(f"[DEBUG] 提取的订单ID：{user_order_ids}")

                # 检查用户是否有订单
                if not user_order_ids:
                    print(f"[ERROR] 用户 {user_id} 没有订单。")
                    return 528, "User has no orders", []

                # 第二步：通过订单ID找到用户已购买的书籍
                purchased_books_query = """
                    SELECT DISTINCT book_id 
                    FROM history_order_detail 
                    WHERE order_id IN :order_ids
                """
                print(f"[DEBUG] 执行查询以获取已购买书籍：{purchased_books_query}")
                purchased_books = conn.execute(
                    text(purchased_books_query),
                    {"order_ids": tuple(user_order_ids)}
                ).fetchall()
                print(f"[DEBUG] 查询结果：{purchased_books}")
                user_purchased_books = {record[0] for record in purchased_books}
                print(f"[DEBUG] 用户 {user_id} 已购买的书籍：{user_purchased_books}")

                # 检查是否找到已购买的书籍
                if not user_purchased_books:
                    print(f"[ERROR] 用户 {user_id} 没有已购买的书籍。")
                    return 528, "User has not purchased any books", []

                # 第三步：查找其他用户购买相同书籍的订单和用户
                similar_users_query = """
                    SELECT DISTINCT h.user_id, hod.order_id, hod.book_id
                    FROM history_order_detail hod
                    JOIN history_order h ON hod.order_id = h.order_id
                    WHERE hod.book_id IN :book_ids
                    AND h.user_id != :user_id
                """
                print(f"[DEBUG] 执行查询以查找购买相同书籍的用户：{similar_users_query}")
                similar_users = conn.execute(
                    text(similar_users_query),
                    {"book_ids": tuple(user_purchased_books), "user_id": user_id}
                ).fetchall()
                print(f"[DEBUG] 查询结果（购买相同书籍的用户）：{similar_users}")

                # 提取订单ID和用户ID
                order_ids = set()
                user_ids = set()
                for record in similar_users:
                    order_ids.add(record[1])  # 假设 order_id 在元组中是第二个元素
                    user_ids.add(record[0])   # 假设 user_id 在元组中是第一个元素
                print(f"[DEBUG] 提取的订单ID：{order_ids}")
                print(f"[DEBUG] 提取的用户ID：{user_ids}")

                # 检查是否找到其他用户
                if not user_ids:
                    print("[ERROR] 未找到购买相同书籍的其他用户。")
                    return 528, "No similar users found", []

                # 第四步：查找这些用户购买的其他书籍，排除当前用户已购买的书籍
                other_books_query = """
                    SELECT hod.book_id, COUNT(*) as frequency
                    FROM history_order_detail hod
                    JOIN history_order h ON hod.order_id = h.order_id
                    WHERE hod.order_id IN :order_ids
                    AND hod.book_id NOT IN :user_books
                    AND h.user_id IN :user_ids
                    GROUP BY hod.book_id
                    ORDER BY frequency DESC
                    LIMIT :count
                """
                print(f"[DEBUG] 执行查询以获取推荐书籍：{other_books_query}")
                print(f"[DEBUG] 查询参数：order_ids={tuple(order_ids)}, user_books={tuple(user_purchased_books)}, user_ids={tuple(user_ids)}, count={count}")
                other_books = conn.execute(
                    text(other_books_query),
                    {
                        "order_ids": tuple(order_ids),
                        "user_books": tuple(user_purchased_books),
                        "user_ids": tuple(user_ids),
                        "count": count,
                    },
                ).mappings().fetchall()
                print(f"[DEBUG] 查询结果：{list(other_books)}")

                if not other_books:
                    print("[ERROR] 未找到推荐书籍。")
                    return 200, "No recommended books found", []

                # 获取书籍详细信息
                book_ids = [record["book_id"] for record in other_books]
                print(f"[DEBUG] 提取的书籍ID：{book_ids}")
                book_query = """
                    SELECT book_id, title, author, publisher, price
                    FROM new_books
                    WHERE book_id IN :book_ids
                """
                print(f"[DEBUG] 执行查询以获取书籍详细信息：{book_query}")
                books = conn.execute(
                    text(book_query),
                    {"book_ids": tuple(book_ids)}
                ).mappings().fetchall()
                print(f"[DEBUG] 书籍查询结果：{list(books)}")

                recommend_books = []
                for book in books:
                    recommend_books.append({
                        "book_id": book["book_id"],
                        "title": book.get("title", "Unknown title"),
                        "author": book.get("author", "Unknown author"),
                        "publisher": book.get("publisher", "Unknown publisher"),
                        "price": book.get("price", "Unknown price"),
                    })

                print(f"[DEBUG] 最终推荐书籍：{recommend_books}")
                return 200, "ok", recommend_books

        except Exception as e: 
            print(f"[ERROR] 推荐过程出现错误：{str(e)}")
            return 528, f"Error in recommendation: {str(e)}", []
        
    def generate_and_extract_titles(self, txt, model_id='charent/ChatLM-mini-Chinese'):
        try:
            # 检查输入是否为空
            if not txt.strip():
                return 540, "输入文本不能为空", []

            # 设置设备
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

            # 加载分词器和模型
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModelForSeq2SeqLM.from_pretrained(model_id, trust_remote_code=True).to(device)

            # 对输入文本进行分词
            encode_ids = tokenizer([txt])
            input_ids = torch.LongTensor(encode_ids['input_ids']).to(device)
            attention_mask = torch.LongTensor(encode_ids['attention_mask']).to(device)

            # 生成输出
            outs = model.my_generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_seq_len=256,
                search_type='beam',
            )

            # 解码生成的输出
            outs_txt = tokenizer.batch_decode(outs.cpu().numpy(), skip_special_tokens=True, clean_up_tokenization_spaces=True)
            output_text = outs_txt[0]

            # 使用正则表达式从生成的输出文本中提取书名
            pattern = r'《(.*?)》'
            titles = re.findall(pattern, output_text)
            unique_titles = list(set(titles))  # 去除重复的书名

            # 插入数据库
            with self.conn.connect() as conn:
                insert_query = text("""
                    INSERT INTO generated_titles (input_text, generated_text, titles, created_at)
                    VALUES (:input_text, :generated_text, :titles, NOW())
                """)
                conn.execute(insert_query, {
                    "input_text": txt,
                    "generated_text": output_text,
                    "titles": json.dumps(unique_titles, ensure_ascii=False),
                })
                conn.commit()

            # 返回状态码和提取的书名
            return 200, unique_titles

        except Exception as e:
            logging.error(f"生成和提取书名时出错: {str(e)}")
            return 528, []