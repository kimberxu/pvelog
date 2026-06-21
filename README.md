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

## 🔒 安全说明

- **PSK 鉴权**: Agent 和 Controller 间的数据通信使用预共享密钥 (PSK) 进行 HMAC-SHA256 签名校验。
- **权限最小化**: Agent 运行在无登录权限的系统级账户下，并通过特化的 `sudoers` 规则，仅允许无密码执行受限的白名单系统命令。
- **沙箱隔离**: 系统具有针对 LLM 提示词注入的防御机制，所有下发指令均有严格的 Pydantic 校验和 Go 正则校验，避免越权执行。

## 🤝 贡献与反馈

欢迎提交 Issue 和 Pull Request 来完善 PVE AIOps 监控体系。

## 📄 许可证

MIT License
