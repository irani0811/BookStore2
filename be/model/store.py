
import os
import threading
from sqlalchemy import create_engine, text


DEFAULT_DB_URL = "mysql+pymysql://root:WXRrr20050811@172.25.139.100/bookstore"


def resolve_db_url(custom_url=None):
    """
    返回有效的数据库连接 URL，优先使用传入值，其次是环境变量，最后使用默认值。
    """
    if custom_url:
        return custom_url
    return os.getenv("BOOKSTORE_DB_URL", DEFAULT_DB_URL)


class Store:
    def __init__(self, db_url=None):
        db_url = resolve_db_url(db_url)
        # 连接 MySQL 数据库
        self.engine = create_engine(db_url, connect_args={'connect_timeout': 60, 'read_timeout': 60, 'write_timeout': 60})
        self.init_tables()  # 初始化表结构

    def init_tables(self):
        with self.engine.connect() as conn:
            # 创建 users 表
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS users (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(255) NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    balance INT DEFAULT 0,
                    token TEXT,
                    terminal VARCHAR(255)
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS stores (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    store_id VARCHAR(255),
                    user_id VARCHAR(255),
                    book_id VARCHAR(255),
                    price DECIMAL(10, 2),
                    stock_level INT,
                    UNIQUE (store_id, book_id)
                );
            """))
            
            

            # 创建 new_order 表
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS new_order (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    commit_time DATETIME,
                    order_id VARCHAR(255),
                    status INT,
                    store_id VARCHAR(255),
                    user_id VARCHAR(255)
                );
            """))

            # 创建 new_order_detail 表
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS new_order_detail (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    book_id VARCHAR(255),
                    count INT,
                    order_id VARCHAR(255),
                    price DECIMAL(10, 2)
                );
            """))

            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS new_books (
                _id INT AUTO_INCREMENT PRIMARY KEY,
                book_id VARCHAR(255),
                tags TEXT,
                pictures_path TEXT,
                title TEXT,
                author TEXT,
                publisher TEXT,
                original_title TEXT,
                translator TEXT,
                pub_year VARCHAR(16),
                pages INT,
                price INT,
                currency_unit VARCHAR(10),
                binding TEXT,
                isbn VARCHAR(20),
                author_intro TEXT,
                book_intro TEXT,
                content TEXT
            );
                        """))
            

            # 创建 history_order 表
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS history_order (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    commit_time DATETIME,
                    order_id VARCHAR(255),
                    status INT,
                    store_id VARCHAR(255),
                    user_id VARCHAR(255)
                );
            """))

            # 创建 history_order_detail 表
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS history_order_detail (
                    _id INT AUTO_INCREMENT PRIMARY KEY,
                    book_id VARCHAR(255),
                    count INT,
                    order_id VARCHAR(255),
                    price DECIMAL(10, 2),
                    sales INT
                );
            """))


            # 检查并创建 users 表索引
            if not self.index_exists(conn, "users", "idx_users_user_id"):
                conn.execute(text("CREATE UNIQUE INDEX idx_users_user_id ON users (user_id);"))

            # 检查并创建 stores 表索引
            if not self.index_exists(conn, "stores", "unique_store_user_book"):
                conn.execute(text("""
                    CREATE UNIQUE INDEX unique_store_user_book 
                    ON stores (store_id, user_id, book_id);
                """))

            # 检查并创建 new_order 表索引
            if not self.index_exists(conn, "new_order", "idx_new_order_order_id"):
                conn.execute(text("CREATE UNIQUE INDEX idx_new_order_order_id ON new_order (order_id);"))

            # 检查并创建 new_order_detail 表索引
            if not self.index_exists(conn, "new_order_detail", "idx_new_order_detail_order_id_book_id"):
                conn.execute(text("CREATE UNIQUE INDEX idx_new_order_detail_order_id_book_id ON new_order_detail (order_id, book_id);"))

            # 检查并创建 history_order 表索引
            if not self.index_exists(conn, "history_order", "idx_history_order_order_id"):
                conn.execute(text("CREATE UNIQUE INDEX idx_history_order_order_id ON history_order (order_id);"))

            # 检查并创建 history_order_detail 表索引
            if not self.index_exists(conn, "history_order_detail", "idx_history_order_detail_order_id_book_id"):
                conn.execute(text("CREATE UNIQUE INDEX idx_history_order_detail_order_id_book_id ON history_order_detail (order_id, book_id);"))

            # 检查并创建 new_books 表全文索引
            if not self.index_exists(conn, "new_books", "idx_new_books_title_tags"):
                conn.execute(text("""
                    CREATE FULLTEXT INDEX idx_new_books_title_tags 
                    ON new_books (title, tags);
                """))

    def index_exists(self, conn, table_name, index_name):
        """
        检查某张表是否存在指定的索引
        """
        query = text(f"""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.STATISTICS
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = :table_name
            AND INDEX_NAME = :index_name;
        """)
        result = conn.execute(query, {"table_name": table_name, "index_name": index_name}).scalar()
        return result > 0

    def get_db(self):
        return self.engine


# 全局实例和同步
database_instance: Store = None
init_completed_event = threading.Event()


def init_database(db_url=None):
    global database_instance
    database_instance = Store(resolve_db_url(db_url))


def get_db_conn():
    global database_instance
    return database_instance.get_db()

