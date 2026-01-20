import os
import asyncio
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from server import fs_tools

# Initialize the server
server = Server("coworker-mcp")

# Configuration: Allowed roots can be set via environment variable (comma-separated)
# Default to current working directory if not set
ALLOWED_ROOTS = os.environ.get("COWORKER_ALLOWED_ROOTS", os.getcwd()).split(",")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="list_files",
            description="List files and directories in a workspace root.",
            inputSchema={
                "type": "object",
                "properties": {
                    "root": {"type": "string", "description": "The root directory to list."},
                },
                "required": ["root"],
            },
        ),
        types.Tool(
            name="scan_index",
            description="Scan a directory and optionally hash files for indexing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "root": {"type": "string", "description": "The root directory to scan."},
                    "hash_files": {"type": "boolean", "description": "Whether to compute SHA256 hashes for each file."},
                },
                "required": ["root"],
            },
        ),
        types.Tool(
            name="organize_plan",
            description="Propose a plan to organize files (e.g., by extension).",
            inputSchema={
                "type": "object",
                "properties": {
                    "root": {"type": "string", "description": "The root directory to organize."},
                    "policy": {"type": "string", "description": "Organization policy (default: 'by_ext')."},
                },
                "required": ["root"],
            },
        ),
        types.Tool(
            name="execute_plan",
            description="Execute a pre-generated plan. WARNING: Real filesystem changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "plan": {"type": "object", "description": "The plan object (from organize_plan)."},
                    "workspace_root": {"type": "string", "description": "The root directory for the workspace."},
                },
                "required": ["plan", "workspace_root"],
            },
        ),
        types.Tool(
            name="restore",
            description="Restore a file from the .trash folder.",
            inputSchema={
                "type": "object",
                "properties": {
                    "trash_item_path": {"type": "string", "description": "The path to the item in trash."},
                    "restore_to": {"type": "string", "description": "The destination path to restore to."},
                    "workspace_root": {"type": "string", "description": "The workspace root."},
                },
                "required": ["trash_item_path", "restore_to", "workspace_root"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls."""
    if not arguments:
        return [types.TextContent(type="text", text="Missing arguments")]

    try:
        if name == "list_files":
            root = arguments.get("root")
            res = fs_tools.list_files(root, ALLOWED_ROOTS)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "scan_index":
            root = arguments.get("root")
            hash_files = arguments.get("hash_files", False)
            res = fs_tools.scan_index(root, ALLOWED_ROOTS, hash_files=hash_files)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "read_file":
            path = arguments.get("path")
            res = fs_tools.read_file_safe(path, ALLOWED_ROOTS)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "organize_plan":
            root = arguments.get("root")
            policy = arguments.get("policy", "by_ext")
            res = fs_tools.propose_organize_plan(root, ALLOWED_ROOTS, policy=policy)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "execute_plan":
            plan = arguments.get("plan")
            workspace_root = arguments.get("workspace_root")
            res = fs_tools.execute_plan(plan, ALLOWED_ROOTS, workspace_root)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "soft_delete":
            path = arguments.get("path")
            workspace_root = arguments.get("workspace_root")
            res = fs_tools.soft_delete(path, ALLOWED_ROOTS, workspace_root)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "restore":
            trash_item_path = arguments.get("trash_item_path")
            restore_to = arguments.get("restore_to")
            workspace_root = arguments.get("workspace_root")
            res = fs_tools.restore_from_trash(trash_item_path, restore_to, ALLOWED_ROOTS, workspace_root)
            return [types.TextContent(type="text", text=str(res))]

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    # Run the server using stdin/stdout streams
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="coworker-mcp",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
