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
import csv
import numpy as np



payment_worksheet_title = "All payments"


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
    try:
        if method == 'POST':
            resp = requests.post(url, data=payload, headers=headers)
        elif method == 'GET' and session:
            resp = session.get(url, headers=headers)
        elif method == 'GET' and not session:
            resp = requests.get(url, headers=headers)
        resp.raise_for_status()
        return resp
    except requests.exceptions.ConnectionError as errc:
        print('Connection error:', errc)
        exit(1)
    except requests.exceptions.Timeout as errt:
        print('Timeout error:', errt)
        exit(1)
    except requests.exceptions.RequestException as err:
        print('Unexpected exception:',err)
        exit(1)

def get_balance(type, url, address):
    '''
    Combined get_evm_balance and get_sol_balance to one function
    Logic implemented based on node type 
    Params:
        type: node type (evm or sol)
        url: rpc url
        address: wallet address
    Returns:
        if type is valid
            balance
        else
            exception
    '''
    headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
    if type == 'evm':
        payload = f'{{"jsonrpc":"2.0","method":"eth_getBalance","params":["{address}", "latest"],"id":1}}'
        r = verify_request(method='POST', url=url, payload=payload, headers=headers)
        balance = int(json.loads(r.text)['result'],16) / 1000000000000000000
    elif type == 'sol':
        payload = f'{{"jsonrpc":"2.0","method":"getBalance","params":["{address}"],"id":1}}'
        r = verify_request(method='POST', url=url, payload=payload, headers=headers)
        balance = json.loads(r.text)['result']['value'] / 1000000000
    else:
        raise SystemExit('Please enter valid node type')
    return balance

def get_block_etherscan(unixtime, closest, apikey, baseurl):
    url = f'{baseurl}/api?module=block&action=getblocknobytime&timestamp={unixtime}&closest={closest}&apikey={apikey}'
    r = verify_request(method='GET', url=url)
    block = json.loads(r.text)['result']
    return block

def get_tx_etherscan(txtype, address, contract, start_block, end_block, apikey, baseurl):
  if txtype == 'erc20':
    url = f'{baseurl}/api?module=account&action=tokentx&contractaddress={contract}&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  elif txtype == 'standard':
    url = f'{baseurl}/api?module=account&action=txlist&address={address}&startblock={start_block}&endblock={end_block}&apikey={apikey}'
  else:
    raise ValueError("Unknown txtype:",txtype,". This is a bug.")
  r = verify_request(method='GET', url=url)
  return r.text

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
  r = verify_request(method='GET', url=url, headers=headers, session=s)
  return r.text

def get_tx_solana(txtype, address,start_time,end_time, offset, baseurl):
  if txtype == 'spl':
    url = f'{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50'
  elif txtype == 'standard':
    url = f'{baseurl}/account/splTransfers?account={address}&fromTime={start_time}&toTime={end_time}&offset={offset}&limit=50'
  else:
    raise ValueError("Unknown txtype:",txtype,". This is a bug.")
  headers = {'accept': 'application/json'}
  r = verify_request(method='GET', url=url, headers=headers)
  return r.text

def sum_incoming_txs(type, address, txs, contract=None):
    '''
    Combines sum_incoming_sol_txs and sum_spl_txs
    '''
    txs_json = json.loads(txs)
    sum = 0
    if type == 'spl':
        for tx in txs_json['data']:
            if tx['owner'].lower() == address.lower() and tx['tokenAddress'].lower() == contract.lower() and tx['changeType'] == 'inc':
                sum += int(tx['changeAmount']) / 10 ** int(tx['decimals'])
    elif type == 'sol':
        for tx in txs_json['data']:
            print(tx)
            if tx['owner'].lower() == address.lower() and tx['changeType'] == 'inc':
                sum += int(tx['changeAmount']) / 10 ** int(tx['decimals'])
    else:
        raise ValueError('Please enter valid tx type')

def sum_incoming_txs_between(address,txs,start_time,end_time):
  txs_json = json.loads(txs)
  sum = 0
  if not txs_json['result']:
    return sum
  for tx in txs_json['result']:
    if tx['to'] == address.lower() and int(tx['timeStamp']) > start_time and int(tx['timeStamp']) < end_time:
      sum += int(tx['value']) / 1000000000000000000
  return sum

