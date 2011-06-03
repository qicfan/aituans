#!/usr/bin/env python2.7
#coding:utf-8
'''
Created on 2011-5-16

@author: zeroq
'''
import bson
import BeautifulSoup;
from decimal import Decimal, getcontext
import os
import pickle
from PIL import Image
import re
import spider
import StringIO
import time
import sys

pickle_file = open("%s/city.list" % os.path.abspath(os.path.dirname(__file__)), "r")
try:
    CITYS = pickle.load(pickle_file)
    pickle_file.close()
except:
    pickle_file.close()      


class ParserBase(object):
    """
    团品解析
    解析传入的页面内容，如果是一个团品（可以通过所有解析规则）则入库，否则不进行操作
    Attribute:
        meta 保存需要的一些元素数据
                meta['name']  站点名称
                meta['url']   站点入口网址
                meta['domain'] 站点域名（有些网站入口地址是子域名，页内连接是跟域名，所以必须进行设置）
                meta['class'] 站点解析器的类名称
        ... ...
    """
    meta = {} # 配置参数
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
    
    def __init__(self, site, url, page_content, mongodb, level = 1):
        self.meta = site
        self.meta['db'] = mongodb
        self.meta['page_content'] = page_content
        self.meta['page_url'] = url
        self.meta['logger'] = spider.createLogger("spider.rule")
        self.meta['level'] = level
        return

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
        return attrs_list

    def save(self):
        try:
            if self.meta['level'] < 2:
                return
            param = self.getAttrs()
            param['status'] = 1
            # 判断是否存在这条记录
            if spider.checkUrlMd5(self.meta['page_content']):
                return False
            products = self.meta['db'].products
            cursor = products.find_one({"url": param['url']})
            if cursor == None:
                cursor = products.find_one({"title": param['title']})
                if cursor == None:
                    products.insert(param)
                else:
                    products.update({"_id":bson.objectid.ObjectId(cursor['_id'])}, {"$set":{"url": self.url}})
        except:
            self.meta['logger'].exception("[parser]save error" )
        return
    
    def findProductFromFile(self):
        """
        从文件内容中匹配出产品信息，如果一个文件无法匹配所有的必须规则，则说明该页面不是一个产品页面，自动忽略
        """
        
        try:
            self.meta['soup'] = BeautifulSoup.BeautifulSoup(self.meta['page_content'])
        except:
            self.meta['logger'].exception("BeautifulSoup init error")
        try:           
            self.parse()
        except:
            # 解析失败，可能不是产品页面
            self.meta['logger'].exception("no product's info: %s" % self.meta['page_url'].encode("utf-8"))
            return False
        self.save()        
        return True
    
    def updateBuys(self, product_data):
        try:
            self.meta['soup'] = BeautifulSoup.BeautifulSoup(self.meta['page_content'])
            self.parse()
            if self.buys == product_data['buys']:
                return True
            col = self.meta['db'].products
            if self.title != product_data['title']:
                # 删除这个记录
                col.remove({"_id":bson.objectid.ObjectId(product_data['_id'])})
                return False
            # 更新数据库            
            col.update({"_id":bson.objectid.ObjectId(product_data['_id'])}, {"$set":{"buys": self.buys}})
        except:
            col = self.meta['db'].products
            col.update({"_id":bson.objectid.ObjectId(product_data['_id'])}, {"$set":{"status": 0}})
            return False
        return True
    
    def parse(self):
        body_text = self.meta['soup'].body.text
        if body_text.find(u"结束时间") >= 0 or body_text.find(u"团购结束") >= 0:
            raise ValueError(u"该团购已经结束")
        if body_text.find(u"继续购买") >= 0 or body_text.find(u"团购成功") >= 0 \
            or body_text.find(u"数量有限") >= 0 or body_text.find(u"请尽快购买") >= 0 \
            or body_text.find(u"剩余时间") >= 0:
                pass
        else:
            raise ValueError(u"该团购还未开始或者不是一个团购页面")
        if self.parseUrl() and self.parseSite() and self.parseAddtime() and self.parseTitle() and self.parseTag() and self.parseBuys() \
        and self.parseArea() and self.parseCover() and self.parseDesc() and self.parseEndtime() and self.parseCompany():
            return True
        else:
            self.meta['logger'].error("[parser]par page_content error : %s" % self.meta['page_url'])            
            raise ValueError(u"分析页面内容失败")
    
    def testParse(self):
        the_data = spider.httpGetUrlContent(self.meta['page_url'])
        if the_data == False:
            return False
        self.meta['name'] = "test"
        self.meta["domain"] = "test.com.cn"
        self.meta["area"] = "Beijing"
        self.meta["class"] = "testclass"
        self.meta['page_content'] = the_data
        self.meta['soup'] = BeautifulSoup.BeautifulSoup(the_data)
        self.parse()
        return self.getAttrs()
    
    def parseAddtime(self):
        self.addtime = int(time.time())
        return True
    
    def parseSite(self):
        self.site = self.meta['name']
        return True
    
    def parseUrl(self):
        self.url = self.meta['page_url']
        return True
    
    def parseTag(self):
        self.tag = self.words(self.title)
        return True
    
    def parseTitle(self):
        """
        取得BODY标签的内容，然后从头开始。寻找连续超过50个字符没有HTML标签出现的字符串如果中文在其中所占比例超过50%，则认为是一个标题
        """
        body_contents = unicode(self.meta['soup'].body)
        body_contents = re.sub("<script(.+?)<\/script>", "", body_contents)
        body_contents = re.sub("<style(.+?)<\/style>", "", body_contents)
        body_contents = re.sub("<style(.+?)<\/style>", "", body_contents)
        body_contents = re.sub("\<\!\-\-(.+?)\-\-\>", "", body_contents)
        body_contents = re.sub("[\t\s]", "", body_contents)
        x = 2000
        y = 2001
        z = 0
        word = ""
        w = ""
        max = 50
        start = False
        second = False
        while True:
            if x > 22000 or x >= len(body_contents):
                if second == True:
                    word = ""
                    break
                body_contents = body_contents[25000:]
                second = True
                x = y = z = 0
                continue
            w = body_contents[x:y]
            if w == u"<":
                # 一个HTML标签出现，判断前面的字符串的长度
                lw = len(word)
                if z > 35:
                    if z > 0 and lw > 0:
                        gl = Decimal(z) / Decimal(lw)
                        if lw > max and gl > Decimal(str(0.5)):
                            # 如果字符串长度超过预定长度，并且中文字符出现的概率超过一半，则认为这是一个标题，退出循环
                            rs = re.findall(u"[\d\.]+元", word)
                            if len(rs) > 0:
                                # 找到了价格
                                break
                gl = 0.0
                word = ""
                z = 0
                start = False
            elif w == u">" :
                # 不是一个HTML标签，开始记录字符串
                start = True
            else:
                if start:
                    word = "%s%s" % (word, w)
                    if self.isChinese(w):
                        z = z + 1
                else:
                    word = ""
                    z = 0
            x = x + 1
            y = x + 1
        if word == "" or word[-1:] == u"…" or word[-2:] == "..":
            raise ValueError("无法自动匹配标题")
            return False
        word = re.sub("[\t\s]", "", word)
        self.title = word
        prices = re.findall(u"[\d\.]+元", word)
        if not prices or len(prices) == 0:
            raise ValueError("无法自动匹配价格")
            return False
        try:
            prices = [float(p.replace(u"元", "")) for p in prices if True]
            if len(prices) > 1:
                price1 = prices[0]
                price2 = prices[1]
            else:
                price1 = price2 = prices[0]
            if price1 > price2:
                price = price2
                market_price = price1
            else:
                price = price1
                market_price = price2
            getcontext().prec = 2
            discount = Decimal(str(price)) / Decimal(str(market_price)) * 10
        except:
            price = 0.0
            market_price = 0.0
            discount = 0.0
        self.price = price
        self.market_price = market_price
        self.discount = discount
        return True
    
    def parseArea(self):
        """
        1、取BODY中的前两个中文组合
        2、判断是否存在于城市列表中
        3、如果存在，则认为是该产品所属城市
        """
        body_contents = unicode(self.meta['soup'].body)
        body_contents = re.sub("<script(.+?)<\/script>", "", body_contents)
        body_contents = re.sub("<style(.+?)<\/style>", "", body_contents)
        body_contents = re.sub("<style(.+?)<\/style>", "", body_contents)
        body_contents = re.sub("\<\!\-\-(.+?)\-\-\>", "", body_contents)
        body_contents = re.sub("<(.+?)>", "", body_contents)
        body_contents = re.sub("[\t\s]", "", body_contents)
        body_string = body_contents[:100]
        del body_contents
        x = 0
        while True:
            y = x + 2
            if y > len(body_string):
                break
            word = body_string[x:y]
            if word in CITYS:
                self.area = word
                return True
            x = x + 1
        self.area = u"全国"
        return True
    
    def parseCover(self):
        """
        1、取所有的图片地址
        2、逐一分析图片的宽和高
        3、取最符合比例的图片作为封面图片(高大于400，宽大于250）
        """
        body_imgs = self.meta['soup'].findAll("img")
        for img in body_imgs:
            try:
                src = img['src']
            except:
                continue
            if src.find('/') == 0:
                src = "http://%s%s" % (spider.getDomainFromUrl(self.meta['page_url']), src)
            elif src.find("http://") != 0:
                src = "http://%s/%s" % (spider.getDomainFromUrl(self.meta['page_url']), src)
            if not src or src == "" or src == None:
                continue
            # 取图像的宽和高
            try:
                im = Image.open(StringIO.StringIO(spider.httpGetUrlContent(src, True)))
            except:
                continue
            w, h = im.size
            if w > 400 and h > 250:
                self.cover = src
                return True
        raise ValueError(u"无法自动匹配封面")
        return True
    
    def parseDesc(self):
        self.desc = ""
        return True
    
    def parseEndtime(self):
        self.endtime = time.time() + 60*60*24*2
        return True
    
    def parseCompany(self):
        self.company = ""
        return True
    
    def parseBuys(self):
        body_text = unicode(self.meta['soup'].body)
        body_text = re.sub(u"^折扣\:[\d\.]+$", "", body_text)
        body_text = re.sub(u"[¥|￥][\d\.]+", "", body_text)
        body_text = re.sub(u"^折扣<span>\:[\d\.]+<\/span>$", "", body_text)
        body_text = re.sub("<script(.+?)<\/script>", "", body_text)
        body_text = re.sub("<style(.+?)<\/style>", "", body_text)
        body_text = re.sub("<style(.+?)<\/style>", "", body_text)
        body_text = re.sub("<(.+?)>", "", body_text)
        body_text = re.sub("[\t\s]", "", body_text)
        s = body_text.find(self.title) + len(self.title)
        rs = re.compile(u"\d+人")
        result = rs.findall(body_text[s:])
        c = str(int(self.market_price) - int(self.price))
        self.buys = int(result[0].replace(c, "").replace(u"人", ""))
        return True
    

if __name__ == "__main__":
    #print ParserBase.__subclasses__()
    #sys.exit()
    args = sys.argv[1:]
    try:
        url = args[0]
    except ValueError:
        sys.exit()
    obj = ParserBase({}, url, None, None)
    p = obj.testParse()
    del p['tag']
    print p