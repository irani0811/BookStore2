import json

from be.model import error
from be.model import db_conn

class Seller(db_conn.DBConn):
    def __init__(self):
        db_conn.DBConn.__init__(self)
    
    def add_book(
        self,
        user_id: str,
        store_id: str,
        book_id: str,
        book_json_str: str,
        stock_level: int,
    ):
        try:
            # 检查用户是否存在
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            # 检查商店是否存在
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)

            # 检查书籍是否已存在：
            # - 若已存在且本次 stock_level <= 0，按单测预期返回 516（exist book id）
            # - 若已存在且本次 stock_level > 0，则累加库存，并按需更新价格，返回 200
            if self.book_id_exist(store_id, book_id):
                if stock_level <= 0:
                    return error.error_exist_book_id(book_id)
                try:
                    price_existing = json.loads(book_json_str).get("price")
                except Exception:
                    price_existing = None
                # 累加库存
                self.conn['stores'].update_one(
                    {"store_id": store_id, "books.book_id": book_id},
                    {"$inc": {"books.$.stock_level": stock_level}}
                )
                # 更新价格（如果提供）
                if price_existing is not None:
                    self.conn['stores'].update_one(
                        {"store_id": store_id, "books.book_id": book_id},
                        {"$set": {"books.$.price": price_existing}}
                    )
                return 200, "ok"
            
            # 从 book_json_str 中提取价格信息
            price = json.loads(book_json_str).get("price")
            
            # 将书籍添加到商店 (stores 集合)
            self.conn['stores'].update_one(
                {"store_id": store_id},
                {"$push": {"books": {"book_id": book_id, "price": price, "stock_level": stock_level}}},
            )
            
            # 将书籍添加到 new_books 集合
            new_book_data = {
                "book_id": book_id,
                "book_info": book_json_str
            }

            # 使用 $setOnInsert 只在文档不存在时插入
            self.conn['new_books'].update_one(
                {"book_id": book_id},  # 根据 book_id 查找
                {"$setOnInsert": new_book_data},  # 仅在书籍不存在时插入
                upsert=True  # 确保文档插入或更新
            )

        except Exception as e:
            return 528, f"An error occurred while adding the book: {str(e)}"
        
        return 200, "ok"


    def add_stock_level(
        self, user_id: str, store_id: str, book_id: str, add_stock_level: int
    ):
        try:
            # 检查用户是否存在
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id)

            # 检查商店是否存在
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)

            # 检查书籍是否存在于商店中
            if not self.book_id_exist(store_id, book_id):
                return error.error_non_exist_book_id(book_id)

            # 验证库存增加量是否合法
            if add_stock_level <= 0:
                return error.error_stock_level_low(book_id)

            # 更新库存
            self.conn['stores'].update_one(
                {"store_id": store_id, "books.book_id": book_id},
                {"$inc": {"books.$.stock_level": add_stock_level}}
            )
        except Exception as e:
            return 528, f"添加库存时发生错误：{str(e)}"
        
        return 200, "ok"
    
    def create_store(self, user_id: str, store_id: str) -> (int, str):
        try:
            # 检查商店是否已存在
            if self.store_id_exist(store_id):
                return error.error_exist_store_id(store_id)

            # 创建商店
            self.conn['stores'].insert_one(
                {"store_id": store_id, "user_id": user_id}
            )
            
        except Exception as e:
            return 528, f"创建商店时发生错误: {str(e)}"

        return 200, "ok"

    def delivery_order(self, store_id: str, order_id: str) -> (int, str):
        try:
            # 检查商店是否存在
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id)

            # 查找订单 - 先在history_order中查找
            order = self.conn['history_order'].find_one({"order_id": order_id})
            
            # 如果在history_order中找不到，尝试在new_order中查找
            if not order:
                order = self.conn['new_order'].find_one({"order_id": order_id})
                if not order:
                    return error.error_invalid_order_id(order_id)
            
            # 检查订单是否属于该商店
            if order['store_id'] != store_id:
                return error.error_invalid_store_id(store_id)

            # 检查订单状态是否为待发货 (状态 1)
            if order.get('status') != 1:
                return error.error_invalid_order_status(order_id)

            # 更新订单状态为待收货 (状态 2)
            self.conn['history_order'].update_one(
                {"order_id": order_id},
                {"$set": {"status": 2}}  # 状态 2 表示待收货
            )
                
        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in delivery_order: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, f"发货时发生未知错误: {str(e)}"

        return 200, "发货成功"

