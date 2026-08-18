import asyncio

from services.qcc_client import list_risk_tools


async def main():
    print("正在连接企查查风险信息服务……")

    tools = await list_risk_tools()

    print(f"连接成功，共发现 {len(tools)} 个风险工具：")
    print()

    for tool in tools:
        print(f"工具名称：{tool.name}")
        print(f"工具说明：{tool.description}")
        print(f"输入参数：{tool.inputSchema}")
        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(main())