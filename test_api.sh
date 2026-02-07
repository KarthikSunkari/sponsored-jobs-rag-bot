#!/bin/bash
# Test script for Google Custom Search API + Job Scraper
# Tests both locally and in Docker to ensure production readiness

set -e

echo "=========================================="
echo "Google Custom Search API Test Suite"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Check API credentials
echo -e "\n${YELLOW}[1/5] Checking API credentials...${NC}"
if grep -q "GOOGLE_SEARCH_API_KEY" .env && grep -q "GOOGLE_SEARCH_ENGINE_ID" .env; then
    echo -e "${GREEN}✅ API credentials found in .env${NC}"
else
    echo -e "${RED}❌ API credentials missing in .env${NC}"
    exit 1
fi

# Test 2: Test API connectivity
echo -e "\n${YELLOW}[2/5] Testing API connectivity...${NC}"
python3 -c "
import os
from dotenv import load_dotenv
import requests

load_dotenv()
api_key = os.getenv('GOOGLE_SEARCH_API_KEY')
search_id = os.getenv('GOOGLE_SEARCH_ENGINE_ID')

url = f'https://www.googleapis.com/customsearch/v1?key={api_key}&cx={search_id}&q=test'
r = requests.get(url)

if r.status_code == 200:
    print('✅ API is working!')
    print(f'   Found {len(r.json().get(\"items\", []))} results')
    exit(0)
elif r.status_code == 403:
    print('⚠️  API still propagating (403 Forbidden)')
    print('   Wait a few more minutes and try again')
    exit(1)
else:
    print(f'❌ API error: {r.status_code}')
    print(f'   {r.text[:200]}')
    exit(1)
"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ API connectivity test passed${NC}"
else
    echo -e "${YELLOW}⚠️  API not ready yet, will use Selenium fallback${NC}"
fi

# Test 3: Test job search
echo -e "\n${YELLOW}[3/5] Testing job search (3 jobs)...${NC}"
python3 utils/google_search.py

# Test 4: Test full scraper (local)
echo -e "\n${YELLOW}[4/5] Testing full scraper locally...${NC}"
python3 etl/scrape_jobs.py --level newgrad --max-jobs 3

# Test 5: Test in Docker (production simulation)
echo -e "\n${YELLOW}[5/5] Testing in Docker (production simulation)...${NC}"

if command -v docker &> /dev/null; then
    echo "Building Docker image..."
    docker build -t jobs-scraper-test . > /dev/null 2>&1
    
    echo "Running scraper in Docker..."
    docker run --env-file .env jobs-scraper-test python etl/scrape_jobs.py --level newgrad --max-jobs 3
    
    echo -e "${GREEN}✅ Docker test passed${NC}"
else
    echo -e "${YELLOW}⚠️  Docker not running, skipping Docker test${NC}"
    echo "   (Docker test will run in GitHub Actions)"
fi

echo -e "\n=========================================="
echo -e "${GREEN}✅ All tests completed!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Push to GitHub"
echo "2. Add secrets to GitHub Actions"
echo "3. Enable Actions workflow"
echo "4. Monitor first automated run"
