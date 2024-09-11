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

def get_balance(type, url, address):
    '''
    Params:
        type: node type (etherscan,etherscan-cf,oklink,solana)
        url: rpc url
        address: wallet address
    Returns:
        if type is valid
            balance
        else
            exception
    '''
    headers = {"content-type": "application/json", "Accept-Charset": "UTF-8"}
    if type == "etherscan" or type == "etherscan-cf" or type == "klaytn" or type == "oklink":
        payload = f'{{"jsonrpc":"2.0","method":"eth_getBalance","params":["{address}", "latest"],"id":1}}'
        r = verify_request(method='POST', url=url, payload=payload, headers=headers)
        balance = int(json.loads(r.text)['result'],16) / 1000000000000000000
    elif type == "solana":
        payload = f'{{"jsonrpc":"2.0","method":"getBalance","params":["{address}"],"id":1}}'
        r = verify_request(method='POST', url=url, payload=payload, headers=headers)
        balance = json.loads(r.text)['result']['value'] / 1000000000
    elif type == "terra":
        headers = {"accept": "application/json"}
        url = f"{url}/cosmos/bank/v1beta1/balances/{address}/by_denom?denom=uluna"
        r = verify_request(method='GET', url=url, headers=headers)
        balance = int(json.loads(r.text)['balance']['amount']) / 1000000
    else:
        raise SystemExit("Please enter valid node type")
    return balance

def main():
    with open("./config/config.toml", "rb") as f:
        config = tomllib.load(f)
    # Google Sheets
    year = datetime.datetime.now(datetime.UTC).strftime("%Y")
    gc = pygsheets.authorize(service_file='./config/gc-credentials.json')
    sh = gc.open(config['sheet']+" "+year)

    chain_list = config['chains']

    # Get Balances
    # Assumes this is run at 23:59 UTC and that accounting happens on UTC
    day_of_year = datetime.datetime.now(datetime.UTC).timetuple().tm_yday
    # Assumes that each worksheet has 367/368 rows, one for each day of the year, starting with header row and then 12/31 of the previous year
    row_to_change = day_of_year + 2
    utc_time_str = datetime.datetime.now(datetime.UTC).strftime("%H:%M")

    node_list = config['nodes']
    for entry in node_list:
        node = node_list[entry]
        chain = chain_list[node['chain']]
        # Throws exception if request is valid but error in the return data
        try:
            balance = get_balance(chain['type'], chain['rpc_url'], node['address'])
        except BaseException as e:
            print("Request is not returning valid data:", e)
            continue
        if args.dry_run:
            print(node['worksheet_title'],"Balance:",balance)
        else:
            # Assumes Date, Balance as the first two columns
            wks = sh.worksheet_by_title(node['worksheet_title'])
            wks.update_value((row_to_change,2),balance)
 
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", help="Print results and do not update Google sheet", action="store_true")
    #parser.add_argument("date", nargs="?", help="Get balance for this date, must be format yyyy-mm-dd. Today if not specified")
    args = parser.parse_args()
    main()
