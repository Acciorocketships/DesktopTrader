import unittest
from trader.Algorithm import Algorithm
from wrapt_timeout_decorator import timeout
from trader.Util import *

class AlgorithmTest(unittest.TestCase):
	def setUp(self):
		self.algo = Algorithm()

class DataRetrievalTest(AlgorithmTest):

	@timeout(60)
	def test_history(self):
		length = 20
		data = self.algo.history("SPY", length=length, datatype='close', interval='day')
		actual_index = (pd.to_datetime(data.index).tz_convert(None) - pd.Timedelta(hours=4)).to_pydatetime()
		enddate = getdatetime()
		startdate = tradingdays(start=length,end=enddate)
		expected_index = np.array(tradingdays(start=startdate, end=actual_index[-1]))
		assert not (np.isnan(data).any())
		assert actual_index.size == expected_index.size
		assert (actual_index == expected_index).all()

	# @timeout(600)
	# def test_history(self):
	# 	length = 20
	# 	data = self.algo.history("SPY", length=length, datatype='close', interval='minute')
	# 	actual_index = (pd.to_datetime(data.index).tz_convert(None) - pd.Timedelta(hours=4)).to_pydatetime()
	# 	print(tradingdays(start=length,end=self.algo.algodatetime()))
	# 	print(self.algo.algodatetime())
	# 	print(actual_index[0])
	# 	print(actual_index[-1])
		
   