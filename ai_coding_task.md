# PVE AIOps 智能监控排错系统：AI 编程实施任务书

> **文档说明**：本文档为纯技术规范与任务拆解书，移除了所有的评估与探讨，仅保留明确的架构、API 契约、数据结构、安全红线及分步实施清单。**作为 AI 编程助手，请在开发时严格遵循本文档的约束进行代码编写。**

---

## 0. 项目元信息

```yaml
项目名称: pve-aiops
仓库结构: monorepo
开发语言:
  中心控制端: Python 3.11+
  PVE 节点代理: Go 1.22+
核心依赖:
  Python: fastapi, uvicorn, langgraph, httpx, pydantic, sqlalchemy, aiosqlite
  Go: 标准库为主 (net/http, os/exec, crypto/tls, encoding/json)
部署目标:
  中心端: Debian 12 VM 或 LXC (2C/2G 即可)
  Agent: Proxmox VE 8.x 宿主机 (Debian 12 based)
```

## 1. 项目目录结构

```
pve-aiops/
├── controller/                    # 中心控制端 (Python)
│   ├── pyproject.toml             # Python 项目配置 (使用 uv 或 poetry)
│   ├── config/
│   │   ├── settings.py            # Pydantic Settings, 读取环境变量
│   │   ├── prompts.py             # 所有 LLM Prompt 模板
│   │   └── allowed_actions.py     # Tool Call 白名单定义
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                # FastAPI 入口, 注册路由
│   │   ├── routes/
│   │   │   ├── log_ingest.py      # POST /api/v1/logs  日志接收
│   │   │   ├── heartbeat.py       # POST /api/v1/heartbeat  心跳
│   │   │   └── admin.py           # GET /api/v1/status  管理接口
│   │   └── middleware/
│   │       ├── auth.py            # PSK / mTLS 认证中间件
│   │       └── rate_limit.py      # 速率限制
│   ├── core/
│   │   ├── analyzer.py            # LangGraph 多轮决策引擎
│   │   ├── tool_dispatcher.py     # 安全指令分发器 (向 Agent 发送诊断请求)
│   │   ├── tool_validator.py      # Tool Call 参数校验器 (Schema 验证 + 白名单)
│   │   ├── log_sanitizer.py       # 日志消毒 (Anti Prompt Injection)
│   │   └── alert_manager.py       # 告警管理 (去重/冷却/分发)
│   ├── db/
│   │   ├── models.py              # SQLAlchemy ORM 模型
│   │   ├── database.py            # 数据库连接与初始化
│   │   └── migrations/            # Alembic 数据库迁移
│   ├── services/
│   │   ├── llm_client.py          # LLM API 封装 (重试/超时/降级)
│   │   ├── email_service.py       # 邮件发送
│   │   └── wechat_service.py      # 微信推送 (可选)
│   ├── scheduler/
│   │   └── tasks.py               # 定时任务 (分析调度、日报生成、数据清理)
│   └── tests/
│       ├── test_tool_validator.py
│       ├── test_log_sanitizer.py
│       └── test_analyzer.py
│
├── agent/                         # PVE 节点代理 (Go)
│   ├── go.mod
│   ├── go.sum
│   ├── cmd/
│   │   └── pve-agent/
│   │       └── main.go            # 入口: 启动日志推送 + 指令监听
│   ├── internal/
│   │   ├── config/
│   │   │   └── config.go          # 配置加载 (YAML 文件 + 环境变量)
│   │   ├── collector/
│   │   │   ├── journald.go        # journalctl 日志读取 (增量)
│   │   │   ├── filter.go          # 本地正则预过滤 (Token 防御层)
│   │   │   └── dedup.go           # 日志去重
│   │   ├── pusher/
│   │   │   └── http_pusher.go     # HTTPS 推送日志到中心端
│   │   ├── executor/
│   │   │   ├── handler.go         # HTTP 服务: 接收中心端诊断请求
│   │   │   ├── actions.go         # 安全动作注册表 (硬编码白名单)
│   │   │   ├── validator.go       # 参数正则校验
│   │   │   └── sandbox.go         # os/exec 安全封装 (超时/资源限制)
│   │   ├── heartbeat/
│   │   │   └── heartbeat.go       # 心跳发送
│   │   └── auth/
│   │       └── psk.go             # PSK 认证 (请求签名)
│   ├── configs/
│   │   └── agent.yaml             # Agent 配置文件模板
│   ├── deploy/
│   │   ├── pve-agent.service      # systemd unit file
│   │   └── sudoers.d/pve-agent    # sudoers 精确授权规则
│   └── tests/
│       ├── actions_test.go
│       ├── validator_test.go
│       └── sandbox_test.go
│
├── docs/
│   ├── architecture.md            # 架构文档
│   ├── security.md                # 安全设计文档
│   └── deployment.md              # 部署指南
│
├── scripts/
│   ├── generate_certs.sh          # mTLS 证书生成脚本
│   └── deploy_agent.sh            # Agent 分发部署脚本
│
└── docker-compose.yml             # 中心端开发环境 (可选)
```

---

## 2. 数据结构与 API 契约

### 2.1 日志推送接口
`POST /api/v1/logs`

**请求 Header**:
```
Content-Type: application/json
X-Node-ID: pve-node-01
X-Timestamp: 1719000000
X-Signature: HMAC-SHA256(node_id + timestamp + body, PSK)
```

**请求 Body (JSON)**:
```json
{
  "node_id": "pve-node-01",
  "hostname": "songyuan",
  "batch_id": "uuid-v4",
  "since_cursor": "__CURSOR=s=abc123...",
  "entries": [
    {
      "timestamp": "2026-06-21T10:00:01+08:00",
      "priority": 3,
      "unit": "corosync.service",
      "message": "Totem NACK received..."
    }
  ],
  "entry_count": 150,
  "filtered_count": 1200,
  "agent_version": "0.1.0"
}
```

