from mcp.server.fastmcp import FastMCP

mcp = FastMCP("short-drama-platform-rules")


@mcp.tool()
def check_sensitive_terms(text: str) -> list[dict]:
    risky_terms = ["绝对", "包治", "稳赚"]
    return [
        {"term": term, "level": "MINOR", "suggestion": "替换为更克制表达"}
        for term in risky_terms
        if term in text
    ]


@mcp.resource("rules://douyin/short-drama")
def douyin_rules() -> str:
    return "避免低俗、过度暴力、虚假承诺；冲突表达应服务剧情，不制造现实伤害。"


if __name__ == "__main__":
    mcp.run()
