#!/usr/bin/env python3
# Fetches balances, payments, and funding events for Chainlink nodes
# Assumes it's run at 23:59 UTC and can sleep() itself into the next day
# Meant mostly for P&L purposes, though the balances are useful for taxes.
# Payment recording isn't accurate enough for the IRS, though this script could dump=
# the data into a separate sheet for tax purposes.
import argparse
import pygsheets
import datetime
from time import sleep, mktime
import requests
from collections import OrderedDict
from requests import Session
from urllib.parse import urlparse
import json
import csv
import numpy as np
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from terra_sdk.client.lcd import LCDClient

# Assumes that google sheet credentials are in ./config/gc-credentials.json

def verify_request(method, url, payload=None, headers=None, session=None):
    '''
    Verifies valid request was sent
    Params:
        method: request type 'GET' or 'POST'
        url: url of request
        payload: request payload
        headers: request headers
        session: session object for CloudFlare
    Returns:
        if request is valid
            response object
        else
            throws exception, exit program
    '''
    for retry in range(1,4):
        try:
            if method == "POST":
                resp = requests.post(url, data=payload, headers=headers)
            elif method == "GET" and session:
                resp = session.get(url, headers=headers)
            elif method == "GET" and not session:
                resp = requests.get(url, headers=headers)
            resp.raise_for_status()
            if retry > 1:
                print("Querying",url,"succeeded on try #",retry)
            return resp
        except requests.exceptions.ConnectionError as errc:
            print("Connection error:", errc)
            if retry < 3:
                print("Retrying, attempt #",retry+1)
                sleep(retry*5)
            else:
                print("Failed on final try #",retry)
            continue
        except requests.exceptions.Timeout as errt:
            print("Timeout error:", errt)
            if retry < 3:
                print("Retrying, attempt #",retry+1)
                sleep(retry*5)
            else:
                print("Failed on final try #",retry)
            continue
        except requests.exceptions.RequestException as err:
            print("Unexpected exception:",err)
            if retry < 3:
                print("Retrying, attempt #",retry+1)
                sleep(retry*5)
            else:
                print("Failed on final try #",retry)
            continue

def get_block_etherscan(unixtime, closest, apikey, baseurl):
    url = f"{baseurl}?module=block&action=getblocknobytime&timestamp={unixtime}&closest={closest}&apikey={apikey}"
    r = verify_request(method="GET", url=url)
    try:
        block = json.loads(r.text)['result']
        return block
    except Exception as e:
        print("Failed to get block from",baseurl,r)

