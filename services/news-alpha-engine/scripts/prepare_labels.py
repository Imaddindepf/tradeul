#!/usr/bin/env python3
"""
Prepare training labels by calculating CAR for all news events.

This script:
1. Loads all news data (from Benzinga/Polygon, HuggingFace datasets)
2. Calculates CAR labels for each news event
3. Classifies direction and magnitude
4. Creates train/val/test splits
5. Saves processed dataset

Usage:
    python scripts/prepare_labels.py
    python scripts/prepare_labels.py --config config/training_config.yaml
"""

import os
import sys
from pathlib import Path
import argparse
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import numpy as np
import yaml
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from datasets import load_from_disk, Dataset

from src.utils.car_calculator import CARCalculator, classify_impact

console = Console()


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_benzinga_news(news_path: Path) -> pd.DataFrame:
    """Load news from local Benzinga/Polygon data."""
    console.print(f"Loading Benzinga news from {news_path}...")
    
    news_files = list(news_path.glob("**/*.parquet")) + list(news_path.glob("**/*.json"))
    
    if not news_files:
        console.print("[yellow]No Benzinga news files found[/yellow]")
        return pd.DataFrame()
    
    dfs = []
    for f in tqdm(news_files, desc="Loading news files"):
        try:
            if f.suffix == '.parquet':
                df = pd.read_parquet(f)
            else:
                df = pd.read_json(f, lines=True)
            dfs.append(df)
        except Exception as e:
            console.print(f"[red]Error loading {f}: {e}[/red]")
    
    if not dfs:
        return pd.DataFrame()
    
    df = pd.concat(dfs, ignore_index=True)
    console.print(f"  Loaded {len(df):,} news articles")
    
    return df


def load_huggingface_sentiment(data_path: Path) -> pd.DataFrame:
    """Load FinGPT sentiment dataset."""
    console.print("Loading FinGPT sentiment dataset...")
    
    dataset_path = data_path / "FinGPT_fingpt-sentiment-train"
    
    if not dataset_path.exists():
        console.print("[yellow]FinGPT dataset not found. Run download_datasets.py first.[/yellow]")
        return pd.DataFrame()
    
    try:
        dataset = load_from_disk(str(dataset_path))
        df = dataset['train'].to_pandas() if 'train' in dataset else pd.DataFrame(dataset)
        console.print(f"  Loaded {len(df):,} sentiment samples")
        return df
    except Exception as e:
        console.print(f"[red]Error loading FinGPT: {e}[/red]")
        return pd.DataFrame()


def load_twitter_financial(data_path: Path) -> pd.DataFrame:
    """Load Twitter financial news dataset."""
    console.print("Loading Twitter financial news...")
    
    dataset_path = data_path / "zeroshot_twitter-financial-news-sentiment"
    
    if not dataset_path.exists():
        console.print("[yellow]Twitter dataset not found. Run download_datasets.py first.[/yellow]")
        return pd.DataFrame()
    
    try:
        dataset = load_from_disk(str(dataset_path))
        df = dataset['train'].to_pandas() if 'train' in dataset else pd.DataFrame(dataset)
        console.print(f"  Loaded {len(df):,} tweets")
        return df
    except Exception as e:
        console.print(f"[red]Error loading Twitter data: {e}[/red]")
        return pd.DataFrame()


def extract_tickers_from_text(text: str, known_tickers: set) -> list:
    """Extract stock tickers mentioned in text."""
    import re
    
    # Pattern for potential tickers (1-5 uppercase letters)
    pattern = r'\b([A-Z]{1,5})\b'
    
    potential = set(re.findall(pattern, text.upper()))
    
    # Filter to known tickers
    found = [t for t in potential if t in known_tickers]
    
    return found


