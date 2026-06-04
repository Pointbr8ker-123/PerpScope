import requests

# Testing our connection to the Bybit API 

def test_connection(url):
        
    params = {
        "category": "linear",
        "symbol": "BTCUSDT",
        "limit": 5
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SUCCESS! Funding rate data works!!!")
            for record in data['result']['list']:
                print(f"Rate: {record['fundingRate']} | Time: {record['fundingRateTimestamp']}")
        else:
            print(f"Response: {response.text[:200]}")
    except Exception as e:
        print(f"Failed: {e}")


if __name__ == "__main__":
    url = "https://api.bytick.com/v5/market/funding/history"
    test_connection(url)