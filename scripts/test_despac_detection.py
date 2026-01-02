#!/usr/bin/env python3
"""
Script para probar diferentes métodos de detección de de-SPACs
Usando Kodiak AI (KDK) como caso de prueba
"""

import asyncio
import httpx
import os
import json
import re
from typing import Optional, Dict, Any

# Cargar variables de entorno
FMP_API_KEY = os.environ.get("FMP_API_KEY", os.environ.get("fmp_api_key"))
SEC_API_KEY = os.environ.get("SEC_API_IO", os.environ.get("sec_api_io"))

TICKER = "KDK"  # Kodiak AI - sabemos que es un de-SPAC

print(f"=" * 60)
print(f"PRUEBA DE DETECCIÓN DE-SPAC PARA: {TICKER}")
print(f"=" * 60)
print(f"FMP_API_KEY: {'✓ Configurada' if FMP_API_KEY else '✗ No encontrada'}")
print(f"SEC_API_KEY: {'✓ Configurada' if SEC_API_KEY else '✗ No encontrada'}")
print()


async def test_method_1_fmp_description():
    """
    MÉTODO 1: Verificar descripción de FMP
    Buscar palabras clave como "SPAC", "merger", "business combination"
    """
    print("-" * 60)
    print("MÉTODO 1: Descripción de FMP")
    print("-" * 60)
    
    if not FMP_API_KEY:
        print("❌ FMP_API_KEY no configurada")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            url = f"https://financialmodelingprep.com/api/v3/profile/{TICKER}?apikey={FMP_API_KEY}"
            resp = await client.get(url)
            
            if resp.status_code == 200:
                data = resp.json()
                if data and len(data) > 0:
                    profile = data[0]
                    description = profile.get("description", "")
                    company_name = profile.get("companyName", "")
                    industry = profile.get("industry", "")
                    sector = profile.get("sector", "")
                    ipo_date = profile.get("ipoDate", "")
                    
                    print(f"Empresa: {company_name}")
                    print(f"Industria: {industry}")
                    print(f"Sector: {sector}")
                    print(f"IPO Date: {ipo_date}")
                    print(f"Descripción (primeros 500 chars):")
                    print(f"  {description[:500]}...")
                    print()
                    
                    # Buscar palabras clave de SPAC/de-SPAC
                    spac_keywords = [
                        r'\bspac\b',
                        r'special purpose acquisition',
                        r'business combination',
                        r'went public through',
                        r'merged with',
                        r'de-spac',
                        r'reverse merger',
                        r'blank check'
                    ]
                    
                    desc_lower = description.lower()
                    found_keywords = []
                    for kw in spac_keywords:
                        if re.search(kw, desc_lower):
                            found_keywords.append(kw)
                    
                    if found_keywords:
                        print(f"✅ DETECTADO: Palabras clave encontradas: {found_keywords}")
                        return True
                    else:
                        print(f"❌ NO DETECTADO: No se encontraron palabras clave de SPAC en descripción")
                        return False
                else:
                    print(f"❌ No hay datos para {TICKER}")
                    return None
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def test_method_2_sec_8k_filings():
    """
    MÉTODO 2: Buscar 8-K con Item 2.01 (Completion of Acquisition)
    """
    print("-" * 60)
    print("MÉTODO 2: SEC 8-K Filings (Item 2.01)")
    print("-" * 60)
    
    if not SEC_API_KEY:
        print("❌ SEC_API_KEY no configurada")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Buscar 8-K filings para el ticker
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{TICKER} AND formType:"8-K"'
                    }
                },
                "from": "0",
                "size": "20",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            url = f"https://api.sec-api.io?token={SEC_API_KEY}"
            resp = await client.post(url, json=query)
            
            if resp.status_code == 200:
                data = resp.json()
                filings = data.get('filings', [])
                
                print(f"Encontrados {len(filings)} 8-K filings")
                
                # Buscar filings con items relacionados a merger
                merger_filings = []
                for filing in filings:
                    items = filing.get('items', [])
                    description = filing.get('description', '')
                    filed_at = filing.get('filedAt', '')
                    
                    # Item 2.01 = Completion of Acquisition
                    # Item 5.01 = Changes in Control
                    # Item 3.03 = Material Modification to Rights of Security Holders
                    merger_items = ['2.01', '5.01', '3.03']
                    
                    for item in items:
                        if any(mi in item for mi in merger_items):
                            merger_filings.append({
                                'date': filed_at,
                                'items': items,
                                'description': description[:100]
                            })
                            break
                
                if merger_filings:
                    print(f"✅ DETECTADO: {len(merger_filings)} filings con items de merger:")
                    for mf in merger_filings[:3]:  # Mostrar primeros 3
                        print(f"   - {mf['date']}: Items {mf['items']}")
                    return True
                else:
                    print(f"❌ NO DETECTADO: No hay 8-K con items de merger")
                    return False
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def test_method_3_sec_full_text_search():
    """
    MÉTODO 3: Búsqueda de texto completo en filings
    """
    print("-" * 60)
    print("MÉTODO 3: SEC Full-Text Search")
    print("-" * 60)
    
    if not SEC_API_KEY:
        print("❌ SEC_API_KEY no configurada")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Buscar filings que mencionen "business combination" o "SPAC"
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{TICKER} AND ("business combination" OR "SPAC merger" OR "de-SPAC")'
                    }
                },
                "from": "0",
                "size": "10",
                "sort": [{"filedAt": {"order": "desc"}}]
            }
            
            url = f"https://api.sec-api.io?token={SEC_API_KEY}"
            resp = await client.post(url, json=query)
            
            if resp.status_code == 200:
                data = resp.json()
                filings = data.get('filings', [])
                total = data.get('total', {}).get('value', 0)
                
                print(f"Total de filings encontrados: {total}")
                
                if filings:
                    print(f"✅ DETECTADO: Filings que mencionan SPAC/merger:")
                    for f in filings[:5]:
                        print(f"   - {f.get('filedAt')}: {f.get('formType')} - {f.get('companyName', '')[:50]}")
                    return True
                else:
                    print(f"❌ NO DETECTADO: No hay filings que mencionen SPAC/merger")
                    return False
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def test_method_4_sec_s4_f4_filings():
    """
    MÉTODO 4: Buscar S-4 o F-4 (Registration for business combination)
    """
    print("-" * 60)
    print("MÉTODO 4: SEC S-4/F-4 Filings")
    print("-" * 60)
    
    if not SEC_API_KEY:
        print("❌ SEC_API_KEY no configurada")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Buscar S-4 o F-4 filings
            query = {
                "query": {
                    "query_string": {
                        "query": f'ticker:{TICKER} AND (formType:"S-4" OR formType:"F-4" OR formType:"DEFM14A")'
                    }
                },
                "from": "0",
                "size": "10"
            }
            
            url = f"https://api.sec-api.io?token={SEC_API_KEY}"
            resp = await client.post(url, json=query)
            
            if resp.status_code == 200:
                data = resp.json()
                filings = data.get('filings', [])
                
                if filings:
                    print(f"✅ DETECTADO: {len(filings)} filings de merger (S-4/F-4/DEFM14A):")
                    for f in filings[:5]:
                        print(f"   - {f.get('filedAt')}: {f.get('formType')} - {f.get('companyName', '')[:50]}")
                    return True
                else:
                    print(f"❌ NO DETECTADO: No hay S-4/F-4/DEFM14A filings")
                    return False
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def test_method_5_check_former_ticker():
    """
    MÉTODO 5: Verificar si el ticker anterior (AACT) era un SPAC
    """
    print("-" * 60)
    print("MÉTODO 5: Buscar SPAC original (AACT)")
    print("-" * 60)
    
    if not SEC_API_KEY:
        print("❌ SEC_API_KEY no configurada")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Buscar el SPAC original - Ares Acquisition Corporation II
            query = {
                "query": {
                    "query_string": {
                        "query": 'ticker:AACT OR companyName:"Ares Acquisition Corporation"'
                    }
                },
                "from": "0",
                "size": "5"
            }
            
            url = f"https://api.sec-api.io?token={SEC_API_KEY}"
            resp = await client.post(url, json=query)
            
            if resp.status_code == 200:
                data = resp.json()
                filings = data.get('filings', [])
                
                if filings:
                    print(f"✅ DETECTADO: SPAC original encontrado:")
                    for f in filings[:3]:
                        print(f"   - {f.get('filedAt')}: {f.get('formType')} - {f.get('companyName', '')[:60]}")
                        print(f"     CIK: {f.get('cik')}")
                    return True
                else:
                    print(f"❌ NO DETECTADO: No se encontró AACT")
                    return False
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def test_method_6_sec_edgar_company_info():
    """
    MÉTODO 6: Verificar info de la empresa en SEC EDGAR
    """
    print("-" * 60)
    print("MÉTODO 6: SEC EDGAR Company Info")
    print("-" * 60)
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Primero necesitamos el CIK
            headers = {'User-Agent': 'TradeUL/1.0 (support@tradeul.com)'}
            
            # Buscar tickers en SEC
            tickers_url = "https://www.sec.gov/files/company_tickers.json"
            resp = await client.get(tickers_url, headers=headers)
            
            if resp.status_code == 200:
                tickers_data = resp.json()
                
                # Buscar el CIK para KDK
                cik = None
                for key, val in tickers_data.items():
                    if val.get('ticker') == TICKER:
                        cik = str(val.get('cik_str')).zfill(10)
                        print(f"CIK encontrado: {cik}")
                        print(f"Nombre en SEC: {val.get('title')}")
                        break
                
                if cik:
                    # Obtener datos completos de la empresa
                    company_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
                    resp2 = await client.get(company_url, headers=headers)
                    
                    if resp2.status_code == 200:
                        company_data = resp2.json()
                        
                        name = company_data.get('name')
                        sic = company_data.get('sic')
                        sic_desc = company_data.get('sicDescription')
                        former_names = company_data.get('formerNames', [])
                        
                        print(f"Nombre actual: {name}")
                        print(f"SIC Code: {sic} ({sic_desc})")
                        print(f"Nombres anteriores: {former_names}")
                        
                        # Verificar si algún nombre anterior era un SPAC
                        spac_keywords = ['acquisition', 'blank check', 'spac', 'merger']
                        
                        for former in former_names:
                            former_name = former.get('name', '').lower()
                            if any(kw in former_name for kw in spac_keywords):
                                print(f"✅ DETECTADO: Nombre anterior era SPAC: {former.get('name')}")
                                return True
                        
                        print(f"❌ NO DETECTADO: Ningún nombre anterior indica SPAC")
                        return False
                else:
                    print(f"❌ No se encontró CIK para {TICKER}")
                    return None
            else:
                print(f"❌ Error HTTP: {resp.status_code}")
                return None
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return None


