import unittest
from trader.Algorithm import Algorithm
from wrapt_timeout_decorator import timeout

class AlgorithmTest(unittest.TestCase):
	def setUp(self):
		self.algo = Algorithm()

class DataRetrievalTest(AlgorithmTest):

	@timeout(60)
	def testHistory(self):
		length = 100
		data = self.algo.history("SPY", length=length, datatype='close', interval='day')
		assert data.size==length
		
	   