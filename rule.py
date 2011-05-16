#!/usr/bin/env python2.7
#coding: utf-8
'''
Created on 2011-5-16

@author: zeroq
'''
import aituans
import bson
from BeautifulSoup import BeautifulSoup;
import codecs
import os
import pickle
import re
import sys
import time
import urllib2

LOGGER = aituans.initLogger("parser")

def parser(site, db):
	"""
	启动一个分析器
	"""
	try:
		site_handle = globals()[site['class']](site, db)
		site_handle.find_product_from_files();
	except Exception, e:
		pass
	return


class ParserBase(object):
	meta = {} # 配置参数
	logger = None # 日志对象
	handler = None # 日志句柄
	title = None # 标题
	market_price = 0.00 # 市场价
	discount = 0.00 # 折扣
	price = 0.00 # 售价
	cover = None # 封面图片地址
	desc = None # 描述
	endtime = 0 # 结束时间
	tag = [] # 标签
	company = None # 商户名称
	buys = 0 # 已购买人数
	url = None # 地址
	addtime = 0 # 添加日期
	site = None # 站点名称

	def __init__(self, site):
		global LOGGER
		if len(site) == 0:
			return
		self.meta = site
		self.meta['db'] = aituans.mongodbConnection()
		self.meta['db'].authenticate("aituans", "qazwsxedc!@#123")
		self.logger = LOGGER
		return;
	
	def getFiles(self):
		"""
		返回站点下所有采集到的网页的文件名列表
		"""
		dir = "%s/page/%s/" % (aituans.ROOT_PATH, self.meta['domain'])
		try:
			files = os.listdir(dir)
		except Exception, e:
			self.logger[0].error("[parser]文件夹不存在，无法载入文件列表%s" % (e))
			return False
		file_list = []
		for file in files:
			file_path = "%s/page/%s/%s" % (aituans.ROOT_PATH, self.meta['domain'], file)
			if not os.path.isfile(file_path):
				continue
			if file == "." or file == "..":
				continue
			# 生成一个文件列表
			file_list.append(file_path)
		return file_list

	def getPageContentFromFile(self, file_name):
		'''
		取得文件内容，返回一个网页URL、分析器CLASS名称、SITE_NAME, 网页内容组成的字典
		'''
		if os.path.isfile(file_name) == False:
			return False
		try:
			file = codecs.open(file_name, "r", "utf-8")
			url = file.readline()
			classs = file.readline()
			site_name = file.readline()
			page_data = file.readline()
			file.close()
		except Exception, e:
			self.logger[0].error(u"[parser]读取URL文件内容时出错: %s" % ( e))
			return False
		del site_name, classs
		return (url, page_data)

	def isChinese(self, uchar):
		"""判断一个unicode是否是汉字"""
		if uchar >= u'\u4e00' and uchar<=u'\u9fa5':
			return True
		else:
			return False

	def replaceString(self, str):
		return str.replace(u"【", '').replace(u"】", '').replace(u"！", '').replace(u"，", '').replace(u"、", '').replace(u"）", '').replace(u"（", '').replace(u"”", '').replace(u"“", '')

	
	def words(self, str):
		"""
		将字符串进行二元切分，得出最大匹配值
		"""
		str = self.replaceString(str)
		lens = len(str)
		start = 0
		words = []
		while True:
			if start > lens:
				break
			end = start + 1
			k = 0
			while True:
				if end > lens:
					break
				if k > 6:
					break;
				word = str[start:end]
				k = k + 1
				words.append(word)
				end = end + 1
			start = start + 1
		return words

	def getAttrs(self):
		"""
		得到产品的属性列表
		"""
		attrs = self.__dict__
		attrs_list = []
		for key in attrs:
			if key in ['__doc__',  '__module__', 'meta', 'logger', 'handler']:
			#if key == '__doc__' or key == '__module__' or key == 'meta' or key == 'logger' or key == 'handler':
				continue
			attrs_list.append(key)
		del attrs
		del key
		return attrs_list

	def save(self):
		try:
			param = self.getAttrs()
			# 判断是否存在这条记录
			products = self.db.products
			cursor = products.find_one({"title": param['title']})
			if cursor == None:
				products.insert(param)
		except Exception, e:
			self.logger[0].error(u"[parser]入库出错:%s" % e)
			pass
		return

	def findProductFromFile(self):
		"""
		从文件内容中匹配出产品信息，如果一个文件无法匹配所有的必须规则，则说明该页面不是一个产品页面，自动忽略
		"""
		files = self.getFiles()
		_count = 0
		for file in files:
			data = self.getPageContentFromFile(file)
			if data == False:
				continue
			# 更新old.urls
			aituans.updateOldUrls(data[0])
			try:
				os.unlink(file)
			except Exception, e:
				self.logger[0].error(u"删除网页内容文件失败:%s" % e)
				pass
			try:
				self.meta['soup'] = BeautifulSoup(data[1])
			except Exception, e:
				self.logger[0].error(u"BeautifulSoup解析错误:%s" % e)
				continue
			if self.parse(data[0]) == False:
				# 解析失败，可能不是产品页面
				continue
			self.save()
			# 删除产品页面
			_count = _count + 1
		self.logger[0].info(u"扫描完成！共入库%d个产品" % (_count))
		return
	
	def update_buys(self, product_data, db, col):
		page_data = aituans.httpGetUrlContent(product_data['url'])
		self.meta['soup'] = BeautifulSoup(page_data)
		try:
			self.parseBuys()
			# 更新数据库
			product_data['buys'] = self.buys
			col.update({"_id":bson.objectid.ObjectId(product_data['_id'])}, product_data)
		except:
			return False
		return True
	
	def parse(self, url = None):
		try:
			self.parseUrl(url)
			self.parseAddtime()
			self.parseSite()
			self.parseTitle()
			self.parseArea()
			self.parseMarkePrice()
			self.parseDiscount()
			self.parsePrice()
			self.parseCover()
			self.parseDesc()
			self.parseEndtime()
			self.parseCompany()
			self.parseTag()
			self.parseBuys()
		except Exception, e:
			self.logger[0].error(u"[parser]分析页面内容失败: %s %s %s" % (self.meta['name'], url, e))
			return False
		return True

	def testParse(self, url):
		the_data = self.get_page(url)
		if the_data == False:
			return False
		self.meta = {"name":"test", "domain":"test.com.cn", "url":"test.com.cn/test", "area":"Beijing", "class":"testclass"}
		self.meta['soup'] = BeautifulSoup(the_data)
		try:
			self.parse()
		except:
			return False
		return self.get_attrs()
	
	def parseAddtime(self):
		self.addtime = int(time.time())
		return True
	
	def parseSite(self):
		self.site = self.meta['name']
		return True
	
	def parseUrl(self, url):
		if url == None:
			return False
		self.url = url
		return True
	def parseTag(self):
		self.tag = self.words(self.title)
		return True
	
	def parseTitle(self):
		self.title = self.meta['soup'].find('h1').text
		return True
	
	def parseArea(self):
		return True
	
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('table').findAll('td')[0].text.replace(u'￥', ''))
		return True
	
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('table').findAll('td')[1].text.replace(u'折', ''))
		return True
	
	def parsePrice(self):
		return True
	
	def parseCover(self):
		return True
	
	def parseDesc(self):
		self.desc = ""
		return True
	
	def parseEndtime(self):
		return True
	
	def parseCompany(self):
		self.company = ""
		return True
	
	def parseBuys(self):
		return True

