import time
import pytest
import random
import uuid

from fe.access import auth
from fe.test.gen_book_data import GenBook
from fe.access.book import BookDB
from fe import conf
from fe.access.new_seller import register_new_seller
from fe.access.new_buyer import register_new_buyer


def test_search_global(search_env):
      code, _ = search_env.auth.search_book_regex(query_text=search_env.title)
      assert code == 200


def test_search_in_store(search_env):
      code, _ = search_env.auth.search_book_regex(
        query_text=search_env.tag,
        store_id=search_env.store_id,
    )
      assert code == 200


def test_search_global_not_exists(search_env):
      code, _ = search_env.auth.search_book_regex(
        query_text="this_is_a_title_that_does_not_exist this_is_a_content_that_does_not_exist"
      )
      assert code == 526


def test_search_not_exist_store_id(search_env):
      code, _ = search_env.auth.search_book_regex(
        query_text=search_env.title,
        store_id="invalid_store_id",
      )
      assert code == 513


def test_search_in_store_not_exist(search_env):
      code, _ = search_env.auth.search_book_regex(
        query_text="this_is_a_title_that_does_not_exist this_is_a_content_that_does_not_exist",
        store_id=search_env.store_id,
      )
      assert code == 526