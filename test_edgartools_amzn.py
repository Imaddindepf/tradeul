"""
Test edgartools XBRL parsing for AMZN - Full comparison
"""
from edgar import Company, set_identity

set_identity("Tradeul Test test@tradeul.com")

print("=" * 100)
print("EDGARTOOLS - AMZN (Amazon.com Inc.)")
print("=" * 100)

company = Company("AMZN")
print(f"Compañía: {company.name}")
print(f"CIK: {company.cik}")

# Get 10-K filings
filings_10k = company.get_filings(form="10-K")
print(f"\nTotal 10-K filings disponibles: {len(filings_10k)}")

# Get latest 10-K
latest_10k = filings_10k[0]
print(f"\nÚltimo 10-K: {latest_10k.filing_date}")

xbrl_data = latest_10k.xbrl()

if xbrl_data:
    # List all statements
    print("\n" + "=" * 100)
    print("STATEMENTS DISPONIBLES:")
    print("=" * 100)
    print(xbrl_data.statements)
    
    # INCOME STATEMENT
    print("\n" + "=" * 100)
    print("INCOME STATEMENT")
    print("=" * 100)
    
    try:
        income = xbrl_data.get_statement('income')
        if income:
            print(income)
    except Exception as e:
        print(f"Error: {e}")
    
    # BALANCE SHEET
    print("\n" + "=" * 100)
    print("BALANCE SHEET")
    print("=" * 100)
    
    try:
        balance = xbrl_data.get_statement('balance')
        if balance:
            print(balance)
    except Exception as e:
        print(f"Error: {e}")
    
    # CASH FLOW
    print("\n" + "=" * 100)
    print("CASH FLOW STATEMENT")
    print("=" * 100)
    
    try:
        cashflow = xbrl_data.get_statement('cash')
        if cashflow:
            print(cashflow)
    except Exception as e:
        print(f"Error: {e}")

print("\n" + "=" * 100)
print("FIN")
print("=" * 100)