class manzuo(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"当日精选", "").replace(u"：", "")
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'city'}).h3.span.text
		return True
	def parseMarketPrice(self):
		self.market_price = super(manzuo, self).parseMarketPrice().replace(u'元', '')
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'buy pngFix'}).p.span.text)
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', id="mainImgSlideShow").img['src']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'con_ltmrmore'})
		return True
	def parseEndtime(self):
		self.endtime = int(self.meta['soup'].find('input', attrs={"id":"TimeCounter"})['value'][:-3])
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'area'}).h2.text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('span', id='currentdealcountId').text)
		return True

class meituan(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"今日团购：", "")
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('h2', id='header-city').text.replace(self.meta['soup'].find('h2', id='header-city').em, "")
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('table', attrs={"class": "deal-discount"}).findAll('td')[0].text.replace(u'¥', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('table', attrs={"class": "deal-discount"}).findAll('td')[1].text.replace(u'折', ''))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'deal-price'}).text.replace(u'¥ ', ''))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"deal-buy-cover-img"}).img['src']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parseEndtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"class":"deal-box deal-timeleft deal-on"})['diff']) + int(time.time())
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('p', attrs={'class':'deal-buy-tip-top'}).strong.text)
		return True

class nuomi(ParserBase):
	def parseArea(self):
		self.area = self.meta['soup'].find('a', attrs={'class':'switch'}).span.text
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'cur-price '}).text.replace(u'￥', ''))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"product-pic"}).img['src']
		return True
	def parseEndtime(self):
		self.endtime = int(self.meta['soup'].find('div', id="countDown")['endtime'][:-3])
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('p', attrs={'class':'sold-num'}).span.text)
		return True

