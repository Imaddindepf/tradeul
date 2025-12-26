#!/usr/bin/env python3
"""
Pattern Matching Service - CLI Tool
Utility commands for managing the service
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from glob import glob

import structlog

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S"),
        structlog.dev.ConsoleRenderer()
    ]
)
logger = structlog.get_logger()


def cmd_download(args):
    """Download flat files from Polygon S3"""
    from flat_files_downloader import FlatFilesDownloader
    
    downloader = FlatFilesDownloader()
    
    if args.days:
        files = downloader.download_last_n_days(args.days, force=args.force)
    else:
        start = datetime.strptime(args.start, "%Y-%m-%d")
        end = datetime.strptime(args.end, "%Y-%m-%d")
        files = downloader.download_range(start, end, force=args.force)
    
    print(f"\n✅ Downloaded {len(files)} files")
    print(downloader.get_download_stats())


def cmd_process(args):
    """Process downloaded files into vectors"""
    from data_processor import DataProcessor
    import numpy as np
    
    processor = DataProcessor()
    
    # Get files
    files = sorted(glob(f"{args.data_dir}/*.csv.gz"))
    
    if args.start:
        files = [f for f in files if args.start <= f.split('/')[-1].replace('.csv.gz', '')]
    if args.end:
        files = [f for f in files if f.split('/')[-1].replace('.csv.gz', '') <= args.end]
    
    if args.limit:
        files = files[:args.limit]
    
    print(f"Processing {len(files)} files...")
    
    vectors, metadata = processor.process_multiple_files(
        files,
        symbols_filter=args.symbols.split(',') if args.symbols else None,
        n_workers=args.workers
    )
    
    print(f"\n✅ Extracted {len(vectors):,} patterns")
    print(f"   Vector shape: {vectors.shape}")
    print(f"   Memory: {vectors.nbytes / 1024**2:.2f} MB")
    
    if args.output:
        np.save(f"{args.output}_vectors.npy", vectors)
        import pickle
        with open(f"{args.output}_metadata.pkl", 'wb') as f:
            pickle.dump(metadata, f)
        print(f"   Saved to {args.output}_*")


def cmd_build(args):
    """Build FAISS index"""
    from data_processor import DataProcessor
    from pattern_indexer import PatternIndexer
    import numpy as np
    
    # Load or process data
    if args.vectors:
        print(f"Loading vectors from {args.vectors}...")
        vectors = np.load(args.vectors)
        import pickle
        with open(args.vectors.replace('_vectors.npy', '_metadata.pkl'), 'rb') as f:
            metadata = pickle.load(f)
    else:
        # Process from scratch
        processor = DataProcessor()
        files = sorted(glob(f"{args.data_dir}/*.csv.gz"))
        
        if args.start:
            files = [f for f in files if args.start <= f.split('/')[-1].replace('.csv.gz', '')]
        if args.end:
            files = [f for f in files if f.split('/')[-1].replace('.csv.gz', '') <= args.end]
        
        print(f"Processing {len(files)} files...")
        vectors, metadata = processor.process_multiple_files(files)
    
    print(f"\n📊 Building index with {len(vectors):,} vectors...")
    
    indexer = PatternIndexer()
    indexer.build_index(vectors, metadata)
    indexer.save(args.name)
    
    print(f"\n✅ Index built and saved as '{args.name}'")
    print(indexer.get_stats())


def cmd_search(args):
    """Test search query"""
    from pattern_matcher import PatternMatcher
    import numpy as np
    
    async def do_search():
        matcher = PatternMatcher()
        await matcher.initialize()
        
        if not matcher.is_ready:
            print("❌ Index not loaded. Build index first.")
            return
        
        if args.prices:
            prices = [float(p) for p in args.prices.split(',')]
            result = await matcher.search_with_prices(prices, k=args.k)
        else:
            result = await matcher.search(
                symbol=args.symbol,
                k=args.k,
                cross_asset=not args.same_ticker
            )
        
        print("\n🔍 Search Results:")
        print(f"   Status: {result.get('status')}")
        
        if 'forecast' in result:
            f = result['forecast']
            print(f"\n📈 Forecast ({f.get('horizon_minutes')} min):")
            print(f"   Mean Return: {f.get('mean_return')}%")
            print(f"   Prob UP:     {f.get('prob_up')*100:.1f}%")
            print(f"   Prob DOWN:   {f.get('prob_down')*100:.1f}%")
            print(f"   Confidence:  {f.get('confidence')}")
        
        if 'neighbors' in result:
            print(f"\n👥 Top Neighbors ({len(result['neighbors'])}):")
            for i, n in enumerate(result['neighbors'][:5]):
                print(f"   {i+1}. {n['symbol']} {n['date']} {n['start_time']} (dist: {n['distance']:.4f})")
        
        if 'stats' in result:
            print(f"\n⚡ Query time: {result['stats'].get('query_time_ms')}ms")
        
        await matcher.close()
    
    asyncio.run(do_search())


def cmd_stats(args):
    """Show index statistics"""
    from pattern_indexer import PatternIndexer
    from flat_files_downloader import FlatFilesDownloader
    
    print("📊 Service Statistics\n")
    
    # Index stats
    indexer = PatternIndexer()
    if indexer.load(args.name):
        print("FAISS Index:")
        for k, v in indexer.get_stats().items():
            print(f"   {k}: {v}")
    else:
        print("FAISS Index: Not found")
    
    print()
    
    # Data stats
    downloader = FlatFilesDownloader()
    print("Downloaded Data:")
    for k, v in downloader.get_download_stats().items():
        print(f"   {k}: {v}")


def main():
    parser = argparse.ArgumentParser(
        description="Pattern Matching Service CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Download command
    dl_parser = subparsers.add_parser('download', help='Download flat files')
    dl_parser.add_argument('--days', type=int, help='Download last N days')
    dl_parser.add_argument('--start', help='Start date (YYYY-MM-DD)')
    dl_parser.add_argument('--end', help='End date (YYYY-MM-DD)')
    dl_parser.add_argument('--force', action='store_true', help='Force re-download')
    
    # Process command
    proc_parser = subparsers.add_parser('process', help='Process files into vectors')
    proc_parser.add_argument('--data-dir', default='./data/minute_aggs')
    proc_parser.add_argument('--start', help='Start date filter')
    proc_parser.add_argument('--end', help='End date filter')
    proc_parser.add_argument('--symbols', help='Comma-separated symbols filter')
    proc_parser.add_argument('--limit', type=int, help='Limit files to process')
    proc_parser.add_argument('--workers', type=int, default=4)
    proc_parser.add_argument('--output', help='Output prefix for vectors/metadata')
    
    # Build command
    build_parser = subparsers.add_parser('build', help='Build FAISS index')
    build_parser.add_argument('--data-dir', default='./data/minute_aggs')
    build_parser.add_argument('--vectors', help='Pre-processed vectors file')
    build_parser.add_argument('--start', help='Start date filter')
    build_parser.add_argument('--end', help='End date filter')
    build_parser.add_argument('--name', default='patterns', help='Index name')
    
    # Search command
    search_parser = subparsers.add_parser('search', help='Test search query')
    search_parser.add_argument('--symbol', default='AAPL', help='Symbol to search')
    search_parser.add_argument('--prices', help='Comma-separated prices')
    search_parser.add_argument('--k', type=int, default=50, help='Number of neighbors')
    search_parser.add_argument('--same-ticker', action='store_true', help='Same ticker only')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.add_argument('--name', default='patterns', help='Index name')
    
    args = parser.parse_args()
    
    if args.command == 'download':
        cmd_download(args)
    elif args.command == 'process':
        cmd_process(args)
    elif args.command == 'build':
        cmd_build(args)
    elif args.command == 'search':
        cmd_search(args)
    elif args.command == 'stats':
        cmd_stats(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()