def get_data_from_csv(data_csv):
    '''
    Parse rows of csv file as a dictionary, append result to list
    Params:
        data_csv: csv file in 'data' directory containing node or wallet information
    Returns
        data_list
    '''
    with open(data_csv, encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        data_list = []
        for line in reader:
            data_list.append(line)
        return data_list

def set_worksheet_balance(sh, node, row_to_change, day_of_year, utc_time_str, balance):
    '''
    Inserts row with columns Day, Balance, Time
    Params:
        sh: google worksheet
        node: node containing worksheet title
        row_to_change: row in sheet to update
        day_of_year: current day of year
        utc_time_str: utc timestamp
        balance: current balance 
    Returns:
        None 
    '''
    wks = sh.worksheet_by_title(node['worksheet-title'])
    # Assumes Date, Time, Balance as the first three column
    wks.insert_rows(row_to_change - 1, values=[[day_of_year, utc_time_str, balance]])
    print('Successfully updated: ', node['worksheet-title'])

def main():
    # Balances
    day_of_year = datetime.utcnow().timetuple().tm_yday
    # Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
    row_to_change = day_of_year + 2
    utc_time_str = datetime.utcnow().strftime("%H:%M")

    # Google Sheets
    sheet_title = "CMF Accounting 2022"
    gc = pygsheets.authorize(service_file='./get-chainlink-activity-29b9ab8e8573.json')
    sh = gc.open(sheet_title)

    # # CSV containing node list
    node_list = get_data_from_csv('./data/node_list.csv')
    for node in node_list:
        # Throws exception if request is valid but error in the return data
        try:
            balance = get_balance(node['type'], node['url'], node['address'])
        except BaseException as e:
            print('Request is not returning valid data:', e)
            exit(1)
        set_worksheet_balance(sh, node, row_to_change, day_of_year, utc_time_str, balance)


    # We need it to be the next day - snooze for 70s assuming the script starts at 23:59
    #sleep(70)

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
    # Payment worksheet

    wks = sh.worksheet_by_title(payment_worksheet_title)
    # CSV containing wallet list
    wallet_list = get_data_from_csv('/.data/wallet_list.csv')
    for wallet in wallet_list:
        if wallet['provider'] == 'etherscan':
            start_block = get_block_etherscan(start_unix,'after',wallet['apikey'],wallet['baseurl'])
            end_block = get_block_etherscan(end_unix,'before',wallet['apikey'],wallet['baseurl'])
            token_txs = get_tx_etherscan('erc20',wallet['address'],wallet['contract'],start_block,end_block,wallet['apikey'],wallet['baseurl'])
            token_sum = sum_incoming_txs_between(wallet['address'],token_txs,start_unix,end_unix)
        elif wallet['provider'] == 'etherscan-all-cf' or wallet['provider'] == 'etherscan-all':
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
                token_sum += sum_incoming_txs('spl', wallet['address'],wallet['contract'],token_txs)
                offset += 50
        else:
            raise ValueError('Unknown API provider',wallet['provider'],', please fix the wallet_list.')
        if token_sum > 0:
            #print(wallet['name'],'Payment:',token_sum)
            wks.update_value((row_to_change,wallet['column']),token_sum)
        else:
            print('Token_sum=0. No updates made to ', wks)
        sleep(3) # Avoid rate limits
        # Funding
        # Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
    row_to_change = day_of_year + 2

    # The API returns the last 10,000 txs. For busy nodes this isn't enough; detecting funding is best-effort
    for node in node_list:
        if node['provider'] == 'etherscan':
            start_block = get_block_etherscan(start_unix, 'after', node['apikey'], node['baseurl'])
            end_block = get_block_etherscan(end_unix, 'before', node['apikey'], node['baseurl'])
            txs = get_tx_etherscan('standard', node['address'], '', start_block, end_block, node['apikey'],
                                   node['baseurl'])
            funding = sum_incoming_txs_between(node['address'], txs, start_unix, end_unix)
        elif node['provider'] == 'etherscan-all-cf':
            start_block = 0
            end_block = 999999999
            txs = get_tx_etherscan_cf('standard', node['address'], '', start_block, end_block, node['apikey'],
                                      node['baseurl'])
            funding = sum_incoming_txs_between(node['address'], txs, start_unix, end_unix)
        elif node['provider'] == 'solana':
            offset = 0
            funding = 0
            while True:
                txs = get_tx_solana('standard', node['address'], start_unix, end_unix, offset, node['baseurl'])
                if not json.loads(txs)['data']:
                    break
                funding += sum_incoming_txs(node['address'], txs)
                offset += 50
        else:
            raise ValueError('Unknown API provider', node['provider'], ', please fix the node_list.')
        wks = sh.worksheet_by_title(node['worksheet-title'])
        # Assumes Date, Time, Balance, Funding as the first four columns
        if funding > 0:
            # print(node['worksheet-title'],'Funding:',funding)
            wks.update_value((row_to_change, 4), funding)
        else:
            print('Funding = 0. No updates made to ', wks)
        sleep(3)  # Avoid rate limits
if __name__ == '__main__':
    main()
