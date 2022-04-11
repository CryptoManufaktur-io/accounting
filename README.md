# Chainlink accounting data collection

## Overview

Gets balances from chainlink node addresses and payment to admin addresses / hot wallets, and enters those into a Google sheet.

Expected to be run from crontab at 23:59 UTC each day.

Written to work with a specific sheet layout.

## Configuration

`./config/config.toml` should hold the configuration, see `./sample-config/config.toml`

The credentials for the Google Sheets API are in `./config/gc-credentials.json`. Make sure to share the Sheet with the credentials you create.
