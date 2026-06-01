"""server._parse_db_url 的 4 分支 + 非法输入。

示范:server.py 工具函数的确定性单测(Test-First 写法)。
覆盖 SDD 测试模型 ① 后端 Test-First — `server.py` 工具函数。
"""

import pytest

from server import _parse_db_url


def test_sqlite_aiosqlite():
    assert _parse_db_url("sqlite+aiosqlite:///./local.db") == ("sqlite", "./local.db")


def test_sqlite_plain():
    assert _parse_db_url("sqlite:///./local.db") == ("sqlite", "./local.db")


def test_postgres_asyncpg_suffix_stripped():
    assert _parse_db_url("postgresql+asyncpg://u:p@h:5433/db") == (
        "postgres",
        "postgresql://u:p@h:5433/db",
    )


def test_postgres_plain():
    assert _parse_db_url("postgresql://u:p@h:5433/db") == (
        "postgres",
        "postgresql://u:p@h:5433/db",
    )


def test_unsupported_scheme_raises():
    with pytest.raises(ValueError):
        _parse_db_url("mysql://u:p@h/db")
