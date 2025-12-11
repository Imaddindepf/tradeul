"""
Test edgartools XBRL parsing for GOOGL - Compare with SEC-API
"""
from edgar import Company, set_identity
import json

# Set identity (required by SEC)
set_identity("Tradeul Test test@tradeul.com")

print("=" * 80)
print("EDGARTOOLS - GOOGL (Alphabet Inc.)")
print("=" * 80)

company = Company("GOOGL")
print(f"\nCompañía: {company.name}")
print(f"CIK: {company.cik}")

# Get 10-K filings
filings_10k = company.get_filings(form="10-K")
latest_10k = filings_10k[0]
print(f"\nÚltimo 10-K: {latest_10k.filing_date}")

# Parse XBRL
print("\nParseando XBRL...")
xbrl_data = latest_10k.xbrl()

if xbrl_data:
    # ============================================
    # INCOME STATEMENT
    # ============================================
    print("\n" + "=" * 80)
    print("1. INCOME STATEMENT (Statement of Operations)")
    print("=" * 80)
    
    try:
        income_stmt = xbrl_data.get_statement('income')
        if income_stmt:
            print(income_stmt)
    except Exception as e:
        print(f"Error: {e}")
        # Try alternative
        try:
            for stmt in xbrl_data.statements:
                stmt_str = str(stmt).lower()
                if 'income' in stmt_str or 'operation' in stmt_str:
                    print(f"\nEncontrado: {stmt}")
                    break
        except:
            pass

    # ============================================
    # BALANCE SHEET
    # ============================================
    print("\n" + "=" * 80)
    print("2. BALANCE SHEET")
    print("=" * 80)
    
    try:
        balance_stmt = xbrl_data.get_statement('balance')
        if balance_stmt:
            print(balance_stmt)
    except Exception as e:
        print(f"Error: {e}")

    # ============================================
    # CASH FLOW STATEMENT
    # ============================================
    print("\n" + "=" * 80)
    print("3. CASH FLOW STATEMENT")
    print("=" * 80)
    
    try:
        cashflow_stmt = xbrl_data.get_statement('cash')
        if cashflow_stmt:
            print(cashflow_stmt)
    except Exception as e:
        print(f"Error: {e}")

    # ============================================
    # ESTRUCTURA DETALLADA (Para comparar jerarquía)
    # ============================================
    print("\n" + "=" * 80)
    print("4. ESTRUCTURA JERÁRQUICA DEL INCOME STATEMENT")
    print("=" * 80)
    
    try:
        income_stmt = xbrl_data.get_statement('income')
        if income_stmt and hasattr(income_stmt, 'data'):
            for item in income_stmt.data[:25]:  # Primeros 25 items
                level = item.get('level', 0)
                indent = "  " * level
                label = item.get('label', 'N/A')
                concept = item.get('concept', 'N/A')
                is_abstract = item.get('is_abstract', False)
                has_values = item.get('has_values', False)
                
                marker = "[HEADER]" if is_abstract else "[DATA]" if has_values else "[EMPTY]"
                print(f"{indent}{marker} {label}")
                print(f"{indent}       concept: {concept}")
    except Exception as e:
        print(f"Error explorando estructura: {e}")
        import traceback
        traceback.print_exc()

else:
    print("No se pudo obtener datos XBRL")

print("\n" + "=" * 80)
print("FIN")
print("=" * 80)

