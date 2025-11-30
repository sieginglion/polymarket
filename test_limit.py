import requests
import json

def test_limit():
    url = "https://gamma-api.polymarket.com/markets"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    params = {
        "limit": 500,
        "order": "volumeNum",
        "ascending": "false",
        "closed": "false"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        markets = response.json()
        print(f"Successfully fetched {len(markets)} markets with limit=100")
    except Exception as e:
        print(f"Error: {e}")
        if 'response' in locals():
            print(f"Response text: {response.text[:200]}")

if __name__ == "__main__":
    test_limit()
