import jwt
import time
import logging
import sqlalchemy as sa
from be.model import error
from be.model import db_conn
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.sql import text
import jieba
import logging

MAX_REGEX_CANDIDATES = 200
# 配置日志记录器
logging.basicConfig(level=logging.INFO)  # 设置最低日志级别为 INFO
logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)  # 启用 SQL 语句日志

# JWT 工具函数
def jwt_encode(user_id: str, terminal: str) -> str:
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    return encoded


def jwt_decode(encoded_token, user_id: str) -> str:
    decoded = jwt.decode(encoded_token, key=user_id, algorithms=["HS256"])
    return decoded


class User(db_conn.DBConn):
    token_lifetime: int = 3600  # Token 有效期（秒）

    def __init__(self):
        db_conn.DBConn.__init__(self)

    def __check_token(self, user_id, db_token, token) -> bool:
        try:
            if db_token != token:
                return False
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text["timestamp"]
            if ts is not None:
                now = time.time()
                if self.token_lifetime > now - ts >= 0:
                    return True
        except jwt.exceptions.InvalidSignatureError as e:# pragma: no cover
            logging.error(str(e))
            return False


    # def register(self, user_id: str, password: str) -> tuple:
    #     try:
    #         terminal = f"terminal_{time.time()}"
    #         token = jwt_encode(user_id, terminal)
            
    #         # 打印生成的 token 和 terminal
    #         # print(f"[DEBUG] Registering user_id: {user_id}, terminal: {terminal}, token: {token}")
            
    #         query = sa.text(
    #             "INSERT INTO users (user_id, password, token, terminal) VALUES (:user_id, :password, :token, :terminal)"
    #         )
    #         with self.conn.connect() as connection:
    #             transaction = connection.begin()
    #             result = connection.execute(
    #                 query, {"user_id": user_id, "password": password, "token": token, "terminal": terminal}
    #             )
    #             transaction.commit() 
    #             # 打印 SQL 执行结果
    #             # print(f"[DEBUG] Insert result: {result.rowcount} rows affected")
    #     except sa.exc.SQLAlchemyError as e:
    #         # 打印错误信息
    #         print(f"[ERROR] Database error: {str(e)}")
    #         return 528, str(e)
    #     return 200, "ok"

    def register(self, user_id: str, password: str) -> tuple:
        """
        注册新用户
        :param user_id: 用户 ID
        :param password: 用户密码
        :return: 返回元组 (状态码, 消息)
        """
        try:
            # 生成用户的 terminal 和 token（事务外）
            terminal = f"terminal_{time.time()}"
            token = jwt_encode(user_id, terminal)
            logging.info(f"[INFO] Registering user_id: {user_id}, terminal: {terminal}")

            # 插入用户信息到数据库（事务内）
            with self.conn.connect() as connection:
                trans = connection.begin()
                try:
                    query = sa.text("""
                        INSERT INTO users (user_id, password, token, terminal) 
                        VALUES (:user_id, :password, :token, :terminal)
                    """)
                    connection.execute(query, {
                        "user_id": user_id,
                        "password": password,
                        "token": token,
                        "terminal": terminal
                    })
                    trans.commit()
                    logging.info(f"[INFO] User {user_id} registered successfully.")
                except sa.exc.IntegrityError as e:
                    trans.rollback()
                    logging.error(f"[ERROR] User {user_id} already exists: {str(e)}")
                    return 400, "User already exists"
                except sa.exc.SQLAlchemyError as e:
                    trans.rollback()
                    logging.error(f"[ERROR] SQLAlchemy error during user registration: {str(e)}")
                    return 528, f"Database error: {str(e)}"
                except Exception as e:
                    trans.rollback()
                    logging.error(f"[ERROR] Unexpected error during user registration: {str(e)}")
                    return 528, f"Unexpected error: {str(e)}"

        except Exception as e:  # 捕获事务外异常
            logging.error(f"[ERROR] Error outside transaction: {str(e)}")
            return 528, f"Unexpected error: {str(e)}"

        return 200, "ok"



    def check_token(self, user_id: str, token: str) -> tuple:
        query = sa.text("SELECT token FROM users WHERE user_id = :user_id")
        try:
            with self.conn.connect() as connection:
                result = connection.execute(query, {"user_id": user_id}).fetchone()
                if not result:
                    return 401, "authorization fail"  # 用户不存在
                db_token = result[0]  # 从数据库中获取 token
                if not self.__check_token(user_id, db_token, token):  # 使用 __check_token 进行全面验证
                    return 401, "authorization fail"
        except sa.exc.SQLAlchemyError as e: 
            return 528, str(e)
        return 200, "ok"



    def check_password(self, user_id: str, password: str) -> tuple:
        try:
            query = sa.text("SELECT password FROM users WHERE user_id = :user_id")
            with self.conn.connect() as connection:
                result = connection.execute(query, {"user_id": user_id}).fetchone()
                print(f"[DEBUG] Fetched password from DB: {result}")
                if not result or result[0] != password:
                    print(f"[DEBUG] Password mismatch for user_id: {user_id}")
                    return error.error_authorization_fail()
            return 200, "ok"
        except sa.exc.SQLAlchemyError as e: 
            print(f"[ERROR] Database error in check_password: {str(e)}")
            return 528, str(e)


    def login(self, user_id: str, password: str, terminal: str) -> tuple:
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, None  # 保持返回值一致
            
            # 生成 token
            token = jwt_encode(user_id, terminal)
            query = sa.text("UPDATE users SET token = :token, terminal = :terminal WHERE user_id = :user_id")
            with self.conn.connect() as connection:
                result = connection.execute(query, {"token": token, "terminal": terminal, "user_id": user_id})
                connection.commit()
                # if result.rowcount == 0:
                #     return 401, "Authorization failed", None  # 更新失败

        except Exception as e: 
            return 528, f"Server error: {str(e)}", None

        return 200, "OK", token  # 成功返回 code, message, token



    def logout(self, user_id: str, token: str) -> tuple:
        logging.debug(f"[DEBUG] Logout attempt for user_id: {user_id} with token: {token}")
        code, message = self.check_token(user_id, token)
        if code != 200:
            logging.debug(f"[DEBUG] Token check failed for user_id: {user_id}, code: {code}, message: {message}")
            return code, message

        query = sa.text("UPDATE users SET token = NULL, terminal = NULL WHERE user_id = :user_id")
        try:
            with self.conn.connect() as connection:
                result = connection.execute(query, {"user_id": user_id})
                connection.commit()  # 显式提交事务
                logging.debug(f"[DEBUG] Logout DB update result: {result.rowcount} rows affected")
                if result.rowcount == 0:
                    return 401, "authorization fail"  # 更新失败
        except sa.exc.SQLAlchemyError as e: 
            logging.error(f"[ERROR] SQLAlchemy error during logout: {str(e)}")
            return 528, str(e)
        return 200, "ok"



    def unregister(self, user_id: str, password: str) -> tuple:
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                print(f"[DEBUG] Password check failed for user_id: {user_id}, code: {code}, message: {message}")
                return code, message

            query = sa.text("DELETE FROM users WHERE user_id = :user_id")
            with self.conn.connect() as connection:
                result = connection.execute(query, {"user_id": user_id})
                # 打印 SQL 执行结果
                print(f"[DEBUG] Delete result: {result.rowcount} rows affected for user_id: {user_id}")
                if result.rowcount == 0:
                    print(f"[ERROR] Authorization failed for user_id: {user_id}")
                    return error.error_authorization_fail()
        except sa.exc.SQLAlchemyError as e: 
            # 打印数据库异常
            print(f"[ERROR] Database error during unregister: {str(e)}")
            return 528, str(e)
        return 200, "ok"


    def change_password(self, user_id: str, old_password: str, new_password: str) -> tuple:
        try:
            # 验证旧密码
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message

            # 更新密码和 token
            terminal = f"terminal_{time.time()}"
            token = jwt_encode(user_id, terminal)
            query = sa.text(
                "UPDATE users SET password = :new_password, token = :token, terminal = :terminal WHERE user_id = :user_id"
            )
            with self.conn.connect() as connection:
                result = connection.execute(
                    query, {"new_password": new_password, "token": token, "terminal": terminal, "user_id": user_id}
                )
                connection.commit()  # 显式提交事务


        except sa.exc.SQLAlchemyError as e: 
            return 528, str(e)

        return 200, "Password changed successfully"

    def recommend_books(self, buyer_id: str, n_recommendations: int = 5) -> tuple:
        """
        推荐书籍功能的 MySQL 实现
        """
        try:
            with self.conn.connect() as connection:
                # 获取用户历史订单ID
                query_orders = sa.text("SELECT order_id FROM history_order WHERE user_id = :buyer_id")
                orders = connection.execute(query_orders, {"buyer_id": buyer_id}).fetchall()
                print(f"[DEBUG] Orders fetched: {orders}")
                
                # 如果 orders 是元组列表，使用索引访问 order_id
                order_ids = [order[0] for order in orders]  # 访问元组的第一个元素
                

                # 获取用户已购买的书籍ID
                query_user_books = sa.text("""
                    SELECT DISTINCT book_id 
                    FROM history_order_detail 
                    WHERE order_id IN :order_ids
                """)
                user_books = connection.execute(
                    query_user_books, {"order_ids": tuple(order_ids)}
                ).fetchall()
                user_books = {book[0] for book in user_books}  # 同样通过索引访问
                
                print(f"[DEBUG] User books fetched: {user_books}")



                # 获取与用户购买过的书籍相关的其他用户ID
                query_related_users = sa.text("""
                    SELECT DISTINCT h.user_id 
                    FROM history_order h
                    JOIN history_order_detail hod ON h.order_id = hod.order_id
                    WHERE hod.book_id IN :user_books AND h.user_id != :buyer_id
                """)
                related_users = connection.execute(
                    query_related_users, {"user_books": tuple(user_books), "buyer_id": buyer_id}
                ).fetchall()
                related_users = {user[0] for user in related_users}  # 通过索引访问
                
                print(f"[DEBUG] Related users fetched: {related_users}")

 
                # 获取这些用户购买的其他书籍
                query_other_books = sa.text("""
                    SELECT hod.book_id, COUNT(*) AS frequency
                    FROM history_order_detail hod
                    JOIN history_order h ON hod.order_id = h.order_id
                    WHERE hod.book_id NOT IN :user_books
                    AND h.user_id IN :related_users
                    GROUP BY hod.book_id
                    ORDER BY frequency DESC
                    LIMIT :n_recommendations
                """)
                print(f"[DEBUG] Number of recommendations requested: {n_recommendations}")
                recommended_books = connection.execute(
                    query_other_books,
                    {
                        "user_books": tuple(user_books),
                        "related_users": tuple(related_users),
                        "n_recommendations": n_recommendations,
                    },
                ).fetchall()
                book_ids = [book[0] for book in recommended_books]  # 通过索引访问
                
                print(f"[DEBUG] Recommended books fetched: {book_ids}")


                # 获取推荐书籍的详细信息
                query_book_details = sa.text("""
                    SELECT book_id, title, author, publisher, price
                    FROM new_books
                    WHERE book_id IN :book_ids
                """)
                book_details = connection.execute(query_book_details, {"book_ids": tuple(book_ids)}).fetchall()

