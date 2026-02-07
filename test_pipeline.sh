#!/bin/bash

# End-to-End Test Pipeline for Jobs Bot
# This script tests the complete workflow from setup to job matching

set -e  # Exit on error

echo "======================================================================"
echo "Jobs Bot - End-to-End Test Pipeline"
echo "======================================================================"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Change to project directory
cd "$(dirname "$0")"

echo ""
echo "${YELLOW}[Step 1/7] Checking Prerequisites${NC}"
echo "----------------------------------------------------------------------"

# Check if .env exists
if [ ! -f .env ]; then
    echo "${RED}❌ .env file not found!${NC}"
    echo "Please create .env file with your credentials"
    exit 1
fi

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "${RED}❌ Python 3 not found!${NC}"
    exit 1
fi

echo "${GREEN}✅ Prerequisites check passed${NC}"

echo ""
echo "${YELLOW}[Step 2/7] Installing Dependencies${NC}"
echo "----------------------------------------------------------------------"
pip install -q -r requirements.txt
echo "${GREEN}✅ Dependencies installed${NC}"

echo ""
echo "${YELLOW}[Step 3/7] Testing Supabase Connection${NC}"
echo "----------------------------------------------------------------------"
python3 -c "from utils.supabase_client import get_supabase_client; client = get_supabase_client(); print('✅ Supabase connected successfully')"

echo ""
echo "${YELLOW}[Step 4/7] Testing Groq API Connection${NC}"
echo "----------------------------------------------------------------------"
python3 agents/groq_client.py

echo ""
echo "${YELLOW}[Step 5/7] Uploading Resume to Database${NC}"
echo "----------------------------------------------------------------------"
python3 utils/resume_extractor.py

echo ""
echo "${YELLOW}[Step 6/7] Scraping Jobs (10 New Grad + 10 Mid-Level)${NC}"
echo "----------------------------------------------------------------------"
echo "Scraping New Grad jobs..."
python3 etl/scrape_jobs.py --level newgrad --max-jobs 10

echo ""
echo "Scraping Mid-Level jobs..."
python3 etl/scrape_jobs.py --level midlevel --max-jobs 10

echo ""
echo "${YELLOW}[Step 7/7] Running Job Matching Pipeline${NC}"
echo "----------------------------------------------------------------------"
python3 rag/match_jobs.py

echo ""
echo "======================================================================"
echo "${GREEN}✅ End-to-End Test Completed Successfully!${NC}"
echo "======================================================================"
echo ""
echo "Next steps:"
echo "1. Check your email (sanji14916@gmail.com) for job notifications"
echo "2. View matches in Supabase dashboard"
echo "3. Run 'python agents/notifier.py' to send email digest"
echo ""
