---
name: deploy
description: 部署苏格拉底学习Agent服务。停止旧进程、启动main.py、验证飞书WebSocket长连接成功。当代码修改完成需要生效时使用，或用户说"部署""重启服务""启动服务"时触发。
---

# 部署苏格拉底服务

## 执行步骤

### Step 1: 停止旧进程
```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
```
等待 2 秒确保进程完全退出。

### Step 2: 启动服务
```powershell
cd e:\GitCode\LearningAgent; py -3 main.py
```
以后台模式启动，不阻塞当前操作。

### Step 3: 验证连接
等待 5 秒后检查终端输出，确认以下关键信息：
- `苏格拉底学习Agent 启动` — 服务启动成功
- `connected to wss://` — WebSocket 长连接建立成功

### Step 4: 确认结果
- 如果两个关键信息都出现：报告"部署成功"
- 如果缺少连接信息：检查日志中的错误，报告具体问题
- 如果进程立即退出：读取错误输出，排查代码问题

## 注意事项
- 部署会导致内存中的对话历史丢失，但学习上下文（state、current_topic）已持久化到文件，不受影响
- 如果用户正在飞书上进行教学对话，部署后教学状态会自动恢复
