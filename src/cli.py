import asyncio
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
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="Output directory"),
    json_output: bool = typer.Option(False, "--json", help="Also save JSON report"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose agent output"),
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
        result = asyncio.run(run_voc_pipeline(model_code, max_reviews))
    except Exception as e:
        console.print(f"\n[red]Pipeline failed:[/red] {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        raise typer.Exit(1)

    _print_summary(result)

    # Save reports
    md_path = out_dir / f"voc_report_{model_code}_{result.analysis_date[:10]}.md"
    md_content = generate_markdown_report(result)
    md_path.write_text(md_content, encoding="utf-8")
    console.print(f"\n[green]Markdown report:[/green] {md_path}")

    if json_output:
        json_path = out_dir / f"voc_report_{model_code}_{result.analysis_date[:10]}.json"
        json_content = generate_json_report(result)
        json_path.write_text(json_content, encoding="utf-8")
        console.print(f"[green]JSON report:[/green] {json_path}")


def _print_summary(result) -> None:
    console.print(f"\n[bold]Analysis Complete[/bold] — {result.total_reviews} reviews analyzed\n")

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
        g = Table(title="Expectation Gaps (핵심)", show_header=True, header_style="bold blue")
        g.add_column("Dimension")
        g.add_column("Severity", width=8)
        g.add_column("Gap")
        for gap in result.expectation_gaps:
            color = {"high": "red", "medium": "yellow", "low": "green"}.get(gap.gap_severity, "white")
            g.add_row(gap.dimension, f"[{color}]{gap.gap_severity}[/{color}]", gap.gap_description[:80] + "…")
        console.print(g)

    # Key insights
    if result.key_insights:
        console.print()
        console.print("[bold]Key Insights:[/bold]")
        for i, insight in enumerate(result.key_insights, 1):
            console.print(f"  {i}. {insight}")


@app.command()
def spec(
    model_code: str = typer.Argument("UN50U7900FFXZA", help="Samsung TV model code"),
):
    """Show product specs for a Samsung TV model."""
    from src.data.spec_extractor import SAMSUNG_U7900F_SPEC, COMPETITOR_SPECS

    specs = {
        "UN50U7900FFXZA": SAMSUNG_U7900F_SPEC,
        **COMPETITOR_SPECS,
    }

    if model_code not in specs:
        console.print(f"[red]Unknown model:[/red] {model_code}")
        console.print(f"Available: {', '.join(specs.keys())}")
        raise typer.Exit(1)

    spec_data = specs[model_code]
    t = Table(title=f"Spec: {model_code}")
    t.add_column("Field")
    t.add_column("Value")
    for k, v in spec_data.items():
        t.add_row(str(k), str(v))
    console.print(t)


@app.command()
def sample(
    model_code: str = typer.Argument("UN50U7900FFXZA"),
    n: int = typer.Option(5, help="Number of sample reviews to show"),
):
    """Show sample reviews for a model."""
    from src.data.scraper import SamsungReviewScraper
    import asyncio

    async def _fetch():
        async with SamsungReviewScraper(model_code) as scraper:
            return await scraper.fetch_reviews(max_reviews=n)

    reviews = asyncio.run(_fetch())
    for r in reviews[:n]:
        stars = "★" * r.rating + "☆" * (5 - r.rating)
        console.print(Panel(
            f"[yellow]{stars}[/yellow]  [dim]{r.date}[/dim]\n\n{r.text}",
            title=f"Review {r.review_id}",
            border_style="dim",
        ))


if __name__ == "__main__":
    app()
