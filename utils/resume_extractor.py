"""
Resume text extractor utility.
Extracts text from resume image and stores in Supabase.
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from rag.embedding_service import get_embedding_service


def extract_resume_from_image():
    """Extract resume text from the uploaded image."""
    # Resume text extracted from the uploaded image
    resume_text = """
KARTHIK SUNKARI
+1 (929) 722-6585 • karthiksunkari23@gmail.com • linkedin.com/in/karthik-sunkari • github.com/karthikSunkari

PROFESSIONAL SUMMARY
Software Engineer with 3+ years of experience building scalable, available and highly reliable distributed systems at Amazon and Observe.AI. Proven track record of full-SDLC ownership, operational excellence, and delivering customer-centric product innovations. MSCS at NYU (May 2026), specializing in Distributed Systems and Cloud Architecture.

EDUCATION
New York University                                                                Sep 2024 - May 2026
Master of Science in Computer Science (3.9/4)                                      New York, USA
Coursework: Algorithms, Information Security and Privacy, Machine Learning, Cloud Computing and Big Data, Deep Learning

Indian Institute of Technology, Bhubaneswar                                        July 2017 - May 2021
Bachelor of Technology in Computer Science (3.7/4)                                 Odisha, India
Coursework: Data Structures, Operating Systems, Computer Networks, Compilers, Computer Architecture, Software Engineering

TECHNICAL SKILLS
Programming Languages: Java, Python, SQL, C/C++, Go, TypeScript, Bash
Frameworks & Libraries: Spring Boot, Django, Next.js, React, PyTest, JUnit, PyTorch
Infra & Tools: AWS, Kubernetes, Docker, Terraform, Kafka, Jenkins, Prometheus, Grafana
Data: PostgreSQL, pgvector, MongoDB, Redis, Supabase, OpenSearch, Spark
Concepts: Distributed Systems, Microservices, Event-Driven Architecture, CI/CD, REST/GraphQL APIs, System Design

INDUSTRY EXPERIENCE

Bohamo                                                                             May 2025 – Aug 2025
Software Engineering Intern                                                        New York, USA
• Designed and built a unified automated reservation intake workflow for multiple non-PMS hotel clients by integrating Google Apps Script for email preprocessing and Supabase Edge Functions with Regex and GPT-4o Mini to consume reservation details
• Engineered a real-time, event-driven integration with Oracle OPERA Cloud PMS and RoomMaster with the help of Streaming APIs and Webhooks to asynchronously sync reservations across 9 enterprise hotels with sub-second reservation delays

Observe.AI                                                                         Oct 2023 – June 2024
Software Development Engineer                                                      Bangalore, India
• Developed a custom API Gateway plugin to intercept and route 50k+ daily requests directly to microservices, bypassing the legacy monolith without client-side changes; improved API response times by 8%
• Optimized resource-intensive API through MongoDB bulk operations and chunification, significantly reducing database network calls that resulted in a 90% reduction in p95 latency; stress tested and benchmarked performance using Apache JMeter
• Built real-time monitoring dashboards with Prometheus and Grafana for 10 Kubernetes clusters, which tracked metrics like request latency, error rates, and throughput that helped in early detection of issues and provided visibility

Amazon (Ship With Amazon)                                                          July 2021 – Aug 2023
Software Development Engineer                                                      Hyderabad, India
• Developed a backward-compatible vehicle validation engine that supports 100,000+ daily shipping labels across NA/EU regions, where I decoupled routing logic to enable dynamic, warehouse-specific configurations for vehicle type and weight
• Spearheaded the design and launch of the Logistics Container Enrollment program that onboarded 30+ enterprise shippers and saw a daily volume of 5,000 shipments within 1 month of P0 launch. Owned the full SDLC from design to production and drove P0 across various stakeholders in different time zones; shippers expressed a 20% improvement in packing efficiency
• Architected the decomposition of legacy monolith into event-driven microservices using AWS CDK to define infrastructure-as-Code for Lambda, VPC, and DynamoDB resources, achieving zero-downtime migration and increasing deployment velocity by 20%
• Championed Operational Excellence with the help of automating remediation scripts for production incidents, reducing weekly ticket volume by 25% that helped reduce Sev-2 outages during peak logistics seasons

