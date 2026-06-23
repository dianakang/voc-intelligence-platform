import json
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from src.config import settings
from src.workflow.graph import run_voc_pipeline
from src.reports.generator import generate_markdown_report, generate_json_report

app = typer.Typer(name="voc", help="Samsung TV VOC Intelligence Platform CLI")
console = Console()


@app.command()
def run(
    model_code: str = typer.Argument("UN50U7900FFXZA", help="Samsung TV model code"),
    max_reviews: int = typer.Option(200, "--max-reviews", "-n", help="Max reviews to fetch"),
    url: Optional[str] = typer.Option(
        None, "--url", help="Product page URL to scrape (defaults to the built-in U7900F page)"
    ),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    json_output: bool = typer.Option(False, "--json", help="Also save JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose agent output"),
    skip_if_cached: bool = typer.Option(
        False,
        "--skip-if-cached",
        help="Skip all LLM analysis and reload the last saved result if reviews, "
        "model_code, max_reviews, and spec are unchanged since the last full run.",
    ),
):
    """Run VOC analysis pipeline for a Samsung TV model."""
    console.print(Panel.fit(
        f"[bold blue]Samsung TV VOC Intelligence Platform[/bold blue]\n"
        f"Model: [cyan]{model_code}[/cyan]  ·  Max reviews: [cyan]{max_reviews}[/cyan]",
        border_style="blue",
    ))

    if not settings.anthropic_api_key and not settings.openrouter_api_key:
        console.print("[red]Error:[/red] Set ANTHROPIC_API_KEY or OPENROUTER_API_KEY in .env")
        raise typer.Exit(1)

    if not settings.openai_api_key:
        console.print("[red]Error:[/red] Set OPENAI_API_KEY in .env (required for embeddings)")
        raise typer.Exit(1)

    out_dir = output_dir or settings.output_path
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[dim]Running pipeline…[/dim]\n")

    try:
        final_state = run_voc_pipeline(model_code, max_reviews, skip_if_cached=skip_if_cached, url=url)
        result = final_state["result"]
    except Exception as e:
        console.print(f"\n[red]Pipeline failed:[/red] {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)

    _print_summary(result)

    # Save reports (these functions write the file themselves and return the saved Path)
    md_path = generate_markdown_report(result)
    console.print(f"\n[green]Markdown report:[/green] {md_path}")

    if json_output:
        json_path = generate_json_report(result)
        console.print(f"[green]JSON report:[/green] {json_path}")


def _print_summary(result) -> None:
    population_note = (
        f" (sampled from {result.total_reviews_available} available)"
        if result.total_reviews_available > result.total_reviews
        else ""
    )
    console.print(f"\n[bold]Analysis Complete[/bold] — {result.total_reviews} reviews analyzed{population_note}\n")

    # Top complaints table
    t = Table(title="Top Complaints", show_header=True, header_style="bold red")
    t.add_column("#", width=3)
    t.add_column("Category")
    t.add_column("Frequency", justify="right")
    for c in result.complaints[:5]:
        t.add_row(str(c.rank), c.category, f"{c.frequency_pct:.1f}%")
    console.print(t)

    # Expectation gaps
    if result.expectation_gaps:
        console.print()
        g = Table(title="Expectation Gaps", show_header=True, header_style="bold blue")
        g.add_column("Dimension")
        g.add_column("Severity", width=8)
        g.add_column("Gap")
        for gap in result.expectation_gaps:
            color = {"high": "red", "medium": "yellow", "low": "green"}.get(gap.gap_severity, "white")
            g.add_row(gap.dimension, f"[{color}]{gap.gap_severity}[/{color}]", gap.gap_description[:80] + "…")
        console.print(g)

    if getattr(result, "segment_divergence_analysis", None):
        console.print()
        s = Table(title="Segment Divergence", show_header=True, header_style="bold magenta")
        s.add_column("Segment")
        s.add_column("Size", justify="right")
        s.add_column("Implication")
        for item in result.segment_divergence_analysis.segment_insights[:5]:
            s.add_row(item.segment, str(item.size_estimate), item.business_implication[:80] + "…")
        console.print(s)

    # Key insights
    if result.key_insights:
        console.print()
        console.print("[bold]Key Insights:[/bold]")
        for i, insight in enumerate(result.key_insights, 1):
            console.print(f"  {i}. {insight}")


@app.command()
def spec(
    model_code: str = typer.Argument("UN50U7900FFXZA", help="Samsung TV model code"),
    url: Optional[str] = typer.Option(
        None, "--url", help="Product page URL to scrape (defaults to the built-in U7900F page)"
    ),
):
    """Show product specs for a Samsung product (live-scraped from the product page)."""
    from src.data.spec_extractor import get_samsung_spec

    product_spec = get_samsung_spec(model_code, url=url)
    t = Table(title=f"Spec: {model_code}  (source: {product_spec.spec_source})")
    t.add_column("Field")
    t.add_column("Value")
    for k, v in product_spec.model_dump().items():
        if k == "raw_spec_groups":
            continue
        t.add_row(str(k), str(v)[:200])
    console.print(t)


@app.command(name="refresh-competitors")
def refresh_competitors(
    model_code: str = typer.Argument(..., help="Samsung model code to find competitors for"),
    url: Optional[str] = typer.Option(None, "--url", help="Product page URL (defaults to the built-in U7900F page)"),
):
    """Manually discover + refresh this product's competitor specs via a search-grounded
    call using Claude's web_search tool. Competitors are discovered per product (any
    category) and cached at data/raw/{model_code}/competitors.json.

    Not run automatically by `voc run` — this is a manual, human-reviewed step, both to keep
    per-run LLM cost predictable and because competitor hardware specs don't change once a
    model ships. Review the sources/fields printed below before trusting the result."""
    if not settings.anthropic_api_key:
        rprint("[red]ANTHROPIC_API_KEY is not set. Set it in .env to use this command.[/red]")
        raise typer.Exit(code=1)

    from src.data.competitor_spec_fetcher import refresh_competitors_for_product
    from src.data.spec_extractor import get_samsung_spec

    product_spec = get_samsung_spec(model_code, url=url)
    console.print(f"[dim]Discovering competitors for {product_spec.product_name} ({product_spec.category})...[/dim]")
    results = refresh_competitors_for_product(model_code, product_spec.product_name, product_spec.category)

    if not results:
        rprint("[yellow]No competitors discovered or fetched.[/yellow]")
        return

    t = Table(title="Competitor spec refresh")
    t.add_column("Competitor")
    t.add_column("Status")
    t.add_column("Price")
    t.add_column("Key Specs")
    t.add_column("Sources")
    for name, r in results.items():
        if r["ok"]:
            spec = r["spec"]
            key_specs = ", ".join(f"{k}: {v}" for k, v in list(spec.key_specs.items())[:2])
            t.add_row(name, "[green]OK[/green]", f"${spec.price_usd}", key_specs, str(len(spec.sources)))
        else:
            t.add_row(name, "[red]FAILED[/red]", "-", "-", r["error"][:60])
    console.print(t)

    failed = [name for name, r in results.items() if not r["ok"]]
    if failed:
        rprint(f"[yellow]Failed to fetch (not cached): {', '.join(failed)}[/yellow]")


@app.command()
def sample(
    model_code: str = typer.Argument("UN50U7900FFXZA"),
    n: int = typer.Option(5, help="Number of sample reviews to show"),
    url: Optional[str] = typer.Option(
        None, "--url", help="Product page URL BazaarVoice needs to load (defaults to the built-in U7900F page)"
    ),
):
    """Show sample reviews for a model."""
    from src.data.scraper import SamsungReviewScraper
    import asyncio

    async def _fetch():
        async with SamsungReviewScraper() as scraper:
            sampled, _ = await scraper.collect_all_reviews(model_code, max_reviews=n, url=url)
            return sampled

    reviews = asyncio.run(_fetch())
    for r in reviews[:n]:
        stars = "★" * int(r.rating) + "☆" * (5 - int(r.rating))
        console.print(Panel(
            f"[yellow]{stars}[/yellow]  [dim]{r.date}[/dim]\n\n{r.text}",
            title=f"Review {r.review_id}",
            border_style="dim",
        ))


@app.command()
def discover(
    category: str = typer.Argument(..., help="Product category to discover, e.g. 'tvs'"),
    force_refresh: bool = typer.Option(
        False, "--force-refresh", help="Re-fetch the sitemap instead of using the cached manifest"
    ),
):
    """Discover product SKUs/URLs for a category via samsung.com/us's sitemap.xml.

    `category` is any samsung.com/us top-level URL path segment, e.g. 'tvs',
    'refrigerators', 'audio-devices' — matches the category as it appears in the
    product page URL (https://www.samsung.com/us/{category}/...)."""
    import asyncio
    from src.data.product_discovery import discover_category, load_cached_discovery, save_discovery

    manifest = None if force_refresh else load_cached_discovery(category)
    if manifest is None:
        try:
            products = asyncio.run(discover_category(category))
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(1)
        manifest = save_discovery(category, products)
    else:
        console.print(
            f"[dim]Using cached discovery from {manifest.fetched_at} "
            f"({len(manifest.products)} products). Pass --force-refresh to re-fetch."
        )

    t = Table(title=f"Discovered {category}: {len(manifest.products)} products")
    t.add_column("Model Code")
    t.add_column("URL")
    for p in manifest.products[:50]:
        t.add_row(p.model_code, p.url)
    console.print(t)
    if len(manifest.products) > 50:
        console.print(f"[dim]...and {len(manifest.products) - 50} more (see data/raw/_discovery/{category}.json)")


@app.command(name="crawl-batch")
def crawl_batch(
    category: str = typer.Argument(..., help="Product category to crawl, e.g. 'tvs'"),
    max_products: Optional[int] = typer.Option(None, "--max-products", help="Cap the number of products to crawl"),
    max_reviews: int = typer.Option(50, "--max-reviews", "-n", help="Max reviews to fetch per product"),
):
    """Bulk-collect reviews + spec for every discovered product in a category.

    Data collection only — does NOT run the 11-agent LLM analysis (use `voc run`
    per product for that), since running full analysis across an entire category
    would multiply LLM cost by the number of products discovered.
    """
    import asyncio
    import time
    from src.data.product_discovery import discover_category, load_cached_discovery, save_discovery
    from src.data.scraper import SamsungReviewScraper
    from src.data.spec_extractor import get_samsung_spec

    manifest = load_cached_discovery(category)
    if manifest is None:
        console.print(f"[yellow]No cached discovery for '{category}'; running discovery first...")
        products = asyncio.run(discover_category(category))
        manifest = save_discovery(category, products)

    products = manifest.products[:max_products] if max_products else manifest.products
    console.print(f"[bold]Crawling {len(products)} products in '{category}'...[/bold]")

    def _crawl_one(model_code: str, url: str) -> bool:
        for attempt in range(2):  # one retry on failure, then skip
            try:
                async def _fetch_reviews():
                    async with SamsungReviewScraper() as scraper:
                        _, all_reviews = await scraper.collect_all_reviews(model_code, max_reviews, url=url)
                        scraper.save_raw(all_reviews, model_code)

                asyncio.run(_fetch_reviews())
                get_samsung_spec(model_code, url=url)  # manages its own event loop; called outside any async context
                return True
            except Exception as e:
                if attempt == 0:
                    console.print(f"[yellow]{model_code} failed ({e}); retrying once...")
                    time.sleep(2)
                else:
                    console.print(f"[red]{model_code} failed after retry ({e}); skipping")
        return False

    ok = failed = 0
    for i, p in enumerate(products, 1):
        console.print(f"[dim]({i}/{len(products)})[/dim] {p.model_code}")
        if _crawl_one(p.model_code, p.url):
            ok += 1
        else:
            failed += 1
        time.sleep(1.0)  # polite delay between products

    console.print(f"\n[bold]Done.[/bold] [green]{ok} succeeded[/green], [red]{failed} failed[/red].")


if __name__ == "__main__":
    app()