def prepare_combined_dataset(
    benzinga_df: pd.DataFrame,
    sentiment_df: pd.DataFrame,
    twitter_df: pd.DataFrame,
    known_tickers: set,
) -> pd.DataFrame:
    """Combine all data sources into unified format."""
    
    combined = []
    
    # Process Benzinga news
    if not benzinga_df.empty:
        for _, row in tqdm(benzinga_df.iterrows(), total=len(benzinga_df), desc="Processing Benzinga"):
            # Normalize column names
            headline = row.get('title', row.get('headline', ''))
            body = row.get('content', row.get('body', row.get('description', '')))
            timestamp = row.get('published', row.get('timestamp', row.get('date', '')))
            tickers = row.get('tickers', row.get('symbols', []))
            
            if isinstance(tickers, str):
                tickers = [t.strip() for t in tickers.split(',')]
            
            if headline and timestamp:
                combined.append({
                    'news_id': f"bz_{len(combined)}",
                    'source': 'benzinga',
                    'headline': headline,
                    'body': body or '',
                    'timestamp': pd.to_datetime(timestamp),
                    'tickers': tickers if tickers else extract_tickers_from_text(headline, known_tickers),
                })
    
    # Process sentiment data (doesn't have dates, use for sentiment training)
    if not sentiment_df.empty:
        for _, row in tqdm(sentiment_df.iterrows(), total=len(sentiment_df), desc="Processing FinGPT"):
            text = row.get('text', row.get('sentence', ''))
            label = row.get('label', row.get('sentiment', ''))
            
            if text:
                tickers = extract_tickers_from_text(text, known_tickers)
                combined.append({
                    'news_id': f"fg_{len(combined)}",
                    'source': 'fingpt',
                    'headline': text,
                    'body': '',
                    'timestamp': None,  # No date info
                    'tickers': tickers,
                    'sentiment_label': label,  # Pre-labeled!
                })
    
    # Process Twitter data
    if not twitter_df.empty:
        for _, row in tqdm(twitter_df.iterrows(), total=len(twitter_df), desc="Processing Twitter"):
            text = row.get('text', row.get('tweet', ''))
            label = row.get('label', row.get('sentiment', ''))
            
            if text:
                tickers = extract_tickers_from_text(text, known_tickers)
                combined.append({
                    'news_id': f"tw_{len(combined)}",
                    'source': 'twitter',
                    'headline': text,
                    'body': '',
                    'timestamp': None,
                    'tickers': tickers,
                    'sentiment_label': label,
                })
    
    df = pd.DataFrame(combined)
    console.print(f"\n[green]Combined dataset: {len(df):,} records[/green]")
    
    return df


def calculate_car_labels(
    df: pd.DataFrame,
    car_calculator: CARCalculator,
    config: dict,
) -> pd.DataFrame:
    """Calculate CAR labels for news with dates and tickers."""
    
    # Filter to news with dates and tickers (for CAR calculation)
    df_with_dates = df[df['timestamp'].notna() & (df['tickers'].apply(len) > 0)].copy()
    
    console.print(f"\nCalculating CAR for {len(df_with_dates):,} news events...")
    
    if len(df_with_dates) == 0:
        console.print("[yellow]No news with dates and tickers found for CAR calculation[/yellow]")
        return df
    
    # Explode tickers (one row per ticker mentioned)
    df_exploded = df_with_dates.explode('tickers').rename(columns={'tickers': 'primary_ticker'})
    df_exploded = df_exploded[df_exploded['primary_ticker'].notna()]
    
    console.print(f"  Exploded to {len(df_exploded):,} ticker-news pairs")
    
    # Calculate CAR for each
    events = df_exploded[['news_id', 'primary_ticker', 'timestamp']].to_dict('records')
    events = [{'news_id': e['news_id'], 'ticker': e['primary_ticker'], 'timestamp': e['timestamp']} 
              for e in events]
    
    car_results = car_calculator.calculate_batch(
        events,
        progress_callback=lambda i, t: None if i % 100 != 0 else console.print(f"  Progress: {i}/{t}")
    )
    
    console.print(f"  Calculated CAR for {len(car_results):,} events")
    
    if car_results.empty:
        return df
    
    # Classify direction and magnitude
    car_results['direction'], car_results['magnitude'] = zip(
        *car_results['car_5d'].apply(lambda x: classify_impact(x) if pd.notna(x) else ('neutral', 'low'))
    )
    
    # Merge back
    df_labeled = df_exploded.merge(
        car_results,
        left_on='news_id',
        right_on='news_id',
        how='left'
    )
    
    # For records without CAR (no price data), set defaults
    df_labeled['car_5d'] = df_labeled['car_5d'].fillna(0)
    df_labeled['direction'] = df_labeled['direction'].fillna('neutral')
    df_labeled['magnitude'] = df_labeled['magnitude'].fillna('low')
    
    return df_labeled