# 检查 book_details 是否为 Row 类型或元组类型
                print(f"[DEBUG] Raw book details fetched: {book_details}")

                books_info = [
                    {
                        "book_id": book[0],       # 使用索引 0 访问 book_id
                        "title": book[1],         # 使用索引 1 访问 title
                        "author": book[2],        # 使用索引 2 访问 author
                        "publisher": book[3],     # 使用索引 3 访问 publisher
                        "price": book[4],         # 使用索引 4 访问 price
                    }
                    for book in book_details
                ]

                print(f"[DEBUG] Book details fetched: {books_info}")
                return 200, books_info

        except sa.exc.SQLAlchemyError as e: 
            logging.error(f"[ERROR] SQLAlchemy error in recommend_books: {str(e)}")
            return 528, f"Database error: {str(e)}"
        except Exception as e: 
            logging.error(f"[ERROR] Unexpected error in recommend_books: {str(e)}")
            return 538, f"Unexpected error: {str(e)}"

    def search_book(self, query_text: str, page: int = 1, page_size: int = 10, store_id: str = None) -> (int, str, dict):
        try:
            with self.conn.connect() as conn:
                # 查询 books 表
                query_books = sa.text("""
                    SELECT book_id, title, tags, book_intro, author_intro, author, content
                    FROM new_books
                    WHERE title LIKE :query_text
                    OR tags LIKE :query_text
                    OR book_intro LIKE :query_text
                    OR author_intro LIKE :query_text
                    OR author LIKE :query_text
                    OR content LIKE :query_text
                """)
                books = conn.execute(query_books, {"query_text": f"%{query_text}%"}).mappings().fetchall()

                if not books:
                    return 526, "No matching books found.", {}

                # 提取 book_id 列表
                book_ids = [book['book_id'] for book in books]

                # 查询 stores 表
                if store_id:
                    # 检查商店是否存在
                    query_store_check = sa.text("SELECT 1 FROM stores WHERE store_id = :store_id")
                    store_exists = conn.execute(query_store_check, {"store_id": store_id}).fetchone()
                    if not store_exists:
                        return 513, "Store not found", {}

                    query_stores = sa.text("""
                        SELECT store_id, book_id, price, stock_level
                        FROM stores
                        WHERE store_id = :store_id
                        AND book_id IN :book_ids
                    """)
                    store_results = conn.execute(query_stores, {"store_id": store_id, "book_ids": tuple(book_ids)}).mappings().fetchall()
                else:
                    query_stores = sa.text("""
                        SELECT store_id, book_id, price, stock_level
                        FROM stores
                        WHERE book_id IN :book_ids
                    """)
                    store_results = conn.execute(query_stores, {"book_ids": tuple(book_ids)}).mappings().fetchall()


                # 准备返回的数据，并将 Decimal 转为 float
                results = []
                for store in store_results:
                    results.append({
                        "store_id": store["store_id"],
                        "book_id": store["book_id"],
                        "price": float(store["price"]),  # 转换为 float
                        "stock_level": store["stock_level"],
                    })

                # 分页处理
                total_results = len(results)
                total_pages = (total_results + page_size - 1) // page_size
                start_index = (page - 1) * page_size
                end_index = start_index + page_size
                paginated_results = results[start_index:end_index]

                return 200, "ok", {
                    "total_results": total_results,
                    "total_pages": total_pages,
                    "current_page": page,
                    "results": paginated_results,
                }
        except Exception as e: 
            return 528, f"Error in query execution: {str(e)}", {}
        
    def jaccard_similarity(self, set1, set2):
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union != 0 else 0

    def search_book_regex(
        self,
        query_text: str,
        page: int = 1,
        page_size: int = 10,
        store_id: str = None,
        min_similarity: float = 0.01
    ) -> (int, str, dict):
        try:
            tokens = [token.strip() for token in jieba.lcut(query_text.strip()) if token.strip()]
            query_set = set(tokens)
            store_book_ids = None

            with self.conn.connect() as conn:
                if store_id:
                    query_store_check = sa.text("SELECT 1 FROM stores WHERE store_id = :store_id")
                    store_exists = conn.execute(query_store_check, {"store_id": store_id}).fetchone()
                    if not store_exists:
                        return 513, "店铺不存在", {}

                    rows = conn.execute(
                        sa.text("SELECT book_id FROM stores WHERE store_id = :store_id"),
                        {"store_id": store_id},
                    ).fetchall()
                    store_book_ids = {row[0] for row in rows}
                    if not store_book_ids:
                        return 526, "Store has no matching books", {}

                pattern = f"%{query_text.strip()}%"
                limit = MAX_REGEX_CANDIDATES

                if store_book_ids is not None:
                    query_books = sa.text("""
                    SELECT book_id, title, tags, author_intro, book_intro, content, author
                    FROM new_books
                    WHERE book_id IN :book_ids
                    AND (
                        title LIKE :pattern
                        OR tags LIKE :pattern
                        OR author_intro LIKE :pattern
                        OR book_intro LIKE :pattern
                        OR content LIKE :pattern
                        OR author LIKE :pattern
                    )
                    LIMIT :limit
                """).bindparams(sa.bindparam("book_ids", expanding=True))
                    books = conn.execute(
                        query_books,
                        {"book_ids": tuple(store_book_ids), "pattern": pattern, "limit": limit},
                    ).mappings().fetchall()
                else:
                    query_books = sa.text("""
                    SELECT book_id, title, tags, author_intro, book_intro, content, author
                    FROM new_books
                    WHERE title LIKE :pattern
                    OR tags LIKE :pattern
                    OR author_intro LIKE :pattern
                    OR book_intro LIKE :pattern
                    OR content LIKE :pattern
                    OR author LIKE :pattern
                    LIMIT :limit
                """)
                    books = conn.execute(
                        query_books,
                        {"pattern": pattern, "limit": limit},
                    ).mappings().fetchall()

                if not books:
                    return 526, "No matching books found.", {}

                books = list(books)
                books_with_similarity = []
                skip_similarity = not query_set

                for book in books:
                    if skip_similarity:
                        books_with_similarity.append((1.0, book))
                        continue

                    fields_to_compare = [
                        str(book["title"] or ""),
                        str(book["tags"] or ""),
                        str(book["author_intro"] or ""),
                        str(book["book_intro"] or ""),
                        str(book["content"] or ""),
                        str(book["author"] or ""),
                    ]
                    combined_text = " ".join(fields_to_compare)
                    combined_tokens = [token.strip() for token in jieba.lcut(combined_text) if token.strip()]
                    combined_set = set(combined_tokens)
                    similarity = self.jaccard_similarity(query_set, combined_set)
                    if similarity >= min_similarity:
                        books_with_similarity.append((similarity, book))

                books_with_similarity.sort(key=lambda x: x[0], reverse=True)
                book_results = [book for similarity, book in books_with_similarity if similarity > 0][:100]
                if not book_results and books:
                    book_results = books[:100]

                book_ids = [book["book_id"] for book in book_results]

                if store_id:
                    query_stores = sa.text("""
                        SELECT store_id, book_id, price, stock_level
                        FROM stores
                        WHERE store_id = :store_id
                        AND book_id IN :book_ids
                    """).bindparams(sa.bindparam("book_ids", expanding=True))
                    store_results = conn.execute(
                        query_stores,
                        {"store_id": store_id, "book_ids": tuple(book_ids)}
                    ).mappings().fetchall()
                else:
                    query_stores = sa.text("""
                        SELECT store_id, book_id, price, stock_level
                        FROM stores
                        WHERE book_id IN :book_ids
                    """).bindparams(sa.bindparam("book_ids", expanding=True))
                    store_results = conn.execute(
                        query_stores,
                        {"book_ids": tuple(book_ids)}
                    ).mappings().fetchall()

                results = []
                for store in store_results:
                    results.append({
                        "book_id": store["book_id"],
                        "price": float(store["price"]),
                        "stock_level": store["stock_level"],
                        "store_id": store["store_id"],
                    })

                total_results = len(results)
                total_pages = (total_results + page_size - 1) // page_size
                start_index = (page - 1) * page_size
                end_index = start_index + page_size
                paginated_results = results[start_index:end_index]

                return 200, "ok", {
                    "total_results": total_results,
                    "total_pages": total_pages,
                    "current_page": page,
                    "results": paginated_results,
                }
        except Exception as e:
            return 528, f"Error in query execution: {str(e)}", {}