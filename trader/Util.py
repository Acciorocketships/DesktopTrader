import pickle
import shelve
import datetime
from typing import *
from trader.Setup import *
from trader.Algorithm import *


def savestate(local={}, path='savestate'):
	shelf = shelve.open(path, flag='n')
	for key in globals().keys():
	    try:
	        shelf['G'+key] = globals()[key]
	    except (TypeError, pickle.PicklingError) as err:
	        logging.debug(err)
	for key in local.keys():
	    try:
	        shelf['L'+key] = local[key]
	    except (TypeError, pickle.PicklingError) as err:
	        logging.debug(err)
	shelf.close()
	logging.info('Saved State')


def loadstate(path='savestate'):
	if not os.path.exists(path + ".db"):
		logging.info('Failed to Load State')
		return {}
	shelf = shelve.open(path, flag='c')
	local = {}
	for key in shelf:
		try:
			isglobal = (key[0] == 'G')
			varname = key[1:]
			if isglobal:
				globals()[varname] = shelf[key]
			else:
				local[varname] = shelf[key]
		except Exception as err:
			logging.debug(err)
	shelf.close()
	logging.info('Successfully Loaded State')
	return local

def getdatetime() -> datetime.datetime:
	return datetime.datetime.now(timezone('US/Eastern')).replace(tzinfo=None)


# If start and end are both dates, it returns a list of trading days from the start date to the end date (not including end date)
# If start is a date and end is an int, it returns the date that is end days after start
# If start is an int and end is a date, it returns the date that is start days before end
def tradingdays(start:Union[Date,Sequence[int],str,int]=getdatetime(), 
				end:Union[Date,Sequence[int],str,int]=1):

	# Convert Date Datatypes
	if isinstance(start, str):
		start = tuple([int(x) for x in start.split("-")])
	if isinstance(end,str):
		end = tuple([int(x) for x in end.split("-")])
	if isinstance(start,list) or isinstance(start,tuple):
		start = datetime.date(start[0], start[1], start[2])
	if isinstance(end,list) or isinstance(end,tuple):
		end = datetime.date(end[0], end[1], end[2])
	start = cast(Date, start)
	end = cast(Date, end)

	if isinstance(start,int) and isinstance(end,int):
		raise TypeError("Either start or end must be a date")

	# Range of Dates
	if isdate(start) and isdate(end):
		datelist = [day.date.to_pydatetime() for day in API.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))]
		return datelist

	# n Days Before End
	if isinstance(start,int) and isdate(end):
		n = start
		start = end - datetime.timedelta(days=2*n)
		datelist = API.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))
		date = datelist[-n].date.to_pydatetime()
		return date

	# n Days After Start
	if isdate(start) and isinstance(end,int):
		n = end
		end = start + datetime.timedelta(days=2*n+5)
		datelist = API.get_calendar(start = start.strftime("%Y-%m-%d"), end = end.strftime("%Y-%m-%d"))
		date = datelist[n].date.to_pydatetime()
		return date


# Determines if variable is a datetime.datetime or datetime.date object
def isdate(var:Any) -> bool:
	return isinstance(var,datetime.datetime) or isinstance(var,datetime.date)


def datetimeequals(dt1:Union[datetime.datetime,datetime.date,datetime.time], 
				   dt2:Union[datetime.datetime,datetime.date,datetime.time]) -> bool:
	# get date and time for each input
	dt1date = None
	dt1time = None
	dt2date = None
	dt2time = None
	if isinstance(dt1, datetime.datetime):
		dt1date = dt1.date()
		dt1time = dt1.time()
	elif isinstance(dt1, datetime.date):
		dt1date = dt1
	elif isinstance(dt1, datetime.time):
		dt1time = dt1
	if isinstance(dt2, datetime.datetime):
		dt2date = dt2.date()
		dt2time = dt2.time()
	elif isinstance(dt2, datetime.date):
		dt2date = dt2
	elif isinstance(dt2, datetime.time):
		dt2time = dt2
	# if all trailing values of one time are 0, then truncate the other time as well
	# that way, 4:30 == 4:30:16:725650
	if dt1time is not None and dt2time is not None:
		if dt1time.second == 0 and dt1time.microsecond == 0:
			dt2time = dt2time.replace(second=0, microsecond=0)
		if dt2time.second == 0 and dt2time.microsecond == 0:
			dt1time = dt1time.replace(second=0, microsecond=0)
		if dt1time.microsecond == 0:
			dt2time = dt2time.replace(microsecond=0)
		if dt2time.microsecond == 0:
			dt1time = dt1time.replace(microsecond=0)
	# if only one date is provided or the dates do not match, they are not equal
	if dt1date != dt2date:
		return False
	# only fail if both times are given and they don't match. 
	if (dt1time is not None) and (dt2time is not None) and (dt1time != dt2time):
		return False
	return True


# Returns the list of datetime objects associated with the entries of a pandas dataframe
def dateidxs(arr:Union[pd.DataFrame,pd.Series]):
	try:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iterrows()]
	except:
		return [pd.to_datetime(item[0]).replace(tzinfo=None).to_pydatetime() for item in arr.iteritems()]


