# Bookstore 2.0

Bookstore 2.0是一个基于 Flask + MySQL 的线上书店后端，实现了课程要求的 60% 基础功能，并在此基础上扩展发货/收货闭环、全文检索、自动化订单管理、推荐系统与书名提取器等高级能力。系统通过 127 条 pytest 用例和 bench/JMeter 压测验证，在 128 并发下单/支付延迟约 0.3s/0.4s，整体覆盖率 96%。

---

## ✨ 功能总览

| 模块 | 功能点 | 说明 |
|------|--------|------|
| 用户 & 认证 | 注册 / 登录 / 登出 / 改密 / 充值 | PyJWT 鉴权、SQLAlchemy 事务保护余额更新 |
| 买家流程 | 下单 → 支付 → 查询 → 取消 | `new_*` → `history_*` 生命周期管理，库存/余额原子更新 |
| 卖家流程 | 创建店铺 / 上架图书 / 补货 / 发货 / 收货 | `stores` 冗余书籍信息，发货状态机覆盖越权与异常 |
| 附加功能 | 发货-收货闭环、全文搜索、订单自动取消 | APScheduler 定时任务、FULLTEXT + Jaccard 搜索 |
| 智能能力 | 书名提取器、双引擎推荐系统 | ChatLM-mini-Chinese + 正则抽取书名；共现 & 协同过滤推荐 |
| 质量保障 | Pytest + Coverage + Bench + JMeter | 127 条用例、96% 覆盖率、TPS_C≈3.1k req/s |

---

## 🏗️ 架构与目录

```
bookstore/
├── be/                # 后端：Flask + SQLAlchemy
│   ├── model/         # 业务实现（buyer/seller/recommend/...）
│   ├── view/          # REST API 路由
│   └── serve.py       # APScheduler、应用入口
├── fe/                # 测试与脚本
│   ├── access/        # HTTP 客户端封装
│   ├── bench/         # 性能测试脚本
│   ├── data/          # 导入数据与工具
│   └── test/          # pytest 用例（用户/买家/卖家/附加功能）
├── script/            # 运行、日志脚本
├── requirements.txt
└── README.md
```

关键技术栈：

- **后端**：Flask 2.x、SQLAlchemy、PyJWT、APScheduler  
- **数据库**：MySQL 8.0（InnoDB），FULLTEXT + 组合索引  
- **工具链**：pytest、coverage、bench、JMeter、Git

---

## 🚀 快速开始

### 1. 环境准备
- Python 3.11+
- MySQL 8.0（确保已创建目标数据库并具备写入权限）

```bash
git clone <repo>
cd bookstore
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 导入基础数据

```bash
# 将 SQLite 中的图书数据迁移到 MySQL
python fe/data/create_table.py \
  --sqlite fe/data/book.db \
  --mysql-url mysql+pymysql://user:password@localhost:3306/bookstore
```

常用环境变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `BOOKSTORE_DB_URI` | SQLAlchemy 连接串 | `mysql+pymysql://user:pwd@127.0.0.1:3306/bookstore` |
| `BOOKSTORE_ENABLE_PICTURE_EXPORT` | 是否导出封面图片 | `0`（默认不落盘） |

### 3. 启动后端

```bash
export FLASK_APP=be.serve  # Windows 使用 set
flask run --host 0.0.0.0 --port 5000
```

APScheduler 会在启动时注册订单超时检查等后台任务。

### 4. 运行测试

```bash
pytest fe/test -n auto                 # 127 条单元 / 集成测试
coverage run -m pytest fe/test && coverage html  # 生成 96% 覆盖率
python fe/bench/run.py                 # bench 下单/支付压测
sh script/test_log.sh                  # JMeter 结果解析（可选）
```

---

## 🔍 主要接口

| 角色 | 路径 | 描述 |
|------|------|------|
| 用户 | `POST /auth/register` / `login` / `logout` / `change_password` / `add_funds` | JWT 鉴权、余额管理 |
| 买家 | `POST /buyer/new_order` / `payment` / `cancel_order`、`GET /buyer/query_order` | 订单全流程 |
| 卖家 | `POST /seller/create_store` / `add_book` / `add_stock_level` / `delivery_order` / `receive_order` | 店铺维护与发货收货 |
| 搜索 | `GET /buyer/search_books` | FULLTEXT + 模糊搜索、分页 |
| 推荐 | `GET /buyer/recommend_books`、`/recommend_books_v2` | 共现 & 协同过滤 |
| 智能 | `POST /buyer/extract_title` | 书名提取器（ChatLM-mini-Chinese） |

更多细节请参考 `bookstore2报告.md` 或 `be/view/*.py`。

---

## 🧪 测试与性能

- **功能测试**：127 条 pytest 用例覆盖用户、买家、卖家、推荐、搜索、发货、自动取消等场景，覆盖率 96%。  
- **性能压测**：bench 脚本展示 TPS_C≈3.1k req/s；JMeter 对比显示 MySQL 版本吞吐量 ~10k req/s，显著优于 MongoDB 基线。  
- **监控 & 日志**：关键事务、自动任务、推荐服务均输出结构化日志到 `logs/`，便于回溯。

---

## 👥 分工

| 成员 | 学号 | 负责内容 | 占比 |
|------|------|----------|:----:|
| 吴彤 | 10222140442 | 用户/买家核心接口、推荐系统、性能测试与覆盖率统计 | 50% |
| 王惜冉 | 10235501401 | 发货/搜索/自动取消等附加功能、MySQL 迁移、书名提取器、报告与 README | 50% |

---

## 📚 参考资料

- [MySQL 官方文档](https://dev.mysql.com/doc/)  
- [SQLAlchemy](https://docs.sqlalchemy.org/)  
- [Flask](https://flask.palletsprojects.com/)  
- [PyJWT](https://pyjwt.readthedocs.io/)  
- [JMeter](https://jmeter.apache.org/)


