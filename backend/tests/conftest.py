"""pytest 公共 fixture / 环境准备。

关键:在任何测试模块 import `server` / `agent` 之前设好环境——
- `agent.py` 模块级 `model = ChatOpenAI(api_key=os.environ["DASHSCOPE_API_KEY"], ...)`
  要求 key 存在(dummy 即可,构造不发网络请求);
- `server.py` lifespan 用 `DATABASE_URL` 选 saver,测试指向临时 SQLite,绝不碰 local.db。

conftest 在收集测试前先被导入,故此处设环境对后续 import 生效。
"""

import os
import tempfile

# dummy key:ChatOpenAI 构造期不发请求,仅满足 os.environ 读取
os.environ.setdefault("DASHSCOPE_API_KEY", "test-dummy-key")

# 临时 SQLite,避免污染 backend/local.db
_tmp_db = os.path.join(tempfile.gettempdir(), "deepagents_pytest.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmp_db}")
