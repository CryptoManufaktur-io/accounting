#!/usr/bin/env python3
# Fetches balances, payments, and funding events for Chainlink nodes
# Assumes it's run at 23:59 UTC and can sleep() itself into the next day
# Meant mostly for P&L purposes, though the balances are useful for taxes.
# Payment recording isn't accurate enough for the IRS, though this script could dump=
# the data into a separate sheet for tax purposes.

import pygsheets
from datetime import datetime, date, timedelta
from time import sleep, mktime
import requests
from collections import OrderedDict
from requests import Session
from urllib.parse import urlparse
import json

# Assumes credentials are stored in ./gc-credentials.json
sheet_title = "CMF Accounting 2022"
payment_worksheet_title = "All payments" # Case sensitive

# List of nodes to fetch balances for, as well as incoming funding
# type: evm or sol
# worksheet-title: The title of the worksheet to update, inside the Google sheet. This is case sensitive!
# url: URL of an RPC server
# address: Address to get balance for, this is your main node address
# provider: API provider to use to find funding, etherscan (and clones), etherscan-all-cf (no block query API, works around CloudFlare triggering), and solana
# baseurl: API provider's base URL
# apikey: Key for that provider, or empty
node_list = [
  {'type':'evm', 'worksheet-title':'Mainnet OCR', 'url':'https://eth-main-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.etherscan.io','apikey':''},
  {'type':'evm', 'worksheet-title':'Mainnet Keeper', 'url':'https://eth-main-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.etherscan.io','apikey':''},
  {'type':'evm', 'worksheet-title':'Polygon OCR', 'url':'https://polygon-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.polygonscan.com','apikey':''},
  {'type':'evm', 'worksheet-title':'Polygon FM', 'url':'https://polygon-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.polygonscan.com','apikey':''},
  {'type':'evm', 'worksheet-title':'Polygon Keeper', 'url':'https://polygon-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.polygonscan.com','apikey':''},
  {'type':'evm', 'worksheet-title':'Opti FM', 'url':'https://mainnet.optimism.io', 'address':'0x','provider':'etherscan-all-cf','baseurl':'https://api-optimistic.etherscan.io','apikey':''},
  {'type':'evm', 'worksheet-title':'Fantom OCR', 'url':'https://fantom-a.example.com', 'address':'0x','provider':'etherscan-all-cf','baseurl':'https://api.ftmscan.com','apikey':''},
  {'type':'evm', 'worksheet-title':'HECO OCR', 'url':'https://heco-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.hecoinfo.com','apikey':''},
  {'type':'evm', 'worksheet-title':'HECO FM', 'url':'https://heco-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api.hecoinfo.com','apikey':''},
  {'type':'evm', 'worksheet-title':'Moonriver OCR', 'url':'https://moonriver-a.example.com', 'address':'0x','provider':'etherscan','baseurl':'https://api-moonriver.moonscan.io','apikey':''},
  {'type':'sol', 'worksheet-title':'Solana OCR', 'url':'https://solana-main-a.example.com', 'address':'','provider':'solana','baseurl':'https://public-api.solscan.io','apikey':''},
  ]

# List of wallets to fetch incoming payment for
# address: Wallet address
# contract: LINK (or other token) contract address
# column: Column this wallet uses in the sheet
# provider: API provider to use, etherscan (and clones), etherscan-all (no block query API), etherscan-all-cf (no block query, works around CloudFlare triggering), and solana
# baseurl: API provider's base URL
# apikey: Key for that provider, or empty
wallet_list = [
  {'name':'Ethereum','address':'0x', 'contract':'0x514910771af9ca656af840dff83e8264ecf986ca', 'column': 2, 'provider':'etherscan', 'baseurl':'https://api.etherscan.io', 'apikey':''},
  {'name':'Polygon','address':'0x', 'contract':'0xb0897686c545045afc77cf20ec7a532e3120e0f1', 'column': 4, 'provider':'etherscan', 'baseurl':'https://api.polygonscan.com', 'apikey':''},
  {'name':'Fantom','address':'0x', 'contract':'0x6f43ff82cca38001b6699a8ac47a2d0e66939407', 'column': 8, 'provider':'etherscan-all', 'baseurl':'https://api.ftmscan.com', 'apikey':''},
  {'name':'Huobi','address':'0x', 'contract':'0x9e004545c59d359f6b7bfb06a26390b087717b42', 'column': 10, 'provider':'etherscan', 'baseurl':'https://api.hecoinfo.com', 'apikey':''},
  {'name':'Moonriver','address':'0x', 'contract':'0x8b12ac23bfe11cab03a634c1f117d64a7f2cfd3e', 'column': 12, 'provider':'etherscan', 'baseurl':'https://api-moonriver.moonscan.io', 'apikey':''},
  {'name':'RocketPool','address':'0x', 'contract':'0xd33526068d116ce69f19a9ee46f0bd304f21a51f', 'column': 16, 'provider':'etherscan', 'baseurl':'https://api.etherscan.io', 'apikey':''},
  {'name':'Solana','address':'', 'contract':'AY2uKQZ21PGHoarsdnJ65xwJv1ojnM1Vn8UGMRpfZ2nX', 'column': 14, 'provider':'solana', 'baseurl':'https://public-api.solscan.io', 'apikey':''},
  {'name':'Optimism','address':'0x', 'contract':'0x350a791bfc2c21f9ed5d10980dad2e2638ffa7f6', 'column': 6, 'provider':'etherscan-all-cf', 'baseurl':'https://api-optimistic.etherscan.io', 'apikey':''},
  ]

