#!/usr/bin/env python3
"""
Download all required datasets for News Alpha Engine.
Run this FIRST before any training.

Usage:
    python scripts/download_datasets.py
    python scripts/download_datasets.py --only fingpt
    python scripts/download_datasets.py --skip-large
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table
from rich import print as rprint

console = Console()


# ============================================
# Dataset Definitions
# ============================================

DATASETS = {
    "fingpt_sentiment": {
        "source": "huggingface",
        "dataset_id": "FinGPT/fingpt-sentiment-train",
        "description": "76K financial sentiment samples (Apache 2.0)",
        "size_mb": 50,
        "required": True,
    },
    "twitter_financial": {
        "source": "huggingface",
        "dataset_id": "zeroshot/twitter-financial-news-sentiment",
        "description": "500K financial tweets with sentiment",
        "size_mb": 200,
        "required": True,
    },
    "financial_phrasebank": {
        "source": "huggingface",
        "dataset_id": "financial_phrasebank",
        "subset": "sentences_allagree",
        "description": "4.8K expert-labeled financial phrases",
        "size_mb": 5,
        "required": False,  # Non-commercial license
    },
    "finbert_model": {
        "source": "huggingface_model",
        "model_id": "ProsusAI/finbert",
        "description": "Pre-trained FinBERT model",
        "size_mb": 440,
        "required": True,
    },
    "sentence_transformers": {
        "source": "huggingface_model",
        "model_id": "sentence-transformers/all-MiniLM-L6-v2",
        "description": "Fast sentence embeddings (backup)",
        "size_mb": 90,
        "required": False,
    },
}


def check_huggingface_auth():
    """Check if user is logged into HuggingFace."""
    try:
        from huggingface_hub import HfApi
        api = HfApi()
        user = api.whoami()
        console.print(f"[green]✓[/green] Logged into HuggingFace as: {user['name']}")
        return True
    except Exception:
        console.print("[yellow]⚠[/yellow] Not logged into HuggingFace (some datasets may require login)")
        console.print("   Run: [cyan]huggingface-cli login[/cyan]")
        return False


def download_huggingface_dataset(dataset_id: str, subset: str = None, output_dir: Path = None):
    """Download a dataset from HuggingFace."""
    from datasets import load_dataset
    
    console.print(f"   Downloading [cyan]{dataset_id}[/cyan]...")
    
    try:
        if subset:
            dataset = load_dataset(dataset_id, subset)
        else:
            dataset = load_dataset(dataset_id)
        
        # Save to disk
        if output_dir:
            output_path = output_dir / dataset_id.replace("/", "_")
            dataset.save_to_disk(str(output_path))
            console.print(f"   [green]✓[/green] Saved to {output_path}")
        
        # Print info
        console.print(f"   [dim]Samples: {sum(len(split) for split in dataset.values())}[/dim]")
        
        return dataset
        
    except Exception as e:
        console.print(f"   [red]✗[/red] Failed: {e}")
        return None


def download_huggingface_model(model_id: str, output_dir: Path = None):
    """Download a model from HuggingFace."""
    from transformers import AutoTokenizer, AutoModel
    
    console.print(f"   Downloading [cyan]{model_id}[/cyan]...")
    
    try:
        # Download tokenizer and model
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModel.from_pretrained(model_id)
        
        # Save locally
        if output_dir:
            output_path = output_dir / model_id.replace("/", "_")
            tokenizer.save_pretrained(str(output_path))
            model.save_pretrained(str(output_path))
            console.print(f"   [green]✓[/green] Saved to {output_path}")
        
        return True
        
    except Exception as e:
        console.print(f"   [red]✗[/red] Failed: {e}")
        return False


def check_polygon_data(polygon_path: Path):
    """Check if Polygon price data is available."""
    console.print("\n[bold]Checking Polygon Price Data...[/bold]")
    
    if not polygon_path.exists():
        console.print(f"[red]✗[/red] Polygon data not found at {polygon_path}")
        console.print("   Make sure your polygon_data volume is mounted correctly")
        return False
    
    # Count parquet files
    parquet_files = list(polygon_path.glob("**/*.parquet"))
    
    if len(parquet_files) == 0:
        console.print(f"[red]✗[/red] No parquet files found in {polygon_path}")
        return False
    
    console.print(f"[green]✓[/green] Found {len(parquet_files)} price data files")
    
    # Check date range
    try:
        import polars as pl
        sample_file = parquet_files[0]
        df = pl.read_parquet(sample_file)
        console.print(f"   [dim]Sample file: {sample_file.name}[/dim]")
        console.print(f"   [dim]Columns: {df.columns}[/dim]")
    except Exception as e:
        console.print(f"   [yellow]⚠[/yellow] Could not read sample file: {e}")
    
    return True


def create_sample_news_data(output_path: Path):
    """Create sample news data structure for testing."""
    console.print("\n[bold]Creating sample news data structure...[/bold]")
    
    import json
    
    sample_news = [
        {
            "news_id": "sample_001",
            "timestamp": "2024-01-15T09:30:00Z",
            "source": "benzinga",
            "headline": "XYZ Pharma Receives FDA Breakthrough Therapy Designation for Cancer Drug",
            "body": "XYZ Pharma announced today that the FDA has granted Breakthrough Therapy designation...",
            "tickers": ["XYZ"],
            "author": "John Doe",
            "url": "https://example.com/news/001",
        },
        {
            "news_id": "sample_002",
            "timestamp": "2024-01-15T10:15:00Z",
            "source": "benzinga",
            "headline": "ABC Corp Reports Q4 Earnings Beat, Raises Full Year Guidance",
            "body": "ABC Corporation reported fourth quarter earnings of $1.50 per share...",
            "tickers": ["ABC"],
            "author": "Jane Smith",
            "url": "https://example.com/news/002",
        },
        {
            "news_id": "sample_003",
            "timestamp": "2024-01-15T11:00:00Z",
            "source": "benzinga",
            "headline": "DEF Inc Announces $50M ATM Offering",
            "body": "DEF Inc filed a prospectus supplement for an at-the-market offering...",
            "tickers": ["DEF"],
            "author": "Bob Johnson",
            "url": "https://example.com/news/003",
        },
    ]
    
    output_path.mkdir(parents=True, exist_ok=True)
    sample_file = output_path / "sample_news.json"
    
    with open(sample_file, "w") as f:
        json.dump(sample_news, f, indent=2)
    
    console.print(f"[green]✓[/green] Created sample news at {sample_file}")
    console.print("   [dim]Replace with your actual Benzinga/Polygon news data[/dim]")


def main():
    parser = argparse.ArgumentParser(description="Download datasets for News Alpha Engine")
    parser.add_argument("--only", type=str, help="Download only specific dataset")
    parser.add_argument("--skip-large", action="store_true", help="Skip large downloads")
    parser.add_argument("--output-dir", type=str, default="/opt/tradeul/services/news-alpha-engine/data/raw",
                        help="Output directory for datasets")
    parser.add_argument("--polygon-path", type=str, default="/data/polygon",
                        help="Path to Polygon price data")
    
    args = parser.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print("\n" + "="*60)
    console.print("[bold blue]NEWS ALPHA ENGINE - Dataset Downloader[/bold blue]")
    console.print("="*60 + "\n")
    
    # Show what we'll download
    table = Table(title="Datasets to Download")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Size", justify="right")
    table.add_column("Required", justify="center")
    
    for name, info in DATASETS.items():
        if args.only and args.only != name:
            continue
        if args.skip_large and info["size_mb"] > 100:
            continue
        table.add_row(
            name,
            info["description"],
            f"{info['size_mb']} MB",
            "✓" if info["required"] else "○"
        )
    
    console.print(table)
    console.print()
    
    # Check HuggingFace auth
    check_huggingface_auth()
    
    # Download each dataset
    console.print("\n[bold]Downloading Datasets...[/bold]")
    
    results = {}
    
    for name, info in DATASETS.items():
        if args.only and args.only != name:
            continue
        if args.skip_large and info["size_mb"] > 100:
            console.print(f"\n[yellow]⏭[/yellow] Skipping {name} (large file)")
            continue
        
        console.print(f"\n[bold]{name}[/bold]")
        
        if info["source"] == "huggingface":
            result = download_huggingface_dataset(
                info["dataset_id"],
                info.get("subset"),
                output_dir
            )
            results[name] = result is not None
            
        elif info["source"] == "huggingface_model":
            result = download_huggingface_model(
                info["model_id"],
                output_dir / "models"
            )
            results[name] = result
    
    # Check Polygon data
    check_polygon_data(Path(args.polygon_path))
    
    # Create sample news structure
    create_sample_news_data(output_dir / "news")
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]Download Summary[/bold]")
    console.print("="*60)
    
    for name, success in results.items():
        status = "[green]✓[/green]" if success else "[red]✗[/red]"
        console.print(f"  {status} {name}")
    
    console.print(f"\n[dim]Data saved to: {output_dir}[/dim]")
    console.print("\n[bold green]Next step:[/bold green] Run [cyan]python scripts/prepare_labels.py[/cyan]")


if __name__ == "__main__":
    main()

