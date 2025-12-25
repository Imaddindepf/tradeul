#!/usr/bin/env python3
"""
Script para inicializar las tablas de mapeo XBRL → Canonical.

Ejecutar desde dentro del contenedor:
    docker exec financials python scripts/init_mapping_tables.py

O directamente:
    python services/financials/scripts/init_mapping_tables.py
"""

import asyncio
import os
import sys

# Añadir path del servicio
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mapping.database import MappingRepository, XBRLMapping
from services.mapping.schema import (
    CANONICAL_FIELDS, 
    XBRL_TO_CANONICAL,
    XBRL_CONCEPT_GROUPS,
    FASB_XBRL_LABELS
)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Initialize mapping tables and populate with initial data."""
    
    # Build connection URL from environment
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "tradeul")
    user = os.getenv("POSTGRES_USER", "tradeul_user")
    password = os.getenv("POSTGRES_PASSWORD", "tradeul_password_secure_123")
    
    database_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    logger.info(f"Connecting to PostgreSQL at {host}:{port}/{db}")
    
    repo = MappingRepository(database_url)
    
    try:
        # 1. Create tables
        logger.info("Creating tables...")
        await repo.initialize_tables()
        logger.info("✓ Tables created successfully")
        
        # 2. Populate canonical fields
        logger.info("Populating canonical fields...")
        field_count = 0
        for key, field in CANONICAL_FIELDS.items():
            await repo.upsert_canonical_field(
                key=key,
                label=field["label"],
                section=field.get("section", "Other"),
                statement_type=field.get("statement", "income"),
                order=field.get("order", 999),
                data_type=field.get("data_type", "monetary"),
                indent=field.get("indent", 0),
                is_subtotal=field.get("is_subtotal", False),
                calculated=field.get("calculated", False),
                importance=field.get("importance", 100)
            )
            field_count += 1
        logger.info(f"✓ Populated {field_count} canonical fields")
        
        # 3. Populate direct mappings
        logger.info("Populating direct XBRL mappings...")
        mapping_count = 0
        for xbrl_concept, canonical_key in XBRL_TO_CANONICAL.items():
            await repo.add_mapping(
                xbrl_concept=xbrl_concept,
                canonical_key=canonical_key,
                confidence=1.0,
                source="manual",
                statement_type="income"  # Default, could be inferred
            )
            mapping_count += 1
        logger.info(f"✓ Populated {mapping_count} direct mappings")
        
        # 4. Populate concept group mappings
        logger.info("Populating concept group mappings...")
        group_count = 0
        for xbrl_concept, canonical_key in XBRL_CONCEPT_GROUPS.items():
            # Skip if already exists
            existing = await repo.get_mapping(xbrl_concept)
            if not existing:
                await repo.add_mapping(
                    xbrl_concept=xbrl_concept,
                    canonical_key=canonical_key,
                    confidence=0.95,
                    source="regex",
                    statement_type="income"
                )
                group_count += 1
        logger.info(f"✓ Populated {group_count} concept group mappings")
        
        # 5. Populate FASB labels (if they exist)
        fasb_count = 0
        if FASB_XBRL_LABELS:
            logger.info("Populating FASB label mappings...")
            for xbrl_concept, data in FASB_XBRL_LABELS.items():
                if isinstance(data, dict) and "canonical" in data:
                    existing = await repo.get_mapping(xbrl_concept)
                    if not existing:
                        await repo.add_mapping(
                            xbrl_concept=xbrl_concept,
                            canonical_key=data["canonical"],
                            confidence=0.9,
                            source="fasb",
                            statement_type=data.get("statement", "income")
                        )
                        fasb_count += 1
            logger.info(f"✓ Populated {fasb_count} FASB label mappings")
        
        # 6. Stats
        logger.info("\n" + "="*50)
        logger.info("MAPPING DATABASE INITIALIZED")
        logger.info("="*50)
        logger.info(f"  Canonical fields: {field_count}")
        logger.info(f"  Direct mappings:  {mapping_count}")
        logger.info(f"  Group mappings:   {group_count}")
        if FASB_XBRL_LABELS:
            logger.info(f"  FASB mappings:    {fasb_count}")
        logger.info("="*50)
        
    except Exception as e:
        logger.error(f"Error initializing tables: {e}")
        raise
    finally:
        await repo.disconnect()


if __name__ == "__main__":
    asyncio.run(main())