def get_evm_balance(url, address):
  payload = f'{{"jsonrpc":"2.0","method":"eth_getBalance","params":["{address}", "latest"],"id":1}}'
  headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
  r = requests.post(url, data=payload, headers=headers)
  balance = int(json.loads(r.text)['result'],16) / 1000000000000000000
  return(balance)

def get_sol_balance(url, address):
  payload = f'{{"jsonrpc":"2.0","method":"getBalance","params":["{address}"],"id":1}}'
  headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
  r = requests.post(url, data=payload, headers=headers)
  balance = json.loads(r.text)['result']['value'] / 1000000000
  return(balance)

def get_block_etherscan(unixtime, closest, apikey, baseurl):
  url = f'{baseurl}/api?module=block&action=getblocknobytime&timestamp={unixtime}&closest={closest}&apikey={apikey}'
  r = requests.get(url)
  block = json.loads(r.text)['result']
  return(block)

def get_tx_etherscan(txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == 'erc20':
    url = f'{baseurl}/api?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  elif txtype == 'standard':
    url = f'{baseurl}/api?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  else:
    print("Unknown txtype:",txtype,". This is a bug.")
    exit(1)
  r = requests.get(url)
  return(r.text)

def get_tx_etherscan_cf(txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == 'erc20':
    url = f'{baseurl}/api?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  elif txtype == 'standard':
    url = f'{baseurl}/api?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  else:
    print("Unknown txtype:",txtype,". This is a bug.")
    exit(1)
  # Working around CloudFlare triggering on the request
  parsed_url = urlparse(baseurl)
  host = parsed_url.netloc
  s = Session()
  headers = OrderedDict({
    'Accept-Encoding': 'gzip, deflate, br',
    'Host': host,
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'close',
    'Upgrade-Insecure-Requests': '1',
    'Dnt': '1'
  })
  s.headers = headers
  r = s.get(url, headers=headers).text
  return(r)

def sum_incoming_txs_between(address,txs,start_time,end_time):
  txs_json = json.loads(txs)
  sum = 0
  if not txs_json['result']:
    return(sum)
  for tx in txs_json['result']:
    if tx['to'] == address.lower() and int(tx['timeStamp']) > start_time and int(tx['timeStamp']) < end_time:
      sum += int(tx['value']) / 1000000000000000000
  return(sum)

def get_tx_solana(txtype, address,start_time,end_time, offset, baseurl):
  if txtype == 'spl':
    url = f'{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50'
  elif txtype == 'standard':
    url = f'{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50'
  else:
    print("Unknown txtype:",txtype,". This is a bug.")
    exit(1)
  headers = {'accept': 'application/json'}
  r = requests.get(url,headers)
  return(r.text)

def sum_incoming_spl_txs(address, contract, txs):
  txs_json = json.loads(txs)
  sum = 0
  for tx in txs_json['data']:
    if tx['owner'].lower() == address.lower() and tx['tokenAddress'].lower() == contract.lower() and tx['changeType'] == 'inc':
      sum += int(tx['changeAmount']) / 10**int(tx['decimals'])
  return(sum)

def sum_incoming_sol_txs(address, txs):
  txs_json = json.loads(txs)
  sum = 0
  for tx in txs_json['data']:
    print(tx)
    if tx['owner'].lower() == address.lower() and tx['changeType'] == 'inc':
      sum += int(tx['changeAmount']) / 10**int(tx['decimals'])
  return(sum)

gc = pygsheets.authorize(service_file='./gc-credentials.json')
sh = gc.open(sheet_title)

# Balances
day_of_year = datetime.utcnow().timetuple().tm_yday
# Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
row_to_change = day_of_year + 2
utc_time_str = datetime.utcnow().strftime("%H:%M")

for node in node_list:
  if node['type'] == 'evm':
    balance = get_evm_balance(node['url'],node['address'])
  elif node['type'] == 'sol':
    balance = get_sol_balance(node['url'],node['address'])
  else:
    print('Unknown node type',node['type'],', please fix the node_list.')
    exit(1)
  wks = sh.worksheet_by_title(node['worksheet-title'])
  # Assumes Date, Time, Balance as the first three columns
  #print(node['worksheet-title'],'Balance:',balance)
  wks.update_value((row_to_change,2),utc_time_str)
  wks.update_value((row_to_change,3),balance)

# We need it to be the next day - snooze for 70s assuming the script starts at 23:59
sleep(70)

today = datetime.utcnow()
yesterday = datetime.utcnow() - timedelta(days=1)
start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0)
end = datetime(today.year, today.month, today.day, 0, 0)
start_unix = int(mktime(start.timetuple()))
end_unix = int(mktime(end.timetuple()))
day_of_year = yesterday.timetuple().tm_yday

# Payments
# Assumes the worksheet has 366/367 rows, one for each day of the year, starting with header row and then 1/1 of the current year
row_to_change = day_of_year + 1

wks = sh.worksheet_by_title(payment_worksheet_title)

for wallet in wallet_list:
  if wallet['provider'] == 'etherscan':
    start_block = get_block_etherscan(start_unix,'after',wallet['apikey'],wallet['baseurl'])
    end_block = get_block_etherscan(end_unix,'before',wallet['apikey'],wallet['baseurl'])
    token_txs = get_tx_etherscan('erc20',wallet['address'],wallet['contract'],start_block,end_block,wallet['apikey'],wallet['baseurl'])
    token_sum = sum_incoming_txs_between(wallet['address'],token_txs,start_unix,end_unix)
  elif wallet['provider'] == 'etherscan-all-cf':
    start_block =  0
    end_block = 999999999
    token_txs = get_tx_etherscan_cf('erc20',wallet['address'],wallet['contract'],start_block,end_block,wallet['apikey'],wallet['baseurl'])
    token_sum = sum_incoming_txs_between(wallet['address'],token_txs,start_unix,end_unix)
  elif wallet['provider'] == 'solana':
    offset = 0
    token_sum = 0
    while True:
      token_txs = get_tx_solana('spl',wallet['address'],start_unix,end_unix,offset,wallet['baseurl'])
      if not json.loads(token_txs)['data']:
        break
      token_sum += sum_incoming_spl_txs(wallet['address'],wallet['contract'],token_txs)
      offset += 50
  else:
    print('Unknown API provider',wallet['provider'],', please fix the wallet_list.')
    exit(1)
  if token_sum > 0:
    #print(wallet['name'],'Payment:',token_sum)
    wks.update_value((row_to_change,wallet['column']),token_sum)
  sleep(3) # Avoid rate limits

# Funding

# Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
row_to_change = day_of_year + 2

# The API returns the last 10,000 txs. For busy nodes this isn't enough; detecting funding is best-effort
for node in node_list:
  if node['provider'] == 'etherscan':
    start_block = get_block_etherscan(start_unix,'after',node['apikey'],node['baseurl'])
    end_block = get_block_etherscan(end_unix,'before',node['apikey'],node['baseurl'])
    txs = get_tx_etherscan('standard',node['address'],'',start_block,end_block,node['apikey'],node['baseurl'])
    funding = sum_incoming_txs_between(node['address'],txs,start_unix,end_unix)
  elif node['provider'] == 'etherscan-all-cf':
    start_block =  0
    end_block = 999999999
    txs = get_tx_etherscan_cf('standard',node['address'],'',start_block,end_block,node['apikey'],node['baseurl'])
    funding = sum_incoming_txs_between(node['address'],txs,start_unix,end_unix)
  elif node['provider'] == 'solana':
    offset = 0
    funding = 0
    while True:
      txs = get_tx_solana('standard',node['address'],start_unix,end_unix,offset,node['baseurl'])
      if not json.loads(txs)['data']:
        break
      funding += sum_incoming_sol_txs(node['address'],txs)
      offset += 50
  else:
    print('Unknown API provider',node['provider'],', please fix the node_list.')
    exit(1)
  wks = sh.worksheet_by_title(node['worksheet-title'])
  # Assumes Date, Time, Balance, Funding as the first four columns
  if funding > 0:
    #print(node['worksheet-title'],'Funding:',funding)
    wks.update_value((row_to_change,4),funding)
  sleep(3) # Avoid rate limits

exit(0)
