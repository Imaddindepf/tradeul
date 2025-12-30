#!/usr/bin/env python3
"""
Fine-tune FinBERT on financial news for sentiment classification.

This script fine-tunes the ProsusAI/finbert model on your specific
financial news data to improve sentiment classification accuracy.

Usage:
    python src/training/train_encoder.py
    python src/training/train_encoder.py --config config/training_config.yaml
    python src/training/train_encoder.py --epochs 3 --batch-size 8
"""

import os
import sys
from pathlib import Path
import argparse
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import torch
import yaml
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, classification_report
from datasets import Dataset, DatasetDict
from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
    TrainingArguments,
    Trainer,
    EarlyStoppingCallback,
)
from rich.console import Console
from rich.progress import Progress

console = Console()

# Label mapping
LABEL2ID = {"negative": 0, "neutral": 1, "positive": 2}
ID2LABEL = {v: k for k, v in LABEL2ID.items()}


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def load_data(data_dir: Path) -> tuple:
    """Load train/val datasets."""
    console.print("Loading datasets...")
    
    train_path = data_dir / "train.parquet"
    val_path = data_dir / "val.parquet"
    
    if not train_path.exists():
        raise FileNotFoundError(f"Training data not found at {train_path}")
    
    train_df = pd.read_parquet(train_path)
    val_df = pd.read_parquet(val_path) if val_path.exists() else None
    
    console.print(f"  Train: {len(train_df):,} samples")
    if val_df is not None:
        console.print(f"  Val: {len(val_df):,} samples")
    
    return train_df, val_df


def prepare_dataset(
    df: pd.DataFrame,
    tokenizer,
    max_length: int = 512,
) -> Dataset:
    """Prepare dataset for training."""
    
    # Get text and labels
    texts = df['headline'].fillna('').tolist()
    
    # Handle different label columns
    if 'sentiment_label' in df.columns:
        labels = df['sentiment_label'].tolist()
    elif 'direction' in df.columns:
        # Map direction to sentiment
        label_map = {'down': 'negative', 'neutral': 'neutral', 'up': 'positive'}
        labels = df['direction'].map(label_map).fillna('neutral').tolist()
    else:
        # Use CAR-based labels
        labels = df['car_5d'].apply(
            lambda x: 'positive' if x > 0.01 else ('negative' if x < -0.01 else 'neutral')
        ).tolist()
    
    # Convert labels to IDs
    label_ids = [LABEL2ID.get(str(l).lower(), 1) for l in labels]  # Default to neutral
    
    # Tokenize
    encodings = tokenizer(
        texts,
        truncation=True,
        padding='max_length',
        max_length=max_length,
        return_tensors='pt',
    )
    
    # Create dataset
    dataset = Dataset.from_dict({
        'input_ids': encodings['input_ids'],
        'attention_mask': encodings['attention_mask'],
        'labels': label_ids,
    })
    
    return dataset


def compute_metrics(eval_pred):
    """Compute metrics for evaluation."""
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    
    accuracy = accuracy_score(labels, predictions)
    f1_macro = f1_score(labels, predictions, average='macro')
    f1_weighted = f1_score(labels, predictions, average='weighted')
    
    return {
        'accuracy': accuracy,
        'f1': f1_macro,
        'f1_weighted': f1_weighted,
    }


