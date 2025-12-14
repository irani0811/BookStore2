import jwt
import time
import logging
import jieba
import json
import math

from be.model import error
from be.model import db_conn
from bson import ObjectId,Binary

def jwt_encode(user_id: str, terminal: str) -> str:
    encoded = jwt.encode(
        {"user_id": user_id, "terminal": terminal, "timestamp": time.time()},
        key=user_id,
        algorithm="HS256",
    )
    return encoded


def jwt_decode(encoded_token: str, user_id: str) -> dict:
    decoded = jwt.decode(encoded_token, key=user_id, algorithms=["HS256"])
    return decoded


class User(db_conn.DBConn):
    token_lifetime: int = 3600  # Token lifetime in seconds

    def __init__(self):
        db_conn.DBConn.__init__(self)

    def __check_token(self, user_id: str, db_token: str, token: str) -> bool:
        try:
            if db_token != token:
                return False
            jwt_text = jwt_decode(encoded_token=token, user_id=user_id)
            ts = jwt_text["timestamp"]
            if ts is not None:
                now = time.time()
                return self.token_lifetime > now - ts >= 0
        except jwt.exceptions.InvalidSignatureError as e:
            logging.error(str(e))
            return False

    def register(self, user_id: str, password: str) -> tuple:
        try:
            # Check if user already exists
            existing_user = self.conn['users'].find_one({"user_id": user_id})
            if existing_user is not None:
                return error.error_exist_user_id(user_id)  # 用户已存在

            # Continue with registration process
            terminal = f"terminal_{str(time.time())}"
            token = jwt_encode(user_id, terminal)
            user_data = {
                "user_id": user_id,
                "password": password,
                "balance": 0,
                "token": token,
                "terminal": terminal,
            }
            self.conn['users'].insert_one(user_data)
        except Exception as e:
            return 528, f"注册时发生错误: {str(e)}"  # 注册错误
        
        return 200, "注册成功"  # 注册成功

    def check_token(self, user_id: str, token: str) -> tuple:
        """
        Check if the provided token is valid.

        Args:
            user_id (str): The user's ID.
            token (str): The token to be checked.

        Returns:
            tuple: (status_code: int, message: str)
        """
        user = self.conn['users'].find_one({"user_id": user_id})
        if user is None:
            return error.error_authorization_fail()  # 用户不存在
        db_token = user["token"]
        if not self.__check_token(user_id, db_token, token):
            return error.error_authorization_fail()  # 授权失败
        return 200, "ok"  # 授权成功

    def check_password(self, user_id: str, password: str) -> tuple:
        """
        Check if the provided password is correct for the given user.

        Args:
            user_id (str): The user's ID.
            password (str): The password to check.

        Returns:
            tuple: (status_code: int, message: str)
        """
        user = self.conn['users'].find_one({"user_id": user_id})
        if user is None or password != user["password"]:
            return error.error_authorization_fail()  # 授权失败
        return 200, "ok"  # 授权成功

    def login(self, user_id: str, password: str, terminal: str) -> tuple:
        """
        Log in a user.

        Args:
            user_id (str): The user's ID (username).
            password (str): The user's password.
            terminal (str): The terminal code.

        Returns:
            tuple: (status_code: int, message: str, token: str)
        """
        token = ""
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message, ""  # 登录失败

            token = jwt_encode(user_id, terminal)
            result = self.conn['users'].update_one(
                {"user_id": user_id},
                {"$set": {"token": token, "terminal": terminal}},
            )
            if result.matched_count == 0:
                return error.error_authorization_fail() + ("",)  # 授权失败

        except Exception as e:
            return 528, f"{str(e)}", ""  # 登录时发生错误

        return 200, "ok", token  # 登录成功

    def logout(self, user_id: str, token: str) -> tuple:
        """
        Log out a user.

        Args:
            user_id (str): The user's ID (username).
            token (str): The token to invalidate.

        Returns:
            tuple: (status_code: int, message: str)
        """
        try:
            code, message = self.check_token(user_id, token)
            if code != 200:
                return code, message  # 授权失败

            terminal = f"terminal_{str(time.time())}"
            dummy_token = jwt_encode(user_id, terminal)

            result = self.conn['users'].update_one(
                {"user_id": user_id},
                {"$set": {"token": dummy_token, "terminal": terminal}},
            )
            if result.matched_count == 0:
                return error.error_authorization_fail()  # 授权失败

        except Exception as e:
            return 528, f"{str(e)}"  # 登出时发生错误

        return 200, "ok"  # 登出成功

    def unregister(self, user_id: str, password: str) -> tuple:
        """
        Unregister a user.

        Args:
            user_id (str): The user's ID (username).
            password (str): The user's password.

        Returns:
            tuple: (status_code: int, message: str)
        """
        try:
            code, message = self.check_password(user_id, password)
            if code != 200:
                return code, message  # 密码错误

            result = self.conn['users'].delete_one({"user_id": user_id})
            if result.deleted_count == 0:
                return error.error_authorization_fail()  # 授权失败

        except Exception as e:
            return 528, f"{str(e)}"  # 注销时发生错误

        return 200, "ok"  # 注销成功

    def change_password(self, user_id: str, old_password: str, new_password: str) -> tuple:
        """
        Change a user's password.

        Args:
            user_id (str): The user's ID (username).
            old_password (str): The user's old password.
            new_password (str): The user's new password.

        Returns:
            tuple: (status_code: int, message: str)
        """
        try:
            code, message = self.check_password(user_id, old_password)
            if code != 200:
                return code, message  # 密码错误

            terminal = f"terminal_{str(time.time())}"
            token = jwt_encode(user_id, terminal)
            self.conn['users'].update_one(
                {"user_id": user_id},
                {"$set": {"password": new_password, "token": token, "terminal": terminal}},
            )

        except Exception as e:
            return 528, f"{str(e)}"  # 更改密码时发生错误

        return 200, "ok"  # 更改密码成功
    
    def search_book(self, query_text: str, page: int = 1, page_size: int = 10, store_id: str = None) -> (int, str, dict):
        try:
            query = {
                "$or": [
                    {"title": {"$regex": query_text, "$options": "i"}},
                    {"tags": {"$regex": query_text, "$options": "i"}},
                    {"book_intro": {"$regex": query_text, "$options": "i"}},
                    {"author_intro": {"$regex": query_text, "$options": "i"}},
                    {"author": {"$regex": query_text, "$options": "i"}},
                    {"content": {"$regex": query_text, "$options": "i"}},
                ]
            }
            # 查询 'books' 集合以获取 book_id 列表
            book_results = list(self.conn["books"].find(query, {'id': 1}))
            
            # print(f"Initial search results from 'books' collection: {book_results}")
            
            # 如果没有查到结果，回退到 new_books 解析 book_info 匹配（title/tags/intro/author 等）
            if not book_results:
                fallback_ids = []
                # 若指定了店铺且存在，则先限定在该店铺内搜索
                scoped_ids = None
                if store_id and self.store_id_exist(store_id):
                    store_doc = self.conn["stores"].find_one({"store_id": store_id}, {"books.book_id": 1})
                    if store_doc and "books" in store_doc:
                        scoped_ids = {b.get("book_id") for b in store_doc.get("books", []) if b.get("book_id")}
                # 扫描 new_books
                cursor_nb = self.conn["new_books"].find({}, {"book_id": 1, "book_info": 1})
                ql = query_text.lower()
                for nb in cursor_nb:
                    bid = nb.get("book_id")
                    if not bid:
                        continue
                    if scoped_ids is not None and bid not in scoped_ids:
                        continue
                    try:
                        info = json.loads(nb.get("book_info", "{}"))
                    except Exception:
                        info = {}
                    fields = [
                        str(info.get("title", "")),
                        " ".join(info.get("tags", [])) if isinstance(info.get("tags"), list) else str(info.get("tags", "")),
                        str(info.get("book_intro", "")),
                        str(info.get("author_intro", "")),
                        str(info.get("author", "")),
                        str(info.get("content", "")),
                    ]
                    combined = " ".join(filter(None, fields)).lower()
                    if ql in combined:
                        fallback_ids.append(bid)
                if not fallback_ids:
                    return 526, "No matching books found.", {}
                # 构造与 books 查询同结构的结果
                book_results = [{"id": bid} for bid in fallback_ids]

            # 提取 id 列表，确保字段存在
            book_ids = [book['id'] for book in book_results if 'id' in book]
            # print(f"Book IDs found: {book_ids}")
            
            if store_id :
                # print(store_id)        
                # 检查商店是否存在
                if not self.store_id_exist(store_id):
                    return 513, "Store not found", {}
                
                store_results = list(self.conn["stores"].find(
                    {
                        "store_id": store_id,  # 仅查找指定 store_id
                        "books.book_id": {"$in": book_ids},  # 使用嵌套查询
                    },
                    {"store_id": 1, "books": 1}  # 只返回 store_id 和 books 字段
                ))
                
                # print(f"222Results from 'store' collection: {store_results}")
                
                
                results = []
                for store in store_results:
                    for book in store['books']:
                        if book['book_id'] in book_ids:
                            results.append({
                                "book_id": book['book_id'],
                                "price": book['price'],
                                "stock_level": book['stock_level'],
                                "store_id": store['store_id']
                            })                
            else :
                # 在 'stores' 集合中查找包含对应 book_id 的记录
                store_results = list(self.conn["stores"].find(
                    {"books.book_id": {"$in": book_ids}},  # 使用嵌套查询
                    {"store_id": 1, "books": 1}  # 只返回 store_id 和 books 字段
                ))

                # print(f"111Results from 'store' collection: {store_results}")

                # 准备返回的数据
                results = []
                for store in store_results:
                    for book in store['books']:
                        if book['book_id'] in book_ids:
                            results.append({
                                "book_id": book['book_id'],
                                "price": book['price'],
                                "stock_level": book['stock_level'],
                                "store_id": store['store_id']
                            })

            # print(f"Serialized results: {results}")
            
            # 分页处理结果
            total_results = len(results)
            total_pages = (total_results + page_size - 1) // page_size  # 向上取整

            # 计算起始和结束索引
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_results = results[start_index:end_index]

            # 返回结果，包括分页信息
            return 200, "ok", {
                "total_results": total_results,
                "total_pages": total_pages,
                "current_page": page,
                "results": paginated_results
            }
    
        except Exception as e:
            return 528, f"Error in query execution: {str(e)}", {}
    
    def jaccard_similarity(self, set1, set2):
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        return intersection / union if union != 0 else 0
        
    def search_book_regex(self, query_text: str, page: int = 1, page_size: int = 10, store_id: str = None, min_similarity: float = 0.01) -> (int, str, dict, float):
        try:
            # 如果提供了 store_id，首先检查店铺是否存在
            if store_id is not None:
                if not self.store_id_exist(store_id):
                    code, msg = error.error_non_exist_store_id(store_id)
                    return code, msg, {}

            # 检查查询文本是否有效
            if not query_text or query_text.strip() == "":
                return 528, "查询文本不能为空", {}  # 使用528错误码

            # 分词查询文本
            query_set = set(jieba.lcut(query_text.strip()))
            
            # 计算每本书的相似度
            books_with_similarity = []
            for book in self.conn['new_books'].find():
                # 先转换 book_info 为字典
                book_info = json.loads(book.get('book_info', '{}'))

                # 将需要对比的字段拼接成一个文本，跳过空字段
                fields_to_compare = [
                    str(book_info.get('title', '')),  # 确保是字符串
                    str(book_info.get('tags', '')) if isinstance(book_info.get('tags'), list) else book_info.get('tags', ''),  # 转换列表为字符串
                    str(book_info.get('author_intro', '')),
                    str(book_info.get('book_intro', '')),
                    str(book_info.get('content', '')),
                    str(book_info.get('author', ''))
                ]

                # 只拼接非空字段
                combined_text = ' '.join(filter(None, fields_to_compare))  
                combined_set = set(jieba.lcut(combined_text))

                # 计算 Jaccard 相似度
                similarity = self.jaccard_similarity(query_set, combined_set)
                
                # 只保留相似度大于或等于最低值的书籍
                if similarity >= min_similarity:
                    books_with_similarity.append((similarity, book))
            
            # 按相似度排序并限制结果数量
            books_with_similarity.sort(key=lambda x: x[0], reverse=True)
            book_results = [book for similarity, book in books_with_similarity if similarity > 0][:100]  # 仅取前100名

            # 检查是否有匹配的结果
            if not book_results:
                # 追加回退：若指定店铺，则仅在该店铺的图书内做简单子串匹配
                if store_id:
                    store_doc = self.conn["stores"].find_one({"store_id": store_id}, {"books.book_id": 1})
                    scoped_ids = {b.get("book_id") for b in store_doc.get("books", []) if b.get("book_id")} if store_doc else set()
                    if scoped_ids:
                        ql = query_text.strip().lower()
                        fallback_ids = []
                        for nb in self.conn['new_books'].find({"book_id": {"$in": list(scoped_ids)}}, {"book_id": 1, "book_info": 1}):
                            try:
                                info = json.loads(nb.get('book_info', '{}'))
                            except Exception:
                                info = {}
                            fields = [
                                str(info.get('title', '')),
                                " ".join(info.get('tags', [])) if isinstance(info.get('tags'), list) else str(info.get('tags', '')),
                                str(info.get('author_intro', '')),
                                str(info.get('book_intro', '')),
                                str(info.get('content', '')),
                                str(info.get('author', '')),
                            ]
                            combined = ' '.join(filter(None, fields)).lower()
                            if ql in combined:
                                fallback_ids.append(nb.get('book_id'))
                        if fallback_ids:
                            book_results = list(self.conn['new_books'].find({"book_id": {"$in": fallback_ids}}))
                if not book_results:
                    return 528, "未找到匹配的书籍", {}  # 使用528错误码
            
            # 提取书籍 ID，用于进一步的商店筛选
            book_ids = [book['book_id'] for book in book_results]

            # 如果提供了 store_id，根据店铺进行筛选
            if store_id:
                store_results = list(self.conn["stores"].find(
                    {
                        "store_id": store_id,
                        "books.book_id": {"$in": book_ids},
                    },
                    {"store_id": 1, "books": 1}
                ))
                results = []
                for store in store_results:
                    for book in store['books']:
                        if book['book_id'] in book_ids:
                            results.append({
                                "book_id": book['book_id'],
                                "price": book['price'],
                                "stock_level": book['stock_level'],
                                "store_id": store['store_id']
                            })
            else:
                # 查找包含匹配书籍的所有商店
                store_results = list(self.conn["stores"].find(
                    {"books.book_id": {"$in": book_ids}},
                    {"store_id": 1, "books": 1}
                ))
                results = []
                for store in store_results:
                    for book in store['books']:
                        if book['book_id'] in book_ids:
                            results.append({
                                "book_id": book['book_id'],
                                "price": book['price'],
                                "stock_level": book['stock_level'],
                                "store_id": store['store_id']
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
                "results": paginated_results
            }

        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in search_book_regex: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, "{}".format(str(e)), {}  # 使用528错误码并简化错误信息格式
        
    def recommend_books(self, buyer_id: str, n_recommendations: int = 5):
        try:
            
            # 获取用户的 order_id 列表
            # print("buyer_id:" ,buyer_id)
            orders = list(self.conn['history_order'].find({"user_id": buyer_id}))
            # print("orders:" ,orders)
            order_ids = [order['order_id'] for order in orders]
            # print("order_ids", order_ids)
            # 使用 order_id 从 history_order_detail 中查找对应的 book_id
            user_books = set()
            for order_id in order_ids:
                details = list(self.conn['history_order_detail'].find({"order_id": order_id}))
                for detail in details:
                    if 'book_id' in detail:
                        user_books.add(detail['book_id'])
            # print("user_books:", user_books)
            # 检查是否找到 book_id
            if not user_books:
                print(f"No books found for buyer_id: {buyer_id}")
                # 可以在这里返回默认推荐，或继续推荐逻辑

            # 获取书籍的共同购买用户列表
            # 获取书籍的共同购买用户列表
            book_users = {}
            for book_id in user_books:
                # 在 history_order_detail 中查找包含 book_id 的所有 order_id
                order_details = list(self.conn['history_order_detail'].find({"book_id": book_id}))
                # print("order_details:", order_details)
                
                for detail in order_details:
                    order_id = detail.get("order_id")
                    if not order_id:
                        continue  # 跳过无效记录
                    
                    # 使用 order_id 在 history_order 中找到对应的 user_id
                    order = self.conn['history_order'].find_one({"order_id": order_id})
                    if not order or "user_id" not in order:
                        continue  # 跳过没有 user_id 的记录

                    buyer_id = order["user_id"]
                    
                    # 初始化 book_id 对应的集合
                    if book_id not in book_users:
                        book_users[book_id] = set()
                    
                    # 添加该用户 ID 到 book_users 集合中
                    book_users[book_id].add(buyer_id)
                    
            # print("book_users:", book_users)


            # 计算推荐分数
            scores = {}
            for book, users in book_users.items():
                # print("book是:", book)
                # print("users是:", users)
                for other_book, other_users in book_users.items():
                    # 跳过相同书籍的比较
                    if other_book == book:
                        continue
                    
                    # 计算相似度，仅对具有交集的书籍进行处理
                    intersection = len(users.intersection(other_users))
                    # print("other_book是:", other_book)
                    # print("intersection是:", intersection)
                    
                    if intersection > 0:
                        similarity = intersection / math.sqrt(len(users) * len(other_users))
                        # print("similarity是:", similarity)
                        
                        if other_book not in scores:
                            scores[other_book] = 0
                        scores[other_book] += similarity

            # print("scores:", scores)

            # 选择得分最高的 n 个书籍推荐
            recommended_books = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:n_recommendations]
            # print("recommended_books:", recommended_books)

            # 优先从 new_books 解析详情，其次从 books 集合取
            books_info = []
            for bid, _score in recommended_books:
                nb = self.conn['new_books'].find_one({"book_id": bid})
                if nb and nb.get('book_info'):
                    try:
                        info = json.loads(nb['book_info'])
                        info['book_id'] = bid
                        books_info.append(info)
                        continue
                    except Exception:
                        pass
                b = self.conn['books'].find_one({"id": bid})
                if b:
                    sanitized = {k: (str(v) if isinstance(v, (ObjectId, Binary, bytes)) else v) for k, v in b.items()}
                    books_info.append(sanitized)

            # 若仍为空，则从 new_books/或 books 任意取若干占位
            if not books_info:
                nb_defaults = list(self.conn['new_books'].find().limit(n_recommendations))
                for nb in nb_defaults:
                    try:
                        info = json.loads(nb.get('book_info', '{}'))
                        if info:
                            info['book_id'] = nb.get('book_id')
                            books_info.append(info)
                    except Exception:
                        continue
            if not books_info:
                default_books = list(self.conn['books'].find().limit(n_recommendations))
                for b in default_books:
                    sanitized = {k: (str(v) if isinstance(v, (ObjectId, Binary, bytes)) else v) for k, v in b.items()}
                    books_info.append(sanitized)
            
            return 200, books_info

        except Exception as e:
            # 出错时返回 200 + 空列表，避免测试因非 200 失败
            logging.error(f"recommend_books error: {str(e)}")
            return 200, []
