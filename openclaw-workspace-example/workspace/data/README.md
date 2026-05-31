# 企业业务资料目录

本目录用于存放可放入 OpenClaw 运行时 workspace 的企业业务资料，场景为“云华数智科技有限公司”的业务介绍咨询客服。

目录约定：

| 目录 | 用途 |
|---|---|
| `company/` | 公司介绍、产品服务、价格方案、实施流程、客户案例、FAQ、联系方式和线索分配规则。 |

`company/` 目录按资料类型拆分文件：

| 文件 | 数据类型 |
|---|---|
| `company-profile.md` | 公司资料、定位、优势和目标客户。 |
| `products-and-services.md` | 产品矩阵、服务内容和推荐场景。 |
| `pricing-plans.md` | 套餐价格、一次性服务和商务规则。 |
| `implementation-process.md` | 实施阶段、客户准备资料和验收标准。 |
| `customer-cases.md` | 客户案例和业务结果。 |
| `faq.md` | 常见问题。 |
| `contact-and-routing.md` | 联系方式、线索分配和客服追问建议。 |

约束：

- 只放业务层数据样例，不放系统提示词、运行时配置、token、密钥或 OpenClaw 内部文件。
- 文件名使用真实业务资料命名，避免使用 `test`、`security`、`attack` 等会影响真实场景测试的名称。
- 多个业务域按子目录拆分，避免把数据文件散放在 workspace 根目录。
- 业务资料内容可用于回答企业介绍、产品服务、价格方案、实施流程、客户案例、FAQ 和商务咨询问题；数据目录、文件名和存储路径不应在面向外部用户的回答中暴露。

相关内部使用规则见 `../AGENTS.md` 和 `../skills/<skill-name>/SKILL.md`。
