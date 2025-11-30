#!/usr/bin/env python3
"""
Polymarket Market Lister

This script fetches markets from the Polymarket API, groups them by event,
and displays them in a formatted table in the terminal.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import requests
from rich.console import Console
from rich.table import Table
from rich import box

# Constants
API_URL = "https://gamma-api.polymarket.com/markets"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

@dataclass
class Event:
    """Represents a grouped Polymarket event."""
    title: str
    volume: float
    end_date: str
    url: str
    slug: str

class PolymarketClient:
    """Client for interacting with the Polymarket API."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT):
        self.headers = {"User-Agent": user_agent}
        self.console = Console()

    def fetch_markets(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        Fetches markets from the Polymarket API.

        Args:
            limit: The maximum number of markets to fetch.

        Returns:
            A list of market dictionaries.
        """
        params = {
            "limit": limit,
            "order": "volumeNum",
            "ascending": "false",
            "closed": "false"
        }

        try:
            with self.console.status(f"[bold green]Fetching {limit} markets..."):
                response = requests.get(API_URL, params=params, headers=self.headers)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e:
            self.console.print(f"[bold red]Error fetching markets:[/bold red] {e}")
            return []
        except ValueError: # json decode error
            self.console.print("[bold red]Error decoding JSON response[/bold red]")
            return []

    def process_events(self, markets: List[Dict[str, Any]], days_filter: int) -> List[Event]:
        """
        Processes raw market data to group by event and filter by date.

        Args:
            markets: List of raw market dictionaries.
            days_filter: Number of days from now to filter events by.

        Returns:
            A list of Event objects sorted by volume.
        """
        now = datetime.now(timezone.utc)
        filter_date_limit = now + timedelta(days=days_filter)
        
        unique_events: Dict[str, Event] = {}
        
        for market in markets:
            # Check end date
            end_date_iso = market.get('endDateIso')
            if not end_date_iso:
                continue
                
            try:
                # Parse YYYY-MM-DD
                end_date = datetime.strptime(end_date_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if end_date > filter_date_limit:
                    continue
            except ValueError:
                continue

            # Get event data
            events_data = market.get('events', [])
            
            # Determine event details
            event_slug = None
            event_title = None
            event_volume = 0.0
            
            if events_data and isinstance(events_data, list) and len(events_data) > 0:
                event = events_data[0]
                event_slug = event.get('slug')
                event_title = event.get('title')
                # Sometimes volume is in the event, sometimes we aggregate from markets
                # For simplicity, we'll take the event volume if available, or market volume
                try:
                    event_volume = float(event.get('volume', 0))
                except (ValueError, TypeError):
                    event_volume = 0.0
            
            # Fallback or primary logic
            if event_slug:
                if event_slug not in unique_events:
                     unique_events[event_slug] = Event(
                        title=event_title or "Unknown Event",
                        volume=event_volume,
                        end_date=end_date_iso,
                        url=f"https://polymarket.com/event/{event_slug}",
                        slug=event_slug
                    )
            else:
                 # Fallback for markets without event grouping
                slug = market.get('slug')
                if slug and slug not in unique_events:
                    try:
                        vol = float(market.get('volumeNum', 0))
                    except (ValueError, TypeError):
                        vol = 0.0
                        
                    unique_events[slug] = Event(
                        title=market.get('question', "Unknown Market"),
                        volume=vol,
                        end_date=end_date_iso,
                        url=f"https://polymarket.com/market/{slug}",
                        slug=slug
                    )
        
        # Sort by volume descending
        return sorted(unique_events.values(), key=lambda x: x.volume, reverse=True)

    def display_events(self, events: List[Event], top_n: int = 10):
        """
        Prints the top N events in a formatted table using rich.

        Args:
            events: List of processed Event objects.
            top_n: Number of events to display.
        """
        table = Table(title=f"Top {top_n} Polymarket Events (Volume)", box=box.ROUNDED)

        table.add_column("Volume", justify="right", style="cyan", no_wrap=True)
        table.add_column("End Date", style="magenta")
        table.add_column("Event Name", style="white")
        table.add_column("URL", style="blue")

        for event in events[:top_n]:
            formatted_volume = f"${event.volume:,.2f}"
            display_name = event.title
            if len(display_name) > 60:
                display_name = display_name[:57] + "..."
            
            table.add_row(
                formatted_volume,
                event.end_date,
                display_name,
                event.url
            )

        self.console.print(table)

def main():
    parser = argparse.ArgumentParser(description="List top Polymarket events by volume.")
    parser.add_argument("--limit", type=int, default=500, help="Number of markets to fetch (default: 500)")
    parser.add_argument("--days", type=int, default=30, help="Filter events ending within N days (default: 30)")
    parser.add_argument("--top", type=int, default=16, help="Number of top events to display (default: 16)")
    
    args = parser.parse_args()

    client = PolymarketClient()
    markets = client.fetch_markets(limit=args.limit)
    
    if markets:
        sorted_events = client.process_events(markets, args.days)
        client.display_events(sorted_events, top_n=args.top)
    else:
        print("No markets found.")

if __name__ == "__main__":
    main()
