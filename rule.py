# -*- coding: utf-8 -*-
from BeautifulSoup import BeautifulSoup;
import os
import hashlib
import pickle
import time
import urllib2
import re
import bson
import logging

root_path = os.path.abspath(os.path.dirname(__file__))

"""
启动一个分析器
"""
def parser(site, db):
	try:
		site_handle = globals()[site['class']](site, db)
		site_handle.find_product_from_files();
	except Exception, e:
		pass
	return

class base:
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

	def __init__(self, site, db):
		if len(site) == 0:
			return
		self.meta = site
		self.meta['urls_data'] = self.get_url_data()
		self.meta['db'] = db
		self.meta['db'].authenticate("aituans", "qazwsxedc!@#123")
		self.logger = self.loginit()
		return;
	# 初始化日志对象
	def loginit(self):
		logdir = "%s/log" % self.root_path
		if os.path.isdir(logdir) == False:
			os.mkdir(logdir)
		logfile = "%s/parser.log" % logdir
		self.logger = logging.getLogger()
		self.handler = logging.FileHandler(logfile)
		formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
		self.handler.setFormatter(formatter)
		self.logger.addHandler(self.handler)
		self.logger.setLevel(logging.DEBUG)
		return self.logger
	'''
	返回站点下所有采集到的网页的文件名列表
	'''
	def get_files(self):
		dir = "%s/pagecontent/%s/" % (root_path, self.meta['domain'])
		files = os.listdir(dir)
		file_list = {}
		for file in files:
			file_path = "%s/pagecontent/%s/%s" % (root_path, self.meta['domain'], file)
			if os.path.isfile(file_path) == False:
				continue
			if file == 'urls.data':
				continue
			md5 = self.md5_check(file_path)
			if md5 in file_list:
				# 如果已经重复，就删除这个文件
				os.unlink(file_path)
				continue
			# 生成一个文件列表
			file_list[md5] = (file_path, file)
		return file_list
	'''
	使用MD5来验证重复文件
	'''
	def md5_check(self, file_path):
		file = open(file_path, "rb")
		data = file.read()
		md5obj = hashlib.md5(data)
		file.close()
		md5obj.digest()
		md5 = md5obj.hexdigest()
		return md5

	'''
	取得文件内容
	'''
	def get_file_contents(self, file_path):
		if os.path.isfile(file_path) == False:
			return False
		try:
			file = open(file_path, 'r')
			file_data = file.read()
			file.close()
		except Exception, e:
			self.logger.error(u"[parser]读取URL文件内容时出错: %s" % e)
			return False
		return file_data

	'''
	获取到需要分析的文件dict
	'''
	def get_url_data(self):
		file = "%s/pagecontent/%s/urls.data" % (root_path, self.meta['domain'])
		urls = False
		if os.path.isfile(file):
			try:
				urls_file = open(file, "r")
				urls = pickle.load(urls_file)
				urls_file.close()
			except:
				self.logger.error(u"[parser]载入本次URL列表的时候出错，文件可能不存在: %s" % file)
				pass
		try:
			os.unlink(file)
		except Exception, e:
			self.logger.error(u"[parser]删除URL列表文件的时候出错:%s——%s" % (file, e))
			pass
		return urls

	def is_chinese(self, uchar):
		"""判断一个unicode是否是汉字"""
		if uchar >= u'\u4e00' and uchar<=u'\u9fa5':
			return True
		else:
			return False

	def replace_string(self, str):
		return str.replace(u"【", '').replace(u"】", '').replace(u"！", '').replace(u"，", '').replace(u"、", '').replace(u"）", '').replace(u"（", '').replace(u"”", '').replace(u"“", '')

	'''
	将字符串进行二元切分，得出最大匹配值
	'''
	def words(self, str):
		str = self.replace_string(str)
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

	def get_attrs(self):
		attrs = dir(self)
		for i in xrange(len(attrs)):
			if attrs[i] == '__doc__' or attrs[i] == '__module__' or attrs[i] == 'meta' or attrs[i] == 'logger' or attrs[i] == 'handler':
				del attrs[i]
		return attrs

	def save(self):
		try:
			param = self.get_attrs()
			# 判断是否存在这条记录
			products = self.db.products
			cursor = products.find_one({"title": param['title']})
			if cursor == None:
				products.insert(param)
		except Exception, e:
			self.logger.error(u"[parser]入库出错:%s" % e)
			pass
		return

	def find_product_from_files(self):
		files = self.get_files()
		for file in files:
			try:
				file_path = files[file][0]
				file_name = files[file][1]
			except Exception, e:
				self.logger.error(u"[parser]解析文件时出错：%s" % e)
				return
			data = self.get_file_contents(file_path)
			try:
				os.unlink(file_path)
			except Exception, e:
				self.logger(u"[parser]删除URL文件时出错:%s——%s" % (file, e))
			if data == False:
				continue
			if data == False:
				continue
			try:
				self.meta['soup'] = BeautifulSoup(data)
			except Exception, e:
				self.logger(u"BeautifulSoup解析错误:%s" % e)
				continue
			if self.parse(file_name) == False:
				# 解析失败，可能不是产品页面
				continue
			self.save()
		self.logger.removeHandler(self.handler)
		return
	def get_page(self, url):
		try:
			headers = {"User-Agent": "Mozilla/5.0 (Windows; U; Windows NT 6.1; zh-CN; rv:1.9.2.12) Gecko/20101026 Firefox/3.6.12", "Referer": url}
			req = urllib2.Request(url, None, headers)
			response = urllib2.urlopen(req)
			the_data = response.read()
			response.close()
		except:
			self.logger(u"[parser]抓取页面内容失败: %s" % url)
			return False
		return the_data
	
	def update_buys(self, product_data, db, col):
		page_data = self.get_page(product_data['url'])
		self.meta['soup'] = BeautifulSoup(page_data)
		try:
			self.parse_buys()
			# 更新数据库
			product_data['buys'] = self.buys
			col.update({"_id":bson.objectid.ObjectId(product_data['_id'])}, product_data)
		except:
			return False
		return True
	
	def parse(self, file_name = None):
		try:
			self.parse_url(file_name)
			self.parse_addtime()
			self.parse_site()
			self.parse_title()
			self.parse_area()
			self.parse_marke_price()
			self.parse_discount()
			self.parse_price()
			self.parse_cover()
			self.parse_desc()
			self.parse_endtime()
			self.parse_company()
			self.parse_tag()
			self.parse_buys()
		except Exception, e:
			self.logger.error(u"[parser]分析页面内容失败: %s %s %s" % (self.meta['name'], file_name, e))
			return False
		return True

	def test_parse(self, url):
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
	def parse_addtme(self):
		self.addtime = int(time.time())
		return True
	def parse_site(self):
		self.site = self.meta['name']
		return True
	def parse_url(self, file_name):
		if file_name ==None:
			return False
		self.url = self.meta['urls_data'][file_name]
		return True
	def parse_tag(self):
		self.tag = self.words(self.title)
		return True
	def parse_title(self):
		self.title = self.meta['soup'].find('h1').text
		return True
	def parse_area(self):
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('table').findAll('td')[0].text.replace(u'￥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('table').findAll('td')[1].text.replace(u'折', ''))
		return True
	def parse_price(self):
		return True
	def parse_cover(self):
		return True
	def parse_desc(self):
		self.desc = ""
		return True
	def parse_endtime(self):
		return True
	def parse_company(self):
		self.company = ""
		return True
	def parse_buys(self):
		return True

class manzuo(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"当日精选", "").replace(u"：", "")
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'city'}).h3.span.text
		return True
	def parse_market_price(self):
		self.market_price = super(manzuo, self).parse_market_price().replace(u'元', '')
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'buy pngFix'}).p.span.text)
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', id="mainImgSlideShow").img['src']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'con_ltmrmore'})
		return True
	def parse_endtime(self):
		self.endtime = int(self.meta['soup'].find('input', attrs={"id":"TimeCounter"})['value'][:-3])
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'area'}).h2.text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('span', id='currentdealcountId').text)
		return True

