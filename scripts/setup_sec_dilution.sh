#!/bin/bash
# Setup script for SEC Dilution Profile System

set -e

echo "🚀 Setting up SEC Dilution Profile System..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 1. Check if .env has GROK_API_KEY
echo "📝 Step 1: Checking GROK_API_KEY..."
if grep -q "GROK_API_KEY" .env 2>/dev/null; then
    echo -e "${GREEN}✓ GROK_API_KEY found in .env${NC}"
else
    echo -e "${YELLOW}⚠ GROK_API_KEY not found in .env${NC}"
    echo "Please add GROK_API_KEY to your .env file:"
    echo "GROK_API_KEY=your_grok_api_key_here"
    echo ""
fi

# 2. Run SQL migration
echo ""
echo "📊 Step 2: Running database migration..."
docker exec -i tradeul_timescaledb psql -U tradeul_user -d tradeul < scripts/init_sec_dilution_profiles.sql

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Database migration completed successfully${NC}"
else
    echo -e "${YELLOW}⚠ Database migration may have errors (check above)${NC}"
fi

# 3. Rebuild dilution-tracker service
echo ""
echo "🔨 Step 3: Rebuilding dilution-tracker service..."
docker-compose up -d --build dilution-tracker

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dilution-tracker service rebuilt and started${NC}"
else
    echo "❌ Failed to rebuild dilution-tracker service"
    exit 1
fi

# 4. Wait for service to be healthy
echo ""
echo "⏳ Step 4: Waiting for service to be ready..."
sleep 5

# Test health endpoint
if curl -f http://localhost:8009/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Service is healthy and responding${NC}"
else
    echo -e "${YELLOW}⚠ Service may not be responding yet${NC}"
fi

# 5. Test a sample ticker
echo ""
echo "🧪 Step 5: Testing with sample ticker (AAPL)..."
echo "This may take 10-30 seconds on first request..."

response=$(curl -s -w "\n%{http_code}" http://localhost:8009/api/sec-dilution/AAPL/profile)
http_code=$(echo "$response" | tail -n 1)
body=$(echo "$response" | sed '$d')

if [ "$http_code" == "200" ]; then
    echo -e "${GREEN}✓ SEC dilution profile endpoint working!${NC}"
    echo "Sample response:"
    echo "$body" | jq '.profile.ticker, .dilution_analysis.total_potential_dilution_pct' 2>/dev/null || echo "$body"
elif [ "$http_code" == "404" ]; then
    echo -e "${YELLOW}⚠ No dilution data found for AAPL (this may be normal)${NC}"
else
    echo -e "${YELLOW}⚠ Received HTTP $http_code${NC}"
fi

echo ""
echo "=============================================="
echo -e "${GREEN}✅ Setup Complete!${NC}"
echo "=============================================="
echo ""
echo "📚 Next steps:"
echo "1. Open http://localhost:3000/dilution-tracker"
echo "2. Search for a ticker (e.g., SOUN, TSLA, AAPL)"
echo "3. Go to the Dilution tab"
echo "4. Scroll down to see SEC Dilution Profile section"
echo ""
echo "📖 Documentation: services/dilution-tracker/README_SEC_DILUTION.md"
echo ""
echo "🔗 API Endpoints:"
echo "  - Profile: http://localhost:8009/api/sec-dilution/{TICKER}/profile"
echo "  - Warrants: http://localhost:8009/api/sec-dilution/{TICKER}/warrants"
echo "  - ATM: http://localhost:8009/api/sec-dilution/{TICKER}/atm-offerings"
echo "  - Shelf: http://localhost:8009/api/sec-dilution/{TICKER}/shelf-registrations"
echo "  - Docs: http://localhost:8009/docs"
echo ""

