from pymongo import UpdateOne
import uuid
import logging
import json
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch
import re
from bson import ObjectId, Binary

from be.model import error
from be.model import db_conn
from datetime import datetime
from be.model import times
from be.model.times import unpaid_orders

class Buyer(db_conn.DBConn): 
    def __init__(self):
        db_conn.DBConn.__init__(self)
        
    def new_order(self, user_id: str, store_id: str, id_and_count: [(str, int)]) -> (int, str, str):
        order_id = ""
        try:
            # 检查用户是否存在
            if not self.user_id_exist(user_id):
                return error.error_non_exist_user_id(user_id) + (order_id, )

            # 检查商店是否存在
            if not self.store_id_exist(store_id):
                return error.error_non_exist_store_id(store_id) + (order_id, )
            
            # 生成订单ID
            uid = "{}_{}_{}".format(user_id, store_id, str(uuid.uuid1()))
            
            for book_id, count in id_and_count:
                # 检查书籍是否存在及库存信息
                book = self.conn['stores'].find_one({"store_id": store_id, "books.book_id": book_id}, {"books.$": 1})
                
                if book is None:
                    return error.error_non_exist_book_id(book_id) + (order_id, )

                # 提取书籍信息
                book_order_info = book['books'][0]
                stock_level = book_order_info['stock_level']
                price = book_order_info['price']

                if stock_level < count:
                    return error.error_stock_level_low(book_id) + (order_id, )
                
                # 更新库存，减少对应书籍的数量
                self.conn['stores'].update_one(
                    {"store_id": store_id, "books.book_id": book_id, "books.stock_level": {"$gte": count}},
                    {"$inc": {"books.$.stock_level": -count}}
                )
                
                # 插入订单详细信息到 new_order_detail 集合
                self.conn['new_order_detail'].insert_one({
                    "order_id": uid,
                    "book_id": book_id,
                    "count": count,
                    "price": price
                })
                
            # 插入订单到 new_order 集合
            self.conn['new_order'].insert_one({
                "order_id": uid,
                "store_id": store_id,
                "user_id": user_id,
                "status": 0, # 待付款
                "commit_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            order_id = uid
            
            # 使用线程安全的方式添加订单到队列
            from be.model.times import add_unpaid_order
            add_unpaid_order(order_id, datetime.now())
            
        except Exception as e:
            logging.error(
                "Error in new_order for user %s, store %s: %s",
                user_id,
                store_id,
                str(e),
                exc_info=True,
            )
            return 528, "{}".format(str(e)), ""
        
        # 成功时，返回订单号
        return 200, "ok", order_id
    
    def payment(self, user_id: str, password: str, order_id: str) -> (int, str): 
        try: 
            # 查找订单 
            order = self.conn['new_order'].find_one({"order_id": order_id, "user_id": user_id}) 
            if not order: 
                return error.error_invalid_order_id(order_id) 

            # 验证用户密码 
            user = self.conn['users'].find_one({"user_id": user_id}) 
            if not user or user['password'] != password: 
                return error.error_authorization_fail() 

            # 使用聚合管道计算订单总金额 
            price_cursor = self.conn['new_order_detail'].aggregate([ 
                {"$match": {"order_id": order_id}}, 
                {"$group": {"_id": None, "total": {"$sum": {"$multiply": ["$price", "$count"]}}}} 
            ]) 

            price_list = list(price_cursor)
            if not price_list:
                return error.error_invalid_order_id(order_id)
            
            total_price = price_list[0]['total']
            
            # 验证余额是否足够 
            if user['balance'] < total_price: 
                return error.error_not_sufficient_funds(order_id)
            
            # 扣除买家余额 
            update_result = self.conn['users'].update_one( 
                {"user_id": user_id, "balance": {"$gte": total_price}}, 
                {"$inc": {"balance": -total_price}} 
            )
            
            if update_result.modified_count == 0:
                return error.error_not_sufficient_funds(order_id)

            # 更新卖家余额 
            store = self.conn['stores'].find_one({"store_id": order['store_id']}) 
            if not store: 
                return error.error_non_exist_store_id(order['store_id']) 
            
            seller_id = store['user_id'] 
            
            self.conn['users'].update_one( 
                {"user_id": seller_id}, 
                {"$inc": {"balance": total_price}} 
            ) 
            
            # 将订单从new_order移动到history_order 
            order['status'] = 1  # 设置状态为已付款 
            self.conn['history_order'].insert_one(order) 
            self.conn['new_order'].delete_one({"order_id": order_id}) 
            
            # 更新库存 
            order_details = list(self.conn['new_order_detail'].find({"order_id": order_id}))
            for detail in order_details: 
                # 将订单详情移动到history_order_detail 
                self.conn['history_order_detail'].insert_one(detail) 
                
                # 更新库存 
                self.conn['stores'].update_one( 
                    {"store_id": order['store_id'], "books.book_id": detail['book_id']}, 
                    {"$inc": {"books.$.stock_level": -detail['count']}} 
                ) 
                
            # 删除new_order_detail中的记录 
            self.conn['new_order_detail'].delete_many({"order_id": order_id})
                
        except Exception as e: 
            import logging
            import traceback
            error_msg = f"Error in payment: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, "{}".format(str(e))
        
        return 200, "ok"

    def add_funds(self, user_id, password, add_value) -> (int, str):
        try:
            # 验证用户信息
            user = self.conn['users'].find_one({"user_id": user_id})  # 改为通过 self.users_collection 获取用户信息
            if not user:
                return error.error_non_exist_user_id(user_id)

            if user["password"] != password:
                return error.error_authorization_fail()

            # 增加余额，并检查是否成功更新
            self.conn['users'].update_one(
                {"user_id": user_id},
                {"$inc": {"balance": add_value}}
            )
        except Exception as e:  # 捕获其他潜在的异常
            return 528, "意外错误: {}".format(str(e))

        return 200, "资金增加成功。"
    
    def query_order(self, user_id: str) -> (int, str, list):
        try:
            def _sanitize_value(value):
                if isinstance(value, (ObjectId, Binary)):
                    return str(value)
                if isinstance(value, bytes):
                    try:
                        return value.decode("utf-8")
                    except UnicodeDecodeError:
                        return value.decode("utf-8", errors="ignore")
                if isinstance(value, datetime):
                    return value.isoformat()
                if isinstance(value, list):
                    return [_sanitize_value(item) for item in value]
                if isinstance(value, dict):
                    return {k: _sanitize_value(v) for k, v in value.items()}
                return value

            # 验证用户是否存在
            if not self.user_id_exist(user_id):
                code, msg = error.error_non_exist_user_id(user_id)
                return code, msg, []

            # 查询历史订单
            history_orders = list(self.conn['history_order'].find({"user_id": user_id}))

            # 查询新订单
            new_orders = list(self.conn['new_order'].find({"user_id": user_id}))

            # 合并订单列表
            all_orders = history_orders + new_orders

            # 如果没有订单，返回 529 错误
            if not all_orders:
                code, msg, payload = error.error_non_exist_order(user_id)
                return code, msg, payload

            # 构建订单详情
            order_list = []
            for order in all_orders:
                try:
                    # 查询订单详情
                    if order.get('status', 0) == 0:  # 新订单
                        details = list(self.conn['new_order_detail'].find({"order_id": order['order_id']}))
                    else:  # 历史订单
                        details = list(self.conn['history_order_detail'].find({"order_id": order['order_id']}))

                    sanitized_details = [_sanitize_value(detail) for detail in details]

                    create_time = order.get('create_time') or order.get('commit_time', "")

                    # 添加订单信息
                    order_info = {
                        "order_id": order['order_id'],
                        "store_id": order.get('store_id', ""),
                        "status": order.get('status', 0),
                        "create_time": _sanitize_value(create_time),
                        "details": sanitized_details
                    }

                    order_list.append(_sanitize_value(order_info))
                except Exception as detail_error:
                    import logging
                    logging.error(f"Error getting details for order {order['order_id']}: {str(detail_error)}")
                    # 继续处理下一个订单
                    continue

        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in query_order: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, "{}".format(str(e)), {}

        return 200, "ok", order_list
    
    def receive_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            # 查找订单
            order = self.conn['history_order'].find_one({"order_id": order_id, "user_id": user_id})
            if not order:
                return error.error_invalid_order_id(order_id)

            # 检查订单状态是否为待收货 (状态 2)
            if order.get('status') != 2:
                return error.error_not_delivery(order_id)

            # 更新订单状态为已完成 (状态 3)
            self.conn['history_order'].update_one(
                {"order_id": order_id},
                {"$set": {"status": 3}}  # 状态 3 表示已完成
            )
                
        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in receive_order: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, f"收货失败: {str(e)}"

        return 200, "ok"

    def cancel_order(self, user_id: str, order_id: str) -> (int, str):
        try:
            # 查找订单
            order = self.conn['new_order'].find_one({"order_id": order_id, "user_id": user_id})
            if not order:
                return error.error_invalid_order_id(order_id)

            # 检查订单状态是否为未付款 (状态 0)
            if order['status'] != 0:
                return error.error_invalid_order_status(order_id)

            try:
                # 将订单从new_order移动到history_order
                order['status'] = 4  # 设置状态为已取消
                self.conn['history_order'].insert_one(order)
                self.conn['new_order'].delete_one({"order_id": order_id})
                
                # 将订单详情从new_order_detail移动到history_order_detail
                order_details = list(self.conn['new_order_detail'].find({"order_id": order_id}))
                for detail in order_details:
                    self.conn['history_order_detail'].insert_one(detail)
                    
                # 删除new_order_detail中的记录
                self.conn['new_order_detail'].delete_many({"order_id": order_id})
                
                # 从未付款队列中移除订单
                from be.model.times import order_lock
                with order_lock:
                    global unpaid_orders
                    unpaid_orders = [order for order in unpaid_orders if order[0] != order_id]
                    
            except Exception as db_error:
                import logging
                logging.error(f"Database error in cancel_order: {str(db_error)}")
                return 522, "Failed to cancel order"
                
        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in cancel_order: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            
            # 根据错误类型返回适当的错误码
            if "order_id" in str(e).lower():
                return error.error_invalid_order_id(order_id)
            elif "status" in str(e).lower():
                return error.error_invalid_order_status(order_id)
            else:
                return 522, f"Cancel order failed: {str(e)}"

        return 200, "ok"
    
    def auto_cancel(self, order_id: str):
        try:
            # 先检查历史订单集合中的状态
            history_order = self.conn['history_order'].find_one({"order_id": order_id})
            
            if history_order and history_order["status"] == 3:
                # 如果在 history_order 中找到且状态为3，表示已取消成功
                return 200, 'ok'

            # 如果在历史订单中没有找到，再检查新订单集合
            new_order = self.conn['new_order'].find_one({"order_id": order_id})
            if new_order:
                if new_order["status"] == 0:
                    # 使用check_specific_order检查订单是否超时并取消
                    from be.model.times import check_specific_order
                    if check_specific_order(order_id):
                        return 200, 'ok'
                    else:
                        return error.error_not_cancel_order(order_id)
                else:
                    # 订单状态不是0，不能取消
                    return error.error_not_cancel_order(order_id)

            # 如果在两个集合中都找不到订单
            return error.error_missing_order(order_id)

        except Exception as e:
            import traceback
            error_msg = f"Error in auto_cancel: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, "{}".format(str(e))
         
    def recommend_books_one(self, user_id: str, count: int) -> (int, str, list):
        try:
            def _sanitize_books(raw_books):
                sanitized_list = []
                for book in raw_books:
                    if not isinstance(book, dict):
                        continue
                    sanitized = {}
                    for key, value in book.items():
                        if isinstance(value, (ObjectId, Binary)):
                            sanitized[key] = str(value)
                        elif isinstance(value, bytes):
                            try:
                                sanitized[key] = value.decode("utf-8")
                            except UnicodeDecodeError:
                                sanitized[key] = value.decode("utf-8", errors="ignore")
                        elif isinstance(value, datetime):
                            sanitized[key] = value.isoformat()
                        else:
                            sanitized[key] = value
                    sanitized_list.append(sanitized)
                return sanitized_list

            # 检查用户是否存在
            user_exists = self.conn['users'].find_one({"user_id": user_id})
            if not user_exists:
                return 404, "User does not exist", []

            # 第一步：找到当前用户的订单
            user_orders = list(self.conn['history_order'].find({"user_id": user_id}))
            
            # 如果用户没有订单，返回无购买记录
            if not user_orders:
                return 528, "no purchase history", []
                
            # 第二步：找到用户购买过的书籍
            purchased_books = []
            for order in user_orders:
                order_details = list(self.conn['history_order_detail'].find({"order_id": order['order_id']}))
                for detail in order_details:
                    if 'book_id' in detail:
                        purchased_books.append(detail['book_id'])
                    
            # 如果没有购买记录详情，同样返回无购买记录
            if not purchased_books:
                return 528, "no purchase history", []

            # 第三步：根据购买过的书籍推荐相似的书籍
            sample_book = self.conn['books'].find_one({"id": purchased_books[0]})
            if sample_book and 'tags' in sample_book:
                raw_tags = sample_book.get('tags')
                if isinstance(raw_tags, str):
                    tags = [tag.strip() for tag in raw_tags.split(',') if tag.strip()]
                elif isinstance(raw_tags, (list, tuple, set)):
                    tags = [tag for tag in raw_tags if isinstance(tag, str) and tag.strip()]
                else:
                    tags = []

                if tags:
                    # 查找具有相同标签的书籍
                    recommended_books = list(self.conn['books'].find(
                        {"tags": {"$in": tags}, "id": {"$nin": purchased_books}}
                    ).limit(count))

                    # 如果推荐数量不足，补充随机书籍
                    if len(recommended_books) < count:
                        additional_count = count - len(recommended_books)
                        additional_books = list(self.conn['books'].aggregate([
                            {"$match": {"id": {"$nin": purchased_books + [book.get('id', '') for book in recommended_books]}}},
                            {"$sample": {"size": additional_count}}
                        ]))
                        recommended_books.extend(additional_books)

                    return 200, "ok", _sanitize_books(recommended_books)

            # 如果无法基于标签推荐，返回随机推荐
            random_books = list(self.conn['books'].aggregate([
                {"$match": {"id": {"$nin": purchased_books}}},
                {"$sample": {"size": count}}
            ]))
            return 200, "ok", _sanitize_books(random_books)
                
        except Exception as e:
            import logging
            import traceback
            error_msg = f"Error in recommend_books_one: {str(e)}\n{traceback.format_exc()}"
            logging.error(error_msg)
            return 528, "{}".format(str(e)), []
        
    def generate_and_extract_titles(self, txt, model_id='charent/ChatLM-mini-Chinese'):
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        try:
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

            # 使用正则表达式从输出文本中提取书名
            pattern = r'《(.*?)》'
            titles = re.findall(pattern, output_text)
            unique_titles = list(set(titles))  # 去除重复的书名

            # 返回成功状态码和提取的书名
            return 200, unique_titles

        except Exception as e:
            # 如果发生异常，记录错误并返回状态码和错误信息
            logging.error("生成和提取书名时出错: {}".format(str(e)))
            return 528, []
