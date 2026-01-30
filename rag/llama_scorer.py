"""
Llama-3 integration for resume-job matching and scoring.
"""
import os
from typing import Dict, Optional
from llama_cpp import Llama
from dotenv import load_dotenv

load_dotenv()


class LlamaScorer:
    """Llama-3 based job relevance scorer."""
    
    def __init__(self):
        """Initialize Llama model."""
        model_path = os.getenv("LLAMA_MODEL_PATH", "./models/llama-3-8b-instruct-q4_0.gguf")
        n_ctx = int(os.getenv("LLAMA_N_CTX", "4096"))
        n_gpu_layers = int(os.getenv("LLAMA_N_GPU_LAYERS", "0"))
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(
                f"Llama model not found at {model_path}. "
                f"Please download it first using: "
                f"huggingface-cli download TheBloke/Llama-3-8B-Instruct-GGUF"
            )
        
        print(f"Loading Llama model from {model_path}...")
        self.llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            verbose=False
        )
        print("Llama model loaded successfully")
    
    def score_job_match(
        self, 
        resume_text: str, 
        job_title: str, 
        job_description: str,
        company_name: str
    ) -> Dict[str, any]:
        """
        Score how well a resume matches a job posting.
        
        Returns:
            Dict with 'score' (0-100) and 'reasoning' (str)
        """
        prompt = f"""You are an expert career advisor. Analyze how well this resume matches the job posting.

Resume:
{resume_text[:2000]}  # Truncate to fit context

Job Title: {job_title}
Company: {company_name}
Job Description:
{job_description[:1500]}

Provide:
1. A relevance score from 0-100 (where 100 is perfect match)
2. Brief reasoning (2-3 sentences)

Format your response as:
SCORE: <number>
REASONING: <explanation>
"""
        
        response = self.llm(
            prompt,
            max_tokens=256,
            temperature=0.3,
            stop=["</s>", "\n\n\n"]
        )
        
        output = response["choices"][0]["text"].strip()
        
        # Parse response
        score = 0
        reasoning = ""
        
        try:
            lines = output.split("\n")
            for line in lines:
                if line.startswith("SCORE:"):
                    score = int(line.replace("SCORE:", "").strip())
                elif line.startswith("REASONING:"):
                    reasoning = line.replace("REASONING:", "").strip()
        except Exception as e:
            print(f"Error parsing Llama response: {e}")
            reasoning = output[:200]
        
        return {
            "score": min(max(score, 0), 100),  # Clamp to 0-100
            "reasoning": reasoning
        }


# Singleton instance
_llama_scorer: Optional[LlamaScorer] = None


def get_llama_scorer() -> LlamaScorer:
    """Get or create Llama scorer singleton."""
    global _llama_scorer
    if _llama_scorer is None:
        _llama_scorer = LlamaScorer()
    return _llama_scorer
