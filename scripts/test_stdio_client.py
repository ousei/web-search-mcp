#!/usr/bin/env python3
"""验证 web-search MCP stdio 是否正常：用官方 MCP 客户端调用 web_search。"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


async def main():
    """通过 stdio 连接本地 web-search 并调用 web_search。"""
    project_root = Path(__file__).resolve().parent.parent
    params = StdioServerParameters(
        command=str(project_root / ".venv" / "bin" / "python"),
        args=["-m", "src.server"],
        cwd=str(project_root),
    )

    print("Connecting via stdio...", file=sys.stderr)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("Initialized. Calling web_search...", file=sys.stderr)
            result = await session.call_tool("web_search", {"query": "Python 3.13", "num_results": 2})
            print("Result:", result)
            print("OK", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