def create_splits(
    df: pd.DataFrame,
    config: dict,
) -> tuple:
    """Create train/val/test splits."""
    
    date_range = config['data']['date_range']
    
    # For data with dates
    df_dated = df[df['timestamp'].notna()].copy()
    df_undated = df[df['timestamp'].isna()].copy()
    
    if len(df_dated) > 0:
        train_mask = (df_dated['timestamp'] >= date_range['train_start']) & \
                     (df_dated['timestamp'] <= date_range['train_end'])
        val_mask = (df_dated['timestamp'] >= date_range['val_start']) & \
                   (df_dated['timestamp'] <= date_range['val_end'])
        test_mask = (df_dated['timestamp'] >= date_range['test_start']) & \
                    (df_dated['timestamp'] <= date_range['test_end'])
        
        train_dated = df_dated[train_mask]
        val_dated = df_dated[val_mask]
        test_dated = df_dated[test_mask]
    else:
        train_dated = pd.DataFrame()
        val_dated = pd.DataFrame()
        test_dated = pd.DataFrame()
    
    # For undated data, do random split (80/10/10)
    if len(df_undated) > 0:
        df_undated = df_undated.sample(frac=1, random_state=42)  # Shuffle
        n = len(df_undated)
        train_undated = df_undated[:int(0.8 * n)]
        val_undated = df_undated[int(0.8 * n):int(0.9 * n)]
        test_undated = df_undated[int(0.9 * n):]
    else:
        train_undated = pd.DataFrame()
        val_undated = pd.DataFrame()
        test_undated = pd.DataFrame()
    
    # Combine
    train_df = pd.concat([train_dated, train_undated], ignore_index=True)
    val_df = pd.concat([val_dated, val_undated], ignore_index=True)
    test_df = pd.concat([test_dated, test_undated], ignore_index=True)
    
    console.print(f"\n[bold]Dataset Splits:[/bold]")
    console.print(f"  Train: {len(train_df):,} samples")
    console.print(f"  Val:   {len(val_df):,} samples")
    console.print(f"  Test:  {len(test_df):,} samples")
    
    return train_df, val_df, test_df


def save_datasets(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    output_dir: Path,
):
    """Save datasets to parquet files."""
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    train_df.to_parquet(output_dir / "train.parquet", index=False)
    val_df.to_parquet(output_dir / "val.parquet", index=False)
    test_df.to_parquet(output_dir / "test.parquet", index=False)
    
    # Also save as HuggingFace dataset format
    try:
        train_dataset = Dataset.from_pandas(train_df)
        val_dataset = Dataset.from_pandas(val_df)
        test_dataset = Dataset.from_pandas(test_df)
        
        train_dataset.save_to_disk(str(output_dir / "train_hf"))
        val_dataset.save_to_disk(str(output_dir / "val_hf"))
        test_dataset.save_to_disk(str(output_dir / "test_hf"))
    except Exception as e:
        console.print(f"[yellow]Could not save HF format: {e}[/yellow]")
    
    console.print(f"\n[green]✓ Datasets saved to {output_dir}[/green]")


