import requests
from bs4 import BeautifulSoup

def get_sp500_stocks():
    try:
        print("Fetching S&P 500 stocks...")
        url = 'https://www.slickcharts.com/sp500'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Check for request errors
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='table table-hover table-borderless table-sm')
        
        tickers = []
        for row in table.find_all('tr')[1:]:  # Get all rows except header
            ticker = row.find_all('td')[2].text.strip()
            tickers.append(ticker)
        
        print(f"Fetched {len(tickers)} S&P 500 stocks.")
        return tickers
    except Exception as e:
        print(f"Error fetching S&P 500 stocks: {e}")
        return []

def save_to_file(tickers, filename="stocks.txt"):
    try:
        with open(filename, 'w') as file:
            for ticker in tickers:
                file.write(f"{ticker}\n")
        print(f"Saved {len(tickers)} stocks to '{filename}'.")
    except Exception as e:
        print(f"Error saving to file: {e}")

if __name__ == "__main__":
    stocks = get_sp500_stocks()
    if stocks:
        save_to_file(stocks)