def get_tx_etherscan(txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == "erc20":
    url = f"{baseurl}?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}"
  elif txtype == "standard":
    url = f"{baseurl}?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}"
  else:
    raise ValueError("Unknown txtype:",txtype,". This is a bug.")
  # Working around CloudFlare triggering on the request
  parsed_url = urlparse(baseurl)
  host = parsed_url.netloc
  s = Session()
#  headers = {
#    'Accept-Encoding': 'gzip, deflate, br',
#    'Host': host,
#    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:77.0) Gecko/20100101 Firefox/77.0',
#    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
#    'Accept-Language': 'en-GB,en;q=0.5',
#    'Accept-Encoding': 'gzip, deflate',
#    'Connection': 'close',
#    'Upgrade-Insecure-Requests': '1',
#    'Dnt': '1'
#  }
#  s.headers = headers
#  r = verify_request(method="GET", url=url, headers=headers, session=s)
  r = verify_request(method="GET", url=url, session=s)
  try:
    return r.text
  except Exception as e:
    print("get_tx_etherscan failed with ",e)

def get_tx_etherscan_cf(txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == "erc20":
    if not apikey:
      url = f"{baseurl}?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}"
    else:
      url = f"{baseurl}?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}"
  elif txtype == "standard":
    if not apikey:
      url = f"{baseurl}?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}"
    else:
      url = f"{baseurl}?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}"
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
  r = verify_request(method="GET", url=url, headers=headers, session=s)
  try:
    return r.text
  except Exception as e:
    print("get_tx_etherscan_cf failed with ",e)

def get_tx_oklink(chain, txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == "erc20":
    url = f"{baseurl}/explorer/address/token-transaction-list?chainShortName={chain}&address={address}&protocolType=token_20&tokenContractAddress={contract}&startBlockHeight={start_block}&endBlockHeight={end_block}"
  elif txtype == "standard":
    url = f"{baseurl}/explorer/address/normal-transaction-list?chainShortName={chain}&address={address}&startBlockHeight={start_block}&endBlockHeight={end_block}"
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
    'Dnt': '1',
    'OK-ACCESS-KEY': {apikey}
  })
  s.headers = headers
  r = verify_request(method="GET", url=url, headers=headers, session=s)
  try:
    return r.text
  except Exception as e:
    print("get_tx_oklink failed with ",e)

def get_tx_solana(txtype, address,start_time,end_time, offset, apikey, baseurl):
  if txtype == "spl":
    url = f"{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50"
  elif txtype == "standard":
    url = f"{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50"
  else:
    raise ValueError("Unknown txtype:",txtype,". This is a bug.")
  # Working around CloudFlare triggering on the request
  s = Session()
  headers = {"accept": "application/json","token": apikey}
  s.headers = headers
  r = verify_request(method="GET", url=url, headers=headers, session=s)
  try:
    return r.text
  except Exception as e:
    print("get_tx_solana failed with ",e)

def sum_incoming_sol_txs(type, address, txs, contract=None):
    ''' 
    Find payments in LINK tokens, or node funding in SOL. Note that
    funding detection is currently disabled in the code.
    '''
    txs_json = json.loads(txs)
    sum = 0
    if type == 'spl':
        for tx in txs_json['data']:
# This should work but I can see increases with dec and a positive change amount, so try for a pos change amount instead
#            if tx['owner'].lower() == address.lower() and tx['tokenAddress'].lower() == contract.lower() and tx['changeType'] == 'inc':
            if tx['owner'].lower() == address.lower() and tx['tokenAddress'].lower() == contract.lower() and int(tx['changeAmount']) > 0:
                sum += int(tx['changeAmount']) / 10 ** int(tx['decimals'])
    elif type == 'sol':
        for tx in txs_json['data']:
            if tx['owner'].lower() == address.lower() and tx['changeType'] == 'inc':
                sum += int(tx['changeAmount']) / 10 ** int(tx['decimals'])
    else:
        raise ValueError("Please enter valid tx type")
    return sum

def sum_incoming_evm_txs_between(address,txs,start_time,end_time):
  txs_json = json.loads(txs)
  sum = 0
  if not txs_json['result']:
    return sum
  for tx in txs_json['result']:
    if tx['to'] == address.lower() and int(tx['timeStamp']) > start_time and int(tx['timeStamp']) < end_time:
      sum += int(tx['value']) / 1000000000000000000
  return sum

def main():
    with open("./config/config.toml", "rb") as f:
        config = tomllib.load(f)
    # Google Sheets
    year = datetime.datetime.now(datetime.UTC).strftime("%Y")
    gc = pygsheets.authorize(service_file='./config/gc-credentials.json')
    sh = gc.open(config['sheet']+" "+year)

    chain_list = config['chains']

    # Get payment information
    wks = sh.worksheet_by_title(config["worksheets"]["payment"])
    wallet_list = config['wallets']

    if args.date:
        queryday = datetime.datetime.strptime(args.date,"%Y-%m-%d")
    else:
    # Assumes this is run the day after
        queryday = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)

    start = datetime.datetime(queryday.year, queryday.month, queryday.day, 0, 0, 0)
    end = datetime.datetime(queryday.year, queryday.month, queryday.day, 23, 59, 59)
    if args.dry_run:
        print("Getting data from",start,"to",end)
    start_unix = int(mktime(start.timetuple()))
    end_unix = int(mktime(end.timetuple()))
    day_of_year = queryday.timetuple().tm_yday

    # Assumes the worksheet has 366/367 rows, one for each day of the year, starting with header row and then 1/1 of the current year
    row_to_change = day_of_year + 1
    for entry in wallet_list:
        wallet = wallet_list[entry]
        chain = chain_list[wallet['chain']]
        if not chain['url']:
            continue
        if chain['type'] == 'etherscan':
            start_block = get_block_etherscan(start_unix,'after', chain['apikey'], chain['url'])
            end_block = get_block_etherscan(end_unix,'before', chain['apikey'], chain['url'])
            token_txs = get_tx_etherscan("erc20", wallet['address'], chain['token_contract'], start_block, end_block, chain['apikey'], chain['url'])
            try:
              token_sum = sum_incoming_evm_txs_between(wallet['address'], token_txs, start_unix, end_unix)
            except:
              print("Error during",entry,"token sum, here's the tx blurb:", token_txs)
              continue
        elif chain['type'] == 'etherscan-cf':
            start_block =  0
            end_block = 999999999
            token_txs = get_tx_etherscan_cf("erc20", wallet['address'], chain['token_contract'], start_block, end_block, chain['apikey'], chain['url'])
            try:
              token_sum = sum_incoming_evm_txs_between(wallet['address'], token_txs, start_unix, end_unix)
            except:
              print("Error during",entry,"token sum, here's the tx blurb:", token_txs)
              continue
        elif chain['type'] == "solana":
            offset = 0
            token_sum = 0
            while True:
                token_txs = get_tx_solana("spl", wallet['address'], start_unix, end_unix, offset, chain['apikey'], chain['url'])
                try:
                  if not json.loads(token_txs)['data']:
                    break
                  token_sum += sum_incoming_sol_txs("spl", wallet['address'], token_txs, chain['token_contract'])
                except Exception as e:
                  print("Error during Solana payment sum, here's the tx blurb:", token_txs)
                  print("Exception was:",e)
                  break
                offset += 50
                sleep(3) # Avoid rate limits 
        elif chain['type'] == "terra":
  #          contracts_list = chain['contracts']
            # If done manually it'd be something like curl 'https://terra-a.example.com/cosmos/tx/v1beta1/txs?pagination.limit=1000&events=message.contract%3D'\'terra1fr7g6n0xue60sytq72zrlteul7xvz8tzl3tnv6\'
   #         terra = LCDClient(chain['url'], "columbus-5")
    #        for contract in contracts_list:
     #           token_txs = terra.tx.search([("pagination.limit", "1000"),("message.contract", contract)])
      #          if token_txs['txs']:
       #             print(token_txs['txs'])
            continue
        elif chain['type'] == "klaytn":
            continue
        else:
            raise ValueError("Unknown API provider",wallet['provider'],", please fix [wallets] in config.toml" )
        if token_sum > 0:
            if args.dry_run:
                print(entry,"Payment:",token_sum)
            else:
                wks.update_value((row_to_change,wallet['column']),token_sum)
        sleep(3) # Avoid rate limits
