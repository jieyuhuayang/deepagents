"""可配置的联网搜索 provider 层。

参考 bisheng `bisheng_langchain/gpts/tools/web_search/tool.py` 的三件套模式:
- `SearchProvider` ABC + 子类实现 `_invoke`
- `init_search_provider(name, **kwargs)` 工厂按 dict 路由
- `normalize_result()` 在基类做字段规范化,各子类只需把响应映射成 list

对外只暴露一个工具 `web_search`(在 tools.py),内部按 `SEARCH_PROVIDER` env 选 provider。
新增引擎:加一个子类 + 在 `_REGISTRY` 加一行即可。

设计约束(看似多余的细节,各有原因):
- `max_results` 在 `__init__` 一次性写死,不让 LLM 通过工具参数动态控制。
  历史教训:langchain_tavily 的 forbidden_params 黑名单,invoke 时透传
  `max_results` 会 silent error。同类隐式限制可能出现在任何 provider 上。
  详见 memory/project_tavily_chinese_empty.md。
- Provider 类不依赖 LangChain,纯 Python。包装成 LangChain `@tool` 在 tools.py
  里做(包装层与实现层分离,未来可移植到非 LangChain 框架)。
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import ClassVar, TypedDict
from urllib.parse import urlparse


class SearchResult(TypedDict):
    title: str
    url: str
    snippet: str
    source: str  # 从 url 提取的 host,例如 "github.com"


class SearchProviderError(RuntimeError):
    """provider 层统一异常,屏蔽各 SDK 自带的异常类型差异。"""


class SearchProvider(ABC):
    name: ClassVar[str] = ""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        max_results: int = 5,
        **_: object,
    ) -> None:
        self.base_url = base_url
        self.max_results = max_results

    @abstractmethod
    def _invoke(self, query: str) -> list[SearchResult]:
        """子类实现:调外部 API,把响应映射成规范化的 SearchResult 列表。"""

    def invoke(self, query: str) -> list[SearchResult]:
        """公共入口。统一异常 → SearchProviderError,调用方只 catch 这一个。"""
        try:
            return self._invoke(query)
        except SearchProviderError:
            raise
        except Exception as e:
            raise SearchProviderError(f"{self.name} search failed: {e}") from e

    @staticmethod
    def normalize_result(
        *,
        title: str | None,
        url: str | None,
        snippet: str | None,
    ) -> SearchResult:
        url_str = (url or "").strip()
        host = ""
        if url_str:
            try:
                host = urlparse(url_str).hostname or ""
            except ValueError:
                host = ""
        return SearchResult(
            title=(title or "").strip(),
            url=url_str,
            snippet=(snippet or "").strip(),
            source=host,
        )

    @classmethod
    def init_search_provider(cls, name: str, **kwargs: object) -> SearchProvider:
        if name not in _REGISTRY:
            raise ValueError(
                f"Unknown SEARCH_PROVIDER={name!r}, available: {sorted(_REGISTRY)}"
            )
        return _REGISTRY[name](**kwargs)


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo Instant Answer + HTML scrape(由 langchain_community 封装)。

    无需 API key。base_url 不可覆盖(SDK 不暴露此参数)。高频访问会限流。
    """

    name = "duckduckgo"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        # 延迟 import,让缺依赖时仍能 import 本模块
        from langchain_community.utilities import DuckDuckGoSearchAPIWrapper

        # max_results 必须在实例化时设定,不要在 .results() 里再传一次性参数
        # —— 与 Tavily forbidden_params 同源的"单一可信入口"约束。
        self._client = DuckDuckGoSearchAPIWrapper(max_results=self.max_results)

    def _invoke(self, query: str) -> list[SearchResult]:
        raw = self._client.results(query, max_results=self.max_results)
        return [
            self.normalize_result(
                title=r.get("title"),
                url=r.get("link"),
                snippet=r.get("snippet"),
            )
            for r in raw
        ]


