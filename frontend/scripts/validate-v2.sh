#!/bin/bash
# =============================================
# Validation Script for Architecture V2
# =============================================

set -e  # Exit on error

echo "🔍 Validating Architecture V2..."
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# =============================================
# 1. Check Dependencies
# =============================================
echo "📦 Checking dependencies..."

check_dependency() {
  local package=$1
  local version=$2
  
  if npm list "$package" 2>/dev/null | grep -q "$version"; then
    echo -e "${GREEN}✓${NC} $package@$version installed"
    return 0
  else
    echo -e "${RED}✗${NC} $package@$version missing"
    return 1
  fi
}

check_dependency "@tanstack/react-virtual" "3.13"
check_dependency "rxjs" "7.8"
check_dependency "zustand" "4.5"
echo ""

# =============================================
# 2. Check Files Exist
# =============================================
echo "📁 Checking required files..."

check_file() {
  local file=$1
  if [ -f "$file" ]; then
    echo -e "${GREEN}✓${NC} $file exists"
    return 0
  else
    echo -e "${RED}✗${NC} $file missing"
    return 1
  fi
}

check_file "stores/useTickersStore.ts"
check_file "hooks/useRxWebSocket.ts"
check_file "components/table/VirtualizedDataTable.tsx"
check_file "components/scanner/CategoryTableV2.tsx"
check_file "ARCHITECTURE_V2.md"
check_file "QUICKSTART_V2.md"
echo ""

# =============================================
# 3. TypeScript Compilation Check
# =============================================
echo "🔧 Running TypeScript check..."

if npx tsc --noEmit --skipLibCheck 2>&1 | grep -q "error TS"; then
  echo -e "${RED}✗${NC} TypeScript errors found"
  npx tsc --noEmit --skipLibCheck | grep "error TS" | head -n 10
  exit 1
else
  echo -e "${GREEN}✓${NC} No TypeScript errors"
fi
echo ""

# =============================================
# 4. ESLint Check (optional)
# =============================================
echo "🧹 Running ESLint..."

if npm run lint 2>&1 | grep -q "error"; then
  echo -e "${YELLOW}⚠${NC}  ESLint warnings found (non-blocking)"
else
  echo -e "${GREEN}✓${NC} No ESLint errors"
fi
echo ""

# =============================================
# 5. Build Test
# =============================================
echo "🏗️  Testing production build..."

if npm run build > /dev/null 2>&1; then
  echo -e "${GREEN}✓${NC} Production build successful"
else
  echo -e "${RED}✗${NC} Production build failed"
  exit 1
fi
echo ""

# =============================================
# 6. Bundle Size Analysis
# =============================================
echo "📊 Analyzing bundle size..."

# Get Next.js build output
BUILD_OUTPUT=$(npm run build 2>&1)

# Extract main bundle size
MAIN_SIZE=$(echo "$BUILD_OUTPUT" | grep "First Load JS" | head -n 1 | awk '{print $4}')

if [ -n "$MAIN_SIZE" ]; then
  echo -e "${GREEN}✓${NC} Main bundle: $MAIN_SIZE"
  
  # Check if bundle is reasonable (<500kB)
  SIZE_NUM=$(echo "$MAIN_SIZE" | sed 's/[^0-9.]//g')
  if (( $(echo "$SIZE_NUM < 500" | bc -l) )); then
    echo -e "${GREEN}✓${NC} Bundle size is optimal"
  else
    echo -e "${YELLOW}⚠${NC}  Bundle size is large (>500kB)"
  fi
else
  echo -e "${YELLOW}⚠${NC}  Could not determine bundle size"
fi
echo ""

# =============================================
# Summary
# =============================================
echo "================================"
echo -e "${GREEN}✅ All validations passed!${NC}"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Start dev server: npm run dev"
echo "2. Open http://localhost:3000/scanner-v2"
echo "3. Check console for RxJS logs"
echo "4. Monitor FPS with Chrome DevTools"
echo ""
echo "📚 Documentation:"
echo "- Architecture: ARCHITECTURE_V2.md"
echo "- Quick Start: QUICKSTART_V2.md"
echo ""

