import urllib.request, urllib.parse, urllib.error,urllib.request,urllib.error,urllib.parse,json,re,datetime,sys,http.cookiejar
from pyquery import PyQuery





class Tweet:

	def __init__(self):
		pass

class TweetCriteria:

	def __init__(self):
		self.maxTweets = 0

	def setUsername(self, username):
		self.username = username
		return self

	def setSince(self, since):
		self.since = since
		return self

	def setUntil(self, until):
		self.until = until
		return self

	def setQuerySearch(self, querySearch):
		self.querySearch = querySearch
		return self

	def setMaxTweets(self, maxTweets):
		self.maxTweets = maxTweets
		return self

	def setLang(self, Lang):
		self.lang = Lang
		return self

	def setTopTweets(self, topTweets):
 		self.topTweets = topTweets
 		return self





class TweetManager:
	
	def __init__(self):
		pass
		
	@staticmethod
	def getTweets(tweetCriteria, receiveBuffer=None, bufferLength=100, proxy=None):
		refreshCursor = ''
	
		results = []
		resultsAux = []
		cookieJar = http.cookiejar.CookieJar()

		active = True

		while active:
			json = TweetManager.getJsonReponse(tweetCriteria, refreshCursor, cookieJar, proxy)
			if len(json['items_html'].strip()) == 0:
				break

			refreshCursor = json['min_position']
			scrapedTweets = PyQuery(json['items_html'])
			#Remove incomplete tweets withheld by Twitter Guidelines
			scrapedTweets.remove('div.withheld-tweet')
			tweets = scrapedTweets('div.js-stream-tweet')
			
			if len(tweets) == 0:
				break
			
			for tweetHTML in tweets:
				tweetPQ = PyQuery(tweetHTML)
				tweet = Tweet()
				
				usernameTweet = tweetPQ("span.username.js-action-profile-name b").text()
				txt = re.sub(r"\s+", " ", tweetPQ("p.js-tweet-text").text().replace('# ', '#').replace('@ ', '@'))
				retweets = int(tweetPQ("span.ProfileTweet-action--retweet span.ProfileTweet-actionCount").attr("data-tweet-stat-count").replace(",", ""))
				dateSec = int(tweetPQ("small.time span.js-short-timestamp").attr("data-time"))
				urls = []
				for link in tweetPQ("a"):
					try:
						urls.append((link.attrib["data-expanded-url"]))
					except KeyError:
						pass

				
				tweet.text = txt
				tweet.user = usernameTweet
				tweet.date = datetime.datetime.fromtimestamp(dateSec)
				tweet.retweets = retweets
				tweet.hashtags = " ".join(re.compile('(#\\w*)').findall(tweet.text))
				tweet.urls = ",".join(urls)
				
				results.append(tweet)
				resultsAux.append(tweet)
				
				if receiveBuffer and len(resultsAux) >= bufferLength:
					receiveBuffer(resultsAux)
					resultsAux = []
				
				if tweetCriteria.maxTweets > 0 and len(results) >= tweetCriteria.maxTweets:
					active = False
					break
					
		
		if receiveBuffer and len(resultsAux) > 0:
			receiveBuffer(resultsAux)
		
		return results
	
	@staticmethod
	def getJsonReponse(tweetCriteria, refreshCursor, cookieJar, proxy):
		url = "https://twitter.com/i/search/timeline?f=tweets&q=%s&src=typd&%smax_position=%s"
		
		urlGetData = ''
		if hasattr(tweetCriteria, 'username'):
			urlGetData += ' from:' + tweetCriteria.username
			
		if hasattr(tweetCriteria, 'since'):
			urlGetData += ' since:' + tweetCriteria.since
			
		if hasattr(tweetCriteria, 'until'):
			urlGetData += ' until:' + tweetCriteria.until
			
		if hasattr(tweetCriteria, 'querySearch'):
			urlGetData += ' ' + tweetCriteria.querySearch
			
		if hasattr(tweetCriteria, 'lang'):
			urlLang = 'lang=' + tweetCriteria.lang + '&'
		else:
			urlLang = ''
		url = url % (urllib.parse.quote(urlGetData), urlLang, refreshCursor)
		#print(url)

		headers = [
			('Host', "twitter.com"),
			('User-Agent', "Mozilla/5.0 (Windows NT 6.1; Win64; x64)"),
			('Accept', "application/json, text/javascript, */*; q=0.01"),
			('Accept-Language', "de,en-US;q=0.7,en;q=0.3"),
			('X-Requested-With', "XMLHttpRequest"),
			('Referer', url),
			('Connection', "keep-alive")
		]

		if proxy:
			opener = urllib.request.build_opener(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}), urllib.request.HTTPCookieProcessor(cookieJar))
		else:
			opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookieJar))
		opener.addheaders = headers

		try:
			response = opener.open(url)
			jsonResponse = response.read()
		except:
			#print("Twitter weird response. Try to see on browser: ", url)
			print("Twitter weird response. Try to see on browser: https://twitter.com/search?q=%s&src=typd" % urllib.parse.quote(urlGetData))
			print("Unexpected error:", sys.exc_info()[0])
			sys.exit()
			return
		
		dataJson = json.loads(jsonResponse.decode())
		
		return dataJson		
