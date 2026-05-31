-- ============================================================
-- 测试数据：测试用户 + api.business_metrics
-- 用于 PostgREST + OpenClaw 沙箱数据库查询演示
-- 依赖：init.sql 中的 api schema 和 anon/web 角色
-- 用法：psql -U postgres -d openclaw_consultant -f sql/test_data.sql
-- ============================================================

-- 业务指标测试数据
INSERT INTO api.business_metrics VALUES (1, 'api_calls_total', 1250000.00, 'API', '2026-W21', NOW());
INSERT INTO api.business_metrics VALUES (2, 'api_calls_total', 1410000.00, 'API', '2026-W22', NOW());
INSERT INTO api.business_metrics VALUES (3, 'active_users', 8500.00, 'Users', '2026-W21', NOW());
INSERT INTO api.business_metrics VALUES (4, 'active_users', 10100.00, 'Users', '2026-W22', NOW());
INSERT INTO api.business_metrics VALUES (5, 'error_rate_pct', 2.30, 'Quality', '2026-W21', NOW());
INSERT INTO api.business_metrics VALUES (6, 'error_rate_pct', 1.20, 'Quality', '2026-W22', NOW());
INSERT INTO api.business_metrics VALUES (7, 'avg_response_ms', 245.00, 'Performance', '2026-W21', NOW());
INSERT INTO api.business_metrics VALUES (8, 'avg_response_ms', 195.00, 'Performance', '2026-W22', NOW());
INSERT INTO api.business_metrics VALUES (9, 'orders_total', 3200.00, 'Business', '2026-W21', NOW());
INSERT INTO api.business_metrics VALUES (10, 'orders_total', 4100.00, 'Business', '2026-W22', NOW());

SELECT pg_catalog.setval('api.business_metrics_id_seq', 10, true);