class TavilyProvider(SearchProvider):
    """Tavily 官方 SDK(tavily-python)。

    用原生 SDK 而不是 langchain_tavily,避开后者的 forbidden_params 黑名单坑
    (详见 memory/project_tavily_chinese_empty.md)。需 `TAVILY_API_KEY` env。
    """

    name = "tavily"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        # 延迟 import,SEARCH_PROVIDER=duckduckgo 时不触发 tavily-python 加载
        from tavily import TavilyClient

        api_key = os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise SearchProviderError(
                "TAVILY_API_KEY missing — set it in .env to use SEARCH_PROVIDER=tavily"
            )
        # tavily-python 的 base_url 通过 api_url 参数传(SDK 内部命名)
        client_kwargs: dict[str, object] = {"api_key": api_key}
        if self.base_url:
            client_kwargs["api_url"] = self.base_url
        self._client = TavilyClient(**client_kwargs)

    def _invoke(self, query: str) -> list[SearchResult]:
        # max_results 在 search() 调用时传(tavily-python 的设计,没有
        # forbidden_params 限制,可控)。include_answer 关掉,我们只要原始结果。
        resp = self._client.search(
            query,
            max_results=self.max_results,
            include_answer=False,
        )
        return [
            self.normalize_result(
                title=item.get("title"),
                url=item.get("url"),
                snippet=item.get("content"),
            )
            for item in resp.get("results", [])
        ]


class CloudswayProvider(SearchProvider):
    """Cloudsway Smart Search(searchapi.cloudsway.net)。

    URL 模板:`{base_url}/search/{endpoint}/smart`,Header `Authorization: Bearer {ak}`。
    env 必填:`CLOUDSWAY_ACCESS_KEY` + `CLOUDSWAY_ENDPOINT`。base_url 可覆盖
    走代理或私有部署。响应 schema 见 https://docs.cloudsway.net/IntelliSearch/。
    """

    name = "cloudsway"
    DEFAULT_BASE_URL = "https://searchapi.cloudsway.net"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        access_key = os.environ.get("CLOUDSWAY_ACCESS_KEY")
        endpoint = os.environ.get("CLOUDSWAY_ENDPOINT")
        if not access_key or not endpoint:
            raise SearchProviderError(
                "CLOUDSWAY_ACCESS_KEY / CLOUDSWAY_ENDPOINT missing — "
                "set both in .env to use SEARCH_PROVIDER=cloudsway"
            )
        self._access_key = access_key
        self._endpoint = endpoint
        self.base_url = self.base_url or self.DEFAULT_BASE_URL

    def _invoke(self, query: str) -> list[SearchResult]:
        # httpx 进程级 client 在 tools.py 层不复用(每次新建),但 search 请求频率低,
        # 一次性 client 的连接复用收益不大;keep it simple,每调一次起一个。
        import httpx

        url = f"{self.base_url.rstrip('/')}/search/{self._endpoint}/smart"
        headers = {"Authorization": f"Bearer {self._access_key}"}
        # Cloudsway count 范围 10-50,我们的 max_results 默认 5,clamp 到 10 拿
        # 够后在 Python 层截取(避免上游 422)。
        params = {"q": query, "count": max(self.max_results, 10)}
        resp = httpx.get(url, headers=headers, params=params, timeout=15.0)
        if resp.status_code != 200:
            raise SearchProviderError(
                f"cloudsway HTTP {resp.status_code}: {resp.text[:300]}"
            )
        items = resp.json().get("webPages", {}).get("value", [])
        return [
            self.normalize_result(
                title=item.get("name"),
                url=item.get("url"),
                snippet=item.get("snippet"),
            )
            for item in items[: self.max_results]
        ]


_REGISTRY: dict[str, type[SearchProvider]] = {
    DuckDuckGoProvider.name: DuckDuckGoProvider,
    TavilyProvider.name: TavilyProvider,
    CloudswayProvider.name: CloudswayProvider,
}
