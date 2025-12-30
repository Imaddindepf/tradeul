#!/usr/bin/env python3
"""
Train BERTopic model for financial news topic clustering.

This creates topic clusters like:
- Earnings & Revenue
- FDA & Regulatory
- Dilution & Offerings
- M&A
- SEC & Legal
- etc.

Usage:
    python src/training/train_topics.py
    python src/training/train_topics.py --use-gpu
    python src/training/train_topics.py --nr-topics 20
"""

import os
import sys
from pathlib import Path
import argparse
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
import yaml
import numpy as np
import pandas as pd
from tqdm import tqdm
from rich.console import Console
from rich.table import Table

console = Console()


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_data(data_dir: Path) -> pd.DataFrame:
    """Load training data."""
    console.print("Loading data...")
    
    train_path = data_dir / "train.parquet"
    
    if not train_path.exists():
        raise FileNotFoundError(f"Training data not found at {train_path}")
    
    df = pd.read_parquet(train_path)
    console.print(f"  Loaded {len(df):,} samples")
    
    return df


def get_embedding_model(config: dict, encoder_path: Path = None):
    """Get embedding model for BERTopic."""
    from sentence_transformers import SentenceTransformer
    
    topic_config = config['topic_model']
    
    # Check if we should use fine-tuned FinBERT
    if topic_config.get('embedding_model') == 'trained_finbert' and encoder_path:
        final_model_path = encoder_path / "final"
        if final_model_path.exists():
            console.print(f"  Using fine-tuned FinBERT from {final_model_path}")
            # Load as sentence transformer (need to wrap it)
            # For now, use the pre-trained version
            console.print("  [yellow]Note: Using pre-trained FinBERT embeddings[/yellow]")
            return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    
    # Use default sentence transformer
    model_name = topic_config.get('embedding_model', 'all-MiniLM-L6-v2')
    if model_name == 'trained_finbert':
        model_name = 'sentence-transformers/all-MiniLM-L6-v2'
    
    console.print(f"  Using embedding model: {model_name}")
    return SentenceTransformer(model_name)


def create_bertopic_model(config: dict, use_gpu: bool = False):
    """Create BERTopic model with optional GPU acceleration."""
    from bertopic import BERTopic
    from sklearn.feature_extraction.text import CountVectorizer
    
    topic_config = config['topic_model']
    
    # Dimensionality reduction
    if use_gpu:
        try:
            from cuml.manifold import UMAP as cumlUMAP
            console.print("  Using GPU-accelerated UMAP (cuML)")
            umap_model = cumlUMAP(
                n_components=topic_config['umap']['n_components'],
                n_neighbors=topic_config['umap']['n_neighbors'],
                min_dist=topic_config['umap']['min_dist'],
                metric=topic_config['umap']['metric'],
            )
        except ImportError:
            console.print("  [yellow]cuML not available, using CPU UMAP[/yellow]")
            use_gpu = False
    
    if not use_gpu:
        from umap import UMAP
        umap_model = UMAP(
            n_components=topic_config['umap']['n_components'],
            n_neighbors=topic_config['umap']['n_neighbors'],
            min_dist=topic_config['umap']['min_dist'],
            metric=topic_config['umap']['metric'],
            low_memory=topic_config['umap'].get('low_memory', True),
            random_state=42,
        )
    
    # Clustering
    if use_gpu:
        try:
            from cuml.cluster import HDBSCAN as cumlHDBSCAN
            console.print("  Using GPU-accelerated HDBSCAN (cuML)")
            hdbscan_model = cumlHDBSCAN(
                min_cluster_size=topic_config['hdbscan']['min_cluster_size'],
                min_samples=topic_config['hdbscan']['min_samples'],
                metric=topic_config['hdbscan']['metric'],
                prediction_data=True,
            )
        except ImportError:
            use_gpu = False
    
    if not use_gpu:
        from hdbscan import HDBSCAN
        hdbscan_model = HDBSCAN(
            min_cluster_size=topic_config['hdbscan']['min_cluster_size'],
            min_samples=topic_config['hdbscan']['min_samples'],
            metric=topic_config['hdbscan']['metric'],
            cluster_selection_method=topic_config['hdbscan'].get('cluster_selection_method', 'eom'),
            prediction_data=True,
        )
    
    # Vectorizer for topic representation
    vectorizer_model = CountVectorizer(
        stop_words='english',
        ngram_range=(1, 2),
        min_df=5,
    )
    
    # Create BERTopic
    nr_topics = topic_config.get('nr_topics', 'auto')
    if nr_topics == 'auto':
        nr_topics = None
    
    topic_model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer_model,
        nr_topics=nr_topics,
        top_n_words=topic_config.get('top_n_words', 10),
        verbose=True,
        calculate_probabilities=True,
    )
    
    return topic_model


