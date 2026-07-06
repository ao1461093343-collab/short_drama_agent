from mcp.server.fastmcp import FastMCP

mcp = FastMCP("short-drama-script-library")


@mcp.tool()
def search_templates(query: str) -> list[dict]:
    return [
        {
            "name": "身份反转前三秒",
            "pattern": "羞辱开场 -> 证据反击 -> 身份揭示 -> 下一集威胁",
            "query": query,
        }
    ]


@mcp.resource("template://short-drama/hook")
def hook_template() -> str:
    return "前三秒必须出现明确冲突：压迫者一句狠话 + 主角一个反常反应。"


if __name__ == "__main__":
    mcp.run()