class meituan(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"今日团购：", "")
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('h2', id='header-city').text.replace(self.meta['soup'].find('h2', id='header-city').em, "")
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('table', attrs={"class": "deal-discount"}).findAll('td')[0].text.replace(u'¥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('table', attrs={"class": "deal-discount"}).findAll('td')[1].text.replace(u'折', ''))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'deal-price'}).text.replace(u'¥ ', ''))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"deal-buy-cover-img"}).img['src']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parse_endtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"class":"deal-box deal-timeleft deal-on"})['diff']) + int(time.time())
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('p', attrs={'class':'deal-buy-tip-top'}).strong.text)
		return True

class nuomi(base):
	def parse_area(self):
		self.area = self.meta['soup'].find('a', attrs={'class':'switch'}).span.text
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'cur-price '}).text.replace(u'￥', ''))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"product-pic"}).img['src']
		return True
	def parse_endtime(self):
		self.endtime = int(self.meta['soup'].find('div', id="countDown")['endtime'][:-3])
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('p', attrs={'class':'sold-num'}).span.text)
		return True

class groupon(base):
	def parse_area(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'posi'}).span.strong.text
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('table').findAll('td')[1].text.replace(u'折', ''))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'pr'}).label.text)
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('li', attrs={"class":"first"}).img['initsrc']
		return True
	def parse_endtime(self):
		endtime = self.meta['soup'].find('p', attrs={"class":"time"}).findAll('span')
		hour = int(endtime[0].em.text)
		minute = int(endtime[1].em.text)
		second = int(endtime[2].em.text)
		diff = int(hour*60*60 + minute * 60 + second)
		self.endtime = int(time.time()) + diff
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('h2', attrs={'class':'c109'}).text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'cot'}).em.text)
		return True

