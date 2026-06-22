"""Samsung.com review scraper using BazaarVoice's browser-gated gateway, with
a Samsung-native-API and cached/sample fallback if that gateway is unreachable."""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console

from src.config import settings
from src.data.models import PageSnapshot, Review

console = Console()

SAMSUNG_BV_PRODUCT_ID = "UN50U7900FFXZA"
SAMSUNG_REVIEWS_API = "https://www.samsung.com/us/api/v2/review/product/{model_code}"


class SamsungReviewScraper:
    def __init__(self):
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.client.aclose()

    async def fetch_page_html(self, url: str) -> tuple[str, int]:
        """Fetch the full product page HTML (generic — works for any product URL)."""
        response = await self.client.get(url, headers={"Accept": "text/html"})
        return response.text, response.status_code

    def save_page_snapshot(self, html: str, model_code: str, url: str, status_code: int) -> PageSnapshot:
        """Persist the raw page HTML + metadata under data/raw/{model_code}/."""
        out_dir = settings.raw_product_dir(model_code)
        html_path = out_dir / "page.html"
        html_path.write_text(html, encoding="utf-8")

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else None

        snapshot = PageSnapshot(
            url=url,
            fetched_at=datetime.now().isoformat(),
            status_code=status_code,
            html_path=str(html_path),
            title=title,
            model_code=model_code,
        )
        (out_dir / "page_meta.json").write_text(
            json.dumps(snapshot.model_dump(), indent=2), encoding="utf-8"
        )
        console.print(f"[green]Saved page snapshot: {html_path} ({len(html):,} bytes)")
        return snapshot

    async def fetch_reviews_bv_bfd(
        self,
        model_code: str,
        max_reviews: Optional[int] = None,
        product_url: Optional[str] = None,
    ) -> list[dict]:
        """Fetch real reviews from BazaarVoice's current gateway (apps.bazaarvoice.com/bfd/...).

        This gateway returns 401 to plain HTTP requests even with identical headers —
        it requires a real browser context (cookies/TLS fingerprint). Confirmed working
        by sniffing the live page's own network requests and replaying the exact
        fetch() call from inside a Playwright-controlled page.

        max_reviews=None (default) paginates until BazaarVoice's own TotalResults is
        exhausted — i.e. fetches every real review, not a capped sample. Pass an explicit
        cap only if you deliberately want fewer than the full population.
        """
        from playwright.async_api import async_playwright

        target_url = product_url or settings.samsung_product_url
        fetch_ceiling = max_reviews if max_reviews is not None else 10_000  # safety ceiling, not a sample cap
        limit = 100
        offset = 0
        all_results: list[dict] = []

        async with async_playwright() as p:
            browser = await p.chromium.launch()
            try:
                page = await browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    )
                )
                await page.goto(target_url, wait_until="load", timeout=45000)
                await page.wait_for_timeout(1000)

                while len(all_results) < fetch_ceiling:
                    batch_limit = min(limit, fetch_ceiling - len(all_results))
                    url = (
                        "https://apps.bazaarvoice.com/bfd/v1/clients/Samsung/api-products/cv2"
                        "/resources/data/reviews.json?resource=reviews&action=REVIEWS_N_STATS"
                        f"&filter=productid:eq:{model_code}"
                        "&filter=contentlocale:eq:en_US,en_US&filter=isratingsonly:eq:false"
                        "&filter_reviews=contentlocale:eq:en_US,en_US&include=authors,products,comments"
                        f"&filteredstats=reviews&Stats=Reviews&limit={batch_limit}&offset={offset}"
                        "&limit_comments=3&sort=submissiontime:desc&apiversion=5.5"
                        "&displaycode=20545-en_us"
                    )
                    data = await page.evaluate(
                        """async (params) => {
                            const resp = await fetch(params.url, {
                                headers: {"bv-bfd-token": "20545,main_site,en_US"}
                            });
                            return await resp.json();
                        }""",
                        {"url": url},
                    )
                    resp = data.get("response", {})
                    results = resp.get("Results", [])
                    if not results:
                        break
                    all_results.extend(results)

                    total = resp.get("TotalResults", 0)
                    console.print(f"[dim]Fetched {len(all_results)}/{total} reviews...")
                    if offset + batch_limit >= total:
                        break
                    offset += batch_limit
                    await asyncio.sleep(0.3)  # polite delay
            finally:
                await browser.close()

        return all_results[:fetch_ceiling]

    async def fetch_reviews_samsung_api(
        self,
        model_code: str,
        page: int = 1,
        page_size: int = 100,
    ) -> dict:
        """Fetch reviews from Samsung's internal review API."""
        url = f"https://www.samsung.com/us/api/v2/review/product/{model_code}"
        params = {
            "page": page,
            "pageSize": page_size,
            "sortBy": "mostRecent",
        }
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def _parse_bv_review(self, raw: dict, model: str) -> Review:
        return Review(
            review_id=str(raw.get("Id", "")),
            product_id=raw.get("ProductId", model),
            model=model,
            rating=float(raw.get("Rating", 3)),
            title=raw.get("Title"),
            text=raw.get("ReviewText", ""),
            date=raw.get("SubmissionTime", "")[:10] if raw.get("SubmissionTime") else None,
            helpful_votes=raw.get("TotalPositiveFeedbackCount", 0),
            verified_purchase=raw.get("IsSyndicated", False),
        )

    def _parse_samsung_api_review(self, raw: dict, model: str) -> Review:
        return Review(
            review_id=str(raw.get("reviewId", raw.get("id", ""))),
            product_id=model,
            model=model,
            rating=float(raw.get("rating", raw.get("starRating", 3))),
            title=raw.get("title", raw.get("headline")),
            text=raw.get("reviewText", raw.get("body", raw.get("text", ""))),
            date=raw.get("submissionDate", raw.get("date", ""))[:10]
            if raw.get("submissionDate", raw.get("date"))
            else None,
            helpful_votes=raw.get("helpfulVotes", 0),
            verified_purchase=raw.get("isVerifiedPurchase", False),
        )

    async def collect_all_reviews(
        self,
        model_code: str = SAMSUNG_BV_PRODUCT_ID,
        max_reviews: int = 500,
    ) -> tuple[list[Review], list[Review]]:
        """Returns (reviews_to_analyze, all_reviews_fetched).

        Fetches the FULL real review population from BazaarVoice, then — if it's
        larger than max_reviews — draws a sample stratified by rating so the
        analyzed subset's rating distribution matches the true population
        (rather than being biased toward whatever order pagination returned).
        all_reviews_fetched is the complete set discovered during fetch (the raw
        evidence to cache); for the fallback paths the two lists are identical
        since those paths can't discover a larger population.
        """
        # Primary: BazaarVoice's current gateway, via a real browser context. Fetches
        # every real review (uncapped) — sampling down to max_reviews happens below.
        try:
            raw_results = await self.fetch_reviews_bv_bfd(model_code, max_reviews=None)
            if raw_results:
                all_reviews = [self._parse_bv_review(r, model_code) for r in raw_results]
                console.print(f"[green]Fetched {len(all_reviews)} real reviews via BazaarVoice (browser gateway)")
                sampled = sample_reviews_stratified(all_reviews, max_reviews)
                if len(sampled) < len(all_reviews):
                    console.print(
                        f"[cyan]Sampled {len(sampled)} reviews (stratified by rating) "
                        f"for analysis out of {len(all_reviews)} available"
                    )
                return sampled, all_reviews
            console.print("[yellow]BazaarVoice browser gateway returned no reviews, trying Samsung's native API...")
        except Exception as e:
            console.print(f"[yellow]BazaarVoice browser gateway failed ({e}), trying Samsung's native API...")

        reviews = await self._fallback_samsung_api(model_code, max_reviews)

        if not reviews:
            console.print("[yellow]Live scraping unavailable. Loading from cache or using sample data.")
            reviews = await self._load_cached_or_sample(model_code)

        # Fallback paths don't reveal the true population size beyond what they fetched.
        sampled = reviews[:max_reviews]
        return sampled, reviews

    async def _fallback_samsung_api(self, model_code: str, max_reviews: int) -> list[Review]:
        reviews = []
        page = 1
        try:
            while len(reviews) < max_reviews:
                data = await self.fetch_reviews_samsung_api(model_code, page=page)
                items = (
                    data.get("reviews", [])
                    or data.get("data", {}).get("reviews", [])
                    or data.get("results", [])
                )
                if not items:
                    break
                for raw in items:
                    reviews.append(self._parse_samsung_api_review(raw, model_code))
                page += 1
                await asyncio.sleep(0.5)
        except Exception as e:
            console.print(f"[red]Samsung API fallback failed: {e}")
        return reviews

    async def _load_cached_or_sample(self, model_code: str) -> list[Review]:
        cache_path = settings.raw_product_dir(model_code) / "reviews.json"
        if cache_path.exists():
            console.print(f"[green]Loading cached reviews from {cache_path}")
            with open(cache_path) as f:
                raw_list = json.load(f)
            return [Review(**r) for r in raw_list]

        console.print("[yellow]No cache found. Generating sample reviews for development...")
        return _generate_sample_reviews(model_code, count=100)

    def save_raw(self, reviews: list[Review], model_code: str) -> Path:
        out = settings.raw_product_dir(model_code) / "reviews.json"
        with open(out, "w") as f:
            json.dump([r.model_dump() for r in reviews], f, indent=2, default=str)
        console.print(f"[green]Saved {len(reviews)} reviews to {out}")
        return out


