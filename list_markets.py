#!/usr/bin/env python3
"""
Polymarket Market Lister

This script fetches markets from the Polymarket API, groups them by event,
and exports them to CSV via standard output.
"""

import csv
import sys
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import httpx
import typer
from pydantic import BaseModel, Field

# Configure logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)

# Constants
API_URL = "https://gamma-api.polymarket.com/markets"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
DEFAULT_LIMIT = 500
DEFAULT_DAYS_FILTER = 91
DEFAULT_TOP_EVENTS = 16

app = typer.Typer(help="List top Polymarket events by volume.")

# --- Data Models ---

class Market(BaseModel):
    """Represents a single market from the API."""
    id: str
    question: str
    slug: Optional[str] = None
    volumeNum: float = 0.0
    endDateIso: Optional[str] = None
    events: List[Dict[str, Any]] = Field(default_factory=list)

class Event(BaseModel):
    """Represents a grouped Polymarket event."""
    title: str
    volume: float
    end_date: Optional[str]
    url: str
    slug: str

# --- Service ---

class MarketClient:
    """Client for interacting with the Polymarket API."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.headers = {"User-Agent": user_agent}

    def fetch_markets(self, limit: int = DEFAULT_LIMIT) -> List[Market]:
        """
        Fetches markets from the Polymarket API.
        """
        params = {
            "limit": limit,
            "order": "volumeNum",
            "ascending": "false",
            "closed": "false"
        }

        logger.info(f"Fetching top {limit} markets from Polymarket...")
        try:
            with httpx.Client() as client:
                response = client.get(API_URL, params=params, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                
                markets = []
                for item in data:
                    try:
                        markets.append(Market(**item))
                    except Exception:
                        continue
                logger.info(f"Successfully fetched {len(markets)} markets.")
                return markets
        except httpx.RequestError as e:
            logger.error(f"Network error fetching markets: {e}")
            return []
        except ValueError:
            logger.error("Error decoding JSON response")
            return []
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return []

class MarketProcessor:
    """Business logic for processing market data."""

    def process_events(self, markets: List[Market], days_filter: int) -> List[Event]:
        """
        Processes raw market data to group by event and filter by date.
        """
        now = datetime.now(timezone.utc)
        filter_date_limit = now + timedelta(days=days_filter)
        
        unique_events: Dict[str, Event] = {}
        
        for market in markets:
            if not market.endDateIso:
                continue
                
            try:
                end_date = datetime.strptime(market.endDateIso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if end_date > filter_date_limit:
                    continue
            except ValueError:
                continue

            event_slug = None
            event_title = None
            event_volume = 0.0
            
            if market.events:
                event_data = market.events[0]
                event_slug = event_data.get('slug')
                event_title = event_data.get('title')
                try:
                    event_volume = float(event_data.get('volume', 0))
                except (ValueError, TypeError):
                    event_volume = 0.0
            
            if event_slug:
                if event_slug not in unique_events:
                     unique_events[event_slug] = Event(
                        title=event_title or "Unknown Event",
                        volume=event_volume,
                        end_date=market.endDateIso,
                        url=f"https://polymarket.com/event/{event_slug}",
                        slug=event_slug
                    )
            else:
                slug = market.slug
                if slug and slug not in unique_events:
                    unique_events[slug] = Event(
                        title=market.question,
                        volume=market.volumeNum,
                        end_date=market.endDateIso,
                        url=f"https://polymarket.com/market/{slug}",
                        slug=slug
                    )
        
        sorted_events = sorted(unique_events.values(), key=lambda x: x.volume, reverse=True)
        logger.info(f"Processed {len(sorted_events)} unique events after filtering.")
        return sorted_events

class MarketCLI:
    """Handles CLI presentation and output."""

    @staticmethod
    def write_csv(events: List[Event], top_n: int):
        """Writes the top N events to stdout in CSV format."""
        try:
            fieldnames = ['Volume', 'End Date', 'Event Name', 'URL']
            writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)

            writer.writeheader()
            for event in events[:top_n]:
                writer.writerow({
                    'Volume': event.volume,
                    'End Date': event.end_date,
                    'Event Name': event.title,
                    'URL': event.url
                })
        except IOError as e:
            logger.error(f"Error writing to CSV: {e}")

# --- CLI ---

@app.command()
def main(
    limit: int = typer.Option(DEFAULT_LIMIT, help="Number of markets to fetch"),
    days: int = typer.Option(DEFAULT_DAYS_FILTER, help="Filter events ending within N days"),
    top: int = typer.Option(DEFAULT_TOP_EVENTS, help="Number of top events to display"),
):
    """
    Fetch and list top Polymarket events by volume.
    """
    client = MarketClient()
    processor = MarketProcessor()
    
    markets = client.fetch_markets(limit=limit)
    
    if markets:
        sorted_events = processor.process_events(markets, days)
        MarketCLI.write_csv(sorted_events, top)
    else:
        logger.warning("No markets found.")

if __name__ == "__main__":
    app()