# Returns the index of the nearest element in dateidxs that occured before (or at the same time) as time.
# If lastchecked==None: Searches backward from the most recent entries
# If lastchecked>=0: Searches forward starting at lastchecked
# If lastchecked<0: Searches backward starting at -lastchecked
def nearestidx(startdate:Date, dateidx:List[Date], lastchecked:Optional[int]=None):
	if lastchecked is None:
		for i in range(len(dateidx)):
			index = len(dateidx) - i - 1
			if dateidx[index] <= startdate:
				return index
	elif lastchecked >= 0:
		for i in range(len(dateidx)):
			index = (lastchecked + i - 5) % len(dateidx)
			if dateidx[index] > startdate:
				return index-1
		return len(dateidx)-1
	else:
		for i in range(len(dateidx)):
			index = (len(dateidx) - lastchecked - i) % len(dateidx)
			if dateidx[index] <= startdate:
				return index
	logging.error("Datetime %s not found in historical data.", startdate)


# Returns the difference of the indexes of startdate and currentdateidx in dateidxs
# startdate: datetime in the past
# currentdateidx: idx of current date in dateidxs (datetime also accepted) (If None given, it will default to the last value)
# dateidx: list of datetimes (original pandas dataframe also accepted)
def datetolength(startdate:Date, dateidx:Union[List[Date],pd.DataFrame,pd.Series], currentdateidx:Optional[Union[Date,int]]=None):
	if isinstance(dateidx,pd.DataFrame) or isinstance(dateidx,pd.Series):
		dateidx = dateidxs(dateidx)
	if isdate(currentdateidx):
		currentdateidx = cast(Date, currentdateidx)
		currentdateidx = nearestidx(currentdateidx, dateidx)
	if currentdateidx is None:
		currentdateidx = len(dateidx)-1
	assert isinstance(currentdateidx, int)
	return currentdateidx - nearestidx(startdate, dateidx, lastchecked=-currentdateidx) + 1


# Converts a dictionary to a string
def dict2string(dictionary:Dict[Any,Any], spaces:int=0):
	string = ""
	if type(dictionary) == dict:
		for (key,value) in dictionary.items():
			if type(value) != dict and type(value) != list:
				string += (" " * spaces*4) + str(key) + " - " + str(value) + "\n"
			else:
				string += (" " * spaces*4) + str(key) + " - \n"
				string += dict2string(value,spaces+1)
	elif type(dictionary) == list:
		for item in dictionary:
			string += dict2string(item,spaces+1)
	else:
		string += (" " * spaces*4) + str(dictionary) + "\n"
	return string


# Input: stock symbol as a string, number of shares as an int
# ordertype: "market", "limit", "stop", "stop_limit"
def buy(stock:str, amount:int, ordertype:str='market', stop:Optional[float]=None, limit:Optional[float]=None, block:bool=True):
	if BROKER == 'alpaca':
		order = API.submit_order(stock, amount, side='buy', type=ordertype, time_in_force='day', limit_price=limit, stop_price=stop)
		if block:
			starttime = getdatetime()
			while (order.filled_at is None) and ((getdatetime()-starttime).seconds < 60):
				order = API.get_order(order.id)
				time.sleep(0.1)
		return order


# Input: stock symbol as a string, number of shares as an int
# ordertype: "market", "limit", "stop", "stop_limit"
def sell(stock:str, amount:int, ordertype:str='market', stop:Optional[float]=None, limit:Optional[float]=None, block:bool=True):
	if BROKER == 'alpaca':
		order = API.submit_order(stock, amount, side='sell', type=ordertype, time_in_force='day', limit_price=limit, stop_price=stop)
		if block:
			starttime = datetime.datetime.now()
			while (order.filled_at is None) and ((datetime.datetime.now()-starttime).seconds < 60):
				order = API.get_order(order.id)
				time.sleep(0.1)
		return order


# Input: stock symbol as a string
# Returns: share price as a float
def price(stock:str):
	if BROKER == 'alpaca':
		for n in range(10):
			try:
				cost = float(API.polygon.last_trade(stock).price)
				return cost
			except Exception as e:
				logging.debug(e)
				if n == 9:
					raise RuntimeError(e)
				time.sleep(2**n)


# Returns: list of ("symbol",amount)
def positions():
	
	positions = {}
	
	if BROKER == 'alpaca':
		poslist = API.list_positions()
		for pos in poslist:
			positions[pos.symbol] = int(pos.qty)
	
	return positions


# Returns dictionary of
	# "value": total portfolio value as a float
	# "cash": portfolio cash as a float
	# "daychange": current day's fraction portfolio value change as a float
def portfoliodata():
	
	portfolio = {}

	if BROKER == 'alpaca':
		portfolio["value"] = float(ACCOUNT.portfolio_value)
		portfolio["cash"] = float(ACCOUNT.buying_power)
	
	portfolio["value"] = round(portfolio["value"],2)
	portfolio["cash"] = round(portfolio["cash"],2)
	return portfolio



# TODO
# check that passing date as length to technical indicators yields the desired length
# Add unit tests / integration tests
# automatically do stoploss for backtest orders if they specify that in ordertype in order
# get rid of logging='day' or 'minute'
# change printing to logging
# rethink init and init input values for Algorithm And BacktestAlgorithm.
# fix error 429 in google trends function
# fix backtest running to enddate of current day even if trading hasn't started yet
# create setup file with logging and credentials setup
# group variables in Algorithm into dicts with names that wont be overridden