class lashou(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('h1').text.replace(u"今日团购: ", "")
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'n_city_name'}).text
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('div', attrs={"class":"shuzi"}).ul.findAll('li')[0].h4.text.replace(u'￥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('div', attrs={"class":"shuzi"}).ul.findAll('li')[1].h3.text.replace(u"折", ""))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'l price'}).text.replace(u"￥", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"image"}).a.img['src']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parse_endtime(self):
		self.endtime = int(time.time()) + int(self.meta['soup'].find('div', attrs={"id":"sec_left"}).text)
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'r company'}).h3.text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'deal_samebox status'}).h6.text.replace(u"已经有", "").replace(u"人购买", ""))
		return True

class quan24(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('a', id="deal-title").text
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('h2', attrs={'id':'header-city'})['sname']
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('table', attrs={"class":"deal-discount"}).findAll('td')[0].text.replace(u'￥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('table', attrs={"class":"deal-discount"}).findAll('td')[1].text.replace(u"折", ""))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('p', attrs={"class": 'deal-price'}).strong.text.replace(u"￥", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={"id":"team_images"}).img['src']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('ul', attrs={'class':'deal-detail-t cf'})
		return True
	def parse_endtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"id":"deal-timeleft"})['diff']) + time.time()
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'class':'deal_samebox status'}).h6.text.replace(u"已经有", "").replace(u"人购买", ""))
		return True

class dianping(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('div', attrs={'class':'deal-title'}).replace(self.meta['soup'].find('div', attrs={'class':'deal-title'}).h1.text, "")
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('span', attrs={'class':'current'}).text
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('div', attrs={"class":"discount"}).findAll('strong')[0].text.replace(u'&#165;', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('div', attrs={"class":"discount"}).findAll('strong')[1].text.replace(u"折", ""))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'buy'}).strong.text.replace(u"&#165;", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={"class":"img-wrap"}).img['src']
		return True
	def parse_endtime(self):
		endtime = self.meta['soup'].find('ul', attrs={"id":"countdown"}).findAll("span")
		day = int(endtime[0].text) * 60 * 60 * 24
		hour = int(endtime[1].text) * 60 *60
		minute = int(endtime[2].text) * 60
		self.endtime = time.time() + day + hour + minute
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'class':'dptg-intro'}).p.span.text
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('span', attrs={'id':'deal-count'}).text)
		return True

