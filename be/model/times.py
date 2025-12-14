from collections import deque
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from be.model.store import resolve_db_url
import os
# 定义全局变量
unpaid_orders = deque()

def _resolve_time_limit_minutes() -> float:
    seconds_env = os.getenv("ORDER_TIME_LIMIT_SECONDS")
    if seconds_env is not None:
        try:
            return float(seconds_env) / 60.0
        except ValueError:
            print(f"[WARN] Invalid ORDER_TIME_LIMIT_SECONDS={seconds_env}, fallback to minutes/default")

    minutes_env = os.getenv("ORDER_TIME_LIMIT_MINUTES")
    if minutes_env is not None:
        try:
            return float(minutes_env)
        except ValueError:
            print(f"[WARN] Invalid ORDER_TIME_LIMIT_MINUTES={minutes_env}, fallback to default")

    return 10.0 / 60.0  # 默认 10 秒

TIME_LIMIT_MINUTES = _resolve_time_limit_minutes()
time_limit = TIME_LIMIT_MINUTES
# 初始化数据库连接
engine = create_engine(resolve_db_url(), echo=True)

def get_time_stamp():
    return datetime.now()

def check_order_time(order_time):
    cur_time = get_time_stamp()
    is_valid = (cur_time - order_time) < timedelta(minutes=time_limit)
    print(f"[DEBUG] Checking order time: current_time={cur_time}, order_time={order_time}, is_valid={is_valid}")
    return is_valid

def cancel_expired_order(order_id):
    try:
        with engine.connect() as conn:
            print(f"[DEBUG] Attempting to cancel order: order_id={order_id}")

            # 查询订单
            query_order = text("SELECT * FROM new_order WHERE order_id = :order_id")
            order = conn.execute(query_order, {"order_id": order_id}).mappings().fetchone()
            print(f"[DEBUG] Queried order: {order}")
            if not order:
                print(f"[DEBUG] Order {order_id} not found in new_order table.")
                return

            # 查询订单详情
            query_order_details = text("SELECT * FROM new_order_detail WHERE order_id = :order_id")
            order_details = conn.execute(query_order_details, {"order_id": order_id}).mappings().fetchall()
            print(f"[DEBUG] Queried order details: {order_details}")

            # 将订单状态设置为 3 并插入到历史订单表
            move_order_to_history = text("""
                INSERT INTO history_order (order_id, store_id, status, user_id, commit_time)
                VALUES (:order_id, :store_id, 3, :user_id, :commit_time)
            """)
            conn.execute(move_order_to_history, {
                "order_id": order["order_id"],
                "store_id": order["store_id"],
                "user_id": order["user_id"],
                "commit_time": order["commit_time"]
            })
            print(f"[DEBUG] Moved order {order_id} to history_order table.")

            # 将订单详情插入到历史订单详情表
            move_order_details_to_history = text("""
                INSERT INTO history_order_detail (_id, book_id, count, order_id, price, sales)
                SELECT _id, book_id, count, order_id, price, 0
                FROM new_order_detail
                WHERE order_id = :order_id
            """)
            conn.execute(move_order_details_to_history, {"order_id": order_id})
            print(f"[DEBUG] Moved order details for {order_id} to history_order_detail table.")

            # 删除新订单表中的订单
            delete_order = text("DELETE FROM new_order WHERE order_id = :order_id")
            conn.execute(delete_order, {"order_id": order_id})
            print(f"[DEBUG] Deleted order {order_id} from new_order table.")

            # 删除新订单详情表中的订单详情
            delete_order_details = text("DELETE FROM new_order_detail WHERE order_id = :order_id")
            conn.execute(delete_order_details, {"order_id": order_id})
            print(f"[DEBUG] Deleted order details for {order_id} from new_order_detail table.")

            # 从未付款订单队列中移除
            global unpaid_orders
            print(f"[DEBUG] Before removing: unpaid_orders={list(unpaid_orders)}")
            unpaid_orders = [order for order in unpaid_orders if order[0] != order_id]
            print(f"[DEBUG] After removing: unpaid_orders={list(unpaid_orders)}")
            
            conn.commit()
            print(f"[DEBUG] Order {order_id} cancelled and moved to history.")
    except Exception as e:
        print(f"[ERROR] Error cancelling expired order {order_id}: {str(e)}")
        conn.rollback()

def time_exceed_delete():
    print(f"[DEBUG] Starting time_exceed_delete: unpaid_orders={list(unpaid_orders)}")
    while unpaid_orders:
        order_id, order_time = unpaid_orders[0]  # 查看队列头部订单
        print(f"[DEBUG] Checking order: order_id={order_id}, order_time={order_time}")
        if check_order_time(order_time):
            print(f"[DEBUG] Order {order_id} has not expired. Stopping check.")
            break  # 如果订单未超时，退出循环
        cancel_expired_order(order_id)
    print(f"[DEBUG] Finished time_exceed_delete: unpaid_orders={list(unpaid_orders)}")