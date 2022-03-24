#!/usr/bin/python3
import argparse
import pygsheets
from datetime import datetime, date, timedelta
from time import sleep
import requests
import json

# Assumes credentials are stored in ./gc-credentials.json
sheet_title = "CMF Accounting 2022"
worksheet_title = "Coin Daily Close" # Case sensitive
# Tiingo API token
api_key = ""
# List of coins
# ticker: Pair to query, usually against USD 
# column: Column this pair uses in the sheet
coin_list = [
  {'ticker':'ethusd', 'column': 2, 'provider':'tiingo'},
  {'ticker':'maticusd', 'column': 3, 'provider':'tiingo'},
  {'ticker':'ftmusd', 'column': 4, 'provider':'tiingo'},
  {'ticker':'htusd', 'column': 5, 'provider':'tiingo'},
  {'ticker':'linkusd', 'column': 6, 'provider':'tiingo'},
  {'ticker':'movrusd', 'column': 7, 'provider':'tiingo'},
  {'ticker':'solusd', 'column': 8, 'provider':'tiingo'},
  {'ticker':'rocket-pool', 'column': 9, 'provider':'coingecko'},
  {'ticker':'usdcusd', 'column': 10, 'provider':'tiingo'},
  {'ticker':'lunausd', 'column': 11, 'provider':'tiingo'}
  ]

def get_closing_price_tiingo(ticker):
  url = f'https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate={yesterday_tiingo_str}&endDate={yesterday_tiingo_str}&token={api_key}'
  headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
  r = requests.get(url, headers=headers)
  price = json.loads(r.text)[0]['close']
  return(price)

def get_closing_price_coingecko(ticker):
  url = f'https://api.coingecko.com/api/v3/coins/{ticker}/history?date={yesterday_coingecko_str}?localization=false'
  headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
  r = requests.get(url, headers=headers)
  price = json.loads(r.text)['market_data']['current_price']['usd']
  sleep(2) # Avoid 429s
  return(price)

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", help="Print results and do not update Google sheet", action="store_true")
args = parser.parse_args()

gc = pygsheets.authorize(service_file='./gc-credentials.json')
sh = gc.open(sheet_title)
wks = sh.worksheet_by_title(worksheet_title)

yesterday = datetime.utcnow() - timedelta(days=1)
yesterday_tiingo_str = yesterday.strftime("%Y-%m-%d")
yesterday_coingecko_str = yesterday.strftime("%d-%m-%Y")
day_of_year = yesterday.timetuple().tm_yday
# Assumes the worksheet has 366/367 rows, one for each day of the year, starting with header row and then 1/1 of the current year
row_to_change = day_of_year + 1

for coin in coin_list:
  if coin['provider'] == 'tiingo':
    price = get_closing_price_tiingo(coin['ticker'])
  elif coin['provider'] == 'coingecko':
    price = get_closing_price_coingecko(coin['ticker'])
  else:
    print('Unknown API provider',coin['provider'],', please fix the coin_list.')
    exit(1)
  if args.dry_run:
    print(coin['ticker'],price)
  else:
    wks.update_value((row_to_change,coin['column']),price)

exit(0)
