#!/usr/bin/env python3
"""
Run the complete training pipeline.

This script runs all training steps in sequence:
1. Download datasets
2. Prepare labels (CAR calculation)
3. Train FinBERT encoder
4. Train BERTopic model
5. Train Impact Predictor
6. Run backtest

Usage:
    python scripts/run_full_pipeline.py
    python scripts/run_full_pipeline.py --skip-download
    python scripts/run_full_pipeline.py --only backtest
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

console = Console()

PROJECT_ROOT = Path(__file__).parent.parent


def run_step(name: str, command: list, skip: bool = False) -> bool:
    """Run a pipeline step."""
    
    if skip:
        console.print(f"[yellow]⏭ Skipping: {name}[/yellow]")
        return True
    
    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold blue]STEP: {name}[/bold blue]")
    console.print(f"[bold blue]{'='*60}[/bold blue]\n")
    
    start_time = datetime.now()
    
    try:
        result = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            check=True,
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        console.print(f"\n[green]✓ {name} completed in {duration:.1f}s[/green]")
        return True
        
    except subprocess.CalledProcessError as e:
        console.print(f"\n[red]✗ {name} failed with exit code {e.returncode}[/red]")
        return False
    except Exception as e:
        console.print(f"\n[red]✗ {name} failed: {e}[/red]")
        return False


def main():
    parser = argparse.ArgumentParser(description="Run full training pipeline")
    parser.add_argument("--skip-download", action="store_true", help="Skip dataset download")
    parser.add_argument("--skip-labels", action="store_true", help="Skip label preparation")
    parser.add_argument("--skip-encoder", action="store_true", help="Skip encoder training")
    parser.add_argument("--skip-topics", action="store_true", help="Skip topic training")
    parser.add_argument("--skip-predictor", action="store_true", help="Skip predictor training")
    parser.add_argument("--only", type=str, help="Run only specific step (download, labels, encoder, topics, predictor, backtest)")
    parser.add_argument("--use-gpu", action="store_true", help="Use GPU acceleration where available")
    args = parser.parse_args()
    
    # Show banner
    console.print(Panel.fit(
        "[bold blue]NEWS ALPHA ENGINE[/bold blue]\n"
        "[dim]Full Training Pipeline[/dim]",
        border_style="blue",
    ))
    
    # Determine which steps to run
    run_all = args.only is None
    
    steps = [
        {
            "name": "Download Datasets",
            "command": ["python", "scripts/download_datasets.py"],
            "skip": args.skip_download or (args.only and args.only != "download"),
        },
        {
            "name": "Prepare Labels (CAR Calculation)",
            "command": ["python", "scripts/prepare_labels.py"],
            "skip": args.skip_labels or (args.only and args.only != "labels"),
        },
        {
            "name": "Train FinBERT Encoder",
            "command": ["python", "src/training/train_encoder.py"],
            "skip": args.skip_encoder or (args.only and args.only != "encoder"),
        },
        {
            "name": "Train BERTopic Model",
            "command": ["python", "src/training/train_topics.py"] + (["--use-gpu"] if args.use_gpu else []),
            "skip": args.skip_topics or (args.only and args.only != "topics"),
        },
        {
            "name": "Train Impact Predictor",
            "command": ["python", "src/training/train_predictor.py"],
            "skip": args.skip_predictor or (args.only and args.only != "predictor"),
        },
        {
            "name": "Run Backtest",
            "command": ["python", "scripts/run_backtest.py"],
            "skip": args.only and args.only != "backtest",
        },
    ]
    
    # Run pipeline
    start_time = datetime.now()
    results = []
    
    for step in steps:
        success = run_step(step["name"], step["command"], step["skip"])
        results.append((step["name"], success, step["skip"]))
        
        if not success and not step["skip"]:
            console.print("\n[red]Pipeline stopped due to error.[/red]")
            break
    
    # Summary
    total_duration = (datetime.now() - start_time).total_seconds()
    
    console.print("\n" + "="*60)
    console.print("[bold]PIPELINE SUMMARY[/bold]")
    console.print("="*60)
    
    for name, success, skipped in results:
        if skipped:
            status = "[yellow]SKIPPED[/yellow]"
        elif success:
            status = "[green]SUCCESS[/green]"
        else:
            status = "[red]FAILED[/red]"
        console.print(f"  {status} {name}")
    
    console.print(f"\n[dim]Total time: {total_duration/60:.1f} minutes[/dim]")
    
    # Check if all succeeded
    all_success = all(success or skipped for _, success, skipped in results)
    
    if all_success:
        console.print("\n[bold green]✓ Pipeline completed successfully![/bold green]")
        console.print("\nYour trained models are in: /models/")
        console.print("Backtest results are in: /data/backtest_results/")
    else:
        console.print("\n[bold red]✗ Pipeline completed with errors.[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()