def print_statistics(df: pd.DataFrame):
    """Print dataset statistics."""
    
    console.print("\n" + "="*60)
    console.print("[bold]Dataset Statistics[/bold]")
    console.print("="*60)
    
    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    
    table.add_row("Total samples", f"{len(df):,}")
    table.add_row("With timestamps", f"{df['timestamp'].notna().sum():,}")
    table.add_row("With tickers", f"{(df['tickers'].apply(len) > 0).sum():,}")
    
    if 'source' in df.columns:
        for source in df['source'].unique():
            count = (df['source'] == source).sum()
            table.add_row(f"  Source: {source}", f"{count:,}")
    
    if 'direction' in df.columns:
        for direction in ['up', 'neutral', 'down']:
            count = (df['direction'] == direction).sum()
            table.add_row(f"  Direction: {direction}", f"{count:,}")
    
    if 'car_5d' in df.columns:
        valid_car = df['car_5d'].dropna()
        if len(valid_car) > 0:
            table.add_row("CAR 5d mean", f"{valid_car.mean():.4f}")
            table.add_row("CAR 5d std", f"{valid_car.std():.4f}")
    
    console.print(table)


def main():
    parser = argparse.ArgumentParser(description="Prepare training labels")
    parser.add_argument("--config", default="config/training_config.yaml", help="Config file path")
    parser.add_argument("--skip-car", action="store_true", help="Skip CAR calculation")
    args = parser.parse_args()
    
    console.print("\n" + "="*60)
    console.print("[bold blue]NEWS ALPHA ENGINE - Label Preparation[/bold blue]")
    console.print("="*60 + "\n")
    
    # Load config
    config_path = Path(__file__).parent.parent / args.config
    config = load_config(str(config_path))
    
    # Paths
    data_path = Path(__file__).parent.parent / "data" / "raw"
    output_path = Path(__file__).parent.parent / "data" / "processed"
    
    # Load known tickers (from your Polygon data)
    # For now, use a basic set of S&P 500 + common tickers
    known_tickers = set([
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'TSLA', 'NVDA', 'AMD', 'INTC',
        'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'V', 'MA', 'PYPL',
        'JNJ', 'PFE', 'UNH', 'MRK', 'ABBV', 'BMY', 'LLY', 'AMGN',
        'XOM', 'CVX', 'COP', 'OXY', 'SLB', 'EOG', 'PXD',
        'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO',
        # Add more as needed
    ])
    
    # Load data from various sources
    benzinga_df = load_benzinga_news(data_path / "news")
    sentiment_df = load_huggingface_sentiment(data_path)
    twitter_df = load_twitter_financial(data_path)
    
    # Combine
    combined_df = prepare_combined_dataset(
        benzinga_df, sentiment_df, twitter_df, known_tickers
    )
    
    if combined_df.empty:
        console.print("[red]No data loaded. Run download_datasets.py first.[/red]")
        return
    
    # Calculate CAR labels
    if not args.skip_car:
        car_calculator = CARCalculator(
            price_data_path=config['data']['price_data']['path'],
            benchmark=config['data']['price_data']['benchmark'],
            estimation_window=config['car_calculation']['estimation_window'],
        )
        
        labeled_df = calculate_car_labels(combined_df, car_calculator, config)
    else:
        labeled_df = combined_df
        console.print("[yellow]Skipping CAR calculation[/yellow]")
    
    # Create splits
    train_df, val_df, test_df = create_splits(labeled_df, config)
    
    # Save
    save_datasets(train_df, val_df, test_df, output_path)
    
    # Statistics
    print_statistics(labeled_df)
    
    console.print("\n[bold green]✓ Label preparation complete![/bold green]")
    console.print("\n[bold]Next step:[/bold] Run [cyan]python scripts/train_encoder.py[/cyan]")


if __name__ == "__main__":
    main()

