# OpenClaw 接入 web-search MCP 配置指南

**重要**：OpenClaw **不直接读取** Claude Desktop 风格的 MCP 配置。它通过 **mcporter 技能** 作为中介调用 MCP。需在 mcporter 的配置中添加 web-search。

---

## 1. 配置 mcporter（OpenClaw 通过它调用 MCP）

在 **mcporter 的配置** 中添加 web-search：

```bash
mkdir -p ~/.mcporter
```

编辑或创建 `~/.mcporter/mcporter.json`：

```json
{
  "mcpServers": {
    "web-search": {
      "command": "bash",
      "args": [
        "-c",
        "cd /path/to/your/webSearchAPI && .venv/bin/python -m src.server"
      ]
    }
  }
}
```

**说明**：
- 将 `/path/to/your/webSearchAPI` 替换为你的项目实际路径（或使用 `$(pwd)` 若在脚本中动态注入）
- 用 `bash -c` 包装，确保在正确目录下运行 Python，否则 `src` 模块无法找到

---

## 2. 确保 mcporter 已安装且对 OpenClaw 可见

```bash
npm i -g mcporter
which mcporter
openclaw skills list --eligible | grep mcporter
```

若 `mcporter` 不在 eligible 列表中，OpenClaw 无法通过它调用 MCP。

---

## 3. 先用 mcporter 直接测试 stdio（确认能调用）

在终端手动测试，成功后再在 OpenClaw 中依赖 mcporter 技能：

```bash
# 列出工具
npx mcporter list web-search

# 调用 web_search
npx mcporter call web-search.web_search query=Python num_results=3
```

若以上失败，请检查：
- `~/.mcporter/mcporter.json` 路径、格式
- `command` 中的项目路径是否正确
- `.venv/bin/python` 是否存在且依赖已安装

---

## 4. 备选：HTTP 模式（更适合稳定调用）

stdio 有时在 OpenClaw/mcporter 下不稳定，可改用 HTTP 模式：

**步骤 1**：在服务器上长期运行 HTTP 服务（可用 systemd/supervisor 管理）：

```bash
cd /path/to/your/webSearchAPI
.venv/bin/python -m src.server --http --port 8765
# 排查超时时可加 --debug，会在终端打印完整请求和响应
.venv/bin/python -m src.server --http --port 8765 --debug
```

**步骤 2**：在 mcporter 中增加 HTTP 条目：

```json
{
  "mcpServers": {
    "web-search": {
      "baseUrl": "http://127.0.0.1:8765/mcp",
      "headers": {}
    }
  }
}
```

**注意**：mcporter 连接 HTTP 时，非 localhost 或 HTTPS 可能需要加 `--allow-http`。本地测试用 `127.0.0.1` 一般可用。

---

## 5. 重启 OpenClaw 并验证

```bash
openclaw gateway restart
```

在对话中测试：「帮我搜索一下 Python 3.13 新特性」。

---

## 6. 常见问题

### stdio 方式无法调用

- OpenClaw 不直接支持 stdio MCP，必须通过 mcporter 技能
- 确认 `~/.mcporter/mcporter.json` 已配置、`openclaw skills list --eligible` 中有 mcporter
- 用 `npx mcporter call web-search.web_search query=test` 先单独验证

### 端口已被占用

```bash
# 查看占用
lsof -i :8765

# 结束进程
kill $(lsof -t -i :8765)

# 或换端口：python -m src.server --http --port 8766
```

### 依赖缺失

在项目目录：`pip install -r requirements.txt`，并确保 `command` 指向的 Python 已安装这些依赖。

### aiclaw 超时（MCP 调用超时 90s）

若 aiclaw 显示「MCP 调用超时」且 web_search 从未执行：

**排查结论**（基于调试日志）：
- **HTTP 模式**：aiclaw 只发送 `initialize`，未发送 `tools/call`，问题在客户端
- **stdio 模式**：若进程已启动但无调用，同样是客户端未正确完成 MCP 握手/调用流程

**建议**：
1. 用官方 MCP 客户端验证本服务器是否正常：
   ```bash
   cd /path/to/webSearchAPI
   .venv/bin/python scripts/test_stdio_client.py
   ```
   若成功（约 4 秒内返回结果），说明 web-search MCP 正常，需排查 aiclaw 的 MCP 集成
2. 或用 mcporter 验证：`npx mcporter call web-search.web_search query=test num_results=3`
3. 向 aiclaw 反馈：客户端在 `initialize` 后需再发 `tools/call`（HTTP 需带 `Mcp-Session-Id`）
4. 尝试让 aiclaw 通过 mcporter 调用（若支持），而非直接连接本服务

---

## 7. 环境变量（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `WEB_SEARCH_REGION` | `jp-ja` | 搜索区域，如 `us-en`、`zh-cn` |
| `WEB_SEARCH_HTTP_TIMEOUT` | `30.0` | HTTP 请求超时（秒） |
| `WEB_SEARCH_RETRY_ATTEMPTS` | `3` | 网络失败时的重试次数 |
| `WEB_SEARCH_CACHE_TTL` | `300` | 搜索结果缓存时长（秒），设为 `0` 禁用缓存 |
| `WEB_SEARCH_DEBUG` | 空 | 设为 `1` 或 `true` 时，打印完整请求和响应（排查超时用），等同 `--debug` |
