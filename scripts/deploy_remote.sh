#!/usr/bin/env bash

# deploy_agent.sh - 自动化部署 Go Agent 到 PVE 节点脚本

set -euo pipefail

# 默认配置
NODE_IP=""
NODE_USER="root"
TARGET_DIR="/usr/local/bin"
CONF_DIR="/etc/pve-agent"
PSK_SECRET="YOUR_SECURE_PSK_HERE"
CONTROLLER_URL="http://localhost:42791"
NODE_ID="pve-node-01"

usage() {
    echo "Usage: $0 -h <PVE_IP> -i <NODE_ID> -c <CONTROLLER_URL> -p <PSK_SECRET>"
    echo "  -h: Target PVE host IP address (Required)"
    echo "  -i: Node identity (Default: $NODE_ID)"
    echo "  -c: Controller API URL (Default: $CONTROLLER_URL)"
    echo "  -p: Pre-Shared Key secret (Default: $PSK_SECRET)"
    exit 1
}

while getopts "h:i:c:p:" opt; do
    case "$opt" in
        h) NODE_IP=$OPTARG ;;
        i) NODE_ID=$OPTARG ;;
        c) CONTROLLER_URL=$OPTARG ;;
        p) PSK_SECRET=$OPTARG ;;
        *) usage ;;
    esac
done

if [ -z "$NODE_IP" ]; then
    echo "Error: Target PVE IP address is required."
    usage
fi

echo "=========================================="
echo "Starting Agent Compilation and Deployment"
echo "Target IP:      $NODE_IP"
echo "Node ID:        $NODE_ID"
echo "Controller URL: $CONTROLLER_URL"
echo "=========================================="

# 1. 编译 Go Agent
echo "Step 1: Compiling Go Agent for linux/amd64..."
cd "$(dirname "$0")/../agent"
GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o pve-agent cmd/pve-agent/main.go
echo "Go Agent compiled successfully."

# 2. 复制二进制文件到目标节点
echo "Step 2: Copying agent binary to $NODE_IP..."
ssh "${NODE_USER}@${NODE_IP}" "mkdir -p /usr/local/bin"
scp pve-agent "${NODE_USER}@${NODE_IP}:${TARGET_DIR}/pve-agent"
ssh "${NODE_USER}@${NODE_IP}" "chmod +x ${TARGET_DIR}/pve-agent"

# 3. 创建系统账号与配置目录
echo "Step 3: Creating pve-agent system user and config folder on target..."
ssh "${NODE_USER}@${NODE_IP}" "
    if ! id -u pve-agent &>/dev/null; then
        useradd -r -s /usr/sbin/nologin pve-agent
    fi
    mkdir -p ${CONF_DIR}
"

# 4. 生成与传输配置文件
echo "Step 4: Writing agent configuration..."
TEMP_CONF=$(mktemp)
cat <<EOF > "$TEMP_CONF"
node_id: "${NODE_ID}"
controller_url: "${CONTROLLER_URL}"
psk_secret: "${PSK_SECRET}"
collect_interval_sec: 300
filter_patterns:
  - "pam_unix"
  - "session opened for user"
  - "CRON"
EOF

scp "$TEMP_CONF" "${NODE_USER}@${NODE_IP}:${CONF_DIR}/agent.yaml"
rm -f "$TEMP_CONF"

ssh "${NODE_USER}@${NODE_IP}" "
    chown -R pve-agent:pve-agent ${CONF_DIR}
    chmod 600 ${CONF_DIR}/agent.yaml
"

# 5. 配置 sudoers 最小权限白名单
echo "Step 5: Configuring sudoers white-list on target..."
scp deploy/sudoers.d/pve-agent "${NODE_USER}@${NODE_IP}:/etc/sudoers.d/pve-agent"
ssh "${NODE_USER}@${NODE_IP}" "
    chmod 440 /etc/sudoers.d/pve-agent
    chown root:root /etc/sudoers.d/pve-agent
"

# 6. 安装并启动 systemd 服务
echo "Step 6: Installing and starting systemd service..."
scp deploy/pve-agent.service "${NODE_USER}@${NODE_IP}:/etc/systemd/system/pve-agent.service"
ssh "${NODE_USER}@${NODE_IP}" "
    systemctl daemon-reload
    systemctl enable pve-agent.service
    systemctl restart pve-agent.service
    systemctl status pve-agent.service --no-pager
"

echo "=========================================="
echo "Deployment Finished Successfully!"
echo "=========================================="
