"""
Smart notification system - sends daily digest of high-quality matches.
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
from datetime import datetime
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from utils.supabase_client import get_supabase_client
from utils.job_location import assess_us_job_location
from dotenv import load_dotenv

load_dotenv()


def format_match_email(matches: List[Dict]) -> str:
    """Format matches into HTML email."""
    html_parts = ["""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; }}
            .match {{ 
                border: 1px solid #ddd; 
                padding: 15px; 
                margin: 10px 0; 
                border-radius: 5px;
            }}
            .score {{ 
                color: #2ecc71; 
                font-weight: bold; 
                font-size: 18px;
            }}
            .company {{ color: #3498db; }}
            .title {{ font-size: 16px; font-weight: bold; }}
            .reasoning {{ 
                color: #666; 
                font-style: italic; 
                margin-top: 10px;
            }}
        </style>
    </head>
    <body>
        <h2>🎯 Your Daily Job Matches</h2>
        <p>Found {count} high-quality sponsored job matches for you!</p>
    """.format(count=len(matches))]
    
    for i, match in enumerate(matches, 1):
        title = match.get('title', 'N/A')
        employer = match.get('employer_name', 'N/A')
        location = match.get('location', 'N/A')
        score = match.get('llama_score', 0)
        profile = match.get('resume_profile', 'Default')
        approval_rate = match.get('approval_rate', 0)
        reasoning = match.get('llama_reasoning', 'No reasoning available')
        job_url = match.get('job_url', '#')
        
        match_html = """
        <div class="match">
            <div class="title">{num}. {title}</div>
            <div class="company">🏢 {employer}</div>
            <div>👤 Resume profile: {profile}</div>
            <div>📍 {location}</div>
            <div class="score">⭐ Match Score: {score}/100</div>
            <div>✅ Sponsorship Approval Rate: {rate:.1f}%</div>
            <div class="reasoning">💡 {reasoning}</div>
            <div style="margin-top: 10px;">
                <a href="{url}" style="color: #3498db;">View Job →</a>
            </div>
        </div>
        """.format(
            num=i,
            title=title,
            employer=employer,
            profile=profile,
            location=location,
            score=score,
            rate=approval_rate,
            reasoning=reasoning,
            url=job_url
        )
        html_parts.append(match_html)
    
    html_parts.append("""
    </body>
    </html>
    """)
    
    return ''.join(html_parts)


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send email notification."""
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    
    if not smtp_user or not smtp_password:
        print("SMTP credentials not configured. Skipping email notification.")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = smtp_user
        msg['To'] = to_email
        
        html_part = MIMEText(html_content, 'html')
        msg.attach(html_part)
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        
        print(f"✅ Email sent to {to_email}")
        return True
        
    except Exception as e:
        print(f"Error sending email: {e}")
        import traceback
        traceback.print_exc()
        return False


def send_daily_digest():
    """Send daily digest of unnotified high-quality matches."""
    client = get_supabase_client()
    
    # Get unnotified matches with score >= 80
    min_score = int(os.getenv("MIN_RELEVANCE_SCORE", "80"))
    matches = client.get_unnotified_matches(min_score=min_score)

    eligible_matches = []
    for match in matches:
        eligible, reason = assess_us_job_location(
            match.get("location", ""),
            match.get("description", ""),
        )
        if eligible:
            eligible_matches.append(match)
        else:
            print(
                f"Skipping non-US notification: {match.get('title', 'Untitled')} "
                f"({match.get('location', 'unknown')}) — {reason}"
            )
    matches = eligible_matches
    
    if not matches:
        print("No new high-quality matches to notify.")
        return
    
    print(f"Found {len(matches)} new matches to notify")
    
    # Format and send email
    notification_email = os.getenv("NOTIFICATION_EMAIL")
    if not notification_email:
        print("NOTIFICATION_EMAIL not configured")
        return
    
    subject = f"🎯 {len(matches)} New Sponsored Job Matches - {datetime.now().strftime('%Y-%m-%d')}"
    html_content = format_match_email(matches)
    
    if send_email(notification_email, subject, html_content):
        # Mark as notified
        match_ids = [m['id'] for m in matches]
        client.mark_as_notified(match_ids)
        print(f"Marked {len(match_ids)} matches as notified")


if __name__ == "__main__":
    send_daily_digest()
