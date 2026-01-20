import os
import asyncio
import json
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types
from server import fs_tools, extended_tools

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
            name="read_file",
            description="Read the contents of a file (safety capped at 1MB).",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "The path to the file to read."},
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="browse_web",
            description="Fetch text content from a URL (web browsing).",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL to browse."},
                },
                "required": ["url"],
            },
        ),
        types.Tool(
            name="create_excel",
            description="Create an Excel file (.xlsx) with provided data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination path for the .xlsx file."},
                    "data": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of rows (dictionaries) to write."
                    },
                },
                "required": ["path", "data"],
            },
        ),
        types.Tool(
            name="create_word",
            description="Create a Word document (.docx) with provided content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination path for the .docx file."},
                    "content": {"type": "string", "description": "Text content for the document."},
                },
                "required": ["path", "content"],
            },
        ),
        types.Tool(
            name="create_pdf",
            description="Create a PDF document with provided content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Destination path for the .pdf file."},
                    "content": {"type": "string", "description": "Text content for the PDF."},
                },
                "required": ["path", "content"],
            },
        ),
        types.Tool(
            name="execute_python",
            description="Execute Python code locally and get the result.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python code to execute."},
                },
                "required": ["code"],
            },
        ),
        types.Tool(
            name="search_past_actions",
            description="Search the audit logs for past filesystem activities.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term for the logs."},
                    "workspace_root": {"type": "string", "description": "The workspace root to search in."},
                },
                "required": ["query", "workspace_root"],
            },
        ),
        types.Tool(
            name="search_google_drive",
            description="Search files in Google Drive (requires credentials.json).",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term for Drive."},
                },
                "required": ["query"],
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
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls."""
    if not arguments:
        return [types.TextContent(type="text", text="Missing arguments")]

    try:
        # Standard FS Tools
        if name == "list_files":
            root = arguments.get("root")
            res = fs_tools.list_files(root, ALLOWED_ROOTS)
            return [types.TextContent(type="text", text=str(res))]

        elif name == "read_file":
            path = arguments.get("path")
            res = fs_tools.read_file_safe(path, ALLOWED_ROOTS)
            return [types.TextContent(type="text", text=str(res))]

        # Extended Tools
        elif name == "browse_web":
            url = arguments.get("url")
            res = extended_tools.browse_web(url)
            return [types.TextContent(type="text", text=res)]

        elif name == "create_excel":
            path = arguments.get("path")
            data = arguments.get("data")
            # Enforce root safety for writes
            fs_tools.enforce_within_roots(path, ALLOWED_ROOTS)
            res = extended_tools.create_excel(path, data)
            return [types.TextContent(type="text", text=res)]

        elif name == "create_word":
            path = arguments.get("path")
            content = arguments.get("content")
            fs_tools.enforce_within_roots(path, ALLOWED_ROOTS)
            res = extended_tools.create_word(path, content)
            return [types.TextContent(type="text", text=res)]

        elif name == "create_pdf":
            path = arguments.get("path")
            content = arguments.get("content")
            fs_tools.enforce_within_roots(path, ALLOWED_ROOTS)
            res = extended_tools.create_pdf(path, content)
            return [types.TextContent(type="text", text=res)]

        elif name == "execute_python":
            code = arguments.get("code")
            res = extended_tools.execute_python_code(code)
            return [types.TextContent(type="text", text=res)]

        elif name == "search_past_actions":
            query = arguments.get("query")
            workspace_root = arguments.get("workspace_root")
            res = extended_tools.search_audit_logs(query, workspace_root)
            return [types.TextContent(type="text", text=res)]

        elif name == "search_google_drive":
            query = arguments.get("query")
            res = extended_tools.search_google_drive(query)
            return [types.TextContent(type="text", text=res)]

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

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="coworker-mcp",
                server_version="0.2.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())
