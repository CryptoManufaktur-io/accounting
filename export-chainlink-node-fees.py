#!/usr/bin/env python3
# Gets node fees recorded in Google Sheet by get-chainlink-activity.py
# and writes them into CSVs suitable for use with CryptoTaxCalculator.io
import argparse
import pygsheets
from datetime import datetime, date, timedelta
from time import sleep, mktime
import csv
import toml
from dateutil.parser import parse

# Assumes that google sheet credentials are in ./config/gc-credentials.json

def main():
    startdate = parse(args.startdate)
    enddate = parse(args.enddate)
    config = toml.load("./config/config.toml")
    # Google Sheets
    year = datetime.utcnow().strftime("%Y")
    gc = pygsheets.authorize(service_file='./config/gc-credentials.json')
    sh = gc.open(config['sheet']+" "+year)

# Each worksheet has date, time, balance, funding, fee burn
# The advanced import is timestamp, type, base currency, base amount, quote currency, quote amount, fee currency, fee amount, from, to, blockchain, ID, Description
# I need timestamp, type, base currency, base amount, blockchain, description
    node_list = config['nodes']
    for entry in node_list:
        node = node_list[entry]
        if args.sheet and node['worksheet_title'] != args.sheet:
            continue
        chain = node['chain']
        match chain:
            case "binance":
                export_chain = "Binance"
                export_coin = "BNB"
            case "ethereum" | "ethereum_rpl" | "ethereum_lido" | "ethereum_ssv":
                export_chain = "Ethereum"
                export_coin = "ETH"
            case "polygon":
                export_chain = "Polygon"
                export_coin = "MATIC"
            case "optimism":
                export_chain = "Optimism"
                export_coin = "ETH"
            case "fantom":
                export_chain = "Fantom"
                export_coin = "FTM"
            case "huobi":
                export_chain = None
                export_coin = "HT"
            case "metis":
                export_chain = None
                export_coin = "Metis"
            case "moonriver":
                export_chain = None
                export_coin = "MOVR"
            case "solana":
                export_chain = Solana
                export_coin = "SOL"
            case _:
                return "Unknown chain, don't know how to export"

        csv_filename = "./" + node['worksheet_title'] + "-CTC Export-" + startdate.strftime("%Y-%m-%d") + "-to-" + enddate.strftime("%Y-%m-%d") + ".csv"
        wks = sh.worksheet_by_title(node['worksheet_title'])
        df = wks.get_as_df()
        data = wks.get_all_values()
        data.pop(0)
        export = [["Timestamp (UTC)","Type","Base Currency","Base Amount","Quote Currency (Optional)","Quote Amount (Optional)","Fee Currency (Optional)","Fee Amount (Optional)","From (Optional)","To (Optional)","Blockchain (Optional)","ID (Optional)","Description (Optional)"]]
        export_idx = {'Timestamp':0,'Type':1,'Base':2,'Amount':3,'To':9,'Blockchain':10,'Description':12}
        for row in data:
            if not row[0]: # End of the sheet data or empty row ... erring on side of empty
                continue
            timestamp = parse(row[0])
            if timestamp >= startdate and timestamp <= enddate and row[4] != 0:
                timestamp += timedelta(hours=23, minutes=59)
                export_row = [None]*13
                export_row[export_idx['Timestamp']] = timestamp.strftime("%Y-%m-%d %H:%M:%S")
                export_row[export_idx['Type']] = "fee"
                export_row[export_idx['Base']] = export_coin
                export_row[export_idx['Amount']] = row[4]
                export_row[export_idx['To']] = "Chainlink Operations"
                export_row[export_idx['Blockchain']] = export_chain
                export_row[export_idx['Description']] = "Gas fees"
                export.append(export_row)
        with open(csv_filename, 'w') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerows(export)
            print("Data in ",node['worksheet_title']," exported to ",csv_filename)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(epilog="Sheet names for the nodes are defined in config/config.toml, and shared with get-chainlink-activity.py\nExported CSV files can be loaded into CryptoTaxCalculator and only contain fees, not funding", \
            formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("startdate", help="Start date to export data from, format YYYY-mm-dd")
    parser.add_argument("enddate", help="End date to export data until, format YYYY-mm-dd")
    parser.add_argument("sheet", nargs="?", help="Sheet name to export. If left blank, all will be")
    args = parser.parse_args()
    main()