PROJECT EXPERIENCE

GrubDash - Serverless Food Delivery Platform (AWS Lambda, SQS, OpenSearch, Stripe, Webhooks)        GrubDash
• Architected an event-driven system using SQS FIFO queues with exactly-once delivery and idempotent state machines for ordered order and delivery flows capable of handling 300 TPS; I provisioned the entire stack via Terraform with auto-scaling capabilities
• Delivered intelligent search and personalized menus using OpenSearch and AWS Personalize with sub-100ms response times and real-time, context-aware filtering across 1+ restaurants; integrated Stripe Checkout for P0-compliant and highly available payments

Autonomous Cloud Control Plane on AWS EKS (Python, Kubernetes, Helm, Prometheus, AlertManager)      Control-Plane
• Orchestrated a high-availability infrastructure on AWS EKS, configuring Rolling Update strategies (maxSurge/maxUnavailable) to ensure zero-downtime deployments during version upgrades
• Engineered a self-healing observability pipeline using Prometheus and Helm; implemented custom liveness and readiness probes to automatically detect zombie processes and trigger pod restarts without human intervention
• Built a critical incident response system by integrating AlertManager with Slack Webhooks, configuring custom rules to dispatch real-time P0 alerts for probe failures and cluster instability

AWARDS AND ACHIEVEMENTS
• Awarded the Customer Obsession accolade at Amazon for outstanding contributions to the Containers Program
"""
    
    return resume_text.strip()


def upload_resume_to_supabase(resume_text: str):
    """Upload resume to Supabase with embedding."""
    print("Generating resume embedding...")
    embedding_service = get_embedding_service()
    embedding = embedding_service.encode(resume_text)
    
    print("Uploading resume to Supabase...")
    client = get_supabase_client()
    
    # Extract skills from resume
    skills = [
        "Java", "Python", "SQL", "C/C++", "Go", "TypeScript", "Bash",
        "Spring Boot", "Django", "Next.js", "React", "PyTest", "JUnit", "PyTorch",
        "AWS", "Kubernetes", "Docker", "Terraform", "Kafka", "Jenkins", "Prometheus", "Grafana",
        "PostgreSQL", "pgvector", "MongoDB", "Redis", "Supabase", "OpenSearch", "Spark",
        "Distributed Systems", "Microservices", "Event-Driven Architecture", "CI/CD", 
        "REST/GraphQL APIs", "System Design"
    ]
    
    # Check if resume already exists
    existing = client.client.table("user_resume").select("*").limit(1).execute()
    
    if existing.data:
        # Update existing resume
        result = client.client.table("user_resume").update({
            "resume_text": resume_text,
            "embedding": embedding,
            "skills": skills,
            "experience_years": 3
        }).eq("id", existing.data[0]["id"]).execute()
        print(f"✅ Updated existing resume (ID: {existing.data[0]['id']})")
    else:
        # Insert new resume
        result = client.client.table("user_resume").insert({
            "resume_text": resume_text,
            "embedding": embedding,
            "skills": skills,
            "experience_years": 3
        }).execute()
        print(f"✅ Inserted new resume (ID: {result.data[0]['id']})")
    
    return result.data[0] if result.data else None


if __name__ == "__main__":
    print("=" * 60)
    print("Resume Extractor")
    print("=" * 60)
    
    # Extract resume text
    print("\n[1/2] Extracting resume text...")
    resume_text = extract_resume_from_image()
    print(f"✅ Extracted {len(resume_text)} characters")
    
    # Upload to Supabase
    print("\n[2/2] Uploading to Supabase...")
    result = upload_resume_to_supabase(resume_text)
    
    if result:
        print("\n" + "=" * 60)
        print("✅ Resume successfully uploaded!")
        print(f"Resume ID: {result['id']}")
        print(f"Skills: {len(result['skills'])} skills extracted")
        print(f"Experience: {result['experience_years']} years")
        print("=" * 60)
    else:
        print("\n❌ Failed to upload resume")
