"""
Command Line Interface (CLI) for WeKnora Vietnamese Pre-RAG Pipeline.
Full Lifecycle: Crawl (Raw) -> Bronze -> Silver -> Gold (Filtered Consultation Knowledge).
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

# Ensure UTF-8 console output on Windows
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Fallback package setup when invoked directly as a standalone script
if __package__ is None or __package__ == "":
    src_parent = Path(__file__).resolve().parent.parent
    if str(src_parent) not in sys.path:
        sys.path.insert(0, str(src_parent))
    __package__ = "pipeline"

from .config import PipelineConfig
from .crawlers.raw_crawler import RawCrawler
from .crawlers.url_discoverer import UrlDiscoverer
from .bronze_to_silver import BronzeToSilverPipeline
from .silver_to_gold import SilverToGoldPipeline
from .orchestrator import PreRAGPipeline


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_crawl(args):
    """Executes the raw crawling stage into Bronze & PDF directories."""
    setup_logging(args.verbose)
    config = PipelineConfig(
        bronze_dir=Path(args.bronze_dir) if args.bronze_dir else None,
        pdf_dir=Path(args.pdf_dir) if args.pdf_dir else None,
        sources_csv=Path(args.sources_csv) if args.sources_csv else None,
    )

    print("=" * 60)
    print("[CRAWLER] WEKNORA VIETNAMESE AUTOMOTIVE RAW DATA INGESTION")
    print("=" * 60)
    print(f"Bronze Directory : {config.bronze_dir}")
    print(f"PDF Directory    : {config.pdf_dir}")
    print(f"Sources CSV      : {config.sources_csv}")
    print("=" * 60)

    crawler = RawCrawler(bronze_dir=config.bronze_dir, pdf_dir=config.pdf_dir)
    discoverer = UrlDiscoverer()

    if args.discover_urls:
        print("\n🔍 Discovering and updating URLs...")
        count = discoverer.export_to_csv(config.sources_csv, include_dynamic=args.include_dynamic)
        print(f"✅ Discovered & exported {count} URLs to {config.sources_csv}")

    target_csv = config.sources_csv if config.sources_csv.exists() else None

    if args.mode == "all":
        print("\n🚀 Ingesting All Sources (API, FAQ, Promos, PDFs, Verified URLs)...")
        report = crawler.crawl_all(sources_csv=target_csv)
        print("\n" + "=" * 60)
        print("[SUCCESS] CRAWL COMPLETED")
        print("=" * 60)
        print(f"Duration             : {report.elapsed_seconds:.2f}s")
        print(f"Relational API       : {report.relational_status} ({report.relational_bytes:,} bytes)")
        print(f"FAQ HTML             : {report.faq_status} ({report.faq_bytes:,} bytes)")
        print(f"EV Promo Articles    : {report.promos_crawled} articles")
        print(f"PDF Documents        : {report.pdf_count} files in manifest")
        print(f"External Sources     : {report.sources_crawled} articles")
        print("=" * 60)
    elif args.mode == "api":
        res = crawler.crawl_relational_pricing()
        print(f"✅ Relational API result: {res}")
    elif args.mode == "faq":
        res = crawler.crawl_faq()
        print(f"✅ FAQ result: {res}")
    elif args.mode == "promos":
        res = crawler.crawl_promotions(max_pages=args.pages)
        print(f"✅ Crawled {len(res)} EV promotional articles")
    elif args.mode == "pdf":
        res = crawler.crawl_brochures_and_policies()
        print(f"✅ PDF Manifest updated: {res}")
    elif args.mode == "sources":
        res = crawler.crawl_sources(sources_csv=target_csv)
        print(f"✅ Crawled {len(res)} sources")


def cmd_silver(args):
    """Executes Bronze-to-Silver normalization and hierarchical chunking."""
    setup_logging(args.verbose)
    config = PipelineConfig(
        bronze_dir=Path(args.bronze_dir) if args.bronze_dir else None,
        pdf_dir=Path(args.pdf_dir) if args.pdf_dir else None,
        silver_dir=Path(args.silver_dir) if args.silver_dir else None,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    print("=" * 60)
    print("[PIPELINE] BRONZE-TO-SILVER (VIETNAMESE SPECIALIZED PRE-RAG)")
    print("=" * 60)
    print(f"Bronze Directory : {config.bronze_dir}")
    print(f"PDF Directory    : {config.pdf_dir}")
    print(f"Silver Directory : {config.silver_dir}")
    print(f"Chunk Settings   : size={config.chunk_size}, overlap={config.chunk_overlap}")
    print("=" * 60)

    silver_pipeline = BronzeToSilverPipeline(config=config)
    report = silver_pipeline.run()

    print("\n" + "=" * 60)
    print("[SUCCESS] BRONZE -> SILVER COMPLETE")
    print("=" * 60)
    print(f"Duration             : {report.elapsed_seconds:.2f}s")
    print(f"Bronze Ingested      : {report.total_bronze_records} records")
    print(f"Silver Documents     : {report.total_silver_documents} docs")
    print(f"Silver Chunks        : {report.total_silver_chunks} chunks")
    print(f"FAQ Q&A Items        : {report.total_faq_items} items")
    print(f"Vehicles Cataloged   : {report.total_vehicles} models")
    print(f"Average Quality Score: {report.average_quality_score}")
    print(f"Silver Directory     : {config.silver_dir}")
    print("=" * 60)


def cmd_gold(args):
    """Executes Silver-to-Gold car consultation filter (dropping irrelevant non-purchasing data)."""
    setup_logging(args.verbose)
    config = PipelineConfig(
        silver_dir=Path(args.silver_dir) if args.silver_dir else None,
        gold_dir=Path(args.gold_dir) if args.gold_dir else None,
    )
    run_gold_stage(config)


def run_gold_stage(config: PipelineConfig):
    """Helper executing Silver-to-Gold pipeline."""
    print("\n" + "=" * 60)
    print("[PIPELINE] SILVER-TO-GOLD: CAR PURCHASING CONSULTATION FILTER")
    print("=" * 60)
    print(f"Silver Directory : {config.silver_dir}")
    print(f"Gold Directory   : {config.gold_dir}")
    print("=" * 60)

    gold_pipeline = SilverToGoldPipeline(config=config)
    gold_report = gold_pipeline.run()

    print("\n" + "=" * 60)
    print("[SUCCESS] GOLD CURATION COMPLETE")
    print("=" * 60)
    print(f"Total Silver Chunks : {gold_report['total_silver_chunks']}")
    print(f"Filtered Out Chunks : {gold_report['filtered_out_chunks']} (traffic rules, fines, chassis, noise)")
    print(f"Admitted Gold Chunks: {gold_report['total_gold_chunks']} ({gold_report['retention_rate_percent']}%)")
    print(f"Gold Documents      : {gold_report['total_gold_documents']}")
    print(f"Gold FAQ Items      : {gold_report['total_gold_faq']}")
    print(f"Gold Vehicles       : {gold_report['total_gold_vehicles']}")
    print("Top Consultation Topics:")
    for topic, count in gold_report["gold_topic_distribution"].items():
        print(f"  - {topic:25s}: {count:4d} chunks")
    print(f"Gold Output Dir     : {config.gold_dir}")
    print("=" * 60)


def cmd_run(args):
    """Executes complete Pre-RAG pipeline: [Crawl ->] Bronze -> Silver -> Gold."""
    setup_logging(args.verbose)
    config = PipelineConfig(
        bronze_dir=Path(args.bronze_dir) if args.bronze_dir else None,
        pdf_dir=Path(args.pdf_dir) if args.pdf_dir else None,
        silver_dir=Path(args.silver_dir) if args.silver_dir else None,
        gold_dir=Path(args.gold_dir) if args.gold_dir else None,
        sources_csv=Path(args.sources_csv) if args.sources_csv else None,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
    )

    orchestrator = PreRAGPipeline(config=config)
    res = orchestrator.run_all(crawl_first=args.crawl, include_dynamic_urls=args.dynamic_urls)

    print("\n" + "=" * 60)
    print("[COMPLETE] END-TO-END PRE-RAG PIPELINE FINISHED")
    print("=" * 60)
    print(f"Duration             : {res['elapsed_seconds']:.2f}s")
    print(f"Silver Documents     : {res['silver_documents']}")
    print(f"Silver Chunks        : {res['silver_chunks']}")
    print(f"Gold Documents       : {res['gold_documents']}")
    print(f"Gold Chunks          : {res['gold_chunks']}")
    print(f"Filtered Out Chunks  : {res['filtered_out_chunks']}")
    print(f"Retention Rate       : {res['retention_rate_percent']}%")
    print("=" * 60)


def cmd_stats(args):
    """Views statistics of generated Silver or Gold dataset."""
    stage = args.stage
    target_dir = Path(args.dir) if args.dir else (Path("dataset/gold") if stage == "gold" else Path("dataset/silver"))
    report_file = target_dir / f"{stage}_report.json"

    if not report_file.exists():
        print(f"[ERROR] Report file not found at {report_file}. Have you run the pipeline yet?")
        sys.exit(1)

    with open(report_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_sample(args):
    """Views sample records from Silver or Gold datasets."""
    stage = args.stage
    target_dir = Path(args.dir) if args.dir else (Path("dataset/gold") if stage == "gold" else Path("dataset/silver"))
    target_type = args.type
    file_map = {
        "documents": target_dir / f"{stage}_documents.jsonl",
        "chunks": target_dir / f"{stage}_chunks.jsonl",
        "faq": target_dir / f"{stage}_faq.jsonl",
        "vehicles": target_dir / f"{stage}_vehicles.jsonl",
    }

    target_file = file_map.get(target_type)
    if not target_file or not target_file.exists():
        print(f"[ERROR] File not found: {target_file}")
        sys.exit(1)

    print(f"--- Displaying {args.n} sample records from {target_file.name} ---")
    with open(target_file, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx >= args.n:
                break
            record = json.loads(line)
            print(f"\n[Record #{idx + 1}]")
            print(json.dumps(record, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="WeKnora Vietnamese Pre-RAG Pipeline (Crawl -> Bronze -> Silver -> Gold)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: crawl
    crawl_parser = subparsers.add_parser("crawl", help="Crawl and ingest raw data into Bronze & PDF layers")
    crawl_parser.add_argument("--mode", choices=["all", "api", "faq", "promos", "pdf", "sources"], default="all", help="Crawl target")
    crawl_parser.add_argument("--bronze-dir", type=str, default=None, help="Path to bronze dir")
    crawl_parser.add_argument("--pdf-dir", type=str, default=None, help="Path to pdf dir")
    crawl_parser.add_argument("--sources-csv", type=str, default=None, help="Path to sources.csv")
    crawl_parser.add_argument("--discover-urls", action="store_true", help="Discover URLs before crawling")
    crawl_parser.add_argument("--include-dynamic", action="store_true", help="Include dynamic feed URLs in discovery")
    crawl_parser.add_argument("--pages", type=int, default=2, help="Number of pages for promo scan")
    crawl_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    crawl_parser.set_defaults(func=cmd_crawl)

    # Subcommand: silver
    silver_parser = subparsers.add_parser("silver", help="Run Bronze -> Silver normalization and hierarchical chunking")
    silver_parser.add_argument("--bronze-dir", type=str, default=None, help="Path to bronze dir")
    silver_parser.add_argument("--pdf-dir", type=str, default=None, help="Path to pdf dir")
    silver_parser.add_argument("--silver-dir", type=str, default=None, help="Path to silver dir")
    silver_parser.add_argument("--chunk-size", type=int, default=512, help="Chunk size")
    silver_parser.add_argument("--chunk-overlap", type=int, default=80, help="Chunk overlap")
    silver_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    silver_parser.set_defaults(func=cmd_silver)

    # Subcommand: gold
    gold_parser = subparsers.add_parser("gold", help="Run Silver -> Gold car purchasing consultation filter")
    gold_parser.add_argument("--silver-dir", type=str, default=None, help="Path to silver dir")
    gold_parser.add_argument("--gold-dir", type=str, default=None, help="Path to gold dir")
    gold_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    gold_parser.set_defaults(func=cmd_gold)

    # Subcommand: run (End-to-End Pre-RAG)
    run_parser = subparsers.add_parser("run", help="Run complete Pre-RAG pipeline ([Crawl ->] Silver -> Gold)")
    run_parser.add_argument("--crawl", action="store_true", help="Execute raw crawler first before normalization")
    run_parser.add_argument("--dynamic-urls", action="store_true", help="Include dynamic URL feeds when crawling")
    run_parser.add_argument("--bronze-dir", type=str, default=None, help="Path to bronze dir")
    run_parser.add_argument("--pdf-dir", type=str, default=None, help="Path to pdf dir")
    run_parser.add_argument("--silver-dir", type=str, default=None, help="Path to silver dir")
    run_parser.add_argument("--gold-dir", type=str, default=None, help="Path to gold dir")
    run_parser.add_argument("--sources-csv", type=str, default=None, help="Path to sources.csv")
    run_parser.add_argument("--chunk-size", type=int, default=512, help="Chunk size")
    run_parser.add_argument("--chunk-overlap", type=int, default=80, help="Chunk overlap")
    run_parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    run_parser.set_defaults(func=cmd_run)

    # Subcommand: stats
    stats_parser = subparsers.add_parser("stats", help="Display summary stats")
    stats_parser.add_argument("--stage", choices=["silver", "gold"], default="gold")
    stats_parser.add_argument("--dir", type=str, default=None, help="Path to target directory")
    stats_parser.set_defaults(func=cmd_stats)

    # Subcommand: sample
    sample_parser = subparsers.add_parser("sample", help="Display sample records")
    sample_parser.add_argument("--stage", choices=["silver", "gold"], default="gold")
    sample_parser.add_argument("--dir", type=str, default=None, help="Path to target directory")
    sample_parser.add_argument("--type", choices=["documents", "chunks", "faq", "vehicles"], default="chunks")
    sample_parser.add_argument("-n", type=int, default=2, help="Number of records to display")
    sample_parser.set_defaults(func=cmd_sample)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
