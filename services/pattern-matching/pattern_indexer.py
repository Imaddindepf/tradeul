"""
FAISS Pattern Indexer
Builds and manages the FAISS index for ultra-fast pattern similarity search

Supports:
- IVFPQ index with SQLite metadata (new, memory efficient)
- Pickle metadata (legacy fallback)
"""

import os
import json
import pickle
import sqlite3
from datetime import datetime
from typing import List, Dict, Tuple, Optional

import numpy as np
import faiss
import structlog

from config import settings

logger = structlog.get_logger(__name__)


class PatternIndexer:
    """
    Builds and manages FAISS index for pattern matching
    
    Supports multiple index types:
    - Flat: Exact search (small datasets)
    - IVF: Inverted file index (medium datasets)
    - IVF+PQ: Product quantization (large datasets, compressed)
    - HNSW: Hierarchical navigable small world (high recall)
    
    Metadata storage:
    - SQLite: For large datasets (362M+ patterns) - memory efficient
    - Pickle: Legacy format for smaller datasets
    
    Trajectories:
    - trajectories.npy: Memory-mapped NumPy array with 15-point future returns
    """
    
    def __init__(
        self,
        dimension: int = None,
        index_type: str = None,
        index_dir: str = None,
        use_gpu: bool = None
    ):
        self.dimension = dimension or settings.window_size
        self.index_type = index_type or settings.index_type
        self.index_dir = index_dir or settings.index_dir
        self.use_gpu = use_gpu if use_gpu is not None else settings.use_gpu
        
        self.index: Optional[faiss.Index] = None
        self.metadata: List[Dict] = []  # For pickle-based metadata
        self.metadata_db: Optional[sqlite3.Connection] = None  # For SQLite metadata
        self.trajectories: Optional[np.ndarray] = None  # Memory-mapped trajectories
        self.use_sqlite = False
        self.is_trained = False
        
        os.makedirs(self.index_dir, exist_ok=True)
        
        logger.info(
            "PatternIndexer initialized",
            dimension=self.dimension,
            index_type=self.index_type,
            use_gpu=self.use_gpu
        )
    
    def _create_index(self, n_vectors: int) -> faiss.Index:
        """
        Create FAISS index based on dataset size and config
        
        Index selection strategy:
        - <100K vectors: Flat (exact, fast enough)
        - 100K-1M: IVFFlat (approximate, good balance)
        - >1M: IVF+PQ (compressed, scalable)
        """
        
        if n_vectors < 100_000:
            # Exact search for small datasets
            logger.info("Creating IndexFlatL2 (exact search)")
            index = faiss.IndexFlatL2(self.dimension)
            
        elif n_vectors < 1_000_000:
            # IVF for medium datasets
            nlist = min(4096, int(np.sqrt(n_vectors)))
            logger.info(f"Creating IndexIVFFlat with {nlist} clusters")
            
            quantizer = faiss.IndexFlatL2(self.dimension)
            index = faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
            
        else:
            # IVF + PQ for large datasets (compressed)
            # Parse index_type string like "IVF4096,PQ32"
            nlist = 4096
            m = 16  # Number of subquantizers
            nbits = 8
            
            if "IVF" in self.index_type and "PQ" in self.index_type:
                parts = self.index_type.split(",")
                nlist = int(parts[0].replace("IVF", ""))
                pq_part = parts[1] if len(parts) > 1 else "PQ16"
                m = int(pq_part.replace("PQ", ""))
            
            logger.info(
                f"Creating IndexIVFPQ",
                nlist=nlist,
                m=m,
                nbits=nbits
            )
            
            quantizer = faiss.IndexFlatL2(self.dimension)
            index = faiss.IndexIVFPQ(quantizer, self.dimension, nlist, m, nbits)
        
        # GPU support
        if self.use_gpu and faiss.get_num_gpus() > 0:
            logger.info("Moving index to GPU")
            res = faiss.StandardGpuResources()
            index = faiss.index_cpu_to_gpu(res, 0, index)
        
        return index
    
    def build_index(
        self,
        vectors: np.ndarray,
        metadata: List[Dict],
        train_size: int = 500_000
    ) -> None:
        """
        Build FAISS index from vectors
        
        Args:
            vectors: Pattern vectors (N, dimension)
            metadata: Metadata for each vector
            train_size: Number of vectors for training (IVF/PQ)
        """
        n_vectors = len(vectors)
        
        if n_vectors == 0:
            raise ValueError("No vectors provided")
        
        if vectors.shape[1] != self.dimension:
            raise ValueError(
                f"Vector dimension {vectors.shape[1]} != expected {self.dimension}"
            )
        
        logger.info(
            "Building index",
            n_vectors=n_vectors,
            dimension=self.dimension
        )
        
        # Ensure float32
        vectors = vectors.astype(np.float32)
        
        # Create index
        self.index = self._create_index(n_vectors)
        
        # Train if needed (IVF, PQ indexes)
        if hasattr(self.index, 'train') and not self.index.is_trained:
            train_size = min(train_size, n_vectors)
            train_indices = np.random.choice(n_vectors, train_size, replace=False)
            train_vectors = vectors[train_indices]
            
            logger.info("Training index", train_size=train_size)
            self.index.train(train_vectors)
        
        # Add vectors
        logger.info("Adding vectors to index")
        self.index.add(vectors)
        
        # Store metadata
        self.metadata = metadata
        self.is_trained = True
        
        logger.info(
            "Index built successfully",
            total_vectors=self.index.ntotal,
            index_type=type(self.index).__name__
        )
    
    def add_vectors(
        self,
        vectors: np.ndarray,
        metadata: List[Dict]
    ) -> None:
        """Add more vectors to existing index"""
        if self.index is None:
            raise RuntimeError("Index not initialized. Call build_index first.")
        
        vectors = vectors.astype(np.float32)
        
        # Update IDs in metadata
        start_id = len(self.metadata)
        for i, meta in enumerate(metadata):
            meta['id'] = start_id + i
        
        self.index.add(vectors)
        self.metadata.extend(metadata)
        
        logger.info(
            "Added vectors",
            new_vectors=len(vectors),
            total_vectors=self.index.ntotal
        )
    
    def search(
        self,
        query: np.ndarray,
        k: int = 50,
        nprobe: int = None
    ) -> Tuple[np.ndarray, np.ndarray, List[Dict]]:
        """
        Search for k nearest neighbors
        
        Args:
            query: Query vector(s) (1, dimension) or (N, dimension)
            k: Number of neighbors
            nprobe: Number of clusters to search (IVF indexes)
            
        Returns:
            distances: Distance to each neighbor
            indices: Index of each neighbor
            neighbors_metadata: Metadata for each neighbor
        """
        if self.index is None:
            raise RuntimeError("Index not loaded")
        
        # Ensure correct shape
        query = query.astype(np.float32)
        if query.ndim == 1:
            query = query.reshape(1, -1)
        
        # Set nprobe for IVF indexes
        nprobe = nprobe or settings.index_nprobe
        if hasattr(self.index, 'nprobe'):
            self.index.nprobe = nprobe
        
        # Search
        distances, indices = self.index.search(query, k)
        
        # Get metadata for results
        neighbors_metadata = []
        
        if self.use_sqlite and self.metadata_db:
            # Fetch from SQLite (batch query for efficiency)
            valid_indices = [int(idx) for idx in indices[0] if idx >= 0]
            if valid_indices:
                placeholders = ','.join('?' * len(valid_indices))
                cursor = self.metadata_db.execute(
                    f"SELECT id, ticker, date, time, future_return FROM patterns WHERE id IN ({placeholders})",
                    valid_indices
                )
                rows = {row[0]: row for row in cursor.fetchall()}
                
                for idx in indices[0]:
                    if idx >= 0 and idx in rows:
                        row = rows[idx]
                        pattern_id = row[0]
                        
                        # Get full 15-point trajectory if available
                        if self.trajectories is not None and pattern_id < len(self.trajectories):
                            future_returns = self.trajectories[pattern_id].tolist()
                        else:
                            # Fallback to final_return only
                            future_returns = [row[4]] if row[4] else []
                        
                        neighbors_metadata.append({
                            'id': pattern_id,
                            'symbol': row[1],
                            'date': row[2],
                            'start_time': row[3],
                            'end_time': row[3],  # Same as start for now
                            'future_returns': future_returns,
                        })
                    else:
                        neighbors_metadata.append(None)
            else:
                neighbors_metadata = [None] * len(indices[0])
        else:
            # Use in-memory metadata (legacy)
            for idx in indices[0]:
                if idx >= 0 and idx < len(self.metadata):
                    neighbors_metadata.append(self.metadata[idx])
                else:
                    neighbors_metadata.append(None)
        
        return distances[0], indices[0], neighbors_metadata
    
    def save(self, name: str = "patterns") -> Tuple[str, str]:
        """
        Save index and metadata to disk
        
        Args:
            name: Base name for files
            
        Returns:
            Paths to index and metadata files
        """
        if self.index is None:
            raise RuntimeError("No index to save")
        
        index_path = os.path.join(self.index_dir, f"{name}.index")
        metadata_path = os.path.join(self.index_dir, f"{name}_metadata.pkl")
        
        # Save FAISS index
        # If GPU index, convert back to CPU for saving
        index_to_save = self.index
        if self.use_gpu:
            index_to_save = faiss.index_gpu_to_cpu(self.index)
        
        faiss.write_index(index_to_save, index_path)
        
        # Save metadata with pickle (faster than JSON for large data)
        with open(metadata_path, 'wb') as f:
            pickle.dump({
                'metadata': self.metadata,
                'dimension': self.dimension,
                'index_type': self.index_type,
                'created_at': datetime.now().isoformat(),
                'n_vectors': self.index.ntotal
            }, f)
        
        logger.info(
            "Index saved",
            index_path=index_path,
            metadata_path=metadata_path,
            n_vectors=self.index.ntotal
        )
        
        return index_path, metadata_path
    
    def load(self, name: str = "patterns") -> bool:
        """
        Load index and metadata from disk
        
        Tries in order:
        1. IVFPQ index + SQLite metadata (new format, memory efficient)
        2. Standard index + pickle metadata (legacy format)
        
        Args:
            name: Base name for files
            
        Returns:
            True if loaded successfully
        """
        # Try new IVFPQ + SQLite format first
        ivfpq_index_path = os.path.join(self.index_dir, f"{name}_ivfpq.index")
        sqlite_metadata_path = os.path.join(self.index_dir, f"{name}_metadata.db")
        
        if os.path.exists(ivfpq_index_path) and os.path.exists(sqlite_metadata_path):
            try:
                logger.info("Loading IVFPQ index with SQLite metadata...")
                
                # Load FAISS IVFPQ index
                self.index = faiss.read_index(ivfpq_index_path)
                
                # Move to GPU if configured
                if self.use_gpu and faiss.get_num_gpus() > 0:
                    res = faiss.StandardGpuResources()
                    self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
                
                # Open SQLite connection (read-only)
                self.metadata_db = sqlite3.connect(
                    f"file:{sqlite_metadata_path}?mode=ro",
                    uri=True,
                    check_same_thread=False
                )
                self.use_sqlite = True
                self.is_trained = True
                
                # Load trajectories (memory-mapped raw binary file)
                trajectories_path = os.path.join(self.index_dir, f"{name}_trajectories.npy")
                if os.path.exists(trajectories_path):
                    try:
                        # File was created with np.memmap, so load as memmap
                        # Shape: (n_patterns, 15) float32
                        n_patterns = self.index.ntotal
                        self.trajectories = np.memmap(
                            trajectories_path, 
                            dtype='float32', 
                            mode='r',  # read-only
                            shape=(n_patterns, 15)
                        )
                        logger.info(
                            "Trajectories loaded (memmap)",
                            shape=self.trajectories.shape,
                            path=trajectories_path
                        )
                    except Exception as e:
                        logger.error("Failed to load trajectories", error=str(e))
                        self.trajectories = None
                else:
                    logger.warning("Trajectories file not found", path=trajectories_path)
                    self.trajectories = None
                
                # Get count from SQLite
                cursor = self.metadata_db.execute("SELECT COUNT(*) FROM patterns")
                n_metadata = cursor.fetchone()[0]
                
                logger.info(
                    "IVFPQ index loaded with SQLite metadata",
                    n_vectors=self.index.ntotal,
                    n_metadata=n_metadata,
                    n_trajectories=self.trajectories.shape[0] if self.trajectories is not None else 0,
                    index_type="IVFPQ",
                    metadata_type="SQLite"
                )
                
                return True
                
            except Exception as e:
                logger.error("Failed to load IVFPQ index", error=str(e))
                # Fall through to try legacy format
        
        # Try legacy format (standard index + pickle)
        index_path = os.path.join(self.index_dir, f"{name}.index")
        metadata_path = os.path.join(self.index_dir, f"{name}_metadata.pkl")
        
        if not os.path.exists(index_path) or not os.path.exists(metadata_path):
            logger.warning("No index files found", 
                         ivfpq_path=ivfpq_index_path,
                         legacy_path=index_path)
            return False
        
        try:
            # Load FAISS index
            self.index = faiss.read_index(index_path)
            
            # Move to GPU if configured
            if self.use_gpu and faiss.get_num_gpus() > 0:
                res = faiss.StandardGpuResources()
                self.index = faiss.index_cpu_to_gpu(res, 0, self.index)
            
            # Load metadata from pickle
            with open(metadata_path, 'rb') as f:
                data = pickle.load(f)
                self.metadata = data['metadata']
                self.dimension = data.get('dimension', self.dimension)
            
            self.use_sqlite = False
            self.is_trained = True
            
            logger.info(
                "Legacy index loaded",
                n_vectors=self.index.ntotal,
                n_metadata=len(self.metadata),
                index_type=type(self.index).__name__,
                metadata_type="pickle"
            )
            
            return True
            
        except Exception as e:
            logger.error("Failed to load index", error=str(e))
            return False
    
    def get_stats(self) -> Dict:
        """Get index statistics"""
        if self.index is None:
            return {"status": "not_initialized"}
        
        # Get metadata count - use index.ntotal as proxy (much faster than COUNT(*))
        # SQLite COUNT(*) on 362M rows takes ~20 seconds
        if self.use_sqlite:
            n_metadata = self.index.ntotal  # Same as vectors, avoid slow COUNT(*)
        else:
            n_metadata = len(self.metadata)
        
        stats = {
            "status": "ready",
            "n_vectors": self.index.ntotal,
            "n_metadata": n_metadata,
            "dimension": self.dimension,
            "index_type": type(self.index).__name__,
            "metadata_type": "SQLite" if self.use_sqlite else "pickle",
            "is_trained": self.is_trained,
            "has_trajectories": self.trajectories is not None,
            "trajectory_points": self.trajectories.shape[1] if self.trajectories is not None else 0,
        }
        
        # Memory estimation
        if hasattr(self.index, 'sa_code_size'):
            # PQ index - compressed
            stats["memory_mb"] = (self.index.ntotal * self.index.sa_code_size()) / (1024**2)
            stats["compression"] = "IVFPQ"
        else:
            # Flat index
            stats["memory_mb"] = (self.index.ntotal * self.dimension * 4) / (1024**2)
            stats["compression"] = "none"
        
        return stats


# CLI for testing
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Pattern Indexer")
    parser.add_argument("--test", action="store_true", help="Run with test data")
    
    args = parser.parse_args()
    
    if args.test:
        # Generate random test data
        n_vectors = 100_000
        dimension = 45
        
        print(f"Generating {n_vectors:,} random vectors...")
        vectors = np.random.randn(n_vectors, dimension).astype(np.float32)
        metadata = [{'id': i, 'symbol': f'TEST{i%100}'} for i in range(n_vectors)]
        
        # Build index
        indexer = PatternIndexer(dimension=dimension)
        indexer.build_index(vectors, metadata)
        
        # Test search
        query = vectors[0]
        distances, indices, neighbors = indexer.search(query, k=5)
        
        print(f"\n🔍 Search results for vector 0:")
        print(f"  Distances: {distances}")
        print(f"  Indices: {indices}")
        
        # Save and reload
        indexer.save("test")
        
        new_indexer = PatternIndexer(dimension=dimension)
        new_indexer.load("test")
        
        print(f"\n📊 Index stats:")
        print(new_indexer.get_stats())