async def main():
    results = {}
    
    # Ejecutar todas las pruebas
    results['FMP Description'] = await test_method_1_fmp_description()
    print()
    
    results['SEC 8-K Items'] = await test_method_2_sec_8k_filings()
    print()
    
    results['SEC Full-Text Search'] = await test_method_3_sec_full_text_search()
    print()
    
    results['SEC S-4/F-4'] = await test_method_4_sec_s4_f4_filings()
    print()
    
    results['SPAC Original (AACT)'] = await test_method_5_check_former_ticker()
    print()
    
    results['SEC EDGAR formerNames'] = await test_method_6_sec_edgar_company_info()
    print()
    
    # Resumen
    print("=" * 60)
    print("RESUMEN DE RESULTADOS")
    print("=" * 60)
    for method, result in results.items():
        status = "✅ Funciona" if result == True else "❌ No funciona" if result == False else "⚠️ Error/No disponible"
        print(f"  {method}: {status}")
    
    print()
    print("RECOMENDACIÓN:")
    working_methods = [k for k, v in results.items() if v == True]
    if working_methods:
        print(f"  Métodos que funcionan: {', '.join(working_methods)}")
    else:
        print("  Ningún método detectó el de-SPAC automáticamente")


if __name__ == "__main__":
    asyncio.run(main())

