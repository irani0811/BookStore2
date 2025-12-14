import threading
import logging
from pymongo import MongoClient, HASHED
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# 数据库连接锁
_db_lock = threading.RLock()

class Store:
    def __init__(self, db_name="bookstore"):
        # 连接 MongoDB 数据库
        try:
            # 添加连接超时和池大小配置
            self.client = MongoClient(
                'localhost', 
                27017, 
                serverSelectionTimeoutMS=5000,  # 5秒超时
                maxPoolSize=100,  # 最大连接池大小
                waitQueueTimeoutMS=5000,  # 等待队列超时
                connectTimeoutMS=5000  # 连接超时
            )
            # 测试连接
            self.client.admin.command('ismaster')
            self.db = self.client[db_name]
            self.init_collections()  # 初始化集合
            logging.info("MongoDB connection established successfully")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logging.error(f"Could not connect to MongoDB: {e}")
            raise

    def init_collections(self):
        collection = self.db['new_order_detail']
        existing_indexes = collection.index_information()
        if 'order_id_1' in existing_indexes:
            collection.drop_index('order_id_1')
        collection.create_index([('order_id', 1), ('book_id', 1)], unique=True)
        # 为用户、订单、书籍集合等添加索引
        self.db['users'].create_index("user_id", unique=True)
        self.db['stores'].create_index([("store_id", 1), ("books.book_id", 1)], unique=True)
        self.db['new_order'].create_index("order_id", unique=True)
        self.db['new_order_detail'].create_index([("order_id", 1), ("book_id", 1)], unique=True)
        self.db['new_books'].create_index("book_id", unique=True)
        self.db['history_order'].create_index("order_id", unique=True)
        self.db['history_order_detail'].create_index([("order_id", 1), ("book_id", 1)], unique=True)
            
        # 为 books 集合中的文本字段创建复合文本索引
        self.db['books'].create_index(
            [("title", "text"), ("tags", "text"), ("book_intro", "text"), ("author_intro", "text"), ("author", "text"), ("content", "text")],
            weights={"title": 10, "tags": 5, "book_intro": 3, "author_intro": 3, "author": 2, "content": 1}
        )
        
        # 为 books 集合中的 id 字段创建哈希索引
        self.db['books'].create_index([("id", HASHED)])

    def get_db(self):
        return self.db


database_instance: Store = None

# 全局事件用于同步
init_completed_event = threading.Event()

def init_database(db_name="bookstore"):
    db_name = "bookstore"  
    global database_instance
    database_instance = Store(db_name)


def get_db_conn():
    """线程安全地获取数据库连接"""
    global database_instance
    with _db_lock:
    # 如果数据库实例不存在，初始化它
        if database_instance is None:
            init_database()
        try:
        # 测试连接是否有效
            database_instance.client.admin.command('ping')
        except Exception as e:
            logging.error(f"Database connection error: {e}. Attempting to reconnect...")
            # 尝试重新连接
            init_database()
        return database_instance.get_db()