class groupon(ParserBase):
	def parseArea(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'posi'}).span.strong.text
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('table').findAll('td')[1].text.replace(u'折', ''))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'pr'}).label.text)
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('li', attrs={"class":"first"}).img['initsrc']
		return True
	def parseEndtime(self):
		endtime = self.meta['soup'].find('p', attrs={"class":"time"}).findAll('span')
		hour = int(endtime[0].em.text)
		minute = int(endtime[1].em.text)
		second = int(endtime[2].em.text)
		diff = int(hour*60*60 + minute * 60 + second)
		self.endtime = int(time.time()) + diff
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('h2', attrs={'class':'c109'}).text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'cot'}).em.text)
		return True

class lashou(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"今日团购: ", "")
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'n_city_name'}).text
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('div', attrs={"class":"shuzi"}).ul.findAll('li')[0].h4.text.replace(u'￥', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('div', attrs={"class":"shuzi"}).ul.findAll('li')[1].h3.text.replace(u"折", ""))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'l price'}).text.replace(u"￥", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"image"}).a.img['src']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parseEndtime(self):
		self.endtime = int(time.time()) + int(self.meta['soup'].find('div', attrs={"id":"sec_left"}).text)
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'r company'}).h3.text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'deal_samebox status'}).h6.text.replace(u"已经有", "").replace(u"人购买", ""))
		return True

class quan24(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('a', id="deal-title").text
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('h2', attrs={'id':'header-city'})['sname']
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('table', attrs={"class":"deal-discount"}).findAll('td')[0].text.replace(u'￥', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('table', attrs={"class":"deal-discount"}).findAll('td')[1].text.replace(u"折", ""))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'deal-price'}).strong.text.replace(u"￥", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={"id":"team_images"}).img['src']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parseEndtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"id":"deal-timeleft"})['diff']) + time.time()
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'deal_samebox status'}).h6.text.replace(u"已经有", "").replace(u"人购买", ""))
		return True

class dianping(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('div', attrs={'class':'deal-title'}).replace(self.meta['soup'].find('div', attrs={'class':'deal-title'}).h1.text, "")
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('span', attrs={'class':'current'}).text
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('div', attrs={"class":"discount"}).findAll('strong')[0].text.replace(u'&#165;', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('div', attrs={"class":"discount"}).findAll('strong')[1].text.replace(u"折", ""))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'buy'}).strong.text.replace(u"&#165;", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"img-wrap"}).img['src']
		return True
	def parseEndtime(self):
		endtime = self.meta['soup'].find('ul', attrs={"id":"countdown"}).findAll("span")
		day = int(endtime[0].text) * 60 * 60 * 24
		hour = int(endtime[1].text) * 60 *60
		minute = int(endtime[2].text) * 60
		self.endtime = time.time() + day + hour + minute
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'dptg-intro'}).p.span.text
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('span', attrs={'id':'deal-count'}).text)
		return True

