# PVE AIOps 智能监控排错系统部署指南

本文档介绍如何部署 `pve-aiops` 系统的中心控制端 (Controller) 和 PVE 节点代理端 (Agent)。

---

## 1. 系统架构与部署目标

- **中心端 (Controller)**:
  - 语言与框架: Python 3.11+ (FastAPI, SQLAlchemy, LangGraph)
  - 运行环境: Debian 12 VM 或 LXC (推荐配置：2核 / 2G 内存以上)
  - 数据库: SQLite (基于 `pve_aiops.db` 本地文件)
- **节点端 (Agent)**:
  - 语言: Go 1.22+
  - 运行环境: Proxmox VE 8.x 宿主机 (基于 Debian 12)
  - 特权操作: 仅限只读性的系统级状态查询 (`smartctl`, `journalctl`, `systemctl`)

---

## 2. 中心控制端 (Controller) 部署

### 2.1 依赖环境
中心端推荐使用 Docker Compose 快速拉起开发/测试环境，或直接在 Python 虚拟环境中运行。

#### 方式一：Docker Compose 部署（开发/测试）
1. 在项目根目录下，修改 [docker-compose.yml](file:///d:/PyCharm_projects/log-analyzer-agent/docker-compose.yml)，确保配置如下环境变量：
   ```yaml
   version: '3.8'
   services:
     controller:
       image: python:3.11-slim
       working_dir: /app
       volumes:
         - ./controller:/app
       command: >
         bash -c "pip install . && uvicorn api.main:app --host 0.0.0.0 --port 42791 --reload"
       ports:
         - "42791:42791"
       environment:
         - DB_URL=sqlite+aiosqlite:///./pve_aiops.db
         - PSK_SECRET=your_secure_pre_shared_key   # 替换为强随机预共享密钥
   ```
2. 启动服务：
   ```bash
   docker compose up -d
   ```

#### 方式二：手动虚拟环境部署（生产推荐）
1. 在 Debian 12 VM/LXC 上安装 Python 3.11+：
   ```bash
   sudo apt-get update && sudo apt-get install -y python3-pip python3-venv
   ```
2. 创建并激活虚拟环境：
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. 安装依赖（在 `controller` 目录下执行）：
   ```bash
   pip install --upgrade pip
   pip install .
   ```
4. 配置环境变量（建议在服务根目录下创建 `.env` 文件，具体配置可参考 [settings.py](file:///d:/PyCharm_projects/log-analyzer-agent/controller/config/settings.py)）：
   ```ini
   DB_URL=sqlite+aiosqlite:////var/lib/pve-aiops/pve_aiops.db
   PSK_SECRET=your_secure_pre_shared_key
   LLM_BASE_URL=https://api.openai.com/v1          # 替换为实际 LLM 接口地址
   LLM_API_KEY=sk-...                             # 替换为实际 LLM API 秘钥
   LLM_MODEL=deepseek-v3.2
   ```
5. 使用 Systemd 管理中心端服务，创建 `/etc/systemd/system/pve-controller.service`：
   ```ini
   [Unit]
   Description=PVE AIOps Controller
   After=network.target

   [Service]
   Type=simple
   User=www-data
   WorkingDirectory=/opt/pve-aiops/controller
   EnvironmentFile=/opt/pve-aiops/controller/.env
   ExecStart=/opt/pve-aiops/controller/venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 42791
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```
6. 启动并启用服务：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now pve-controller
   ```

---

## 3. PVE 节点代理 (Agent) 部署

Agent 需要直接部署在 Proxmox VE 宿主机上，通过 systemd 服务运行，且需要受控的 `sudo` 权限来收集物理磁盘 S.M.A.R.T. 信息与系统日志。

### 3.1 编译 Agent 二进制文件
可以在开发机上进行交叉编译，或者直接在 PVE 节点上进行编译（需要 Go 环境）：
```bash
# 进入 agent 目录
cd agent
# 交叉编译适合 Linux x86_64 的二进制文件
GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o pve-agent cmd/pve-agent/main.go
```

### 3.2 部署到 PVE 节点
1. **传输二进制文件**：
   将编译好的 `pve-agent` 发送到 PVE 节点：
   ```bash
   scp pve-agent root@<pve-node-ip>:/usr/local/bin/pve-agent
   chmod +x /usr/local/bin/pve-agent
   ```

2. **创建独立的运行用户**：
   为降低安全风险，Agent 严禁以 root 用户直接运行。创建只读系统用户 `pve-agent`：
   ```bash
   sudo useradd -r -s /usr/sbin/nologin pve-agent
   ```

3. **配置 sudoers 最小特权白名单**：
   Agent 需要执行 `smartctl` 和 `journalctl`，需精细化授予免密 sudo 权限。
   在 PVE 节点上创建并配置权限：
   ```bash
   # 创建权限定义文件并写入配置
   sudo mkdir -p /etc/sudoers.d
   sudo bash -c 'echo "pve-agent ALL=(ALL) NOPASSWD: /usr/sbin/smartctl, /usr/bin/journalctl" > /etc/sudoers.d/pve-agent'
   sudo chmod 440 /etc/sudoers.d/pve-agent
   ```

4. **配置 Agent 服务配置参数**：
   在 PVE 节点创建 `/etc/pve-agent/agent.yaml`，样例如下：
   ```yaml
   node_id: "pve-node-01"                                # 当前节点唯一标识
   controller_url: "http://<controller-ip>:42791"         # 中心端服务地址
   psk_secret: "your_secure_pre_shared_key"              # 必须与中心端 PSK_SECRET 一致
   ```
   > **注意**：日志过滤规则 (`filter_patterns`) 目前由 Controller 中心化管理，Agent 在启动时及每天会自动从 Controller 拉取最新规则，无需在此处配置。
   设置安全目录权限：
   ```bash
   sudo mkdir -p /etc/pve-agent
   sudo chown -R pve-agent:pve-agent /etc/pve-agent
   sudo chmod 600 /etc/pve-agent/agent.yaml
   ```

5. **配置 Systemd 服务管理**：
   在 PVE 节点创建服务文件 `/etc/systemd/system/pve-agent.service`：
   ```ini
   [Unit]
   Description=PVE AIOps Agent
   After=network.target

   [Service]
   Type=simple
   User=pve-agent
   ExecStart=/usr/local/bin/pve-agent -config /etc/pve-agent/agent.yaml
   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=multi-user.target
   ```
6. **启动 Agent**：
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now pve-agent
   ```

---

## 4. 部署验证与排错

### 4.1 检查服务日志
- **中心端**:
  ```bash
  journalctl -u pve-controller -f
  ```
- **PVE 节点端**:
  ```bash
  journalctl -u pve-agent -f
  ```

### 4.2 验证心跳和日志接收
当 Agent 成功运行后，中心端会接收到来自 Agent 的心跳和过滤后的日志。你可以查询数据库确认：
```bash
# 在中心端查看数据库生成的表数据
sqlite3 /var/lib/pve-aiops/pve_aiops.db "SELECT * FROM Node;"
```

### 4.3 诊断白名单动作测试
中心端可以下发限定白名单动作：
1. `diagnose_ping`: 测试内网 IP 连接状态。
2. `diagnose_smart`: 获取磁盘 S.M.A.R.T. 健康状态。
3. `get_detailed_journal`: 查询特定系统服务日志。
4. `check_service_status`: 检查核心服务状态（例如 `corosync`, `pveproxy`）。
