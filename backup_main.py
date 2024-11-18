import yfinance as yf
import numpy as np
import pandas as pd
import requests
from datetime import datetime
from scipy.stats import norm
from bs4 import BeautifulSoup
import time
import gspread
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)

from oauth2client.service_account import ServiceAccountCredentials

RISK_FREE_RATE = 0.01

def get_sp500_stocks():
    try:
        print("Fetching the top 100 S&P 500 stocks...")
        url = 'https://www.slickcharts.com/sp500'
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Check for request errors
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', class_='table table-hover table-borderless table-sm')
        
        tickers = []
        for row in table.find_all('tr')[1:101]:  # Limit to the top 100 rows
            ticker = row.find_all('td')[2].text.strip()
            tickers.append(ticker)
        
        print("Fetched the top 100 S&P 500 stocks.")
        return tickers
    except Exception as e:
        print(f"Error fetching S&P 500 stocks: {e}")
        return []

def fetch_stock_data(ticker):
    try:
        print(f"Fetching stock data for {ticker}...")
        data = yf.download(ticker, period="1d", interval="1m", progress=False)
        if data.empty:
            print(f"No data available for {ticker}.")
            return None
        return data
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return None

def calculate_probability_ITM(S, K, T, r, sigma):
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        return norm.cdf(d1)
    except Exception as e:
        print(f"Error calculating probability ITM: {e}")
        return 0

def recommend_single_option(options_data, S, probability_ITM):
    try:
        otm_options = options_data[
            ((options_data['optionType'] == 'call') & (options_data['strike'] > S)) |
            ((options_data['optionType'] == 'put') & (options_data['strike'] < S))
        ].copy()
        
        if otm_options.empty:
            print("No out-of-the-money options found.")
            return None

        otm_options['distance'] = abs(otm_options['strike'] - S)
        otm_options['probability_ITM'] = otm_options.apply(
            lambda row: calculate_probability_ITM(
                S,
                row['strike'],
                14 / 365,
                RISK_FREE_RATE,
                row['impliedVolatility'] if 'impliedVolatility' in row and not pd.isna(row['impliedVolatility']) else 0.2
            ),
            axis=1
        )
        otm_options['edge'] = (otm_options['probability_ITM'] / probability_ITM - 1) * 100
        
        valid_options = otm_options[otm_options['edge'] > 0]
        
        if valid_options.empty:
            print("No options with positive market edge found.")
            return None
        
        best_option = valid_options.sort_values(by='distance').head(1)
        return best_option.iloc[0] if not best_option.empty else None
    except Exception as e:
        print(f"Error recommending single option: {e}")
        return None

def analyze_stock(ticker, count, total):
    try:
        print(f"\nAnalyzing {count} out of {total}: {ticker}...")
        stock_data = fetch_stock_data(ticker)
        if stock_data is None:
            print(f"No data for {ticker}. Skipping analysis.")
            return None
        
        # Ensure current_price is a scalar by extracting the last value as a float
        current_price = float(stock_data['Close'].iloc[-1])  # Get the most recent closing price
        print(f"Current price for {ticker} is ${current_price:.2f}. Fetching options data...")

        stock = yf.Ticker(ticker)
        try:
            options_data = stock.options
            if not options_data:
                print(f"No options data available for {ticker}. Skipping.")
                return None
        except Exception as e:
            print(f"Error fetching options for {ticker}: {e}")
            return None
            
        all_options = []
        for option_expiration in options_data:
            try:
                option_chain = stock.option_chain(option_expiration)
                calls = option_chain.calls.assign(optionType='call', expiration=option_expiration)
                puts = option_chain.puts.assign(optionType='put', expiration=option_expiration)
                all_options.append(pd.concat([calls, puts]))
            except Exception as e:
                print(f"Error fetching options chain for {ticker} on {option_expiration}: {e}")
                continue
                
        if not all_options:
            print(f"No options chains could be fetched for {ticker}.")
            return None
        
        print(f"Fetched all options for {ticker}.")
        
        all_options_df = pd.concat(all_options, ignore_index=True)
        all_options_df = all_options_df[all_options_df['lastPrice'] <= 250]
        
        if all_options_df.empty:
            print(f"No suitable options found for {ticker}.")
            return None

        if 'impliedVolatility' not in all_options_df:
            all_options_df['impliedVolatility'] = 0.2  # Default if IV is not available

        probability_ITM = 0.5
        option = recommend_single_option(all_options_df, current_price, probability_ITM)
        
        if option is not None:
            contract_symbol = option['contractSymbol']
            last_price_real_time = option['lastPrice']
            edge = option['edge']
            
            itm_otm = "ITM" if (option['strike'] < current_price if option['optionType'] == 'call' else option['strike'] > current_price) else "OTM"
            option_type = f"{itm_otm} {option['optionType'].upper()}"
            print(f"\nFound recommended option for {ticker}")
            print(f"Current Price: ${current_price:.2f}")
            print(f"{option_type}: {contract_symbol}")
            print(f"Strike: ${option['strike']:.2f} ({abs(((option['strike'] - current_price) / current_price) * 100):.1f}% {itm_otm})")
            print(f"Premium: ${last_price_real_time:.2f}")
            print(f"Expiry: {option['expiration']}")
            print(f"Market Edge: {edge:.2f}")
            print("________________________")
                
            return {
                "Ticker": ticker,
                "Current Price": current_price,
                "Recommended Option Type": option_type,
                "Recommended Option": contract_symbol,
                "Strike": option['strike'],
                "Premium": last_price_real_time,
                "Expiry": option['expiration'],
                "Market Edge": edge
            }
        else:
            print(f"No recommended option found for {ticker}.")
            return None
    except Exception as e:
        print(f"An error occurred while analyzing {ticker}: {e}")
        return None

def main():
    tickers = get_sp500_stocks()[:100]
    total_stocks = len(tickers)
    
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/spreadsheets",
             "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key("1XBIqcV1ky446ouQhheuwuNeGVOhtu7fKuM2gKmyEDQ0").sheet1

    sheet.clear()
    header = ["Ticker", "Current Price", "Recommended Option Type", "Recommended Option",
              "Strike", "Premium", "Expiry", "Market Edge", "Timestamp"]
    sheet.append_row(header)

    while True:
        print("\nStarting analysis for top 100 S&P 500 stocks...")
        
        for count, ticker in enumerate(tickers, start=1):
            stock_info = analyze_stock(ticker, count, total_stocks)
            if stock_info:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                row_data = list(stock_info.values()) + [timestamp]
                sheet.append_row(row_data)
        
        print("\nCompleted analysis cycle.")
        print("Waiting 5 minutes before the next check...")
        time.sleep(600)

if __name__ == "__main__":
    main()