class dida(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('meta', attrs={'property':'og:description'})['content']
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('div', attrs={'class':'city'}).h2.text
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('span', attrs={'class':'yuanjia'}).span.text.replace(u'¥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('span', attrs={'class':'zhekou'}).span.text.replace(u":", ""))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('span', attrs={"class": 'deal-price'}).text.replace(u"¥", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('meta', attrs={'property':'og:image'})['content']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'t_h'})
		return True
	def parse_endtime(self):
		self.endtime = int(self.meta['soup'].find('div', attrs={"id":"deal-timeleft"})['diff'][:-3]) + time.time()
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text.strip()
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('span', attrs={'class':'deal-buy-people'}).text)
		return True

class tuan58(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('meta', attrs={"http-equiv":"description"})['content']
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('a', attrs={'id':'changecity_more'}).text
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find("table", width="100%", border="0", cellspacing="0", cellpadding="0").findAll('i')[0].text.replace(u'&yen;', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find("table", width="100%", border="0", cellspacing="0", cellpadding="0").findAll('i')[1].text)
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"id": 'order'}).span.text.replace(u"&yen;", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={'id':'product'}).img['src']
		return True
	def parse_endtime(self):
		pe = re.compile("var endDate = new Date\(Date.parse\('(.+?)'.replace\(/-/g,\"/\"\)\)\);")
		script = pe.findall(self.meta['soup'].findAll('script', src=None, type=None)[3].text)
		self.endtime = time.mktime(time.strptime(script[0], "%b %d, %Y %I:%M:%S %p"))
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('dl', attrs={'class':'class="sjdz"'}).dt.span.text.strip()
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('li', attrs={'class':'sold'}).i.text)
		return True

class aibang(base):
	def parse_title(self):
		self.title = self.meta['soup'].find('table', attrs={'class':'at_jrat'}).tr.td.h1.text.replace(self.meta['soup'].find('table', attrs={'class':'at_jrat'}).tr.td.h1.span.text, "")
		return True
	def parse_area(self):
		self.area = self.meta['soup'].find('em', attrs={'class':'t_h_icon'}).text
		return True
	def parse_market_price(self):
		self.market_price = float(self.meta['soup'].find('span', attrs={'class':'yuanjia'}).span.text.replace(u'¥', ''))
		return True
	def parse_discount(self):
		self.discount = float(self.meta['soup'].find('span', attrs={'class':'zhekou'}).span.text.replace(u":", ""))
		return True
	def parse_price(self):
		self.price = float(self.meta['soup'].find('div', attrs={"class": 'at_buy'}).label.text.replace(u"￥", ""))
		return True
	def parse_cover(self):
		self.cover = self.meta['soup'].find('div', attrs={'class':'t_deal_r'}).img['src']
		return True
	def parse_desc(self):
		self.desc = self.meta['soup'].find('div', attrs={'class':'t_deal_r'})
		self.desc = self.desc.replace(self.desc.img, "")
		return True
	def parse_endtime(self):
		pe = re.compile("new Tools.RemainTime\(\[(\d+),(\d+),(\d+)\],(\d+)")
		script = pe.findall(self.meta['soup'].findAll('script', src=None, type=None)[2].text)[0]
		self.endtime = int(script[3]) * 86400 + int(script[0]) * 3600 + int(script[1]) * 60 + int(script[2]) + time.time() - 86400
		return True
	def parse_company(self):
		self.company = self.meta['soup'].find('div', attrs={'id':'e_gdfd'}).div.h2.text.strip()
		return True
	def parse_buys(self):
		self.buys = int(self.meta['soup'].find('div', attrs={'id':'tuanState'}).span.text)
		return True
#obj = aibang({}, None)
#p = obj.test_parse("http://tuan.aibang.com/beijing/gaoerfu8.html")
#print p['endtime']
#print time.ctime(p['endtime'])