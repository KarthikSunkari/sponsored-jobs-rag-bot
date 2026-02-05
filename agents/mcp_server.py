"""
Model Context Protocol (MCP) Server
Standardizes tool interfaces for agent orchestration.
Implements MCP specification for job search tools.
"""

from typing import Dict, List, Any, Callable, Optional
from dataclasses import dataclass
from enum import Enum
import json


class ToolCategory(Enum):
    """Tool categories for MCP."""
    SEARCH = "search"
    FILTER = "filter"
    SCORE = "score"
    NOTIFY = "notify"


@dataclass
class Tool:
    """MCP Tool definition."""
    name: str
    description: str
    category: ToolCategory
    parameters: Dict[str, Any]
    function: Callable
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tool to MCP-compatible dict."""
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "parameters": self.parameters
        }


class MCPServer:
    """
    Model Context Protocol Server for job search agents.
    Provides standardized tool interfaces for:
    - Job searching
    - Sponsorship filtering
    - Relevance scoring
    - Notifications
    """
    
    def __init__(self):
        self.tools: Dict[str, Tool] = {}
        self._register_default_tools()
    
    def _register_default_tools(self):
        """Register default job search tools."""
        
        # Search tool
        self.register_tool(Tool(
            name="search_jobs",
            description="Search for jobs from multiple sources (LinkedIn, Indeed, GitHub Jobs)",
            category=ToolCategory.SEARCH,
            parameters={
                "query": {"type": "string", "description": "Job search query"},
                "location": {"type": "string", "description": "Job location", "optional": True},
                "max_results": {"type": "integer", "description": "Max results to return", "default": 50}
            },
            function=self._search_jobs_impl
        ))
        
        # Filter tool
        self.register_tool(Tool(
            name="filter_by_sponsorship",
            description="Filter jobs by companies with proven H-1B/PERM sponsorship history",
            category=ToolCategory.FILTER,
            parameters={
                "jobs": {"type": "array", "description": "List of job objects"},
                "min_approval_rate": {"type": "float", "description": "Minimum approval rate (0-1)", "default": 0.7}
            },
            function=self._filter_sponsorship_impl
        ))
        
        # Score tool
        self.register_tool(Tool(
            name="score_relevance",
            description="Score job relevance against resume using Groq Llama-3",
            category=ToolCategory.SCORE,
            parameters={
                "job": {"type": "object", "description": "Job object"},
                "resume": {"type": "string", "description": "Resume text"},
                "threshold": {"type": "integer", "description": "Minimum score threshold", "default": 80}
            },
            function=self._score_relevance_impl
        ))
        
        # Notify tool
        self.register_tool(Tool(
            name="send_notification",
            description="Send email notification with top job matches",
            category=ToolCategory.NOTIFY,
            parameters={
                "matches": {"type": "array", "description": "List of scored job matches"},
                "recipient": {"type": "string", "description": "Email recipient"}
            },
            function=self._send_notification_impl
        ))
    
    def register_tool(self, tool: Tool):
        """Register a tool with the MCP server."""
        self.tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get tool by name."""
        return self.tools.get(name)
    
    def list_tools(self, category: Optional[ToolCategory] = None) -> List[Dict[str, Any]]:
        """List all tools or filter by category."""
        tools = self.tools.values()
        if category:
            tools = [t for t in tools if t.category == category]
        return [t.to_dict() for t in tools]
    
    def execute_tool(self, name: str, **kwargs) -> Any:
        """Execute a tool by name with parameters."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool '{name}' not found")
        
        # Validate parameters (basic validation)
        for param_name, param_def in tool.parameters.items():
            if param_name not in kwargs and not param_def.get("optional", False):
                if "default" in param_def:
                    kwargs[param_name] = param_def["default"]
                else:
                    raise ValueError(f"Missing required parameter: {param_name}")
        
        return tool.function(**kwargs)
    
    # Tool implementations (these call actual modules)
    
    def _search_jobs_impl(self, query: str, location: str = None, max_results: int = 50) -> List[Dict]:
        """Implementation of job search tool."""
        # This would call actual scraping logic
        from etl import job_scraper
        return job_scraper.search_jobs(query, location, max_results)
    
    def _filter_sponsorship_impl(self, jobs: List[Dict], min_approval_rate: float = 0.7) -> List[Dict]:
        """Implementation of sponsorship filter tool."""
        from utils.supabase_client import get_supabase_client
        
        client = get_supabase_client()
        filtered_jobs = []
        
        for job in jobs:
            company = job.get("company", "").strip()
            if not company:
                continue
            
            # Check sponsorship history
            result = client.client.table("companies").select("*").ilike("name", f"%{company}%").execute()
            
            if result.data:
                company_data = result.data[0]
                approval_rate = company_data.get("approval_rate", 0)
                if approval_rate >= min_approval_rate:
                    job["sponsorship_data"] = company_data
                    filtered_jobs.append(job)
        
        return filtered_jobs
    
    def _score_relevance_impl(self, job: Dict, resume: str, threshold: int = 80) -> Dict:
        """Implementation of relevance scoring tool."""
        from agents.groq_client import GroqClient
        
        client = GroqClient()
        result = client.score_job_relevance(
            job_description=job.get("description", ""),
            resume_text=resume,
            job_title=job.get("title", ""),
            company=job.get("company", "")
        )
        
        # Add job data to result
        result["job"] = job
        result["meets_threshold"] = result["score"] >= threshold
        
        return result
    
    def _send_notification_impl(self, matches: List[Dict], recipient: str) -> bool:
        """Implementation of notification tool."""
        from agents.notifier import send_daily_digest
        return send_daily_digest(matches, recipient)
    
    def to_mcp_schema(self) -> Dict[str, Any]:
        """Export MCP schema for agent consumption."""
        return {
            "version": "1.0",
            "server": "jobs-rag-bot-mcp",
            "tools": self.list_tools()
        }


# Global MCP server instance
_mcp_server = None

def get_mcp_server() -> MCPServer:
    """Get singleton MCP server instance."""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server


if __name__ == "__main__":
    # Test MCP server
    server = get_mcp_server()
    
    print("🔧 MCP Server Tools:")
    print(json.dumps(server.to_mcp_schema(), indent=2))
    
    print("\n✅ MCP Server initialized successfully!")
