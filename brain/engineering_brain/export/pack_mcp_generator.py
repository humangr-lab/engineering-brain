"""PackMCPGenerator — transforms MaterializedPack into an MCP server.

Two modes:
1. generate_server() → In-process PackMCPServer for pack.serve()
2. export() → Standalone directory with server.py + pack_data.json

The export pipeline:
1. Serialize MaterializedPack to pack_data.json
2. Copy pack_mcp_runtime.py (self-contained, zero deps)
3. Generate server.py entry point (10 LOC)
4. Generate README.md with usage instructions
5. Generate .mcp.json for easy registration
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from engineering_brain.core.types import MaterializedPack, PackTemplate

logger = logging.getLogger(__name__)


class PackMCPGenerator:
    """Generates MCP servers from MaterializedPacks."""

    def generate_server(
        self,
        pack: MaterializedPack,
        template: PackTemplate | None = None,
    ) -> Any:
        """Create an in-process PackMCPServer.

        Args:
            pack: The materialized pack
            template: Optional template for tool definitions

        Returns:
            PackMCPServer instance ready for handle_request() or serve()
        """
        from engineering_brain.export.pack_mcp_runtime import PackMCPServer

        pack_data = self._build_pack_data(pack, template)
        tool_manifest = pack_data.get("tool_manifest", [])
        return PackMCPServer(pack_data, tool_manifest)

    def export(
        self,
        pack: MaterializedPack,
        output_dir: str,
        template: PackTemplate | None = None,
    ) -> dict[str, Any]:
        """Export pack as a standalone MCP server directory.

        Creates:
            output_dir/
            ├── server.py          (entry point, ~10 LOC)
            ├── pack_data.json     (serialized pack + tool manifest)
            ├── pack_mcp_runtime.py (self-contained runtime, zero deps)
            ├── README.md          (usage instructions)
            └── .mcp.json          (MCP registration config)

        Args:
            pack: The materialized pack to export
            output_dir: Directory to create
            template: Optional template (used for tool defs if available)

        Returns:
            Dict with export stats
        """
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Build and write pack_data.json
        pack_data = self._build_pack_data(pack, template)
        data_path = out / "pack_data.json"
        with open(data_path, "w") as f:
            json.dump(pack_data, f, indent=2, default=str)

        # 2. Copy runtime
        runtime_src = Path(__file__).parent / "pack_mcp_runtime.py"
        runtime_dst = out / "pack_mcp_runtime.py"
        shutil.copy2(runtime_src, runtime_dst)

        # 3. Generate server.py
        server_py = out / "server.py"
        server_name = pack_data.get("metadata", {}).get("server_name", "pack-server")
        server_py.write_text(
            f'"""MCP server for {server_name} knowledge pack."""\n'
            f'import os\n'
            f'import sys\n'
            f'\n'
            f'# Add current directory to path for runtime import\n'
            f'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\n'
            f'\n'
            f'from pack_mcp_runtime import run_server\n'
            f'\n'
            f'if __name__ == "__main__":\n'
            f'    run_server(os.path.join(os.path.dirname(__file__), "pack_data.json"))\n'
        )

        # 4. Generate README.md
        readme = out / "README.md"
        readme.write_text(self._generate_readme(pack, pack_data))

        # 5. Generate .mcp.json
        mcp_json = out / ".mcp.json"
        mcp_config = {
            "mcpServers": {
                server_name: {
                    "command": "python",
                    "args": [str(server_py.resolve())],
                },
            },
        }
        with open(mcp_json, "w") as f:
            json.dump(mcp_config, f, indent=2)

        stats = {
            "output_dir": str(out),
            "nodes": len(pack.nodes),
            "tools": len(pack_data.get("tool_manifest", [])),
            "pack_data_bytes": data_path.stat().st_size,
            "files": ["server.py", "pack_data.json", "pack_mcp_runtime.py", "README.md", ".mcp.json"],
        }
        logger.info(
            "Exported pack %s: %d nodes, %d tools → %s",
            pack.template_id, stats["nodes"], stats["tools"], output_dir,
        )
        return stats

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_pack_data(
        self,
        pack: MaterializedPack,
        template: PackTemplate | None = None,
    ) -> dict[str, Any]:
        """Build the serialized pack data dict."""
        # Get tool manifest from template or build default
        tool_manifest = self._build_tool_manifest(pack, template)

        server_name = "pack-server"
        server_desc = ""
        if template:
            server_name = template.mcp_server_name or template.id
            server_desc = template.mcp_server_description or template.description

        return {
            "nodes": pack.nodes,
            "edges": pack.edges,
            "reasoning_edges": pack.reasoning_edges,
            "tool_manifest": tool_manifest,
            "metadata": {
                "template_id": pack.template_id,
                "template_version": pack.template_version,
                "server_name": server_name,
                "server_description": server_desc,
                "version": "1.0.0",
                "node_count": pack.node_count,
                "technologies": pack.technologies,
                "domains": pack.domains,
                "layers_present": pack.layers_present,
                "quality_score": pack.quality_score,
                "created_at": str(pack.created_at),
            },
        }

    def _build_tool_manifest(
        self,
        pack: MaterializedPack,
        template: PackTemplate | None = None,
    ) -> list[dict[str, Any]]:
        """Build tool manifest from template MCP tools or generate defaults."""
        if template and template.mcp_tools:
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema or {"type": "object", "properties": {}, "required": []},
                    "handler_type": tool.handler_type,
                    "handler_config": tool.handler_config,
                }
                for tool in template.mcp_tools
            ]

        # Default tools for packs without template tools
        return [
            {
                "name": "search_knowledge",
                "description": "Search the knowledge pack for relevant information.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What to search for"},
                    },
                    "required": ["query"],
                },
                "handler_type": "query",
                "handler_config": {},
            },
            {
                "name": "list_nodes",
                "description": "List knowledge nodes, optionally filtered by layer or domain.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string", "description": "Filter by domain"},
                        "technology": {"type": "string", "description": "Filter by technology"},
                    },
                    "required": [],
                },
                "handler_type": "filter",
                "handler_config": {},
            },
            {
                "name": "get_node",
                "description": "Get detailed information about a specific knowledge node.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "node_id": {"type": "string", "description": "Node ID to look up"},
                    },
                    "required": ["node_id"],
                },
                "handler_type": "lookup",
                "handler_config": {},
            },
            {
                "name": "pack_stats",
                "description": "Get pack statistics and metadata.",
                "input_schema": {"type": "object", "properties": {}, "required": []},
                "handler_type": "stats",
                "handler_config": {},
            },
        ]

    def _generate_readme(self, pack: MaterializedPack, pack_data: dict[str, Any]) -> str:
        """Generate README.md for the exported pack."""
        metadata = pack_data.get("metadata", {})
        server_name = metadata.get("server_name", "pack-server")
        server_desc = metadata.get("server_description", "")
        tools = pack_data.get("tool_manifest", [])

        lines = [
            f"# {server_name}",
            "",
            server_desc or f"Knowledge pack with {pack.node_count} nodes.",
            "",
            "## Requirements",
            "",
            "- Python 3.11+",
            "- No additional dependencies needed",
            "",
            "## Usage",
            "",
            "### Standalone (stdio)",
            "```bash",
            "python server.py",
            "```",
            "",
            "### With Claude Desktop / Cursor",
            "Add to your MCP configuration:",
            "```json",
            json.dumps({
                "mcpServers": {
                    server_name: {
                        "command": "python",
                        "args": ["<path-to>/server.py"],
                    },
                },
            }, indent=2),
            "```",
            "",
            "## Available Tools",
            "",
        ]

        for tool in tools:
            lines.append(f"### `{tool.get('name', '')}`")
            lines.append(tool.get("description", ""))
            lines.append("")

        lines.extend([
            "## Pack Info",
            "",
            f"- **Nodes**: {pack.node_count}",
            f"- **Technologies**: {', '.join(pack.technologies) or 'all'}",
            f"- **Domains**: {', '.join(pack.domains) or 'all'}",
            f"- **Layers**: {', '.join(pack.layers_present)}",
            f"- **Quality Score**: {pack.quality_score:.2f}",
            "",
            "---",
            "*Generated by Engineering Brain Pack Factory*",
        ])

        return "\n".join(lines)