def get_seed_topics(config: dict) -> list:
    """Get seed topics for guided topic modeling."""
    topic_config = config['topic_model']
    guided = topic_config.get('guided_topics', [])
    
    if not guided:
        return None
    
    # Extract just the keywords lists
    seed_topics = [topic['keywords'] for topic in guided]
    
    console.print(f"  Using {len(seed_topics)} guided topics:")
    for topic in guided:
        console.print(f"    - {topic['name']}: {topic['keywords'][:3]}...")
    
    return seed_topics


def train_topic_model(
    config: dict,
    df: pd.DataFrame,
    use_gpu: bool = False,
    output_dir: str = None,
):
    """Train BERTopic model."""
    
    topic_config = config['topic_model']
    
    # Set output directory
    if output_dir is None:
        output_dir = topic_config.get('output_dir', '/models/topic_model')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"\n[bold]Training BERTopic Model[/bold]")
    console.print(f"  Output: {output_dir}")
    console.print(f"  GPU: {'Yes' if use_gpu else 'No'}")
    
    # Get texts
    texts = df['headline'].fillna('').tolist()
    console.print(f"  Documents: {len(texts):,}")
    
    # Get embedding model
    encoder_path = Path(__file__).parent.parent.parent / "models" / "news_encoder"
    embedding_model = get_embedding_model(config, encoder_path)
    
    # Generate embeddings
    console.print("\nGenerating embeddings...")
    embeddings = embedding_model.encode(
        texts,
        show_progress_bar=True,
        batch_size=32,
    )
    console.print(f"  Embeddings shape: {embeddings.shape}")
    
    # Create model
    console.print("\nCreating BERTopic model...")
    topic_model = create_bertopic_model(config, use_gpu)
    
    # Get seed topics for guided modeling
    seed_topics = get_seed_topics(config)
    
    # Train
    console.print("\n[bold green]Fitting topic model...[/bold green]")
    
    if seed_topics:
        # Guided topic modeling (semi-supervised)
        topics, probs = topic_model.fit_transform(
            texts,
            embeddings=embeddings,
        )
    else:
        topics, probs = topic_model.fit_transform(
            texts,
            embeddings=embeddings,
        )
    
    # Get topic info
    topic_info = topic_model.get_topic_info()
    
    console.print(f"\n[green]✓ Created {len(topic_info) - 1} topics[/green]")  # -1 for outlier topic
    
    # Display topics
    table = Table(title="Discovered Topics")
    table.add_column("ID", justify="right", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column("Name/Keywords")
    
    for _, row in topic_info.head(20).iterrows():
        if row['Topic'] != -1:  # Skip outliers
            table.add_row(
                str(row['Topic']),
                str(row['Count']),
                row['Name'][:50] + "..." if len(row['Name']) > 50 else row['Name']
            )
    
    console.print(table)
    
    # Save model
    console.print("\nSaving model...")
    topic_model.save(str(output_dir / "bertopic_model"))
    
    # Save embeddings for later use
    np.save(str(output_dir / "embeddings.npy"), embeddings)
    
    # Save topic assignments
    df_with_topics = df.copy()
    df_with_topics['topic_id'] = topics
    df_with_topics['topic_prob'] = [max(p) if len(p) > 0 else 0 for p in probs]
    df_with_topics.to_parquet(output_dir / "data_with_topics.parquet", index=False)
    
    # Save topic info
    topic_info.to_csv(output_dir / "topic_info.csv", index=False)
    
    # Save training metadata
    info = {
        'n_documents': len(texts),
        'n_topics': len(topic_info) - 1,
        'embedding_model': str(topic_config.get('embedding_model', 'all-MiniLM-L6-v2')),
        'timestamp': datetime.now().isoformat(),
    }
    
    with open(output_dir / "training_info.json", 'w') as f:
        json.dump(info, f, indent=2)
    
    console.print(f"\n[bold green]✓ Topic model saved to {output_dir}[/bold green]")
    
    return topic_model, topics, probs


def analyze_topics_by_impact(
    df: pd.DataFrame,
    topics: list,
    output_dir: Path,
):
    """Analyze how topics relate to market impact."""
    
    if 'car_5d' not in df.columns:
        console.print("[yellow]No CAR data available for impact analysis[/yellow]")
        return
    
    console.print("\n[bold]Topic Impact Analysis[/bold]")
    
    df_analysis = df.copy()
    df_analysis['topic_id'] = topics
    
    # Group by topic and calculate stats
    topic_stats = df_analysis.groupby('topic_id').agg({
        'car_5d': ['mean', 'std', 'count'],
        'headline': 'first',  # Sample headline
    }).reset_index()
    
    topic_stats.columns = ['topic_id', 'avg_car', 'std_car', 'count', 'sample']
    topic_stats = topic_stats[topic_stats['topic_id'] != -1]  # Remove outliers
    topic_stats = topic_stats.sort_values('avg_car', ascending=False)
    
    # Display
    table = Table(title="Topics by Average Impact (CAR 5d)")
    table.add_column("Topic", justify="right", style="cyan")
    table.add_column("Avg CAR", justify="right")
    table.add_column("Std", justify="right")
    table.add_column("Count", justify="right")
    table.add_column("Sample", max_width=40)
    
    for _, row in topic_stats.head(15).iterrows():
        color = "green" if row['avg_car'] > 0.01 else ("red" if row['avg_car'] < -0.01 else "white")
        table.add_row(
            str(int(row['topic_id'])),
            f"[{color}]{row['avg_car']:.4f}[/{color}]",
            f"{row['std_car']:.4f}",
            str(int(row['count'])),
            str(row['sample'])[:40] + "..."
        )
    
    console.print(table)
    
    # Save analysis
    topic_stats.to_csv(output_dir / "topic_impact_analysis.csv", index=False)


def main():
    parser = argparse.ArgumentParser(description="Train BERTopic model")
    parser.add_argument("--config", default="config/training_config.yaml")
    parser.add_argument("--use-gpu", action="store_true", help="Use GPU acceleration (requires cuML)")
    parser.add_argument("--nr-topics", type=int, help="Force number of topics")
    parser.add_argument("--output-dir", type=str, help="Override output directory")
    args = parser.parse_args()
    
    # Load config
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / args.config
    config = load_config(str(config_path))
    
    # Override config
    if args.nr_topics:
        config['topic_model']['nr_topics'] = args.nr_topics
    
    # Load data
    data_dir = project_root / "data" / "processed"
    df = load_data(data_dir)
    
    # Train
    output_dir = args.output_dir or str(project_root / "models" / "topic_model")
    topic_model, topics, probs = train_topic_model(
        config=config,
        df=df,
        use_gpu=args.use_gpu,
        output_dir=output_dir,
    )
    
    # Analyze
    analyze_topics_by_impact(df, topics, Path(output_dir))
    
    console.print("\n[bold]Next step:[/bold] Run [cyan]python src/training/train_predictor.py[/cyan]")


if __name__ == "__main__":
    main()

