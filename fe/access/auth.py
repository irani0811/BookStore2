import requests
from urllib.parse import urljoin


class Auth:
    def __init__(self, url_prefix):
        self.url_prefix = urljoin(url_prefix, "auth/")

    def login(self, user_id: str, password: str, terminal: str) -> (int, str):
        json = {"user_id": user_id, "password": password, "terminal": terminal}
        url = urljoin(self.url_prefix, "login")
        r = requests.post(url, json=json)
        return r.status_code, r.json().get("token")

    def register(self, user_id: str, password: str) -> int:
        json = {"user_id": user_id, "password": password}
        url = urljoin(self.url_prefix, "register")
        r = requests.post(url, json=json)
        return r.status_code

    def password(self, user_id: str, old_password: str, new_password: str) -> int:
        json = {
            "user_id": user_id,
            "oldPassword": old_password,
            "newPassword": new_password,
        }
        url = urljoin(self.url_prefix, "password")
        r = requests.post(url, json=json)
        return r.status_code

    def logout(self, user_id: str, token: str) -> int:
        json = {"user_id": user_id}
        headers = {"token": token}
        url = urljoin(self.url_prefix, "logout")
        r = requests.post(url, headers=headers, json=json)
        return r.status_code

    def unregister(self, user_id: str, password: str) -> int:
        json = {"user_id": user_id, "password": password}
        url = urljoin(self.url_prefix, "unregister")
        r = requests.post(url, json=json)
        return r.status_code
    
    def recommend_books(self, buyer_id: str, n_recommendations: int = 5) -> (int, dict):
        print(buyer_id)
        params = {"buyer_id": buyer_id, "n_recommendations": n_recommendations}
        url = urljoin(self.url_prefix, "recommend_books")
        r = requests.get(url, params=params)  # 使用 params 而不是 json
        return r.status_code, r.json()
    
    def search_book(self, query_text: str, page: int = 1, page_size: int = 10, store_id: str = None):
        url = urljoin(self.url_prefix, "search_book")
        json = {
            "query_text": query_text,  # 查询文本
            "page": page,               # 当前页码
            "page_size": page_size      # 每页的书籍数量
        }
        if store_id is not None:
            json["store_id"] = store_id
        
        r = requests.get(url, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("book_list")
    
    def search_book_regex(self, query_text: str, page: int = 1, page_size: int = 10, store_id: str = None):
        url = urljoin(self.url_prefix, "search_book_regex")
        json = {
            "query_text": query_text,  # 查询文本
            "page": page,               # 当前页码
            "page_size": page_size      # 每页的书籍数量
        }
        if store_id is not None:
            json["store_id"] = store_id
        
        r = requests.get(url, json=json)
        response_json = r.json()
        return r.status_code, response_json.get("book_list")
