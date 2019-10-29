import datetime
import pkg_resources
import json
from pytrends.request import TrendReq # Google Searches
import alpaca_trade_api as tradeapi
import logging
from typing import *
Date = Union[datetime.datetime, datetime.date] # Datetime Type

PAPERTRADE = True
BROKER = "alpaca"

# Get Credentials
CREDS:Dict[str,str] = {}
credential_file = pkg_resources.resource_filename(__name__, "creds.txt")
try:
	with open(credential_file, "r") as f:
		CREDS = json.load(f)
except IOError:
	CREDS['Email Address'] = input('Email Address: ')
	CREDS['Email Password'] = input('Email Password: ')
	if BROKER == 'alpaca':
		CREDS['Alpaca ID'] = input('Alpaca ID: ')
		CREDS['Alpaca Secret Key'] = input('Alpaca Secret Key: ')
		CREDS['Alpaca Paper ID'] = input('Alpaca ID: ')
		CREDS['Alpaca Paper Secret Key'] = input('Alpaca Secret Key: ')
	with open(credential_file, "w") as f:
		json.dump(CREDS,f)
except PermissionError:
	logging.error("Inadequate permissions to read credentials file.")
	exit(-1)

# Set Up Alpaca API
if BROKER == 'alpaca':
	API = tradeapi.REST(CREDS['Alpaca ID'] if not PAPERTRADE else CREDS['Alpaca Paper ID'], 
						CREDS['Alpaca Secret Key'] if not PAPERTRADE else CREDS['Alpaca Paper Secret Key'],
						base_url='https://api.alpaca.markets' if not PAPERTRADE else 'https://paper-api.alpaca.markets', 
						api_version='v2')
	ACCOUNT = API.get_account()
	# import pdb; pdb.set_trace()

# Google Trends API
PYTRENDS = TrendReq(hl='en-US', tz=360)

# Set Up Logging
logging.basicConfig(format='%(levelname)-7s: %(asctime)-s | %(message)s', 
					filename='logs.log', 
					datefmt='%d-%m-%Y %I:%M:%S %p',
					level=logging.INFO)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)