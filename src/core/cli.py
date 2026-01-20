"""Command-line interface for AETHER-MINE."""

import asyncio
import sys
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from src.core.config import get_settings


console = Console()


@click.group()
@click.version_option(version="1.0.0")
def main():
    """AETHER-MINE: Distributed Intelligence & Adversarial Web Mining Engine."""
    pass


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload")
def serve(host: str, port: int, reload: bool):
    """Start the API server."""
    import uvicorn
    
    console.print(f"[green]Starting AETHER-MINE API server on {host}:{port}[/green]")
    uvicorn.run(
        "src.api.controller:app",
        host=host,
        port=port,
        reload=reload,
    )


@main.command()
@click.argument("url")
@click.option("--method", "-m", default="shadow_api", 
              type=click.Choice(["shadow_api", "pattern_fuzz", "cloud_sniff", "dorking"]))
@click.option("--output", "-o", help="Output file for results")
def mine(url: str, method: str, output: Optional[str]):
    """Mine a target URL."""
    console.print(f"[blue]Mining {url} using {method}...[/blue]")
    
    async def run_mining():
        if method == "shadow_api":
            from src.miners.shadow_api import ShadowAPIInterceptor
            
            interceptor = ShadowAPIInterceptor()
            try:
                await interceptor.start()
                apis = await interceptor.navigate_and_intercept(url)
                
                table = Table(title="Discovered APIs")
                table.add_column("Endpoint", style="cyan")
                table.add_column("Method", style="green")
                table.add_column("Auth Type", style="yellow")
                
                for api in apis:
                    table.add_row(api.endpoint, api.method.value, api.auth_type or "None")
                
                console.print(table)
                console.print(f"[green]Discovered {len(apis)} APIs[/green]")
                
            finally:
                await interceptor.stop()
                
        elif method == "pattern_fuzz":
            from src.miners.pattern_fuzzer import PatternFuzzer
            
            fuzzer = PatternFuzzer()
            results = await fuzzer.fuzz_url(url)
            discoveries = fuzzer.get_discoveries()
            
            console.print(f"[green]Checked {len(results)} URLs[/green]")
            console.print(f"[green]Discovered {len(discoveries)} resources[/green]")
            
            for d in discoveries[:10]:
                console.print(f"  [cyan]{d}[/cyan]")
                
        elif method == "cloud_sniff":
            from src.miners.cloud_sniffer import CloudBucketSniffer
            
            sniffer = CloudBucketSniffer()
            results = await sniffer.sniff_brand(url)
            public = sniffer.get_public_buckets()
            
            console.print(f"[green]Checked {len(results)} bucket permutations[/green]")
            console.print(f"[green]Found {len(public)} public buckets[/green]")
            
            for b in public:
                console.print(f"  [cyan]{b.url}[/cyan] ({b.objects_found} objects)")
                
        elif method == "dorking":
            from src.miners.dorking import DorkingSwarm
            
            swarm = DorkingSwarm()
            results = await swarm.swarm_target(url)
            
            total = sum(len(r) for r in results.values())
            console.print(f"[green]Found {total} results across {len(results)} categories[/green]")
            
            for category, items in results.items():
                console.print(f"  [yellow]{category}[/yellow]: {len(items)} results")
    
    asyncio.run(run_mining())


@main.command()
@click.argument("brand_name")
@click.option("--providers", "-p", multiple=True, default=["aws", "azure", "gcp"])
@click.option("--max-perms", default=200, help="Maximum permutations to check")
def sniff_buckets(brand_name: str, providers: tuple, max_perms: int):
    """Sniff for public cloud buckets related to a brand."""
    from src.miners.cloud_sniffer import CloudBucketSniffer
    
    console.print(f"[blue]Sniffing for buckets related to '{brand_name}'...[/blue]")
    
    async def run():
        sniffer = CloudBucketSniffer()
        results = await sniffer.sniff_brand(
            brand_name,
            providers=list(providers),
            max_permutations=max_perms,
        )
        
        public = sniffer.get_public_buckets()
        
        table = Table(title="Public Buckets Found")
        table.add_column("Bucket", style="cyan")
        table.add_column("Provider", style="green")
        table.add_column("Objects", style="yellow")
        
        for b in public:
            table.add_row(b.bucket_name, b.provider, str(b.objects_found))
        
        console.print(table)
        console.print(f"[green]Total checked: {len(results)}[/green]")
        console.print(f"[green]Public buckets: {len(public)}[/green]")
    
    asyncio.run(run())


