import json
import csv
import sys
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Union, Dict, Any

import httpx
import typer
from pydantic import BaseModel, Field, field_validator

app = typer.Typer()

class Market(BaseModel):
    outcomes: Optional[str] = None
    outcomePrices: Optional[str] = None

    def get_outcomes_list(self) -> List[str]:
        if not self.outcomes:
            return []
        try:
            return json.loads(self.outcomes)
        except json.JSONDecodeError:
            return []

    def get_prices_list(self) -> List[float]:
        if not self.outcomePrices:
            return []
        try:
            parsed = json.loads(self.outcomePrices)
            if isinstance(parsed, list):
                return [float(p) for p in parsed]
            return []
        except (json.JSONDecodeError, ValueError, TypeError):
            return []

class Event(BaseModel):
    title: str
    slug: str
    endDate: str
    volume: float = 0.0
    markets: List[Market] = Field(default_factory=list)

def calculate_event_score(event: Event) -> float:
    if not event.markets:
        return 0.0

    # Single-market event (SMP)
    if len(event.markets) == 1:
        market = event.markets[0]
        prices = market.get_prices_list()
        if not prices:
            return 0.0
        return max(prices)

    # Multi-market event (GMP)
    max_yes_price = 0.0
    found_yes = False

    for market in event.markets:
        outcomes = market.get_outcomes_list()
        prices = market.get_prices_list()

        if len(outcomes) != len(prices):
            continue

        for outcome, price in zip(outcomes, prices):
            if outcome.lower() == "yes":
                found_yes = True
                if price > max_yes_price:
                    max_yes_price = price
    
    if found_yes:
        return max_yes_price
    
    return 0.0

def fetch_events(limit: int, days: int) -> List[Event]:
    url = "https://gamma-api.polymarket.com/events"
    
    now = datetime.now(timezone.utc)
    end_date_max = now + timedelta(days=days)
    end_date_max_str = end_date_max.strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "limit": limit,
        "order": "volume:desc",
        "closed": "false",
        "end_date_max": end_date_max_str
    }

    try:
        response = httpx.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        data = response.json()
    except httpx.RequestError as e:
        print(f"Error fetching events: {e}", file=sys.stderr)
        return []
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e}", file=sys.stderr)
        return []
    except json.JSONDecodeError:
        print("Error decoding JSON response", file=sys.stderr)
        return []

    events_data = []
    if isinstance(data, list):
        events_data = data
    elif isinstance(data, dict) and "events" in data:
        events_data = data["events"]
    
    events = []
    for item in events_data:
        try:
            events.append(Event(**item))
        except Exception as e:
            # Skip invalid events but log warning if needed
            # print(f"Skipping invalid event: {e}", file=sys.stderr)
            continue
            
    return events

@app.command()
def main(
    limit: int = typer.Option(500, help="Number of events to request from API"),
    days: int = typer.Option(91, help="Maximum days until event end date"),
    min_event_prob: float = typer.Option(0.8, help="Minimum score threshold"),
    top: int = typer.Option(16, help="Number of rows to output"),
):
    events = fetch_events(limit, days)
    
    scored_events = []
    for event in events:
        score = calculate_event_score(event)
        if score >= min_event_prob:
            scored_events.append((event, score))
    
    # Sort by volume descending
    scored_events.sort(key=lambda x: x[0].volume, reverse=True)
    
    # Select top events
    top_events = scored_events[:top]
    
    # Output CSV
    writer = csv.writer(sys.stdout)
    writer.writerow(["Volume", "Title", "End Date", "Event Score", "URL"])
    
    for event, score in top_events:
        writer.writerow([
            int(event.volume),
            event.title,
            event.endDate,
            int(score * 100),
            f"https://polymarket.com/event/{event.slug}"
        ])

if __name__ == "__main__":
    app()
