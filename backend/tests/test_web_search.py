"""web_search 确定性纯函数种子测试。

- `SearchProvider.normalize_result`:strip + 从 url 提 host 到 source。
- `init_search_provider`:未知 provider 名抛 ValueError。

覆盖 SDD 测试模型 ① 后端 Test-First — `web_search.py` 纯函数。
"""

import pytest

from web_search import SearchProvider


def test_normalize_result_strips_and_extracts_host():
    # SearchResult 是 TypedDict,按 key 访问
    r = SearchProvider.normalize_result(
        title="  Hello  ", url="https://example.com/path?q=1", snippet="  body  "
    )
    assert r["title"] == "Hello"
    assert r["url"] == "https://example.com/path?q=1"
    assert r["snippet"] == "body"
    assert r["source"] == "example.com"


def test_normalize_result_handles_none():
    r = SearchProvider.normalize_result(title=None, url=None, snippet=None)
    assert r["title"] == "" and r["url"] == "" and r["snippet"] == "" and r["source"] == ""


def test_init_search_provider_unknown_raises():
    with pytest.raises(ValueError):
        SearchProvider.init_search_provider("definitely-not-a-provider")
