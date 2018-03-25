import os, sys
sys.path.append(os.path.dirname(os.path.realpath("")))
from AlgoManager import *
from keras.models import Sequential
from keras.layers import *
from keras.callbacks import *
from keras.regularizers import l1
import keras.backend as K
import matplotlib.pyplot as pyplot

class RNN(Algorithm):

	def initialize(self):
		self.securities = ['QQQ','FB','WMT','MSFT']
		self.sec = 'QQQ'
		self.benchmark = self.sec
		self.lookback = 3
		self.weights_path = 'rnn_weights.h5'
		# original: LSTM32, Dense128, Dense1
		self.model = Sequential()
		self.model.add(LSTM(16,input_shape=(self.lookback,5),dropout=0.2,recurrent_dropout=0.2,kernel_regularizer=l1(0.001),recurrent_regularizer=l1(0.001)))
		self.model.add(Dropout(0.2))
		self.model.add(LSTM(32,input_shape=(self.lookback,5),dropout=0.2,recurrent_dropout=0.2,kernel_regularizer=l1(0.001),recurrent_regularizer=l1(0.001)))
		self.model.add(Dropout(0.2))
		self.model.add(Dense(1,kernel_regularizer=l1(0.001)))
		try:
			self.model.load_weights(self.weights_path)
		except OSError as err:
			print(err)
		self.model.compile(loss='mean_squared_error',optimizer='adam',metrics=[])
		# percent change * 100
		# (bollinger upper - bollinger lower) / bollinger middle
		# macd hist
		# d/dt (14-day rsi) / 100
		# ((2-day rsi) - 50) / 100


	def run(self):
		signals = []
		for security in self.securities:
			print(security)
			signals.append(self.indicator(security))
		maxsig = max(signals)
		maxsigstock = self.securities[signals.index(maxsig)]
		pass


	def indicator(self,stock,length=1):
		dataX, _ = self.getdata(stock,length)
		return self.model.predict(dataX)


	def getdata(self,stock,datapoints=1,skip=-1):
		# returns tuple (inputs, resulting next day price change)
		# datapoints: number of time steps
		# skip: number of most recent datapoints to skip 
		# (if -1, then the last element in dataX is the most recent data for the stock and dataY is NaN)
		percchange = self.percentchange(stock,length=skip+datapoints+self.lookback)
		bollinger = self.bollinger(stock,length=skip+datapoints+self.lookback)
		macd = self.macd(stock,length=skip+datapoints+self.lookback)
		rsi2 = self.rsi(stock,mawindow=2,length=skip+datapoints+self.lookback)
		rsi14 = self.rsi(stock,mawindow=14,length=skip+datapoints+self.lookback)
		dataX = []
		dataY = []
		for i in range(datapoints):
			dataX.append(self.formatdata(percchange[i:i+self.lookback],
										 bollinger[i:i+self.lookback],
										 macd[i:i+self.lookback],
										 rsi2[i:i+self.lookback],
										 rsi14[i:i+self.lookback]))
			if i+self.lookback < len(percchange):
				dataY.append(percchange[i+self.lookback])
			else:
				dataY.append(np.nan)
		dataX = np.array(dataX)
		dataY = np.array(dataY)
		return (dataX, dataY)


	def formatdata(self,percchange,bollinger,macd,rsi2,rsi14):
		percchange = percchange * 100
		volatility = (bollinger['Real Upper Band'] - bollinger['Real Lower Band']) / bollinger['Real Middle Band']
		rsi2 /= 100
		ddtrsi14 = rsi14.diff() / 100
		ddtrsi14[0] = 0
		data = np.concatenate((np.expand_dims(percchange,axis=1),
							   np.expand_dims(volatility,axis=1),
							   np.expand_dims(macd,axis=1),
							   np.expand_dims(rsi2,axis=1),
							   np.expand_dims(ddtrsi14,axis=1)),axis=1)
		return data


if __name__ == '__main__':
	algo = RNN()
	#algo.getdata('SPY',10,0)
	algo.getdata('SPY')
		
