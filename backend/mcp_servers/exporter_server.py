from mcp.server.fastmcp import FastMCP

mcp = FastMCP("short-drama-exporter")


@mcp.tool()
def export_markdown(title: str, scenes: list[dict]) -> str:
    lines = [f"# {title}", ""]
    for scene in scenes:
        lines.append(f"## 场景 {scene.get('scene_no')}：{scene.get('location')}")
        lines.append(scene.get("action", ""))
        for item in scene.get("dialogue", []):
            lines.append(f"- {item.get('speaker')}：{item.get('line')}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run()
