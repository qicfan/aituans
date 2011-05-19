#!/usr/bin/env python2.7
#coding:utf-8
'''
Created on 2011-5-16

@author: zeroq
'''
import aituans
import bson
import BeautifulSoup;
import codecs
import os
import re
import time


class ParserBase(object):
    """
    团购产品解析器，负责读取团购蜘蛛抓取的页面，并且解析器中的产品信息
    操作步骤：
        1、初始化站点信息（参数），初始化MONGODB连接，初始化日志独享
        2、读取网页目录下的文件列表
        3、循环列表
            a、读取文件内容
            b、解析出文件内容中的网页URL和网页内容
            c、解析网页内容中的产品信息
            d、如果成功则入库，不成功则继续循环直到列表结束（非产品页面—忽略）
    Attribute:
        meta 保存需要的一些元素数据
                meta['name']  站点名称
                meta['url']   站点入口网址
                meta['domain'] 站点域名（有些网站入口地址是子域名，页内连接是跟域名，所以必须进行设置）
                meta['class'] 站点解析器的类名称
        ... ...
    """
    meta = {} # 配置参数
    logger = None # 日志对象
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
        if len(site) == 0:
            return
        self.meta = site
        self.meta['db'] = aituans.mongodbConnection()
        self.logger = aituans.initLogger("parser") 
        return
    
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
            datas = file.readlines()
            file.close()
        except Exception, e:
            self.logger[0].error(u"[parser]读取URL文件内容时出错: %s" % ( e))
            return False
        return (datas[0], datas[3])

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
        attrs_list = {}
        for key in attrs:
            if key in ['__doc__',  '__module__', 'meta', 'logger', 'handler']:
            #if key == '__doc__' or key == '__module__' or key == 'meta' or key == 'logger' or key == 'handler':
                continue
            value = getattr(self, key)
            if type(value).__name__ not in ["unicode", "str", "int", "float", "list", "dict"]:
                value = str(value)
            attrs_list[key] = value
        del attrs
        del key
        return attrs_list

    def save(self):
        try:
            param = self.getAttrs()
            # 判断是否存在这条记录
            products = self.meta['db'].products
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
                self.meta['soup'] = BeautifulSoup.BeautifulSoup(data[1])
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
    
    def updateBuys(self, product_data):
        page_data = aituans.httpGetUrlContent(product_data['url'])
        self.meta['soup'] = BeautifulSoup.BeautifulSoup(page_data)
        try:
            self.parseBuys()
            # 更新数据库
            product_data['buys'] = self.buys
            db = aituans.mongodbConnection()
            col = db.products
            col.update({"_id":bson.objectid.ObjectId(product_data['_id'])}, product_data)
        except:
            return False
        aituans.mongodbDisconnect()
        return True
    
    def parse(self, url = None):
        try:
            self.parseUrl(url)
            self.parseAddtime()
            self.parseSite()
            self.parseTitle()
            self.parseArea()
            self.parseMarketPrice()
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
        the_data = aituans.httpGetUrlContent(url)
        if the_data == False:
            return False
        self.meta = {"name":"test", "domain":"test.com.cn", "url":"test.com.cn/test", "area":"Beijing", "class":"testclass"}
        self.meta['soup'] = BeautifulSoup.BeautifulSoup(the_data)
        try:
            self.parse()
        except Exception, e:
            print e
            return False
        return self.getAttrs()
    
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
    """
    满座的解析器
    """
    def parseTitle(self):
        self.title = self.meta['soup'].find('h1').text.replace(u"当日精选", "").replace(u"：", "")
        return True
    
    def parseArea(self):
        self.area = self.meta['soup'].find('div', attrs={'class':'city'}).h3.span.text
        return True
    
    def parseMarketPrice(self):
        self.market_price = float(self.meta['soup'].find('table').findAll('td')[0].text.replace(u'元', ''))
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
    """
    美团网的解析器
    """
    def parseTitle(self):
        self.title = self.meta['soup'].find('h1').text.replace(u"今日团购：", "")
        return True
    
    def parseArea(self):
        self.area = self.meta['soup'].find('h2', id='header-city').text.replace(self.meta['soup'].find('h2', id='header-city').em.text, "")
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
    """
    糯米的解析器
    """
    def parseMarketPrice(self):
        self.market_price = float(self.meta['soup'].find('table').findAll('td')[0].text.replace(u'¥', ''))
        return True
    
    def parseArea(self):
        self.area = self.meta['soup'].find('a', attrs={'class':'switch'}).span.text
        return True
    
    def parsePrice(self):
        self.price = float(self.meta['soup'].find('p', attrs={"class": 'cur-price'}).text.replace(u'¥', ''))
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
    """
    团宝网的解析器
    """
    def parseArea(self):
        self.area = self.meta['soup'].find('div', attrs={'class':'posi'}).span.strong.text
        return True
    
    def parseDiscount(self):
        self.discount = float((100 - float(self.meta['soup'].find('table').findAll('td')[1].text.replace(u'%', ''))) / 10)
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
    """
    拉手团的解析器
    """
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
    """
    21券的解析器
    """
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
        self.endtime = int(self.meta['soup'].find('div', attrs={"id":"deal-timeleft"})['diff'][:-3]) + time.time()
        return True
    
    def parseCompany(self):
        self.company = self.meta['soup'].find('div', attrs={'id':'side-business'}).h2.text
        return True
    
    def parseBuys(self):
        self.buys = int(self.meta['soup'].find('strong', attrs={'id':'pay_num'}).text)
        return True
    

