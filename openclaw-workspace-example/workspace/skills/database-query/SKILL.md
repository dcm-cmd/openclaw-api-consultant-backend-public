---
name: database-query
description: 通过 RESTful API 查询 PostgreSQL 数据库中的业务指标数据，进行分析并生成中文回复。
---

# 数据库查询

当用户询问数据分析、指标查询、趋势变化等问题时，使用本 skill。

## 查询方式

沙箱中已预置 Python 脚本 `/scripts/query_db.py`，通过 PostgREST API 查询数据库。

用法：

```
python3 /scripts/query_db.py <metric> [--category CAT] [--limit N]
```

示例：
- 查询订单量：`python3 /scripts/query_db.py orders_total`
- 查询 API 调用量：`python3 /scripts/query_db.py api_calls_total`
- 按类别过滤：`python3 /scripts/query_db.py --category API`

## 数据库资源

| 表 | 字段 |
|---|---|
| business_metrics | id, metric_name, metric_value, category, period, recorded_at |

## 执行规则

1. 只允许执行 `python3 /scripts/query_db.py`，不能执行其他命令
2. 结果以 JSON 返回，分析后生成中文回答
3. 回答时不要暴露 SQL、API URL、数据库连接信息
4. 如果查询失败，不要透露内部错误细节，请用户稍后重试
