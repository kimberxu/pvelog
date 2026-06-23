# PVE AIOps 智能监控排错系统

> 💡 **提示：这是一个全 vibe coding 项目** (本项目的代码、测试及文档均由 AI 编码助手自主生成与维护)

PVE AIOps 是一个基于大语言模型 (LLM) 和 LangGraph 的 Proxmox VE (PVE) 智能监控与故障排查系统。它包含轻量级的 PVE 节点代理端 (Agent) 和基于 Python 的中心控制端 (Controller)，实现对虚拟化平台的智能日志分析、异常检测和自动化根因诊断。

## 🎯 核心功能

1. **智能日志巡检**: 通过 Go Agent 从 PVE 节点提取 `journalctl` 日志，并在节点本地利用正则进行基础降噪过滤。
2. **中心化 AI 分析引擎**: 基于 Python FastAPI 和 LangGraph，通过大模型能力进行智能日志分析和聚合，自动区分常规系统行为与真正的故障。
3. **安全闭环诊断**: 针对异常情况，中心端可下发指令 (如 Ping、获取 S.M.A.R.T 信息、查询服务状态) 至节点，Agent 以特权沙箱安全执行，防止任意代码执行或注入。
4. **多端告警触达**: 支持通过邮件或企业微信发送分级的异常报告和每日运维总结。

## 📦 架构概览

- **Agent (节点代理端)**:
  - 采用 Go 开发，资源占用低。
  - 直接部署在 PVE 宿主机。
  - 核心模块: 日志收集 (Collector)、加密通信推送 (Pusher)、安全指令执行 (Executor)。
- **Controller (中心控制端)**:
  - 采用 Python 3.11+, 结合 FastAPI 和 LangGraph。
  - 可部署在 Debian 12 的虚拟机或容器中。
  - 核心模块: 指令校验、LangGraph 分析工作流、告警分发、定时任务调度。

## 🚀 部署指南

我们提供了完整的部署手册与自动化脚本，支持通过 Docker Compose (Controller) 和 Shell 脚本 (Agent) 快速拉起服务。

请参考详细部署文档：[部署指南 (Deployment Guide)](docs/deployment.md)

### 快速预览

1. **中心端启动**:
   配置好 `.env` 文件中的 `DB_URL`、`PSK_SECRET` 和 `LLM_API_KEY` 后，执行：
   ```bash
   docker compose up -d
   ```

2. **Agent 节点自动化部署**:
   ```bash
   chmod +x scripts/deploy_agent.sh
   ./scripts/deploy_agent.sh -h <PVE_NODE_IP> -i <NODE_ID> -c <CONTROLLER_URL> -p <YOUR_PSK>
   ```

## ⚙️ 配置说明

系统支持通过环境变量（通常位于 `.env` 文件中）和配置文件自定义各项运行参数。以下是核心配置项及其默认值：

### 中心端 (Controller) 环境配置

| 变量名 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `DB_URL` | 数据库连接字符串 | `sqlite+aiosqlite:///./pve_aiops.db` |
| `PSK_SECRET` | 节点通信的预共享安全密钥 (建议务必修改) | `YOUR_SECURE_PSK_HERE` |
| `LLM_BASE_URL` | 大语言模型 (LLM) 接口地址 | `https://api.openai.com/v1` |
| `LLM_API_KEY` | 大语言模型 API 密钥 | `YOUR_API_KEY_HERE` |
| `LLM_MODEL` | 使用的大语言模型名称 | `deepseek-v3.2` |
| `INSPECT_INTERVAL_SEC`| 定期巡检和系统日志分析的时间间隔（秒） | `3600` |
| `SMTP_SERVER` / `PORT` | 告警邮件 SMTP 服务器地址和端口 | `smtp.example.com` / `465` |
| `SMTP_USERNAME` / `PWD`| 告警邮件 SMTP 登录账号和密码 | `your_email@example.com` / `your_email_password` |
| `EMAIL_FROM` | 告警邮件的发件人地址 | `your_email@example.com` |
| `ALERT_EMAIL_TO` | 告警邮件接收人的地址 | `admin@example.com` |
| `LOG_LEVEL` | 日志级别 (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`；设为 `DEBUG` 时可详细追踪大模型调用细节及 Agent 执行步骤) | `INFO` |

### 节点端 (Agent) 配置 (`agent.yaml`)

节点端可通过配置文件或环境变量进行参数配置。环境变量优先级高于配置文件。

| 配置项 | 对应环境变量 | 说明 | 默认值 |
| :--- | :--- | :--- | :--- |
| `node_id` | `PVE_NODE_ID` | PVE 节点唯一标识 | **必填 (无默认值)** |
| `controller_url` | `PVE_CONTROLLER_URL`| 中心控制端 API 接口地址 | **必填 (无默认值)** |
| `psk_secret` | `PVE_PSK_SECRET` | 预共享安全密钥，需与中心端一致 | **必填 (无默认值)** |
| `collect_interval_sec`| `PVE_COLLECT_INTERVAL_SEC` | Agent 收集并向中心端推送日志的时间间隔（秒） | `300` |
| `filter_patterns` | 无 | 本地日志降噪正则表达式列表 | `[]` (运行时自动从中心端同步) |

## 📊 日志分析与大模型诊断记录查询

系统会自动将大语言模型（LLM）的分析报告、检测出的异常严重程度以及相关 Token 开销持久化到数据库。可以通过以下两种方式进行查询：

### 1. HTTP 接口查询（推荐）
中心端提供便捷的查询接口，便于通过浏览器、Postman 或 curl 获取诊断信息：
* **最近分析列表**（支持通过参数 `node_id` 过滤，以及 `limit` 限制返回条数，默认返回最近 20 条记录）：
  ```bash
  curl http://localhost:42791/api/v1/analysis?limit=10
  ```
* **单条分析报告详情**：
  ```bash
  curl http://localhost:42791/api/v1/analysis/{analysis_id}
  ```

### 2. 数据库直接查询
使用 `sqlite3` 命令直接查询数据库中的 `analysis_records` 表：
```bash
sqlite3 controller/pve_aiops.db "SELECT id, node_id, severity, tool_calls_count, llm_tokens_used, created_at FROM analysis_records ORDER BY created_at DESC LIMIT 5;"
```

## 🔒 安全说明

- **PSK 鉴权**: Agent 和 Controller 间的数据通信使用预共享密钥 (PSK) 进行 HMAC-SHA256 签名校验。
- **权限最小化**: Agent 运行在无登录权限的系统级账户下，并通过特化的 `sudoers` 规则，仅允许无密码执行受限的白名单系统命令。
- **沙箱隔离**: 系统具有针对 LLM 提示词注入的防御机制，所有下发指令均有严格的 Pydantic 校验和 Go 正则校验，避免越权执行。

## 🤝 贡献与反馈

欢迎提交 Issue 和 Pull Request 来完善 PVE AIOps 监控体系。

## 📄 许可证

MIT License