### 2.2 心跳接口
`POST /api/v1/heartbeat`

**请求 Body**:
```json
{
  "node_id": "pve-node-01",
  "hostname": "songyuan",
  "uptime_seconds": 86400,
  "agent_version": "0.1.0",
  "cpu_usage_percent": 12.5,
  "memory_usage_percent": 45.2,
  "disk_usage": {
    "/": 68.3,
    "/data": 42.1
  }
}
```

### 2.3 诊断指令接口（中心端 → Agent）
`POST /api/v1/execute`

**请求 Header**:
```
X-Request-ID: uuid-v4
X-Signature: HMAC-SHA256(request_id + body, PSK)
```

**请求 Body**:
```json
{
  "request_id": "uuid-v4",
  "action": "diagnose_ping",
  "params": {
    "target_ip": "192.168.1.2"
  },
  "timeout_seconds": 30
}
```

**响应**:
```json
{
  "request_id": "uuid-v4",
  "action": "diagnose_ping",
  "status": "success",
  "result": {
    "stdout": "PING 192.168.1.2 ...\n4 packets transmitted, 4 received, 0% packet loss...",
    "stderr": "",
    "exit_code": 0,
    "duration_ms": 3012
  },
  "executed_at": "2026-06-21T10:05:01+08:00"
}
```

---

## 3. 安全机制与白名单规范

> **安全红线**：禁止发送裸 Shell 命令，禁止直接拼接系统调用，强制执行参数化 API 与本地正则表达式校验。

### 3.1 核心防线
1. **参数化 API (No Raw Shell)**：中心端只发送 Action ID 与结构化参数。
2. **中心端 Schema 校验 (Pydantic)**：LLM 返回的 Tool Call 必须通过 Pydantic 验证。
3. **Agent 端二次校验与安全执行沙箱**：使用 Go 的 `os/exec` 设置独立的进程组与资源上限，且通过正则表达式拦截异常字符注入。
4. **日志消毒 (Anti-Prompt-Injection)**：拦截日志中包含的指令注入关键字并明确使用数据边界隔离。

### 3.2 允许的指令动作白名单 (仅限 4 种)
1. `diagnose_ping`: 仅允许内网 IP 地址 (`10.x.x.x`, `192.168.x.x`, `172.16-31.x.x`)
2. `diagnose_smart`: 仅允许符合规则的设备名 (`sda`, `nvme0n1`, `vd[a-z]`)
3. `get_detailed_journal`: 限定特定的服务名称和分钟范围（1-60）。
4. `check_service_status`: 限定 PVE 核心服务列表（如 corosync, pveproxy, ceph-mon 等）。

---

## 4. 数据库 Schema 约定

```python
# controller/db/models.py
Node:
  - id (String 64) [PK]
  - hostname
  - agent_version
  - last_heartbeat
  - last_log_cursor
  - is_online

LogBatch:
  - batch_id (String 36) [PK]
  - node_id
  - entry_count
  - filtered_count
  - received_at
  - analyzed
  - analysis_id

AnalysisRecord:
  - id (UUID) [PK]
  - node_id
  - severity
  - report
  - tool_calls_count
  - llm_tokens_used
  - alert_sent

AuditLog:
  - id [PK]
  - timestamp
  - event_type
  - request_id
  - node_id
  - action
  - params (JSON)
  - result_status
  - result_summary
  - duration_ms
  - triggered_by
```

---

## 5. 分阶段开发任务拆解

### 阶段 1：基础通信层
1. 创建 Python 与 Go 项目骨架。
2. 实现日志接收 API (`POST /api/v1/logs`) 与 SQLite 初始化。
3. 实现 Go Agent 从 `journalctl` 增量读取日志，并使用本地正则预过滤噪音。
4. 实现 Go Agent HTTPS 日志推送功能。
5. 编写 PSK 签名双向认证逻辑。
6. 实现节点心跳注册机制。

### 阶段 2：AI 分析引擎
1. 封装重试与降级兼顾的 LLM 客户端调用逻辑。
2. 开发日志消毒模块，过滤潜在的指令注入。
3. 设定 `SYSTEM_PROMPT` 模板。
4. 使用 LangGraph 搭建初步日志异常检测的状态机（此时先不挂载 Tool Call）。
5. 实现基于单节点或多节点的告警触发及冷却机制（邮件分发）。
6. 开发定时任务模块，每十分钟发起一次巡检。

### 阶段 3：闭环智能诊断
1. 中心端开发 Pydantic Tool Call 校验器与指令分发器。
2. Go Agent 暴露本地只读端口接受中心端的诊断请求。
3. Go Agent 实现安全沙箱（`SafeExec`），完成动作注册表（Ping, Smartctl, systemctl, journalctl）。
4. Go Agent 添加 `sudoers` 控制文件支持。
5. 将 LangGraph 工作流改造成包含多轮 Tool Call 循环的状态机（上限 3 次循环）。
6. 添加审计日志写入功能。

---

## 6. 与原有 Shell 脚本 (log_analyzer.sh) 的功能平替指引

- `LOCAL_IGNORE_KEYWORDS` -> 迁移到 Go Agent 配置文件 `agent.yaml` 的 `filter_patterns` 中。
- `filter_logs()` -> 由 Go 标准库 `regexp` 替代。
- `deduplicate_logs()` -> Go 内存字典去重。
- `call_llm_api()` -> Python FastAPI + `httpx` 调用。
- `do_check()` / `do_summary()` -> 重构至 LangGraph 定时状态机。
- `send_email()` -> 替换为 Python 原生的 `smtplib` 发送机制。
