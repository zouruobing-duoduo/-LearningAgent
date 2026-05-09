#!/bin/bash
set -e

echo "=== 苏格拉底 LearningAgent 部署脚本 ==="

# 1. 安装 Python3 和 git
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git > /dev/null 2>&1

# 2. 创建项目目录
mkdir -p /opt/socrates
cd /opt/socrates

# 3. 拉取代码
if [ -d ".git" ]; then
    git pull origin main
else
    git clone https://github.com/zouruobing-duoduo/-LearningAgent.git .
fi

# 4. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 5. 安装依赖
pip install -q -r requirements.txt

# 6. 配置环境变量
cat > /opt/socrates/.env << 'EOF'
FEISHU_APP_ID=cli_a954b51ad2b8dcd3
FEISHU_APP_SECRET=cNIwgCy4ZQFAnqP2mD3CjfsjNyq8lpsX
DEEPSEEK_API_KEY=sk-64c29eb106964be2bd5147165bae73e1
EOF

# 7. 创建 systemd 服务，开机自启
cat > /etc/systemd/system/socrates.service << 'EOF'
[Unit]
Description=Socrates Learning Agent
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/socrates
Environment=PATH=/opt/socrates/venv/bin
ExecStart=/opt/socrates/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 8. 启动服务
systemctl daemon-reload
systemctl enable socrates
systemctl restart socrates

# 9. 查看状态
sleep 2
systemctl status socrates --no-pager

echo "=== 部署完成！==="
echo "查看日志: journalctl -u socrates -f"