def sample_reviews_stratified(reviews: list[Review], sample_size: int, seed: int = 42) -> list[Review]:
    """Draw a sample whose rating distribution matches the full population's.

    Plain "most recent N" or random-N sampling can skew the analyzed subset (e.g.
    incentivized review campaigns cluster in time and tend to skew positive).
    Stratifying by rating keeps the analyzed sample's sentiment mix representative
    of the true population regardless of fetch order. Deterministic (fixed seed)
    so the same input review set always produces the same sample.
    """
    if len(reviews) <= sample_size:
        return reviews

    import random

    rng = random.Random(seed)
    by_rating: dict[float, list[Review]] = {}
    for r in reviews:
        by_rating.setdefault(r.rating, []).append(r)

    total = len(reviews)
    sampled: list[Review] = []
    for group in by_rating.values():
        quota = round(sample_size * len(group) / total)
        sampled.extend(rng.sample(group, min(quota, len(group))))

    # Rounding can drift slightly off sample_size; correct by trimming or topping up.
    if len(sampled) > sample_size:
        sampled = rng.sample(sampled, sample_size)
    elif len(sampled) < sample_size:
        remaining = [r for r in reviews if r not in sampled]
        sampled.extend(rng.sample(remaining, min(sample_size - len(sampled), len(remaining))))

    return sampled