class dida(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('meta', attrs={'property':'og:description'})['content']
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'city'}).h2.text
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('span', attrs={'class':'yuanjia'}).span.text.replace(u'¥', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('span', attrs={'class':'zhekou'}).span.text.replace(u":", ""))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('span', attrs={"class": 'deal-price'}).text.replace(u"¥", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('meta', attrs={'property':'og:image'})['content']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'t_h'})
		return True
	def parseEndtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"id":"deal-timeleft"})['diff'][:-3]) + time.time()
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text.strip()
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('span', attrs={'class':'deal-buy-people'}).text)
		return True

class tuan58(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('meta', attrs={"http-equiv":"description"})['content']
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('a', attrs={'id':'changecity_more'}).text
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find("table", width="100%", border="0", cellspacing="0", cellpadding="0").findAll('i')[0].text.replace(u'&yen;', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find("table", width="100%", border="0", cellspacing="0", cellpadding="0").findAll('i')[1].text)
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"id": 'order'}).span.text.replace(u"&yen;", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={'id':'product'}).img['src']
		return True
	def parseEndtime(self):
		pe = re.compile("var endDate = new Date\(Date.parse\('(.+?)'.replace\(/-/g,\"/\"\)\)\);")
		script = pe.findall(self.meta['soup'].findAll('script', src=None, type=None)[3].text)
		self.endtime = time.mktime(time.strptime(script[0], "%b %d, %Y %I:%M:%S %p"))
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('dl', attrs={'class':'class="sjdz"'}).dt.span.text.strip()
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('li', attrs={'class':'sold'}).i.text)
		return True

class aibang(ParserBase):
	def parseTitle(self):
		self.title = self.meta['soup'].find('table', attrs={'class':'at_jrat'}).tr.td.h1.text.replace(self.meta['soup'].find('table', attrs={'class':'at_jrat'}).tr.td.h1.span.text, "")
		return True
	def parseArea(self):
		self.area = self.meta['soup'].find('em', attrs={'class':'t_h_icon'}).text
		return True
	def parseMarketPrice(self):
		self.market_price = float(self.meta['soup'].find('span', attrs={'class':'yuanjia'}).span.text.replace(u'¥', ''))
		return True
	def parseDiscount(self):
		self.discount = float(self.meta['soup'].find('span', attrs={'class':'zhekou'}).span.text.replace(u":", ""))
		return True
	def parsePrice(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'at_buy'}).label.text.replace(u"￥", ""))
		return True
	def parseCover(self):
		self.cover = self.meta['soup'].find('div', attrs={'class':'t_deal_r'}).img['src']
		return True
	def parseDesc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'t_deal_r'})
		self.desc = self.desc.replace(self.desc.img, "")
		return True
	def parseEndtime(self):
		pe = re.compile("new Tools.RemainTime\(\[(\d+),(\d+),(\d+)\],(\d+)")
		script = pe.findall(self.meta['soup'].findAll('script', src=None, type=None)[2].text)[0]
		self.endtime = int(script[3]) * 86400 + int(script[0]) * 3600 + int(script[1]) * 60 + int(script[2]) + time.time() - 86400
		return True
	def parseCompany(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'e_gdfd'}).div.h2.text.strip()
		return True
	def parseBuys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'id':'tuanState'}).span.text)
		return True
#obj = aibang({}, None)
#p = obj.testParse("http://tuan.aibang.com/beijing/gaoerfu8.html")
#print p['endtime']
#print time.ctime(p['endtime'])