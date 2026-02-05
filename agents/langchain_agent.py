"""
LangChain Multi-Agent Pipeline
Orchestrates job search, sponsorship filtering, and relevance scoring.
Uses MCP server for standardized tool access.
"""

import os
from typing import List, Dict, Any
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import Tool
from langchain_groq import ChatGroq
from langchain.schema import SystemMessage, HumanMessage
from dotenv import load_dotenv

from agents.mcp_server import get_mcp_server, ToolCategory

load_dotenv()


class JobSearchAgent:
    """
    LangChain-powered multi-agent system for intelligent job search.
    Uses Groq's Llama-3 for ultra-low latency inference.
    """
    
    def __init__(self, resume_text: str):
        """
        Initialize job search agent.
        
        Args:
            resume_text: User's resume text for matching
        """
        self.resume_text = resume_text
        self.mcp_server = get_mcp_server()
        
        # Initialize Groq LLM
        self.llm = ChatGroq(
            api_key=os.getenv("GROQ_API_KEY"),
            model_name=os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
            temperature=0.7
        )
        
        # Convert MCP tools to LangChain tools
        self.tools = self._create_langchain_tools()
        
        # Create agent
        self.agent = self._create_agent()
    
    def _create_langchain_tools(self) -> List[Tool]:
        """Convert MCP tools to LangChain Tool objects."""
        langchain_tools = []
        
        for mcp_tool in self.mcp_server.tools.values():
            # Create wrapper function that captures tool name
            def make_tool_func(tool_name):
                def tool_func(**kwargs):
                    return self.mcp_server.execute_tool(tool_name, **kwargs)
                return tool_func
            
            langchain_tool = Tool(
                name=mcp_tool.name,
                description=mcp_tool.description,
                func=make_tool_func(mcp_tool.name)
            )
            langchain_tools.append(langchain_tool)
        
        return langchain_tools
    
    def _create_agent(self) -> AgentExecutor:
        """Create LangChain agent with MCP tools."""
        
        system_message = """You are an intelligent job search assistant helping a user find H-1B/PERM sponsored positions.

Your workflow:
1. Search for jobs using the search_jobs tool
2. Filter jobs by sponsorship history using filter_by_sponsorship tool
3. Score job relevance using score_relevance tool
4. Return top matches (score >= 80)

Be concise and focus on high-quality matches. The user values:
- Companies with proven sponsorship history (>70% approval rate)
- High relevance to their resume (>80% match)
- Recent postings (last 7 days preferred)"""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad")
        ])
        
        agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=prompt
        )
        
        return AgentExecutor(
            agent=agent,
            tools=self.tools,
            verbose=True,
            max_iterations=5
        )
    
    def search_and_match(
        self,
        query: str,
        location: str = None,
        max_results: int = 50,
        min_score: int = 80
    ) -> List[Dict[str, Any]]:
        """
        Search for jobs and return scored matches.
        
        Args:
            query: Job search query (e.g., "Python ML Engineer")
            location: Optional location filter
            max_results: Maximum jobs to scrape
            min_score: Minimum relevance score threshold
            
        Returns:
            List of scored job matches
        """
        
        input_text = f"""Find me the best H-1B sponsored jobs for this query: "{query}"
        
Location: {location or 'Remote/Any'}
Max results: {max_results}
Minimum relevance score: {min_score}

My resume:
{self.resume_text[:1500]}

Return only jobs that:
1. Are from companies with proven sponsorship history
2. Score >= {min_score} on relevance
3. Match my skills and experience level"""

        try:
            result = self.agent.invoke({"input": input_text})
            return result.get("output", [])
        except Exception as e:
            print(f"Agent execution error: {e}")
            return []
    
    def explain_match(self, job: Dict[str, Any]) -> str:
        """
        Get detailed explanation of why a job matches the resume.
        
        Args:
            job: Job object with score and reasoning
            
        Returns:
            Detailed explanation
        """
        prompt = f"""Explain why this job is a good match for the candidate:

Job: {job.get('title')} at {job.get('company')}
Score: {job.get('score', 0)}/100

Job Description:
{job.get('description', '')[:1000]}

Candidate Resume:
{self.resume_text[:1000]}

Provide a 3-4 sentence explanation focusing on:
1. Key skill alignments
2. Experience level fit
3. Career growth potential"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            return response.content
        except Exception as e:
            return f"Error generating explanation: {e}"


def run_daily_job_search(resume_text: str, search_queries: List[str]) -> List[Dict]:
    """
    Run daily job search for multiple queries.
    
    Args:
        resume_text: User's resume
        search_queries: List of job search queries
        
    Returns:
        Combined list of all matches
    """
    agent = JobSearchAgent(resume_text)
    all_matches = []
    
    for query in search_queries:
        print(f"\n🔍 Searching for: {query}")
        matches = agent.search_and_match(query, min_score=80)
        all_matches.extend(matches)
    
    # Deduplicate by job URL
    seen_urls = set()
    unique_matches = []
    for match in all_matches:
        url = match.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_matches.append(match)
    
    return unique_matches


if __name__ == "__main__":
    # Test the agent
    test_resume = """
    Senior Software Engineer with 5 years of Python experience.
    Expertise in ML, data pipelines, and cloud infrastructure (AWS).
    Built production RAG systems and LLM applications.
    """
    
    agent = JobSearchAgent(test_resume)
    
    print("🤖 LangChain Agent initialized!")
    print(f"📋 Available tools: {[t.name for t in agent.tools]}")
    
    # Test search
    print("\n🔍 Running test search...")
    matches = agent.search_and_match("Senior Python ML Engineer", max_results=10)
    
    print(f"\n✅ Found {len(matches)} matches!")
    if matches:
        print(f"\nTop match: {matches[0].get('title')} at {matches[0].get('company')}")