def _generate_sample_reviews(model_code: str, count: int = 100) -> list[Review]:
    """Generate realistic sample reviews for development/testing."""
    import random
    from datetime import datetime, timedelta

    sample_pool = [
        # 5-star reviews with hidden complaints (contradiction type A)
        (5, "Amazing picture quality!", "The 4K picture quality is stunning - colors are vivid and blacks are deep. My whole family loves watching movies on this. However, the sound quality is quite disappointing, it's very thin and lacks bass. I had to buy a soundbar immediately. Also the Tizen OS can be a bit sluggish sometimes."),
        (5, "Great TV for the price", "Beautiful display, Samsung brand reliability, easy setup. The smart features work well once you get used to the interface. Only downside is the remote feels cheap and the UI could be faster. Ads on the home screen are annoying."),
        (5, "Love this TV", "Crystal clear picture. Gaming mode is great with low input lag. The 4K upscaling is impressive. Sound could be better but that's expected at this price point. The Tizen smart TV platform has everything I need."),
        # 4-star reviews
        (4, "Solid mid-range TV", "Good picture quality for the price. 4K content looks fantastic. Netflix and Amazon Prime work great. The built-in speakers are weak - definitely need a soundbar. Smart TV interface is decent but a bit slow to respond."),
        (4, "Good value Samsung TV", "Picture quality meets my expectations for a mid-range TV. HDR content looks vibrant. The TV was easy to set up and connect to my home network. Some lag in the smart TV menus which is annoying. Volume buttons on remote are too small."),
        # 3-star reviews
        (3, "Mixed feelings", "The picture is good but not exceptional compared to OLED TVs I've used before. Smart TV works but is frustratingly slow. Apps take too long to load. Ads on the home screen are really intrusive. Expected better from Samsung."),
        (3, "Average performance", "Image quality is acceptable for 4K but HDR implementation feels weak compared to more expensive models. The Tizen OS is getting better but still has room for improvement. Audio is poor as expected for a slim TV."),
        # 2-star reviews
        (2, "Disappointed with Samsung quality", "The TV itself has decent picture quality but within 3 months the WiFi disconnects constantly. Customer support was unhelpful. Expected better reliability from Samsung. Smart TV freezes regularly requiring restart."),
        (2, "Not worth the Samsung premium", "Compared to my LG from 3 years ago, this Samsung feels like a downgrade in software quality. The UI is cluttered with ads. Remote control layout is counterintuitive. Picture is fine but software ruins the experience."),
        # 1-star reviews with product praise (contradiction type B)
        (1, "Dead pixel after 2 months", "The TV itself is beautiful and the picture quality is excellent. But I got a dead pixel cluster right in the center of the screen after just 2 months of normal use. Samsung refused to replace it under warranty. Great TV, terrible warranty policy."),
        (1, "Arrived damaged", "The TV was damaged in shipping - screen cracked at the corner. The TV itself looks like it would have been great based on what I can see working. Samsung and the seller are arguing about who should replace it. Very frustrated."),
        (1, "Software update bricked features", "After the last software update, my gaming mode stopped working and HDR is all washed out. Picture quality was excellent before. Samsung support says to wait for another update. This is unacceptable."),
        # More varied reviews
        (5, "Perfect for my bedroom", "Great size for my bedroom, easy to wall mount. Picture is sharp and vibrant. Smart features connect to my phone seamlessly. Samsung ecosystem integration is excellent. Sound is thin but I use Bluetooth speaker anyway."),
        (4, "Excellent picture, weak audio", "The Crystal 4K display is genuinely impressive. Colors pop and motion handling is smooth. Tizen interface has all major streaming apps. Audio is the weak point - definitely buy a soundbar. Value for money is good."),
        (3, "Expected more from Samsung", "Samsung used to be known for quality. This TV has acceptable picture quality but the software experience is below expectations. Home screen is cluttered with advertisements and the UI lags. Picture quality saves it from a lower rating."),
        (4, "Gaming on this TV is great", "Low input lag in game mode makes a real difference. 4K gaming looks spectacular. The auto low latency mode works with my PS5. Main complaint is the audio - definitely needs external speakers. Smart TV features are comprehensive."),
        (2, "WiFi keeps dropping", "The picture quality is nice but the WiFi disconnects every few hours requiring manual reconnection. I've tried everything - different channels, router settings. Other devices work fine. Samsung support was no help. Had to run ethernet cable."),
        (5, "Great value 4K TV", "Compared to competitors at this price point, Samsung delivers better picture quality and a more polished smart TV experience. The 4K upscaling of HD content is impressive. No major complaints after 6 months of daily use."),
        (1, "Panel defect", "Developed a large dark patch on the left side of the screen after 4 months. TV was used normally, never dropped or mishandled. This appears to be a panel defect. Samsung warranty process is slow and painful. Product quality control seems poor."),
        (4, "Solid TV with minor issues", "Picture quality is excellent for the price. 4K HDR content looks stunning. Tizen OS is responsive most of the time. Minor annoyances: home screen ads, occasional app crashes, sound quality is weak. Overall good value."),
    ]

    reviews = []
    base_date = datetime.now()

    for i in range(count):
        pool_idx = i % len(sample_pool)
        rating, title, text = sample_pool[pool_idx]

        # Add some variation
        date = (base_date - timedelta(days=random.randint(1, 730))).strftime("%Y-%m-%d")
        helpful_votes = random.randint(0, 50)

        reviews.append(
            Review(
                review_id=f"SAMPLE_{model_code}_{i:04d}",
                product_id=model_code,
                model=model_code,
                rating=float(rating),
                title=title,
                text=text,
                date=date,
                helpful_votes=helpful_votes,
                verified_purchase=random.random() > 0.3,
            )
        )

    return reviews