@main.command()
@click.argument("url")
@click.option("--max-variants", default=20, help="Max variants per pattern")
@click.option("--depth", default=1, help="Recursive depth")
def fuzz(url: str, max_variants: int, depth: int):
    """Fuzz URL patterns to discover unindexed resources."""
    from src.miners.pattern_fuzzer import PatternFuzzer, URLPatternAnalyzer
    
    console.print(f"[blue]Analyzing patterns in {url}...[/blue]")
    
    analyzer = URLPatternAnalyzer()
    patterns = analyzer.analyze(url)
    
    if patterns:
        table = Table(title="Detected Patterns")
        table.add_column("Type", style="cyan")
        table.add_column("Value", style="green")
        table.add_column("Position", style="yellow")
        
        for p in patterns:
            table.add_row(p.pattern_type, p.original_value, str(p.position))
        
        console.print(table)
    else:
        console.print("[yellow]No fuzzable patterns detected[/yellow]")
        return
    
    async def run():
        fuzzer = PatternFuzzer()
        results = await fuzzer.fuzz_url(url, max_variants, depth)
        discoveries = fuzzer.get_discoveries()
        
        console.print(f"\n[green]Checked {len(results)} URLs[/green]")
        console.print(f"[green]Discovered {len(discoveries)} resources:[/green]")
        
        for d in discoveries:
            console.print(f"  [cyan]{d}[/cyan]")
    
    asyncio.run(run())


@main.command()
def stats():
    """Show system statistics."""
    from src.storage.duckdb_index import get_index
    from src.storage.quarantine import QuarantineManager
    from src.core.telemetry import get_telemetry
    
    index = get_index()
    quarantine = QuarantineManager()
    telemetry = get_telemetry()
    
    index_stats = index.get_global_stats()
    quarantine_stats = quarantine.get_quarantine_stats()
    telemetry_stats = telemetry.get_stats()
    
    table = Table(title="AETHER-MINE System Statistics")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Total Records", str(index_stats["total_records"]))
    table.add_row("Unique Content Hashes", str(index_stats["unique_content_hashes"]))
    table.add_row("Unique Domains", str(index_stats["unique_domains"]))
    table.add_row("Finalized Batches", str(index_stats["finalized_batches"]))
    table.add_row("Total Storage", f"{index_stats['total_storage_bytes'] / 1024 / 1024:.2f} MB")
    table.add_row("Duplicate Rate", f"{index_stats['duplicate_rate']:.2%}")
    table.add_row("Quarantined Records", str(quarantine_stats["total_quarantined"]))
    table.add_row("Total Requests", str(telemetry_stats.get("total_requests", 0)))
    table.add_row("Success Rate", f"{telemetry_stats.get('success_rate', 0):.2%}")
    
    console.print(table)


@main.command()
def config():
    """Show current configuration."""
    settings = get_settings()
    
    table = Table(title="AETHER-MINE Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Environment", settings.environment)
    table.add_row("Log Level", settings.log_level)
    table.add_row("Batch Max Records", str(settings.batch_max_records))
    table.add_row("Batch Max Size", f"{settings.batch_max_size_mb} MB")
    table.add_row("Proxy Pool Size", str(settings.proxy_pool_size))
    table.add_row("Fingerprint Rotation", f"Every {settings.fingerprint_rotation_requests} requests")
    table.add_row("Behavioral Noise", "Enabled" if settings.behavioral_noise_enabled else "Disabled")
    table.add_row("LLM Provider", settings.llm_provider)
    table.add_row("Browser Headless", "Yes" if settings.browser_headless else "No")
    
    console.print(table)


@main.command()
@click.option("--queue", "-q", default="aether_mine", help="Queue to process")
@click.option("--concurrency", "-c", default=4, help="Worker concurrency")
def worker(queue: str, concurrency: int):
    """Start a Celery worker."""
    from src.workers.celery_app import celery_app
    
    console.print(f"[green]Starting Celery worker for queue: {queue}[/green]")
    
    celery_app.worker_main([
        "worker",
        f"--queues={queue}",
        f"--concurrency={concurrency}",
        "--loglevel=INFO",
    ])


@main.command()
def beat():
    """Start the Celery beat scheduler."""
    from src.workers.celery_app import celery_app
    
    console.print("[green]Starting Celery beat scheduler[/green]")
    
    celery_app.start([
        "beat",
        "--loglevel=INFO",
    ])


if __name__ == "__main__":
    main()
