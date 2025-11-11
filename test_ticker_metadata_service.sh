#!/bin/bash

################################################################################
# Test Script - Ticker Metadata Service
# Pruebas manuales del nuevo servicio
################################################################################

echo "════════════════════════════════════════════════════════════════════════════"
echo "TESTING: ticker-metadata-service"
echo "════════════════════════════════════════════════════════════════════════════"
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base URLs
METADATA_SERVICE="http://localhost:8010"
API_GATEWAY="http://localhost:8000"

# Símbolos de prueba
TEST_SYMBOLS=("AAPL" "TSLA" "NVDA" "INVALID_SYM")

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

print_test() {
    echo -e "${YELLOW}▶ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

check_service() {
    local url=$1
    local name=$2
    
    if curl -s -f "$url" > /dev/null 2>&1; then
        print_success "$name is running"
        return 0
    else
        print_error "$name is NOT running"
        return 1
    fi
}

################################################################################
# Pre-flight Checks
################################################################################

print_header "1. PRE-FLIGHT CHECKS"

print_test "Checking Redis..."
if docker exec tradeul_redis redis-cli ping > /dev/null 2>&1; then
    print_success "Redis is running"
else
    print_error "Redis is NOT running"
    echo "Run: docker-compose up -d redis"
    exit 1
fi

print_test "Checking TimescaleDB..."
if docker exec tradeul_timescale pg_isready -U tradeul_user > /dev/null 2>&1; then
    print_success "TimescaleDB is running"
else
    print_error "TimescaleDB is NOT running"
    echo "Run: docker-compose up -d timescaledb"
    exit 1
fi

print_test "Checking ticker-metadata service..."
check_service "$METADATA_SERVICE/health" "Ticker Metadata Service"
METADATA_RUNNING=$?

print_test "Checking api-gateway..."
check_service "$API_GATEWAY/health" "API Gateway"
GATEWAY_RUNNING=$?

if [ $METADATA_RUNNING -ne 0 ] && [ $GATEWAY_RUNNING -ne 0 ]; then
    print_error "Both services are down. Start them with:"
    echo "docker-compose up -d ticker_metadata api_gateway"
    exit 1
fi

################################################################################
# Test 1: Health Checks
################################################################################

print_header "2. HEALTH CHECKS"

if [ $METADATA_RUNNING -eq 0 ]; then
    print_test "GET $METADATA_SERVICE/health"
    response=$(curl -s "$METADATA_SERVICE/health")
    echo "$response" | jq '.' 2>/dev/null || echo "$response"
    
    if echo "$response" | jq -e '.status == "healthy"' > /dev/null 2>&1; then
        print_success "Health check passed"
    else
        print_error "Health check failed"
    fi
fi

################################################################################
# Test 2: Metadata Endpoints
################################################################################

print_header "3. METADATA ENDPOINTS"

if [ $METADATA_RUNNING -eq 0 ]; then
    for symbol in "${TEST_SYMBOLS[@]}"; do
        print_test "GET $METADATA_SERVICE/api/v1/metadata/$symbol"
        
        response=$(curl -s -w "\n%{http_code}" "$METADATA_SERVICE/api/v1/metadata/$symbol")
        http_code=$(echo "$response" | tail -n1)
        body=$(echo "$response" | sed '$d')
        
        if [ "$http_code" = "200" ]; then
            print_success "✓ $symbol: HTTP $http_code"
            echo "$body" | jq -r '"\(.company_name) | \(.sector) | \(.exchange)"' 2>/dev/null
        elif [ "$http_code" = "404" ]; then
            print_error "✗ $symbol: HTTP $http_code (Not Found - Expected for INVALID_SYM)"
        else
            print_error "✗ $symbol: HTTP $http_code"
        fi
        
        sleep 0.5
    done
else
    print_error "Metadata service not running, skipping tests"
fi

################################################################################
# Test 3: Company Endpoints
################################################################################

print_header "4. COMPANY ENDPOINTS"

if [ $METADATA_RUNNING -eq 0 ]; then
    print_test "GET $METADATA_SERVICE/api/v1/company/AAPL"
    
    response=$(curl -s "$METADATA_SERVICE/api/v1/company/AAPL")
    echo "$response" | jq '.' 2>/dev/null
    
    if echo "$response" | jq -e '.symbol' > /dev/null 2>&1; then
        print_success "Company profile retrieved"
    else
        print_error "Company profile failed"
    fi
fi

################################################################################
# Test 4: Statistics Endpoints
################################################################################

print_header "5. STATISTICS ENDPOINTS"

if [ $METADATA_RUNNING -eq 0 ]; then
    print_test "GET $METADATA_SERVICE/api/v1/statistics/AAPL"
    
    response=$(curl -s "$METADATA_SERVICE/api/v1/statistics/AAPL")
    echo "$response" | jq '.' 2>/dev/null
    
    if echo "$response" | jq -e '.market_cap' > /dev/null 2>&1; then
        print_success "Statistics retrieved"
    else
        print_error "Statistics failed"
    fi
fi

################################################################################
# Test 5: Service Stats
################################################################################

print_header "6. SERVICE STATISTICS"

if [ $METADATA_RUNNING -eq 0 ]; then
    print_test "GET $METADATA_SERVICE/api/v1/metadata/stats/service"
    
    response=$(curl -s "$METADATA_SERVICE/api/v1/metadata/stats/service")
    echo "$response" | jq '.' 2>/dev/null
    
    if echo "$response" | jq -e '.cache_hit_rate' > /dev/null 2>&1; then
        print_success "Service stats retrieved"
    else
        print_error "Service stats failed"
    fi
fi

################################################################################
# Test 6: API Gateway Integration
################################################################################

print_header "7. API GATEWAY INTEGRATION"

if [ $GATEWAY_RUNNING -eq 0 ]; then
    print_test "GET $API_GATEWAY/api/v1/ticker/AAPL/metadata"
    
    response=$(curl -s -w "\n%{http_code}" "$API_GATEWAY/api/v1/ticker/AAPL/metadata")
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        print_success "✓ API Gateway integration working: HTTP $http_code"
        echo "$body" | jq -r '"\(.company_name) | \(.sector)"' 2>/dev/null
        
        if [ $METADATA_RUNNING -eq 0 ]; then
            print_success "Using ticker-metadata-service"
        else
            print_success "Using fallback (DB direct)"
        fi
    else
        print_error "✗ API Gateway failed: HTTP $http_code"
    fi
fi

################################################################################
# Test 7: Cache Check
################################################################################

print_header "8. CACHE VERIFICATION"

print_test "Checking Redis cache..."

cache_keys=$(docker exec tradeul_redis redis-cli KEYS "ticker:metadata:*" 2>/dev/null)

if [ -n "$cache_keys" ]; then
    count=$(echo "$cache_keys" | wc -l)
    print_success "Found $count cached entries"
    echo "$cache_keys" | head -5
    
    if [ "$count" -gt 5 ]; then
        echo "... (showing first 5)"
    fi
else
    print_error "No cache entries found (expected after first requests)"
fi

################################################################################
# Test 8: Fallback Behavior
################################################################################

print_header "9. FALLBACK BEHAVIOR TEST"

if [ $METADATA_RUNNING -eq 0 ] && [ $GATEWAY_RUNNING -eq 0 ]; then
    print_test "Testing with metadata service running..."
    
    response1=$(curl -s "$API_GATEWAY/api/v1/ticker/TSLA/metadata")
    if echo "$response1" | jq -e '.symbol' > /dev/null 2>&1; then
        print_success "✓ Request successful with service"
    fi
    
    print_test "Simulating service failure (would need to stop service manually)"
    echo "To test fallback: docker-compose stop ticker_metadata"
    echo "Then: curl http://localhost:8000/api/v1/ticker/TSLA/metadata"
    echo "Should still work using DB fallback"
fi

################################################################################
# Test 9: Performance Check
################################################################################

print_header "10. PERFORMANCE CHECK"

if [ $METADATA_RUNNING -eq 0 ]; then
    print_test "Running 10 requests to measure performance..."
    
    total_time=0
    for i in {1..10}; do
        start=$(date +%s%N)
        curl -s "$METADATA_SERVICE/api/v1/metadata/AAPL" > /dev/null
        end=$(date +%s%N)
        elapsed=$(( ($end - $start) / 1000000 ))
        total_time=$(( $total_time + $elapsed ))
        echo -n "."
    done
    echo ""
    
    avg_time=$(( $total_time / 10 ))
    
    if [ $avg_time -lt 100 ]; then
        print_success "✓ Average latency: ${avg_time}ms (EXCELLENT)"
    elif [ $avg_time -lt 500 ]; then
        print_success "✓ Average latency: ${avg_time}ms (GOOD)"
    else
        print_error "✗ Average latency: ${avg_time}ms (SLOW)"
    fi
fi

################################################################################
# Summary
################################################################################

print_header "11. SUMMARY"

echo ""
echo "Test completed!"
echo ""
echo "Next steps:"
echo "1. Check docker logs: docker logs -f tradeul_ticker_metadata"
echo "2. Test from frontend: http://localhost:3000/scanner"
echo "3. Click on a symbol to open metadata modal"
echo ""
echo "If everything works:"
echo "  git checkout main"
echo "  git merge feature/ticker-metadata-service"
echo "  git push origin main"
echo ""
echo "If something fails:"
echo "  See: services/ROLLBACK_PLAN.txt"
echo ""

################################################################################
# End
################################################################################