'''
    # Get Funding
    # Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
    row_to_change = day_of_year + 2

    # The API returns the last 10,000 txs. For busy nodes this isn't enough; detecting funding is best-effort
    for node in node_list:
        if node['provider'] == 'etherscan':
            start_block = get_block_etherscan(start_unix, 'after', node['apikey'], node['baseurl'])
            end_block = get_block_etherscan(end_unix, 'before', node['apikey'], node['baseurl'])
            txs = get_tx_etherscan('standard', node['address'], '', start_block, end_block, node['apikey'],
                                   node['baseurl'])
            funding = sum_incoming_evm_txs_between(node['address'], txs, start_unix, end_unix)
        elif node['provider'] == 'etherscan-all-cf':
            start_block = 0
            end_block = 999999999
            txs = get_tx_etherscan_cf('standard', node['address'], '', start_block, end_block, node['apikey'],
                                      node['baseurl'])
            funding = sum_incoming_evm_txs_between(node['address'], txs, start_unix, end_unix)
        elif node['provider'] == 'solana':
            offset = 0
            funding = 0
            while True:
                txs = get_tx_solana('standard', node['address'], start_unix, end_unix, offset, node['baseurl'])
                if not json.loads(txs)['data']:
                    break
                funding += sum_incoming_sol_txs(node['address'], txs)
                offset += 50
        elif node['provider'] == 'nada':
            continue
        else:
            raise ValueError('Unknown API provider', node['provider'], ', please fix the node_list.')
        if funding > 0:
            if args.dry_run:
                print(node['worksheet-title'],'Funding:',funding)
            else:
                # Assumes Date, Time, Balance, Funding as the first four columns
                wks = sh.worksheet_by_title(node['worksheet-title'])
                wks.update_value((row_to_change, 4), funding)
        sleep(3)  # Avoid rate limits
'''
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", help="Print results and do not update Google sheet", action="store_true")
    parser.add_argument("date", nargs="?", help="Get prices for this date, must be format yyyy-mm-dd. Today if not specified")
    args = parser.parse_args()
    main()
