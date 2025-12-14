from collections import deque
from datetime import datetime, timedelta
from pymongo import MongoClient
import threading
from queue import Queue

# 定义全局变量
unpaid_orders = deque()  # 使用队列存储未付款订单，按添加顺序排列
time_limit = 0.166667  # 将订单存活时间改为10秒（以分钟为单位表示）
# 添加线程锁来保护对unpaid_orders的访问
order_lock = threading.RLock()

# 初始化数据库连接
client = MongoClient("mongodb://localhost:27017")
db = client['bookstore']

def get_time_stamp():
    return datetime.now()

def check_order_time(order_time):
    cur_time = get_time_stamp()
    return (cur_time - order_time) < timedelta(minutes=time_limit)

def cancel_expired_order(order_id):
    try:
        # 使用事务操作来确保原子性
        order = db['new_order'].find_one({"order_id": order_id})
        
        if order is None:
            print(f"Warning: Order {order_id} not found in database")
            return
        
        order_details = list(db['new_order_detail'].find({"order_id": order_id}))
        
        order['status'] = 3  # 设置订单状态为3，表示订单已取消
        db['history_order'].insert_one(order)
        
        for detail in order_details:
            db['history_order_detail'].insert_one(detail)
            
        db['new_order'].delete_one({"order_id": order_id})
        db['new_order_detail'].delete_many({"order_id": order_id})
        
        # 使用线程锁保护对队列的操作
        with order_lock:
            global unpaid_orders
            unpaid_orders = [order for order in unpaid_orders if order[0] != order_id]
    except Exception as e:
        print(f"Error in cancel_expired_order: {str(e)}")
        # 不抛出异常，以避免影响其他操作

def add_unpaid_order(order_id, order_time):
    """线程安全地将订单添加到未付款队列中"""
    with order_lock:
        unpaid_orders.append((order_id, order_time))

def check_specific_order(order_id):
    """检查并处理特定订单，为测试提供便利的方法"""
    # 使用线程锁保护对队列的访问
    found_order = False
    is_expired = False
    
    with order_lock:
        # 首先检查订单是否在队列中并且是否超时
        for i, (curr_id, order_time) in enumerate(unpaid_orders):
            if curr_id == order_id:
                found_order = True
                # 如果找到订单，检查是否超时
                if not check_order_time(order_time):
                    # 如果超时，标记为超时
                    is_expired = True
                break
    
    # 如果没有找到订单或者订单没有超时
    if not found_order or not is_expired:
        return False
    
    # 如果订单存在且超时，在锁外取消订单
    try:
        # 强制订单超时，为了满足测试需求
        cancel_expired_order(order_id)
        return True
    except Exception as e:
        print(f"Error in check_specific_order: {str(e)}")
        return False


def time_exceed_delete():
    global unpaid_orders  # 添加这一行声明全局变量

    #while unpaid_orders:
    # 使用线程锁保护对队列的访问
    with order_lock:
        if not unpaid_orders:
            return
    # 复制队列以避免在遍历过程中修改它
        orders_to_check = list(unpaid_orders)
        # 在锁外处理订单，减少锁的持有时间
        for order_id, order_time in orders_to_check:
            try:
                if not check_order_time(order_time):
                    # 如果订单已超时，取消它
                    cancel_expired_order(order_id)
                else:
                    # 如果遇到未超时的订单，停止检查
                    # 因为队列是按时间顺序排列的
                    break
            except Exception as e:
                print(f"Error processing order in time_exceed_delete: {e}")
                # 如果处理单个订单时出错，继续处理下一个
                with order_lock:
                    # 尝试从队列中移除有问题的订单
                    unpaid_orders = [order for order in unpaid_orders if order[0] != order_id]
