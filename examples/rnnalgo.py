from trader.AlgoManager import *
from trader.Algorithm import *
from keras.models import Sequential
from keras.layers import *
from keras.callbacks import *
from keras.regularizers import l1
import keras.backend as K
import tensorflow as tf
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

class RNN(Algorithm):

	def initialize(self):
		self.securities = ["FB","SVXY","ARKK","NFLX"]
		self.sec = 'SPY'
		self.heldstock = None
		self.signals = []
		self.lastrun = None
		self.benchmark = self.securities
		self.lookback = 3
		self.weights_path = 'rnn_weights.h5'
		# original: LSTM32, Dense128, Dense1
		self.model = Sequential()
		self.model.add(LSTM(32,input_shape=(self.lookback,4),return_sequences=False,dropout=0.2,recurrent_dropout=0.2,kernel_regularizer=l1(0.001),recurrent_regularizer=l1(0.001)))
		self.model.add(Dropout(0.2))
		self.model.add(Dense(128,kernel_regularizer=l1(0.001),activation='relu'))
		self.model.add(Dropout(0.2))
		self.model.add(Dense(1,kernel_regularizer=l1(0.001)))
		try:
			self.model.load_weights(self.weights_path)
		except OSError as err:
			print(err)
		self.model.compile(loss='mean_squared_error',optimizer='adam',metrics=[accuracy])
		self.graph = tf.get_default_graph()
		self.logs = {'signals': np.zeros((0,0)), 'change': np.zeros((0,0)), 'date': np.zeros(0)}
		# Features:
		# percent change * 100
		# (bollinger upper - bollinger lower) / bollinger middle
		# macd hist
		# (2-day rsi) / 100


	def run(self):
		print(self.datetime.strftime("%Y-%m-%d %H:%M:%S"))
		signals = []
		for security in self.securities:
			prediction = self.indicator(security)
			signals.append(prediction[0])
		maxsig = max(signals)
		maxsigstock = self.securities[signals.index(maxsig)]
		if maxsig > 0.4:
			if maxsigstock != self.heldstock:
				self.sellall(verbose=True)
			self.orderpercent(maxsigstock,1,verbose=True,notify_address='acciorocketships@gmail.com')
			self.heldstock = maxsigstock
		elif self.heldstock in self.stocks and signals[self.securities.index(self.heldstock)] < 0.1:
			self.sellall(verbose=True)
			self.heldstock = None
		self.stopsell(maxsigstock,-0.01)
		# Extra GUI Variables
		self.signals = signals
		self.lastrun = self.datetime
		# Logs
		if len(self.logs['signals']) != 0:
			self.logs['change'] = cat(self.logs['change'], [self.percentchange(stock)[0] for stock in self.securities], 0)
		self.logs['signals'] = cat(self.logs['signals'], signals, 0)
		self.logs['date'] = cat(self.logs['date'], prediction._index[0], 0)



	def indicator(self,stock,length=1,skip=-1):
		dataX, _ = self.getdata(stock,length,skip)
		with self.graph.as_default():
			dataY = self.model.predict(dataX)[:,0]
		dates = pd.DatetimeIndex(self.macd(stock,length=skip+length+1)._index[1:length])
		if skip == -1:
			dates = dates.append(pd.DatetimeIndex([self.nexttradingday(self.datetime)[0].strftime('%Y-%m-%d')]))
		dataY = pd.DataFrame({'date':dates,'Predicted Price Change from Previous Day':dataY})
		dataY = dataY.set_index('date')['Predicted Price Change from Previous Day']
		return dataY


	def train(self):
		callbacks = []
		callbacks.append(ModelCheckpoint(self.weights_path, monitor='val_loss', verbose=1, save_best_only=True, save_weights_only=True))
		dataX, dataY = self.getdata("SPY",datapoints=3200,skip=1200)
		dataXval, dataYval = self.getdata("SPY",datapoints=800,skip=400)
		self.model.fit(dataX,dataY,validation_data=(dataXval,dataYval),callbacks=callbacks,epochs=100)
		self.model.save_weights(self.weights_path)


	def test(self,length=10,skip=0):
		predicted = self.indicator(stock="SPY",length=length,skip=skip)
		actual = self.percentchange(stock="SPY",length=length+skip) * 100
		if skip != 0:
			actual = actual[:-skip]
		errors = np.absolute(predicted - actual)
		mean = np.mean(errors)
		std = np.std(errors)
		plt.hold(True)
		t = np.linspace(1,length,length)
		correct = (actual * predicted) > 0
		for i in range(predicted.shape[0]):
			plt.plot([t[i],t[i]],[predicted[i],actual[i]],'c')
		plt.plot(t,predicted,'go')
		plt.plot(t[correct],predicted[correct],'b.')
		plt.plot(t,actual,'r.')
		plt.plot(np.array([0,length]),np.array([0,0]))
		plt.title('Accuracy: ' + str(float(predicted[correct].shape[0])/float(predicted.shape[0])) + \
				  ',  Mean Error: ' + str(round(mean,2)) + ',  Std Dev Error: ' + str(round(std,2)))
		plt.ylabel('SPY Percent Change')
		plt.xlabel('Green: Predicted, Red: Actual')
		plt.show()


	def getdata(self,stock,datapoints=1,skip=0):
		# returns tuple (inputs, resulting next day price change)
		# datapoints: number of time steps
		# skip: number of most recent datapoints to skip 
		# (if -1, then the last element in dataX is the most recent data for the stock and dataY is NaN)
		percchange = self.percentchange(stock,length=skip+datapoints+self.lookback)
		bollinger = self.bollinger(stock,length=skip+datapoints+self.lookback)
		macd = self.macd(stock,length=skip+datapoints+self.lookback)
		rsi2 = self.rsi(stock,mawindow=2,length=skip+datapoints+self.lookback)
		dataX = []
		dataY = []
		for i in range(datapoints):
			dataX.append(self.formatdata(percchange[i:i+self.lookback],
										 bollinger[i:i+self.lookback],
										 macd[i:i+self.lookback],
										 rsi2[i:i+self.lookback]))
			if i+self.lookback < len(percchange):
				dataY.append(percchange[i+self.lookback] * 100)
			else:
				dataY.append(np.nan)
		dataX = np.array(dataX)
		dataY = np.array(dataY)
		return (dataX, dataY)


	def formatdata(self,percchange,bollinger,macd,rsi2):
		percchange = percchange * 100
		volatility = (bollinger['Real Upper Band'] - bollinger['Real Lower Band']) / bollinger['Real Middle Band']
		rsi2 /= 100
		data = np.concatenate((np.expand_dims(percchange,axis=1),
							   np.expand_dims(volatility,axis=1),
							   np.expand_dims(macd,axis=1),
							   np.expand_dims(rsi2,axis=1)),axis=1)
		return data



def accuracy(y_true,y_pred):
	return K.sum(tf.to_float(K.equal(K.sign(y_true),K.sign(y_pred)))) / tf.to_float(tf.shape(y_true)[0])

def train():
	algo = RNN()
	algo.train()

def test():
	algo = RNN()
	algo.test(length=20,skip=0)

def predict():
	algo = RNN()
	print("Percent Change Today: ", algo.indicator("SPY",length=2,skip=-1))

def backtest():
	algo = backtester(RNN(),capital=1000)
	Manager.algogui(algo)
	algo.startbacktest()
	import code; code.interact(local=locals())

def debug():
	algo = backtester(RNN())
	algo.datetime = datetime(2018,3,27)
	import code; code.interact(local=locals())

if __name__ == '__main__':
	backtest()

def cat(array,value,dim=0):
	for i in range(len(array.shape) - len(np.array(value).shape)):
		value = [value]
	if len(array) != 0:
		array = np.append(array,value,dim)
	else:
		array = np.array(value)
	return array
		
