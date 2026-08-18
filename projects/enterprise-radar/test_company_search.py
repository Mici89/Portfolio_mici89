import asyncio
import json

from services.qcc_client import call_company_tool


async def main():
    keyword = input("请输入企业名称或简称：").strip()

    if not keyword:
        print("企业名称不能为空")
        return

    print(f"正在搜索：{keyword}")

    result = await call_company_tool(
        tool_name="get_company_by_query",
        arguments={
            "searchKey": keyword,
        },
    )

    result_data = result.model_dump(mode="json")

    print()
    print("企查查返回结果：")
    print(
        json.dumps(
            result_data,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())