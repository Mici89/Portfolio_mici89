import asyncio
import json

from services.qcc_client import call_company_tool


async def main():
    credit_code = input("请输入统一社会信用代码：").strip()

    if not credit_code:
        print("统一社会信用代码不能为空")
        return

    print("正在查询工商登记信息……")

    result = await call_company_tool(
        tool_name="get_company_registration_info",
        arguments={
            "searchKey": credit_code,
        },
    )

    result_data = result.model_dump(mode="json")

    print()
    print("工商登记信息：")
    print(
        json.dumps(
            result_data,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())