"""
Impact Predictor Model

Multi-task neural network that predicts:
1. CAR (Cumulative Abnormal Return) - regression
2. Direction (up/neutral/down) - classification
3. Magnitude (low/medium/high) - classification
4. Confidence score - regression

Input features:
- News embedding (768-dim from FinBERT)
- Topic embedding (from BERTopic)
- Sentiment score
- Stock features (market cap, float, volume, etc.)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np


@dataclass
class PredictorOutput:
    """Output from the impact predictor."""
    car_1d: float
    car_5d: float
    direction: str  # up, neutral, down
    direction_probs: Dict[str, float]
    magnitude: str  # low, medium, high
    magnitude_probs: Dict[str, float]
    confidence: float
    
    def to_dict(self) -> dict:
        return {
            'car_1d': self.car_1d,
            'car_5d': self.car_5d,
            'direction': self.direction,
            'direction_probs': self.direction_probs,
            'magnitude': self.magnitude,
            'magnitude_probs': self.magnitude_probs,
            'confidence': self.confidence,
        }


class FocalLoss(nn.Module):
    """
    Focal Loss for handling class imbalance.
    FL(p_t) = -α_t * (1 - p_t)^γ * log(p_t)
    """
    
    def __init__(self, alpha: float = 1.0, gamma: float = 2.0, reduction: str = 'mean'):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.reduction = reduction
    
    def forward(self, inputs: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = F.cross_entropy(inputs, targets, reduction='none')
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * ce_loss
        
        if self.reduction == 'mean':
            return focal_loss.mean()
        elif self.reduction == 'sum':
            return focal_loss.sum()
        return focal_loss


class ImpactPredictor(nn.Module):
    """
    Multi-task neural network for predicting news impact.
    
    Architecture:
    - Shared encoder layers
    - Task-specific heads for each output
    """
    
    def __init__(
        self,
        news_embedding_dim: int = 768,
        topic_embedding_dim: int = 32,
        stock_features_dim: int = 20,
        hidden_dims: List[int] = [512, 256, 128],
        dropout: float = 0.3,
        num_directions: int = 3,  # down, neutral, up
        num_magnitudes: int = 3,  # low, medium, high
    ):
        super().__init__()
        
        self.num_directions = num_directions
        self.num_magnitudes = num_magnitudes
        
        # Input dimension
        input_dim = news_embedding_dim + topic_embedding_dim + 1 + stock_features_dim  # +1 for sentiment
        
        # Shared encoder
        layers = []
        prev_dim = input_dim
        
        for i, hidden_dim in enumerate(hidden_dims):
            layers.extend([
                nn.Linear(prev_dim, hidden_dim),
                nn.LayerNorm(hidden_dim),
                nn.GELU(),
                nn.Dropout(dropout),
            ])
            prev_dim = hidden_dim
        
        self.encoder = nn.Sequential(*layers)
        
        # Task-specific heads
        final_dim = hidden_dims[-1]
        
        # CAR regression heads
        self.car_1d_head = nn.Sequential(
            nn.Linear(final_dim, 64),
            nn.GELU(),
            nn.Linear(64, 1),
        )
        
        self.car_5d_head = nn.Sequential(
            nn.Linear(final_dim, 64),
            nn.GELU(),
            nn.Linear(64, 1),
        )
        
        # Direction classification head
        self.direction_head = nn.Sequential(
            nn.Linear(final_dim, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_directions),
        )
        
        # Magnitude classification head
        self.magnitude_head = nn.Sequential(
            nn.Linear(final_dim, 64),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_magnitudes),
        )
        
        # Confidence head (predicts how confident the model is)
        self.confidence_head = nn.Sequential(
            nn.Linear(final_dim, 32),
            nn.GELU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )
        
        # Initialize weights
        self.apply(self._init_weights)
    
    def _init_weights(self, module):
        if isinstance(module, nn.Linear):
            torch.nn.init.xavier_uniform_(module.weight)
            if module.bias is not None:
                torch.nn.init.zeros_(module.bias)
    
    def forward(
        self,
        news_embedding: torch.Tensor,
        topic_embedding: torch.Tensor,
        sentiment_score: torch.Tensor,
        stock_features: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            news_embedding: [batch, 768] - FinBERT embeddings
            topic_embedding: [batch, topic_dim] - Topic embeddings
            sentiment_score: [batch, 1] - Sentiment score
            stock_features: [batch, n_features] - Stock features
        
        Returns:
            Dictionary with all predictions
        """
        # Concatenate all inputs
        x = torch.cat([
            news_embedding,
            topic_embedding,
            sentiment_score,
            stock_features,
        ], dim=-1)
        
        # Encode
        encoded = self.encoder(x)
        
        # Task-specific predictions
        car_1d = self.car_1d_head(encoded).squeeze(-1)
        car_5d = self.car_5d_head(encoded).squeeze(-1)
        direction_logits = self.direction_head(encoded)
        magnitude_logits = self.magnitude_head(encoded)
        confidence = self.confidence_head(encoded).squeeze(-1)
        
        return {
            'car_1d': car_1d,
            'car_5d': car_5d,
            'direction_logits': direction_logits,
            'magnitude_logits': magnitude_logits,
            'confidence': confidence,
        }
    
    def predict(
        self,
        news_embedding: torch.Tensor,
        topic_embedding: torch.Tensor,
        sentiment_score: torch.Tensor,
        stock_features: torch.Tensor,
    ) -> PredictorOutput:
        """Make prediction and return structured output."""
        
        self.eval()
        with torch.no_grad():
            outputs = self.forward(
                news_embedding,
                topic_embedding,
                sentiment_score,
                stock_features,
            )
        
        # Direction
        direction_probs = F.softmax(outputs['direction_logits'], dim=-1)
        direction_idx = direction_probs.argmax(dim=-1).item()
        direction_labels = ['down', 'neutral', 'up']
        
        # Magnitude
        magnitude_probs = F.softmax(outputs['magnitude_logits'], dim=-1)
        magnitude_idx = magnitude_probs.argmax(dim=-1).item()
        magnitude_labels = ['low', 'medium', 'high']
        
        return PredictorOutput(
            car_1d=outputs['car_1d'].item(),
            car_5d=outputs['car_5d'].item(),
            direction=direction_labels[direction_idx],
            direction_probs={
                label: prob.item() 
                for label, prob in zip(direction_labels, direction_probs[0])
            },
            magnitude=magnitude_labels[magnitude_idx],
            magnitude_probs={
                label: prob.item()
                for label, prob in zip(magnitude_labels, magnitude_probs[0])
            },
            confidence=outputs['confidence'].item(),
        )


