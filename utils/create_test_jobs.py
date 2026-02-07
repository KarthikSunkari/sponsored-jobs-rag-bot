"""
Quick script to insert test jobs for pipeline testing.
"""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from rag.embedding_service import get_embedding_service

def create_test_jobs():
    """Create test jobs that match the user's resume."""
    client = get_supabase_client()
    embedding_service = get_embedding_service()
    
    # Test jobs matching user's skills
    test_jobs = [
        {
            "title": "Software Engineer II - Distributed Systems",
            "description": """
            We're looking for a mid-level Software Engineer with 3+ years of experience to join our team.
            
            Requirements:
            - 3+ years of software development experience
            - Strong proficiency in Java, Python, and Go
            - Experience with distributed systems and microservices architecture
            - Knowledge of AWS, Kubernetes, and Docker
            - Experience with SQL and NoSQL databases (PostgreSQL, DynamoDB)
            - Strong understanding of system design and scalability
            
            Nice to have:
            - Experience with React and TypeScript
            - Knowledge of CI/CD pipelines
            - Previous work at high-growth startups
            
            We offer H-1B sponsorship for qualified candidates.
            """,
            "location": "New York, NY (Hybrid)",
            "company": "Amazon",
            "url": "https://example.com/job/amazon-sde2",
            "source": "test"
        },
        {
            "title": "Backend Engineer - Cloud Infrastructure",
            "description": """
            Join our infrastructure team to build scalable cloud services.
            
            Requirements:
            - BS/MS in Computer Science or related field
            - 2-4 years of backend development experience
            - Proficiency in Python, Java, or Go
            - Experience with AWS services (EC2, S3, Lambda, DynamoDB)
            - Knowledge of Kubernetes and container orchestration
            - Strong problem-solving skills
            
            Bonus:
            - Experience with Terraform or CloudFormation
            - Knowledge of monitoring tools (Datadog, Prometheus)
            - Open source contributions
            
            Visa sponsorship available.
            """,
            "location": "Seattle, WA",
            "company": "Stripe",
            "url": "https://example.com/job/stripe-backend",
            "source": "test"
        },
        {
            "title": "Full Stack Engineer - Early Career",
            "description": """
            We're hiring early career engineers to work on our customer-facing products.
            
            Requirements:
            - 1-3 years of professional experience
            - Strong JavaScript/TypeScript skills
            - Experience with React or similar frontend frameworks
            - Backend experience with Node.js, Python, or Java
            - Understanding of RESTful APIs and databases
            
            Nice to have:
            - Experience with Next.js or similar frameworks
            - Knowledge of GraphQL
            - AWS or GCP experience
            
            We sponsor H-1B visas.
            """,
            "location": "San Francisco, CA",
            "company": "Airbnb",
            "url": "https://example.com/job/airbnb-fullstack",
            "source": "test"
        },
        {
            "title": "Machine Learning Engineer",
            "description": """
            Build ML models and infrastructure for our recommendation systems.
            
            Requirements:
            - MS/PhD in Computer Science, Statistics, or related field
            - 2+ years of ML engineering experience
            - Strong Python skills with ML frameworks (TensorFlow, PyTorch)
            - Experience with distributed computing (Spark, Ray)
            - Knowledge of ML ops and model deployment
            
            Preferred:
            - Experience with recommendation systems
            - Knowledge of NLP or computer vision
            - Publications in top-tier conferences
            
            Sponsorship provided.
            """,
            "location": "Remote (US)",
            "company": "Netflix",
            "url": "https://example.com/job/netflix-ml",
            "source": "test"
        },
        {
            "title": "Site Reliability Engineer",
            "description": """
            Ensure reliability and performance of our global infrastructure.
            
            Requirements:
            - 3+ years of SRE or DevOps experience
            - Strong Linux/Unix administration skills
            - Experience with Kubernetes and Docker
            - Proficiency in Python, Go, or similar languages
            - Knowledge of monitoring and observability tools
            - Experience with incident management
            
            Bonus:
            - On-call experience
            - Experience with Terraform
            - Knowledge of networking and security
            
            H-1B sponsorship available.
            """,
            "location": "Austin, TX",
            "company": "Google",
            "url": "https://example.com/job/google-sre",
            "source": "test"
        }
    ]
    
    # Company sponsorship data
    companies = {
        "Amazon": {"total_approvals": 8921, "approval_rate": 88.7},
        "Stripe": {"total_approvals": 456, "approval_rate": 92.3},
        "Airbnb": {"total_approvals": 234, "approval_rate": 89.5},
        "Netflix": {"total_approvals": 178, "approval_rate": 91.2},
        "Google": {"total_approvals": 12456, "approval_rate": 94.1}
    }
    
    print("Creating test companies and jobs...")
    print("=" * 60)
    
    saved_count = 0
    for job_data in test_jobs:
        # Create or get company
        company_name = job_data["company"]
        company_info = companies.get(company_name, {})
        
        existing_company = client.get_company_by_name(company_name)
        if not existing_company:
            company_record = {
                "employer_name": company_name,
                "total_approvals": company_info.get("total_approvals", 0),
                "total_denials": 0,
                "h1b_approvals": company_info.get("total_approvals", 0),
                "approval_rate": company_info.get("approval_rate", 0)
            }
            company = client.insert_company(company_record)
            company_id = company['id']
        else:
            company_id = existing_company['id']
        
        # Create job
        import hashlib
        url_hash = hashlib.md5(job_data["url"].encode()).hexdigest()
        
        # Check if exists
        existing = client.client.table("jobs").select("id").eq("url_hash", url_hash).execute()
        if existing.data:
            print(f"⏭️  Job already exists: {job_data['title']}")
            continue
        
        job_record = {
            "company_id": company_id,
            "title": job_data["title"],
            "description": job_data["description"],
            "location": job_data["location"],
            "job_url": job_data["url"],
            "url_hash": url_hash,
            "source": job_data["source"],
            "is_active": True
        }
        
        job = client.insert_job(job_record)
        job_id = job['id']
        
        # Generate embedding
        job_text = f"{job_data['title']} {job_data['description']}"
        embedding = embedding_service.encode(job_text)
        client.insert_job_embedding(job_id, embedding)
        
        sponsorship_note = f" [🟢 {company_info.get('total_approvals', 0)} approvals, {company_info.get('approval_rate', 0):.1f}% rate]"
        print(f"✅ Created: {job_data['title']} at {company_name}{sponsorship_note}")
        saved_count += 1
    
    print("=" * 60)
    print(f"✅ Created {saved_count} test jobs")
    print("\nNow run:")
    print("  python3 rag/match_jobs.py")
    print("  python3 agents/notifier.py")

if __name__ == "__main__":
    create_test_jobs()