def train_encoder(
    config: dict,
    train_df: pd.DataFrame,
    val_df: pd.DataFrame = None,
    output_dir: str = None,
):
    """Fine-tune FinBERT encoder."""
    
    encoder_config = config['encoder']
    
    # Set output directory
    if output_dir is None:
        output_dir = encoder_config.get('output_dir', '/models/news_encoder')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"\n[bold]Training FinBERT Encoder[/bold]")
    console.print(f"  Base model: {encoder_config['base_model']}")
    console.print(f"  Output: {output_dir}")
    
    # Check GPU
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        console.print(f"  GPU: {torch.cuda.get_device_name(0)}")
        console.print(f"  VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    else:
        console.print("  [yellow]WARNING: Training on CPU (will be slow)[/yellow]")
    
    # Load tokenizer and model
    console.print("\nLoading model...")
    tokenizer = AutoTokenizer.from_pretrained(encoder_config['base_model'])
    model = AutoModelForSequenceClassification.from_pretrained(
        encoder_config['base_model'],
        num_labels=3,
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        problem_type="single_label_classification",
    )
    
    # Prepare datasets
    console.print("Preparing datasets...")
    train_dataset = prepare_dataset(
        train_df,
        tokenizer,
        max_length=encoder_config['max_length'],
    )
    
    val_dataset = None
    if val_df is not None:
        val_dataset = prepare_dataset(
            val_df,
            tokenizer,
            max_length=encoder_config['max_length'],
        )
    
    console.print(f"  Train samples: {len(train_dataset):,}")
    if val_dataset:
        console.print(f"  Val samples: {len(val_dataset):,}")
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=encoder_config['epochs'],
        per_device_train_batch_size=encoder_config['batch_size'],
        per_device_eval_batch_size=encoder_config['batch_size'],
        gradient_accumulation_steps=encoder_config.get('gradient_accumulation_steps', 1),
        learning_rate=encoder_config['learning_rate'],
        weight_decay=encoder_config.get('weight_decay', 0.01),
        warmup_ratio=encoder_config.get('warmup_ratio', 0.1),
        
        # Evaluation
        eval_strategy="epoch" if val_dataset else "no",
        save_strategy="epoch",
        load_best_model_at_end=True if val_dataset else False,
        metric_for_best_model="f1" if val_dataset else None,
        greater_is_better=True if val_dataset else None,
        
        # Optimization
        fp16=encoder_config.get('fp16', True) and device == "cuda",
        dataloader_num_workers=4,
        
        # Logging
        logging_dir=str(output_dir / "logs"),
        logging_steps=100,
        report_to=["wandb"] if config.get('tracking', {}).get('wandb', {}).get('enabled', False) else [],
        
        # Save
        save_total_limit=3,
    )
    
    # Callbacks
    callbacks = []
    if val_dataset:
        callbacks.append(EarlyStoppingCallback(early_stopping_patience=3))
    
    # Initialize trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
        callbacks=callbacks,
    )
    
    # Train
    console.print("\n[bold green]Starting training...[/bold green]\n")
    
    train_result = trainer.train()
    
    # Save final model
    console.print("\nSaving model...")
    trainer.save_model(str(output_dir / "final"))
    tokenizer.save_pretrained(str(output_dir / "final"))
    
    # Evaluation
    if val_dataset:
        console.print("\nEvaluating...")
        eval_results = trainer.evaluate()
        console.print(f"  Accuracy: {eval_results['eval_accuracy']:.4f}")
        console.print(f"  F1 Score: {eval_results['eval_f1']:.4f}")
    
    # Save training info
    info = {
        'base_model': encoder_config['base_model'],
        'train_samples': len(train_dataset),
        'val_samples': len(val_dataset) if val_dataset else 0,
        'epochs': encoder_config['epochs'],
        'final_loss': train_result.training_loss,
        'timestamp': datetime.now().isoformat(),
    }
    
    import json
    with open(output_dir / "training_info.json", 'w') as f:
        json.dump(info, f, indent=2)
    
    console.print(f"\n[bold green]✓ Training complete![/bold green]")
    console.print(f"  Model saved to: {output_dir / 'final'}")
    
    return model, tokenizer


def main():
    parser = argparse.ArgumentParser(description="Train FinBERT encoder")
    parser.add_argument("--config", default="config/training_config.yaml")
    parser.add_argument("--epochs", type=int, help="Override epochs")
    parser.add_argument("--batch-size", type=int, help="Override batch size")
    parser.add_argument("--output-dir", type=str, help="Override output directory")
    args = parser.parse_args()
    
    # Load config
    project_root = Path(__file__).parent.parent.parent
    config_path = project_root / args.config
    config = load_config(str(config_path))
    
    # Override config with CLI args
    if args.epochs:
        config['encoder']['epochs'] = args.epochs
    if args.batch_size:
        config['encoder']['batch_size'] = args.batch_size
    
    # Load data
    data_dir = project_root / "data" / "processed"
    train_df, val_df = load_data(data_dir)
    
    # Train
    train_encoder(
        config=config,
        train_df=train_df,
        val_df=val_df,
        output_dir=args.output_dir,
    )
    
    console.print("\n[bold]Next step:[/bold] Run [cyan]python src/training/train_topics.py[/cyan]")


if __name__ == "__main__":
    main()