class ImpactPredictorLoss(nn.Module):
    """
    Combined loss for multi-task learning.
    
    Combines:
    - Huber loss for CAR regression
    - Focal loss for direction classification
    - Focal loss for magnitude classification
    - MSE for confidence calibration
    """
    
    def __init__(
        self,
        car_weight: float = 1.0,
        direction_weight: float = 0.5,
        magnitude_weight: float = 0.5,
        confidence_weight: float = 0.3,
        huber_delta: float = 0.1,
        focal_gamma: float = 2.0,
    ):
        super().__init__()
        
        self.car_weight = car_weight
        self.direction_weight = direction_weight
        self.magnitude_weight = magnitude_weight
        self.confidence_weight = confidence_weight
        
        self.huber_loss = nn.HuberLoss(delta=huber_delta)
        self.focal_loss = FocalLoss(gamma=focal_gamma)
        self.mse_loss = nn.MSELoss()
    
    def forward(
        self,
        predictions: Dict[str, torch.Tensor],
        targets: Dict[str, torch.Tensor],
    ) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Calculate combined loss.
        
        Args:
            predictions: Model outputs
            targets: Ground truth labels
        
        Returns:
            total_loss, loss_components
        """
        losses = {}
        
        # CAR regression losses
        if 'car_1d' in targets:
            losses['car_1d'] = self.huber_loss(predictions['car_1d'], targets['car_1d'])
        if 'car_5d' in targets:
            losses['car_5d'] = self.huber_loss(predictions['car_5d'], targets['car_5d'])
        
        car_loss = sum([losses.get('car_1d', 0), losses.get('car_5d', 0)]) / 2
        
        # Direction classification
        if 'direction' in targets:
            losses['direction'] = self.focal_loss(
                predictions['direction_logits'],
                targets['direction'],
            )
        
        # Magnitude classification
        if 'magnitude' in targets:
            losses['magnitude'] = self.focal_loss(
                predictions['magnitude_logits'],
                targets['magnitude'],
            )
        
        # Confidence calibration (confidence should predict correctness)
        if 'direction' in targets:
            direction_pred = predictions['direction_logits'].argmax(dim=-1)
            correct = (direction_pred == targets['direction']).float()
            losses['confidence'] = self.mse_loss(predictions['confidence'], correct)
        
        # Combined loss
        total_loss = (
            self.car_weight * car_loss +
            self.direction_weight * losses.get('direction', 0) +
            self.magnitude_weight * losses.get('magnitude', 0) +
            self.confidence_weight * losses.get('confidence', 0)
        )
        
        # Convert to float for logging
        loss_dict = {k: v.item() if torch.is_tensor(v) else v for k, v in losses.items()}
        loss_dict['total'] = total_loss.item()
        
        return total_loss, loss_dict


# ============================================
# Training utilities
# ============================================

class ImpactDataset(torch.utils.data.Dataset):
    """Dataset for impact prediction training."""
    
    def __init__(
        self,
        news_embeddings: np.ndarray,
        topic_embeddings: np.ndarray,
        sentiment_scores: np.ndarray,
        stock_features: np.ndarray,
        car_1d: np.ndarray,
        car_5d: np.ndarray,
        directions: np.ndarray,
        magnitudes: np.ndarray,
    ):
        self.news_embeddings = torch.tensor(news_embeddings, dtype=torch.float32)
        self.topic_embeddings = torch.tensor(topic_embeddings, dtype=torch.float32)
        self.sentiment_scores = torch.tensor(sentiment_scores, dtype=torch.float32).unsqueeze(-1)
        self.stock_features = torch.tensor(stock_features, dtype=torch.float32)
        self.car_1d = torch.tensor(car_1d, dtype=torch.float32)
        self.car_5d = torch.tensor(car_5d, dtype=torch.float32)
        self.directions = torch.tensor(directions, dtype=torch.long)
        self.magnitudes = torch.tensor(magnitudes, dtype=torch.long)
    
    def __len__(self):
        return len(self.news_embeddings)
    
    def __getitem__(self, idx):
        return {
            'news_embedding': self.news_embeddings[idx],
            'topic_embedding': self.topic_embeddings[idx],
            'sentiment_score': self.sentiment_scores[idx],
            'stock_features': self.stock_features[idx],
            'car_1d': self.car_1d[idx],
            'car_5d': self.car_5d[idx],
            'direction': self.directions[idx],
            'magnitude': self.magnitudes[idx],
        }


def collate_fn(batch: List[dict]) -> Tuple[Dict, Dict]:
    """Collate batch into model inputs and targets."""
    
    inputs = {
        'news_embedding': torch.stack([b['news_embedding'] for b in batch]),
        'topic_embedding': torch.stack([b['topic_embedding'] for b in batch]),
        'sentiment_score': torch.stack([b['sentiment_score'] for b in batch]),
        'stock_features': torch.stack([b['stock_features'] for b in batch]),
    }
    
    targets = {
        'car_1d': torch.stack([b['car_1d'] for b in batch]),
        'car_5d': torch.stack([b['car_5d'] for b in batch]),
        'direction': torch.stack([b['direction'] for b in batch]),
        'magnitude': torch.stack([b['magnitude'] for b in batch]),
    }
    
    return inputs, targets

