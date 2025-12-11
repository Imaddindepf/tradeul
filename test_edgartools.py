"""
Test edgartools XBRL parsing for AAPL
"""
from edgar import Company, set_identity
import json

# Set identity (required by SEC)
set_identity("Tradeul Test test@tradeul.com")

# Get Apple's filings
print("=" * 60)
print("PROBANDO EDGARTOOLS CON AAPL")
print("=" * 60)

company = Company("AAPL")
print(f"\nCompañía: {company.name}")
print(f"CIK: {company.cik}")

# Get 10-K filings
filings_10k = company.get_filings(form="10-K")
print(f"\nFilings 10-K encontrados: {len(filings_10k)}")

# Get most recent 10-K
latest_10k = filings_10k[0]
print(f"\nÚltimo 10-K:")
print(f"  - Fecha: {latest_10k.filing_date}")
print(f"  - Accession: {latest_10k.accession_no}")

# Parse XBRL
print("\n" + "=" * 60)
print("PARSEANDO XBRL...")
print("=" * 60)

xbrl_data = latest_10k.xbrl()
print(f"\nTipo de objeto: {type(xbrl_data)}")

if xbrl_data:
    # Explore the structure
    print("\n" + "-" * 40)
    print("ATRIBUTOS DE XBRL DATA:")
    print("-" * 40)
    for attr in dir(xbrl_data):
        if not attr.startswith('_'):
            print(f"  {attr}")
    
    # List available statements
    print("\n" + "-" * 40)
    print("STATEMENTS DISPONIBLES:")
    print("-" * 40)
    
    statements = xbrl_data.statements
    print(f"Tipo de statements: {type(statements)}")
    print(f"\nStatements object:")
    print(statements)
    
    # Try to iterate
    print("\n" + "-" * 40)
    print("EXPLORANDO STATEMENTS:")
    print("-" * 40)
    
    # Check if it's iterable with names
    if hasattr(statements, 'names'):
        print("Nombres de statements:")
        for name in statements.names:
            print(f"  - {name}")
    
    # Try to get specific statements
    print("\n" + "=" * 60)
    print("BUSCANDO INCOME STATEMENT")
    print("=" * 60)
    
    # Try different approaches
    try:
        # Method 1: Direct access
        if hasattr(xbrl_data, 'income_statement'):
            print("Income Statement (directo):")
            print(xbrl_data.income_statement)
        
        # Method 2: get_statement
        if hasattr(xbrl_data, 'get_statement'):
            print("\nUsando get_statement:")
            stmt = xbrl_data.get_statement('income')
            if stmt:
                print(stmt)
        
        # Method 3: By name
        stmt_names = [
            "ConsolidatedStatementsOfOperations",
            "CONSOLIDATEDSTATEMENTSOFOPERATIONS"
        ]
        for name in stmt_names:
            try:
                stmt = statements[name] if hasattr(statements, '__getitem__') else None
                if stmt:
                    print(f"\nStatement '{name}':")
                    print(stmt)
                    break
            except:
                continue
                
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Explore instance/facts
    print("\n" + "=" * 60)
    print("EXPLORANDO FACTS (DATOS RAW)")
    print("=" * 60)
    
    if hasattr(xbrl_data, 'instance'):
        instance = xbrl_data.instance
        print(f"Tipo de instance: {type(instance)}")
        
        if hasattr(instance, 'facts'):
            facts = instance.facts
            print(f"Total facts: {len(facts)}")
            print(f"\nColumnas disponibles: {facts.columns.tolist()}")
            
            # Show sample facts
            print("\n" + "-" * 40)
            print("MUESTRA DE FACTS (primeros 15):")
            print("-" * 40)
            print(facts[['concept', 'value']].head(15).to_string())
            
            # Filter revenue facts
            print("\n" + "-" * 40)
            print("FACTS RELACIONADOS CON REVENUE:")
            print("-" * 40)
            revenue_facts = facts[facts['concept'].str.contains('Revenue|Sales|NetSales', case=False, regex=True)]
            if len(revenue_facts) > 0:
                print(revenue_facts[['concept', 'value']].head(20).to_string())
            else:
                print("No se encontraron facts de Revenue")
    
    # Explore presentation
    print("\n" + "=" * 60)
    print("EXPLORANDO PRESENTATION (ESTRUCTURA JERÁRQUICA)")
    print("=" * 60)
    
    if hasattr(xbrl_data, 'presentation'):
        presentation = xbrl_data.presentation
        print(f"Tipo de presentation: {type(presentation)}")
        print("\nPresentation:")
        print(presentation)
    
    # Explore labels
    print("\n" + "=" * 60)
    print("EXPLORANDO LABELS")
    print("=" * 60)
    
    if hasattr(xbrl_data, 'labels'):
        labels = xbrl_data.labels
        print(f"Tipo de labels: {type(labels)}")
        
        # Try to get a few labels
        concepts_to_check = [
            "us-gaap:Revenues",
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:NetIncomeLoss",
            "us-gaap:CostOfGoodsSold"
        ]
        
        for concept in concepts_to_check:
            try:
                if hasattr(labels, 'get_label'):
                    label = labels.get_label(concept)
                    print(f"  {concept} -> {label}")
                elif hasattr(labels, '__getitem__'):
                    label = labels[concept]
                    print(f"  {concept} -> {label}")
            except Exception as e:
                print(f"  {concept} -> Error: {e}")

else:
    print("No se pudo obtener datos XBRL")

print("\n" + "=" * 60)
print("FIN DE LA PRUEBA")
print("=" * 60)