class dianping(ParserBase):
    """
    大众点评团购的解析器
    """
    def parseTitle(self):
        self.title = self.meta['soup'].find('div', attrs={'class':'deal-title'}).text.replace(self.meta['soup'].find('div', attrs={'class':'deal-title'}).h1.text, "")
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
        self.company = self.meta['soup'].find('div', attrs={'class':'dptg-info'}).p.span.text
        return True
    
    def parseBuys(self):
        self.buys = int(self.meta['soup'].find('span', attrs={'id':'deal-count'}).text)
        return True
    

class dida(ParserBase):
    """
    嘀嗒团的解析器
    """
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
    """
    58同城团购的解析器
    """
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
        try:
            self.endtime = time.mktime(time.strptime(script[0], "%b %d, %Y %I:%M:%S %p"))
        except:
            self.endtime = time.mktime(time.strptime(script[0], "%Y-%m-%d %H:%M:%S"))
        return True
    
    def parseCompany(self):
        try:
            self.company = self.meta['soup'].find('dl', attrs={'class':'sjdz'}).dt.span.text.strip()
        except:
            self.company = self.meta['soup'].find('div', attrs={'id':'sjdz'}).text.strip()
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
        self.market_price = float(self.meta['soup'].find('div', attrs={'class':'t_deal_l'}).table.findAll('th')[1].text.replace(u'￥', ''))
        return True
    
    def parseDiscount(self):
        self.discount = float(self.meta['soup'].find('div', attrs={'class':'t_deal_l'}).table.findAll('th')[0].text)
        return True
    
    def parsePrice(self):
        self.price = float(self.meta['soup'].find('div', attrs={"class": 'at_buy'}).label.text.replace(u"￥", ""))
        return True
    
    def parseCover(self):
        self.cover = self.meta['soup'].find('div', attrs={'class':'t_deal_r'}).img['src']
        return True
    
    def parseDesc(self):
        self.desc = self.meta['soup'].find('div', attrs={'class':'t_deal_r'})
        img = str(self.desc.img)
        self.desc = str(self.desc).replace(img, "")
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
    
if __name__ == "__main__":   
#    obj = manzuo({})
#    p = obj.testParse("http://www.manzuo.com/deal/beijing/58781165.htm")
#    print p
    pass