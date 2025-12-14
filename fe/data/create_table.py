import os
import re
import sqlite3
import pandas as pd
from sqlalchemy import create_engine, text
from tqdm import tqdm

SQLITE_DB_PATH = "F:/database/ref/xqh/bookstore2代码/bookstore/fe/data/book.db"
DEFAULT_MYSQL_URL = "mysql+pymysql://root:WXRrr20050811@172.25.139.100/bookstore"
MYSQL_URL = os.getenv("BOOKSTORE_DB_URL", DEFAULT_MYSQL_URL)
TABLE_NAME = "books"
PICTURE_FOLDER = "F:/database/ref/xqh/bookstore2代码/bookstore/fe/data/pictures"


def _str_to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


CLEAR_BEFORE_IMPORT = _str_to_bool(os.getenv("BOOKSTORE_CLEAR_BEFORE_IMPORT"), default=True)
# 控制是否清空测试相关表（new_books、stores 等）以保证用例环境干净。
CLEAR_TEST_TABLES = _str_to_bool(os.getenv("BOOKSTORE_CLEAR_TEST_TABLES"), default=True)
# 通过 BOOKSTORE_ENABLE_PICTURE_EXPORT 控制是否导出图片；默认关闭，防止本地落盘。
EXPORT_PICTURES = _str_to_bool(os.getenv("BOOKSTORE_ENABLE_PICTURE_EXPORT"), default=False)

if EXPORT_PICTURES:
    os.makedirs(PICTURE_FOLDER, exist_ok=True)

def save_picture_to_filesystem(book_id, picture_data):
    if not picture_data:
        return None
    picture_path = os.path.join(PICTURE_FOLDER, f"{book_id}.jpg")
    try:
        with open(picture_path, "wb") as file:
            file.write(picture_data)
        return picture_path
    except Exception as e:
        print(f"Error saving picture for book ID {book_id}: {e}")
        return None

def clear_table(mysql_engine, table_name):
    """
    清空目标表中的数据
    """
    with mysql_engine.begin() as conn:
        try:
            conn.execute(text(f"TRUNCATE TABLE {table_name}"))
            print(f"表 {table_name} 已清空（TRUNCATE）")
        except Exception as truncate_err:
            print(f"TRUNCATE 失败（{truncate_err}），改用 DELETE 清空（{truncate_err}）")
            conn.execute(text(f"DELETE FROM {table_name}"))
            print(f"表 {table_name} 已清空（DELETE）")


def transfer_data(sqlite_db_path, mysql_url, table_name, clear_existing=False):
    """
    从 SQLite 导入数据到 MySQL，并处理图片存储
    """
    # 连接 SQLite 和 MySQL
    sqlite_conn = sqlite3.connect(sqlite_db_path)
    mysql_engine = create_engine(mysql_url)

    # 创建目标表结构
    with mysql_engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id VARCHAR(255) PRIMARY KEY,
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
                content TEXT,
                tags TEXT,
                picture_path TEXT
            );
        """))
        try:
            conn.execute(text(f"ALTER TABLE {table_name} MODIFY pub_year VARCHAR(16);"))
        except Exception as alter_err:
            print(f"Warning: unable to ensure pub_year length ({alter_err})")
    if clear_existing:
        clear_table(mysql_engine, table_name)

    if CLEAR_TEST_TABLES:
        for extra_table in ["new_books", "stores", "users", "new_order", "new_order_detail", "history_order", "history_order_detail"]:
            try:
                clear_table(mysql_engine, extra_table)
            except Exception as clear_err:
                print(f"Warning: failed to clear {extra_table}: {clear_err}")

    # 从 SQLite 分块读取数据
    query = "SELECT * FROM book"
    for chunk in tqdm(pd.read_sql_query(query, sqlite_conn, chunksize=1000), desc="导入数据"):
        processed_data = []
        for _, row in chunk.iterrows():
            row_dict = row.to_dict()
            picture_data = row_dict.pop("picture", None)
            if EXPORT_PICTURES:
                picture_path = save_picture_to_filesystem(row_dict["id"], picture_data)
                row_dict["picture_path"] = picture_path or ""
            else:
                row_dict["picture_path"] = ""
            processed_data.append(row_dict)

        # 将处理后的数据转为 DataFrame
        processed_df = pd.DataFrame(processed_data)

        # **调试信息：打印即将插入的数据**
        print("Sample data to be inserted:")
        print(processed_df.head())

        # 插入数据到 MySQL
        with mysql_engine.begin() as conn:
            for _, row in processed_df.iterrows():
                try:
                    insert_query = text(f"""
                        INSERT INTO {table_name} (
                            id, title, author, publisher, original_title, translator, 
                            pub_year, pages, price, currency_unit, binding, isbn, 
                            author_intro, book_intro, content, tags, picture_path
                        ) VALUES (
                            :id, :title, :author, :publisher, :original_title, :translator,
                            :pub_year, :pages, :price, :currency_unit, :binding, :isbn,
                            :author_intro, :book_intro, :content, :tags, :picture_path
                        )
                    """)
                    conn.execute(insert_query, row.to_dict())
                    print(f"Inserted ID: {row['id']}")  # **调试信息：记录已插入的 ID**
                except Exception as e:
                    print(f"Skipping problematic entry for ID {row['id']}: {e}")  # **调试信息：异常记录**

    # 关闭连接
    sqlite_conn.close()
    with mysql_engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        total_books = result.scalar() or 0
        print(f"当前 {table_name} 表共 {total_books} 条记录")


if __name__ == "__main__":
    transfer_data(SQLITE_DB_PATH, MYSQL_URL, TABLE_NAME, clear_existing=CLEAR_BEFORE_IMPORT)
