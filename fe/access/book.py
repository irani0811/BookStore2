
import logging
import mysql.connector as mysql
from sqlalchemy import create_engine, text
import json
import os

class Book:
    id: str
    title: str
    author: str
    publisher: str
    original_title: str
    translator: str
    pub_year: str
    pages: int
    price: int
    currency_unit: str
    binding: str
    isbn: str
    author_intro: str
    book_intro: str
    content: str
    tags: list[str]  # 标签是字符串列表
    picture_path: str  # 图片路径作为单一字符串存储

    def __init__(self):
        self.tags = []  # 初始化为空列表
        self.picture = ""  # 初始化为空字符串
        

    def to_dict(self):
        """Convert the Book object to a dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "original_title": self.original_title,
            "translator": self.translator,
            "pub_year": self.pub_year,
            "pages": self.pages,
            "price": self.price,
            "currency_unit": self.currency_unit,
            "binding": self.binding,
            "isbn": self.isbn,
            "author_intro": self.author_intro,
            "book_intro": self.book_intro,
            "content": self.content,
            "tags": self.tags,
            "picture": self.picture,
        }

class BookDB:
    def __init__(self, use_large_db=True):
        try:
            # 默认的 MySQL 数据库配置
            self.host = "xxxx"
            self.port = xxx
            self.user = "root"
            self.password = "xxxxx"
            self.database = "bookstore"

            # print(f"DEBUG: Attempting to connect to MySQL database")
            
            # 建立数据库连接
            self.conn = mysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database
            )
            # print(f"DEBUG: Successfully connected to MySQL database")

        except mysql.Error as e: 
            print(f"ERROR: MySQL connection failed: {str(e)}")
            logging.error(f"MySQL connection error: {e}")
            raise
        except Exception as e: 
            print(f"ERROR: Unexpected error during connection: {str(e)}")
            logging.error(f"Unexpected connection error: {e}")
            raise

    def get_book_count(self):
        try:
            print("DEBUG: Executing get_book_count")
            with self.conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM books")
                row = cursor.fetchone()
                count = row[0] if row else 0
                print(f"DEBUG: Book count result: {count}")
                return count
        except mysql.Error as e: 
            print(f"ERROR: MySQL error in get_book_count: {str(e)}")
            logging.error(f"MySQL error in get_book_count: {e}")
            raise
        except Exception as e: 
            print(f"ERROR: Unexpected error in get_book_count: {str(e)}")
            logging.error(f"Unexpected error in get_book_count: {e}")
            raise

    def get_book_info(self, start: int, size: int) -> [dict]:
        """
        分页获取书籍信息。
        - start: 查询的起始位置 (offset)。
        - size: 查询的数量 (limit)。
        """
        books = []
        try:
            print(f"DEBUG: Executing get_book_info with start={start}, size={size}")
            
            # 构造分页查询 SQL
            query = """
            SELECT id, title, author, publisher, original_title, translator,
                pub_year, pages, price, currency_unit, binding, isbn,
                author_intro, book_intro, content, tags, picture_path
            FROM books
            LIMIT %s OFFSET %s;
            """
            params = (size, start)

            # 执行 SQL 查询
            with self.conn.cursor(dictionary=True) as cursor:
                cursor.execute(query, params)
                results = cursor.fetchall()
                print(f"DEBUG: Fetched {len(results)} books from database")

                # 处理查询结果
                for row in results:
                    book = Book()
                    book.id = row.get("id", "")
                    book.title = row.get("title", "")
                    book.author = row.get("author", "")
                    book.publisher = row.get("publisher", "")
                    book.original_title = row.get("original_title", "")
                    book.translator = row.get("translator", "")
                    book.pub_year = row.get("pub_year", "")
                    book.pages = row.get("pages", 0)
                    book.price = row.get("price", 0)
                    book.currency_unit = row.get("currency_unit", "")
                    book.binding = row.get("binding", "")
                    book.isbn = row.get("isbn", "")
                    book.author_intro = row.get("author_intro", "")
                    book.book_intro = row.get("book_intro", "")
                    book.content = row.get("content", "")

                    # 处理标签
                    tags = row.get("tags", "")
                    if tags:
                        book.tags = [tag.strip() for tag in tags.split(",") if tag.strip()]

                    # 处理图片路径
                    picture_path = row.get("picture_path", "")
                    if picture_path:
                        abs_picture_path = os.path.abspath(picture_path)
                        try:
                            with open(abs_picture_path, "rb") as img_file:
                                book.picture = picture_path
                        except FileNotFoundError: 
                            print(f"DEBUG: Picture file not found for book {book.id}: {abs_picture_path}")
                            book.picture = ""
                        except Exception as e: 
                            print(f"DEBUG: Error loading picture for book {book.id}: {str(e)}")
                            book.picture = ""
                    else:
                        print(f"DEBUG: No picture path for book {book.id}")

                    # 转换为字典并添加到结果列表
                    books.append(book.to_dict())

            print(f"DEBUG: Successfully processed {len(books)} books")
            return books

        except mysql.Error as e: 
            print(f"ERROR: MySQL error in get_book_info: {str(e)}")
            logging.error(f"Error fetching books: {str(e)}")
            return []
        except Exception as e: 
            print(f"ERROR: Unexpected error in get_book_info: {str(e)}")
            logging.error(f"Error fetching books: {str(e)}")
            return []

