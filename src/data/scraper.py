"""Samsung.com review scraper using BazaarVoice API and Playwright fallback."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from src.config import settings
from src.data.models import Review

console = Console()

# Samsung uses BazaarVoice for reviews. This passkey is the public display key
# embedded in Samsung.com's page source (not a secret - used only for read access).
SAMSUNG_BV_PASSKEY = "caV4EnxNNNLxZIiJCfFxFsrIjIkfvAUqKGnMPsHjFuCGMQN5qIAEGnFAlLUWbRPQ"
SAMSUNG_BV_PRODUCT_ID = "UN50U7900FFXZA"

BV_API_BASE = "https://api.bazaarvoice.com/data/reviews.json"
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

    async def fetch_reviews_bv(
        self,
        product_id: str,
        passkey: str,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """Fetch reviews from BazaarVoice API."""
        params = {
            "apiversion": "5.4",
            "passkey": passkey,
            "Filter": f"ProductId:{product_id}",
            "Include": "Products",
            "Stats": "Reviews",
            "Limit": limit,
            "Offset": offset,
            "Sort": "SubmissionTime:desc",
        }
        response = await self.client.get(BV_API_BASE, params=params)
        response.raise_for_status()
        return response.json()

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
        passkey: str = SAMSUNG_BV_PASSKEY,
    ) -> list[Review]:
        reviews: list[Review] = []
        offset = 0
        batch = 100

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Fetching Samsung reviews for {model_code}...", total=max_reviews
            )

            while len(reviews) < max_reviews:
                try:
                    data = await self.fetch_reviews_bv(
                        product_id=model_code,
                        passkey=passkey,
                        limit=min(batch, max_reviews - len(reviews)),
                        offset=offset,
                    )
                    results = data.get("Results", [])
                    if not results:
                        break

                    for raw in results:
                        reviews.append(self._parse_bv_review(raw, model_code))

                    total_results = data.get("TotalResults", 0)
                    progress.update(task, completed=len(reviews), total=min(max_reviews, total_results))

                    if offset + batch >= total_results:
                        break
                    offset += batch
                    await asyncio.sleep(0.5)  # polite delay

                except httpx.HTTPStatusError as e:
                    console.print(f"[yellow]BazaarVoice API error {e.response.status_code}, trying Samsung API...")
                    break
                except Exception as e:
                    console.print(f"[red]Error fetching reviews: {e}")
                    break

        if not reviews:
            # Fallback: try Samsung's own API
            reviews = await self._fallback_samsung_api(model_code, max_reviews)

        if not reviews:
            console.print("[yellow]Live scraping unavailable. Loading from cache or using sample data.")
            reviews = await self._load_cached_or_sample(model_code)

        return reviews[:max_reviews]

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
        cache_path = settings.raw_data_path / f"{model_code}_reviews.json"
        if cache_path.exists():
            console.print(f"[green]Loading cached reviews from {cache_path}")
            with open(cache_path) as f:
                raw_list = json.load(f)
            return [Review(**r) for r in raw_list]

        console.print("[yellow]No cache found. Generating sample reviews for development...")
        return _generate_sample_reviews(model_code, count=100)

    def save_raw(self, reviews: list[Review], model_code: str) -> Path:
        out = settings.raw_data_path / f"{model_code}_reviews.json"
        with open(out, "w") as f:
            json.dump([r.model_dump() for r in reviews], f, indent=2, default=str)
        console.print(f"[green]Saved {len(reviews)} reviews to {out}")
        return out


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
