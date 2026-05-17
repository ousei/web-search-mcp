# Web Search MCP

本地网页检索 MCP 服务，供 OpenClaw、Cursor 等 LLM 调用进行网页搜索与内容抓取。无 Docker、零常驻进程、最省资源。

## 功能

- **web_search**：按关键词搜索，返回标题、URL、摘要（基于 ddgs，聚合 DuckDuckGo/Bing 等）
- **fetch_page**：按 URL 抓取网页并提取正文为 Markdown（基于 trafilatura）

## 依赖

- Python >= 3.10
- mcp, ddgs, trafilatura, httpx, pydantic

## 安装

```bash
cd webSearchAPI
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 运行

```bash
python -m src.server
```

默认使用 stdio 传输，供 MCP 客户端按需启动。

## OpenClaw 接入

详细步骤见 [OPENCLAW_SETUP.md](OPENCLAW_SETUP.md)。

简要配置：在 OpenClaw 配置（如 `~/.clawdbot/clawdbot.json5`）的 `mcp.servers` 中添加：

```json
{
  "mcp": {
    "servers": {
      "web-search": {
        "command": "/path/to/webSearchAPI/.venv/bin/python",
        "args": ["-m", "src.server"],
        "cwd": "/path/to/webSearchAPI"
      }
    }
  }
}
```

将 `/path/to/webSearchAPI` 替换为实际路径，修改后执行 `clawdbot gateway restart`。

## 搜索日志

每次 `web_search` 和 `fetch_page` 调用会追加到项目根目录的 `web_search.log`，便于事后查看或检索：

```bash
tail -f web_search.log          # 实时查看
grep "web_search" web_search.log # 筛选搜索记录
```

## 工具参数

| 工具 | 参数 | 说明 |
|------|------|------|
| web_search | query | 搜索词（必填） |
| | num_results | 结果数量，默认 8 |
| | max_chars | 返回字符上限，默认 8000 |
| fetch_page | url | 要抓取的 URL（必填） |
| | max_length | 返回字符上限，默认 5000 |

## 用 mcporter 测试

### 方式一：HTTP 模式（推荐，可在服务端终端看到 `[web_search]` 日志）

**Terminal 1** - 启动 HTTP 服务：
```bash
cd /Users/wengzheng/Library/CloudStorage/SynologyDrive-weng/test/webSearchAPI
.venv/bin/python -m src.server --http
```

**Terminal 2** - 用 mcporter 调用：
```bash
cd /Users/wengzheng/Library/CloudStorage/SynologyDrive-weng/test/webSearchAPI

# 列出工具
npx mcporter list --http-url http://127.0.0.1:8765/mcp --allow-http

# 调用 web_search（此时 Terminal 1 会打印 [web_search] 日志）
npx mcporter call --http-url http://127.0.0.1:8765/mcp --allow-http web_search query=Python num_results=3
```

### 方式二：stdio 模式（mcporter 每次会启动新进程，服务端终端无日志）

```bash
npx mcporter list --stdio ".venv/bin/python -m src.server" --cwd . --name web-search
npx mcporter call --stdio ".venv/bin/python -m src.server" --cwd . --name web-search web_search query=Python num_results=3
```

## 许可证

MIT
