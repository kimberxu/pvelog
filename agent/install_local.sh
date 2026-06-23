#!/bin/bash
set -e

# 确保脚本以 root 权限运行
if [ "$EUID" -ne 0 ]; then
  echo "错误: 请以 root 权限运行此部署脚本 (Please run as root)"
  exit 1
fi

echo "====================================================="
echo "       PVE AIOps Agent 一键部署脚本"
echo "====================================================="

BINARY_NAME="pve-agent"
TARGET_PATH="/usr/local/bin/$BINARY_NAME"
CONFIG_DIR="/etc/pve-agent"
CONFIG_FILE="$CONFIG_DIR/agent.yaml"

# 1. 检查二进制文件
echo "[1/6] 检查 pve-agent 二进制文件..."
if [ -f "./$BINARY_NAME" ]; then
    echo "      发现当前目录存在 $BINARY_NAME，正在复制到 $TARGET_PATH ..."
    cp "./$BINARY_NAME" "$TARGET_PATH"
elif [ -f "$TARGET_PATH" ]; then
    echo "      当前目录未发现 $BINARY_NAME，但目标路径 $TARGET_PATH 已存在，继续使用..."
else
    echo "错误: 未找到 $BINARY_NAME 文件！"
    echo "请先手动编译或下载 $BINARY_NAME 二进制文件，然后将其与本脚本放在同一目录，或者直接将其放置到 $TARGET_PATH。"
    exit 1
fi

chmod +x "$TARGET_PATH"

# 2. 配置运行用户
echo "[2/6] 配置系统运行用户 pve-agent ..."
if id -u pve-agent >/dev/null 2>&1; then
    echo "      用户 pve-agent 已存在，跳过创建。"
    # 确保已有用户也在 systemd-journal 组中
    usermod -aG systemd-journal pve-agent 2>/dev/null || true
else
    # 创建用户并直接加入 systemd-journal 组
    useradd -r -s /usr/sbin/nologin -G systemd-journal pve-agent
    echo "      已创建独立系统用户 pve-agent 并加入 systemd-journal 组。"
fi

# 3. 配置 sudoers 免密白名单
echo "[3/6] 配置 sudo 免密提权白名单 ..."
mkdir -p /etc/sudoers.d
echo "pve-agent ALL=(ALL) NOPASSWD: /usr/sbin/smartctl, /usr/bin/journalctl" > /etc/sudoers.d/pve-agent
chmod 440 /etc/sudoers.d/pve-agent
echo "      已授权 smartctl 和 journalctl 的免密执行权限。"

# 4. 生成或更新配置文件
echo "[4/6] 配置 Agent 运行参数 ..."
mkdir -p "$CONFIG_DIR"

DO_CONFIG="yes"
if [ -f "$CONFIG_FILE" ]; then
    echo "      配置文件 $CONFIG_FILE 已存在。"
    read -p "      是否需要重新配置覆盖它？(y/N): " OVERWRITE
    if [[ "$OVERWRITE" =~ ^[Yy]$ ]]; then
        DO_CONFIG="yes"
    else
        DO_CONFIG="no"
    fi
fi

if [ "$DO_CONFIG" = "yes" ]; then
    DEFAULT_NODE_ID=$(hostname)
    read -p "      请输入当前节点唯一标识 (Node ID) [默认: $DEFAULT_NODE_ID]: " NODE_ID
    NODE_ID=${NODE_ID:-$DEFAULT_NODE_ID}

    read -p "      请输入中心端服务地址 (例如 http://192.168.1.100:42791): " CONTROLLER_URL
    while [ -z "$CONTROLLER_URL" ]; do
        read -p "      中心端服务地址不能为空，请重新输入: " CONTROLLER_URL
    done

    read -p "      请输入预共享密钥 (PSK Secret): " PSK_SECRET
    while [ -z "$PSK_SECRET" ]; do
        read -p "      预共享密钥不能为空，请重新输入: " PSK_SECRET
    done

    cat > "$CONFIG_FILE" <<EOF
node_id: "$NODE_ID"
controller_url: "$CONTROLLER_URL"
psk_secret: "$PSK_SECRET"
EOF
    echo "      配置文件 $CONFIG_FILE 已生成。"
fi

chown -R pve-agent:pve-agent "$CONFIG_DIR"
chmod 600 "$CONFIG_FILE"

# 5. 注册 systemd 服务
echo "[5/6] 注册 Systemd 守护服务 ..."
cat > /etc/systemd/system/pve-agent.service <<EOF
[Unit]
Description=PVE AIOps Agent
After=network.target

[Service]
Type=simple
User=pve-agent
StateDirectory=pve-agent
WorkingDirectory=/var/lib/pve-agent
ExecStart=$TARGET_PATH -config $CONFIG_FILE
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF

# 6. 启动并启用服务
echo "[6/6] 启动并设置 pve-agent 开机自启 ..."
systemctl daemon-reload
systemctl enable --now pve-agent

echo ""
echo "====================================================="
echo " 部署成功！pve-agent 已在后台运行。"
echo "====================================================="
echo "- 服务状态检查: systemctl status pve-agent"
echo "- 实时查看日志: journalctl -u pve-agent -f"
echo "====================================================="
