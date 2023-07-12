#!/usr/bin/python3
import argparse
import pygsheets
from datetime import datetime, date, timedelta
from time import sleep
import requests
import json
import toml

# Assumes credentials are stored in ./gc-credentials.json
config = toml.load("./config/config.toml")

coin_list = config['coins']

def get_closing_price_tiingo(ticker):
  url = f"https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate={yesterday_tiingo_str}&endDate={yesterday_tiingo_str}&token={config['apikeys']['tiingo']}"
  headers = {"content-type": "application/json", "Accept-Charset": "UTF-8"}
  r = requests.get(url, headers=headers)
  try:
    price = json.loads(r.text)[0]['close']
  except Exception as e:
    print('Failed to load coin price response for',ticker,':',e)
    print('Response in full:',r.text)
    price = 0
  return(price)

def get_closing_price_coingecko(ticker):
  coingecko_key = config.get('apikeys', {}).get('coingecko')
  if coingecko_key is None:
    url = f"https://api.coingecko.com/api/v3/coins/{ticker}/history?date={yesterday_coingecko_str}?localization=false"
  else:
    url = f"https://pro-api.coingecko.com/api/v3/coins/{ticker}/history?x_cg_pro_api_key={config['apikeys']['coingecko']}&date={yesterday_coingecko_str}?localization=false"
  headers = {"content-type": "application/json", "Accept-Charset": "UTF-8"}
  r = requests.get(url, headers=headers)
  try:
    price = json.loads(r.text)['market_data']['current_price']['usd']
  except Exception as e:
    print('Failed to load coin price response for',ticker,':',e)
    print('Response in full:',r.text)
    price = 0
  if coingecko_key is None:
    sleep(2) # Avoid 429s
  return(price)

parser = argparse.ArgumentParser()
parser.add_argument("--dry-run", help="Print results and do not update Google sheet", action="store_true")
parser.add_argument("date", nargs="?", help="Get prices for this date, must be format yyyy-mm-dd. Yesterday if not specified")
args = parser.parse_args()

year = datetime.utcnow().strftime("%Y")
gc = pygsheets.authorize(service_file="./config/gc-credentials.json")
sh = gc.open(config['sheet']+" "+year)
wks = sh.worksheet_by_title(config['worksheets']['coin'])

if args.date:
  yesterday = datetime.strptime(args.date,"%Y-%m-%d")
  print("Getting data for",yesterday)
else:
  yesterday = datetime.utcnow() - timedelta(days=1)
yesterday_tiingo_str = yesterday.strftime("%Y-%m-%d")
yesterday_coingecko_str = yesterday.strftime("%d-%m-%Y")
day_of_year = yesterday.timetuple().tm_yday
# Assumes the worksheet has 366/367 rows, one for each day of the year, starting with header row and then 1/1 of the current year
row_to_change = day_of_year + 1

for entry in coin_list:
  coin = coin_list[entry]
  if coin['provider'] == "tiingo":
    price = get_closing_price_tiingo(coin['ticker'])
  elif coin['provider'] == "coingecko":
    price = get_closing_price_coingecko(coin['ticker'])
  else:
    print("Unknown API provider",coin['provider'],", please fix the [coins] entry in config.toml.")
    exit(1)
  if args.dry_run:
    print(coin['ticker'],price)
  else:
    wks.update_value((row_to_change,coin['column']),price)

exit(0)
