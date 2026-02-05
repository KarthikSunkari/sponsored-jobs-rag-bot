"""
Groq API Client for ultra-low latency Llama-3 inference.
Replaces local llama.cpp with cloud-based inference (FREE tier: 30 req/min).
"""

import os
import time
from typing import Optional, Dict, Any
from groq import Groq
from dotenv import load_dotenv

load_dotenv()


class GroqClient:
    """Client for Groq API with retry logic and rate limiting."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "llama-3.1-8b-instant",
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize Groq client.
        
        Args:
            api_key: Groq API key (defaults to GROQ_API_KEY env var)
            model: Model to use (llama-3.1-8b-instant for speed)
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
        """
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY not found in environment variables")
        
        self.client = Groq(api_key=self.api_key)
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs
    ) -> str:
        """
        Generate text using Groq API with retry logic.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments for chat completion
            
        Returns:
            Generated text
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
                return response.choices[0].message.content
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    print(f"Groq API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff
                else:
                    raise Exception(f"Groq API failed after {self.max_retries} attempts: {e}")
    
    def score_job_relevance(
        self,
        job_description: str,
        resume_text: str,
        job_title: str,
        company: str
    ) -> Dict[str, Any]:
        """
        Score job relevance using Llama-3 via Groq.
        
        Args:
            job_description: Full job description
            resume_text: User's resume text
            job_title: Job title
            company: Company name
            
        Returns:
            Dict with score (0-100), reasoning, and key_matches
        """
        system_prompt = """You are an expert job matching AI. Analyze job-resume fit and return a JSON response with:
{
  "score": <0-100 integer>,
  "reasoning": "<2-3 sentence explanation>",
  "key_matches": ["<skill/experience match 1>", "<match 2>", "<match 3>"]
}"""
        
        user_prompt = f"""Job Title: {job_title}
Company: {company}

Job Description:
{job_description[:2000]}  # Truncate to avoid token limits

Resume:
{resume_text[:2000]}

Rate this job's relevance to the resume (0-100). Focus on:
1. Required skills match
2. Experience level alignment
3. Domain/industry fit
4. Career progression potential"""

        try:
            response = self.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,  # Lower temperature for consistent scoring
                max_tokens=512
            )
            
            # Parse JSON response
            import json
            result = json.loads(response)
            return {
                "score": int(result.get("score", 0)),
                "reasoning": result.get("reasoning", ""),
                "key_matches": result.get("key_matches", [])
            }
            
        except Exception as e:
            print(f"Error scoring job: {e}")
            return {"score": 0, "reasoning": f"Error: {str(e)}", "key_matches": []}
    
    def test_connection(self) -> bool:
        """Test Groq API connection."""
        try:
            response = self.generate("Say 'OK' if you can read this.", max_tokens=10)
            return "OK" in response.upper()
        except Exception as e:
            print(f"Connection test failed: {e}")
            return False


if __name__ == "__main__":
    # Test the client
    client = GroqClient()
    
    if client.test_connection():
        print("✅ Groq API connection successful!")
        
        # Test job scoring
        test_result = client.score_job_relevance(
            job_description="Senior Python Engineer with ML experience. Build scalable data pipelines.",
            resume_text="5 years Python, ML engineer, built ETL pipelines with Airflow and Spark.",
            job_title="Senior ML Engineer",
            company="Tech Corp"
        )
        print(f"\n📊 Test Score: {test_result['score']}/100")
        print(f"💡 Reasoning: {test_result['reasoning']}")
    else:
        print("❌ Groq API connection failed. Check your API key.")
