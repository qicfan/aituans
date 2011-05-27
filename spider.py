#!/usr/bin/env python
#coding:utf-8

"""
1、得到网站列表
2、抓取URL队列
3、已抓取URL列表
4、保存网页内容到文件（UTF-8）
5、网页内容分析入库

工作流程：
    1、生成URL队列, 生成10个工作进程/线程
    2、从队列中获取URL, 检查URL是否抓取过，抓取过的话重复本条
    3、分解URL得到主机名
    4、从主机名得到解析器class_name
    5、下载网页HTML, 检测是否该URL是否已经存在（通过网页HTML的MD5值)，如果已存在则重复2
    6、从网页HTML中分析出所有站内链接
    7、过滤分析出的链接（剔除抓取过的）
    8、将过滤后的链接依次插入URL队列
    9、调用解析器分析网页HTML，如果是一个团品，检测团品是否已经存在（根据URL），否则将团品信息入库
    10、休息1秒钟、重复2直到队列为空
    11、队列为空时自动结束工作进程，主进程休息12个小时后，重复1

"""

import BeautifulSoup
import hashlib
import logging
import multiprocessing as mp
import os
import platform
import pymongo
from rule import *
import signal
import sys
import time
import urllib2
import xml.etree.ElementTree as ET
import re

ROOT_PATH = os.path.abspath(os.path.dirname(__file__))
SITES = []
SITES_DICT = {}
MONGODB_HOST = "10.69.10.100"
MONGODB_PORT = 27277
MONGODB_USER = "aituans"
MONGODB_PASSWD = "qazwsxedc!@#123"
MONGODB_CONN = None
PIDS = []
LOGGER = None

def getSitesFromXml():
    """
    从根目录的sites.xml中获取到要抓取的站点的信息
    """
    global ROOT_PATH, SITES, SITES_DICT, LOGGER
    LOGGER = createLogger()
    xml_file = "%s/sites.xml" % ROOT_PATH
    if not os.path.isfile(xml_file):
        error = "%s not found!" % xml_file
        print error
        LOGGER.error(error)
        return False
    try:
        dom = ET.parse(xml_file)
    except:
        error = "can't parse sites.xml"
        print error
        LOGGER.exception(error)
        return False
    root = dom.getroot();
    sites = root.findall("site")
    for site in sites:        
        domain = site.find('domain').text.decode("utf-8")
        name = site.find('name').text
        url = site.find('url').text.decode("utf-8")
        classs = site.find('class').text.decode("utf-8")
        domain1 = site.find('domain1').text.decode("utf-8")
        site = {'name': name, 'url': url, 'class': classs, 'domain': domain, 'domain1': domain1}
        SITES.append(site)
        SITES_DICT[domain] = site
    return True

def initUrlQueue():
    """
    初始化抓取URL队列
    """
    global SITES
    mq = mp.Queue()
    for site in SITES:
        mq.put(site['url'])
    return mq

def createLogger(log_file_name = "spider"):
    """
    返回一个指定名字的logger(logging模块的实例)
    """
    global ROOT_PATH
    logdir = "%s/log" % ROOT_PATH
    try:
        if os.path.isdir(logdir) == False:
            os.mkdir(logdir)
    except:
        return False
    logfile = "%s/%s.log" % (logdir, log_file_name)
    logger = logging.getLogger(log_file_name)
    handler = logging.FileHandler(logfile, "a")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger

def mongodbConnection():
    """
    返回一个验证过的mongodb的数据库 链接
    """
    global MONGODB_HOST, MONGODB_PORT, MONGODB_USER, MONGODB_PASSWD, MONGODB_CONN, LOGGER
    # 初始化数据库连接
    try:
        MONGODB_CONN = pymongo.Connection(MONGODB_HOST, MONGODB_PORT)
    except:
        LOGGER.exception("mongodb connection error")
        return False
    # 选择数据库
    try:
        db = MONGODB_CONN.aituans
    except:
        LOGGER.exception("select database error")
        return False
    try:
        db.authenticate(MONGODB_USER, MONGODB_PASSWD)
    except:
        LOGGER.exception("mongodb auth error")
        return False
    return db

def mongodbDisconnect():
    """
    关闭数据库连接
    """
    global MONGODB_CONN, LOGGER
    try:
        MONGODB_CONN.disconnect()
    except:
        LOGGER.exception("mongodb close error")
    return True

def getDomainFromUrl(url, root = True):
    """
    从URL中获取到根域名
    """
    global LOGGER
    url_info = re.findall("http\:\/\/([\d\w\.-]*).*", url)
    if not url_info:
        LOGGER.exception("can't find domain from url: %s" % url)
        return False
    domain = url_info[0]
    if not root:
        return domain
    domain_info = domain.split('.')
    l = len(domain_info)
    if l > 2:
        for i in xrange(l-2):
            domain_info.pop(0)
    return ".".join(domain_info)

def httpGetUrlContent(url):
    """
    通过HTTP请求获取到指定URL的网页HTML
    """
    global LOGGER
    headers = {"User-Agent": "Mozilla/5.0 (Windows; U; Windows NT 6.1; zh-CN; rv:1.9.2.12) Gecko/20101026 Firefox/3.6.12"}
    try:        
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req, None, 10)
        page_content = response.read()
        response.close()
    except urllib2.URLError:
        LOGGER.exception("error for get %s" % (url))
        return False
    page_content = page_content.replace("\n", "")
    page_content = page_content.replace("\r", "")
    if isinstance(page_content, unicode) == True:
        return page_content
    try:
        return page_content.decode("utf-8", "ignore")
    except:
        LOGGER.exception("use utf-8 decode page_content failed! use gbk decode")
        return page_content.decode("gbk", "ignore")

def findUrlFromPage(url, is_content = False, return_all_urls = False, domain1 = False ):
    """
    利用BeautifulSoup从页面内容中寻找特定domain开头的URL，如果没指定domain，则查找全部有效的URL
    """
    global LOGGER
    if not is_content:
        page_content = httpGetUrlContent(url)
    else:
        page_content = url[1]
        url = url[0]
    domain = getDomainFromUrl(url, False)
    if page_content == "" or page_content == None or not page_content:
        LOGGER.error("page_content is none")
        return False
    try:
        links = BeautifulSoup.SoupStrainer("a")
        urls_list = list(BeautifulSoup.BeautifulSoup(page_content, parseOnlyThese=links))
    except:
        LOGGER.exception("%s-BeautifullSoup init error" % domain)
        return False
    if len(urls_list) == 0:
        LOGGER.warning("no urls on this page")
        return False
    urls = []  # 用来存放过滤完毕后的url列表
    for url_t in urls_list:
        if not url_t.has_key("href"):
            continue
        if url_t['href'].find("/") == 0:
            url_t['href'] = "http://%s%s" % (domain, url_t['href'])
        if url_t in urls:
            continue
        if url_t['href'] == url:
            continue
        if url_t['href'].find(u"#") == 0 or url_t['href'].find(u"javascript") == 0:
            continue
        if return_all_urls == True:
            urls.append(url_t['href'])
            continue
        if domain1:
            if url_t['href'].find(domain1) >= 0:
                urls.append(url_t['href'])
            continue
        if getDomainFromUrl(url_t['href']) == getDomainFromUrl(url):
            urls.append(url_t['href'])
    return urls

def encodeByMd5(self, page_content):
    """
    得到网页内容的MD5值
    """
    global LOGGER
    try:
        md5 = hashlib.md5(page_content.encode("utf-8"))
        md5.digest()
        return  md5.hexdigest()
    except:
        LOGGER.exception("md5 error")
    return False

def deamon():
    """
    1以后台进程方式启动程序
    """
    global ROOT_PATH, LOGGER
    if platform.platform().lower().find("windows") >= 0:
        # WINDOWS系统，直接返回
        LOGGER.info("不能在WINDOWS系统下以fork模式运行，会自动切换到thread模式")
        return False
    
    LOGGER.info("[main]开启deamon模式")
    try:
        pid = os.fork()
        if pid > 0:
            # exit first parent
            sys.exit(0)
    except OSError, e:
        LOGGER.exception("[main]fork #1 failed")
        sys.exit(1)
    # decouple from parent environment
    os.chdir("/")
    os.setsid()
    os.umask(0)
    # do second fork
    try:
        pid = os.fork()
        if pid > 0:
            # exit from second parent, print eventual PID before
            LOGGER.info("Daemon PID %d" % pid)
            sys.exit(0)
    except OSError, e:
        LOGGER.exception("fork #2 failed")
        sys.exit(1)
    # start the daemon main loop
    # 写入pid
    pidfile = open("%s/a.pid" % ROOT_PATH, "w")
    pidfile.write(str(os.getpid()))
    pidfile.close()
    return

def spiderMain():
    """
    1、初始化URL队列
    2、生成工作进程
    3、工作完成后休息12小时
    """
    global SITES, SITES_DICT, LOGGER
    while 1:
        if not getSitesFromXml():
            sys.exit()
        mq = initUrlQueue()
        process_list = []
        for i in xrange(10):
            p = Spider(mq)
            process_list.append(p)
            p.start()
        del p
        for p in process_list:
            p.join()
        LOGGER.info("finish! sleep 12 hours")
        time.sleep(43200)
    return

def updaterMain():
    """
    1、初始化更新URL队列
    """
    global SITES, SITES_DICT, LOGGER
    while 1:
        if not getSitesFromXml():
            sys.exit()
        db = mongodbConnection()
        if not db:
            return False
        col = db.products
        products = col.find({"endtime":{"$gt":time.time()}}, {"title":1, "url":1, "site":1, "buys":1})
        mq = mp.Queue()
        for product in products:
            domain = getDomainFromUrl(product['url'])
            classs = SITES_DICT[domain]['class']
            product['class'] = classs
            product['siteinfo'] = SITES_DICT[domain]
            mq.put(product)
        process_list = []
        process_list = []
        for i in xrange(10):
            pl = mp.Process(target=updateBuys, args=(mq,))
            process_list.append(pl)
            pl.start()
        # 等待所有线程执行完成
        for pl in process_list:
            pl.join()
        del db
        del col
        del mq
        del process_list
        mongodbDisconnect()
        time.sleep(60*60*1)
    return

def updateBuys(mq):
    """
    更新器进程的入口函数，负责调用分析器更新团购已购买人数
    """
    global LOGGER
    db = mongodbConnection()
    while True:
        # 如果队列已经结束，则退出本次更新
        if mq.empty():
            break
        # 取一个产品数据
        product = mq.get()
        # 生成一个分析器实例
        page_content = httpGetUrlContent(product['url'])
        if page_content == False:
            continue
        site_handle = globals()[product['class']](product['siteinfo'], product['url'], page_content, db)
        if not site_handle.updateBuys(product):
            LOGGER.error("%s-%s-update buyers failed!" % (os.getpid(), product['title'].encode("utf-8")))
        # 购买人数更新完毕,初始化变量，然后休息1秒继续
        time.sleep(1)
    LOGGER.info("[%s]updater finish!" % os.getpid())
    mongodbDisconnect()
    return

def main():
    """
    主入口函数，负责生成两个进程团购蜘蛛和人数更新器
    """
    global PIDS
    args = sys.argv[1:]
    try:
        args.index("fork" )
        deamon()
    except ValueError:
        pass
    # 执行spider
    spider_process = mp.Process(target=spiderMain, args=())
    spider_process.start()
    PIDS.append(spider_process)
    time.sleep(60*30)
    # 启动更新器
    update_process = mp.Process(target=updaterMain, args=())
    update_process.start()
    PIDS.append(update_process)
    return
    
def sigintHandler(signum, frame):
    """
    信号处理程序，响应SIGTERM和SIGINT
    """
    global PIDS, ROOT_PATH
    # 终止子进程
    if len(PIDS) > 0:
        for pid in PIDS:
            pid.terminate()
    # 删除PID
    try:
        os.unlink("%s/a.pid" % ROOT_PATH)
    except:
        pass
    # 自身退出
    sys.exit()


class Spider(mp.Process):
    """
    团购蜘蛛
    Attribute:
        url_queue multiprocessing.Queue的实例，多进程共享的URL队列
        mongodb MONGODB的数据库连接
        logger 日志对象
    """
    url_queue = None
    mongodb = None
    logger = None
    def __init__(self, mq):
        if type(mq).__name__ != "Queue":
            sys.exit()
        self.url_queue = mq
        mp.Process.__init__(self)
    
    def checkUrlExists(self, url):
        """
        验证URL是否已经抓取过
        """
        col = self.mongodb.urls
        rs = col.find_one({"url": url})
        if rs == None or not rs:
            col.insert({"url": url, "lasttime": int(time.time()), "count": 1})
            return False
        if (time.time() - rs['lasttime']) > 60*60*24:
            try:
                count = rs['count'] + 1
            except:
                count = 1
            col.update({"_id":bson.objectid.ObjectId(rs['_id'])}, {"$set":{"lasttime": int(time.time()), "count": count}})
            return False
        return True
    
    def checkUrlMd5(self, page_content):
        """
        有些页面的URL可能不同，但是可能指向同一个网站，所以增加了使用MD5来验证页面内容是否一致的方法
        """
        url_md5_string = encodeByMd5(page_content)
        if not url_md5_string:
            return False
        col = self.mongodb.urlmd5
        rs = col.find_one({"urlmd5": url_md5_string})
        if rs == None or not rs:
            return False
        return True
    
    def run(self):
        """
        1、迭代URL队列
        2、从当前URL分析出所有站内链接
        3、验证链接有效性，如果链接已存在则重复1
        4、解析页面内容
        5、分析该页面的站内链接
        6、更新URL队列
        """
        c = 0
        self.mongodb = mongodbConnection()
        self.logger = createLogger("spider.main")
        if not getSitesFromXml():
            sys.exit()
        while 1:
            if self.url_queue.empty():
                break
            current_url = self.url_queue.get()
            domain = getDomainFromUrl(current_url)
            domain1 = SITES_DICT[domain]['domain1']
            if SITES_DICT[domain]['url'] != current_url:
                if self.checkUrlExists(current_url):
                    self.logger.warning("%s is exists" % current_url)
                    continue
            page_content = httpGetUrlContent(current_url)
            if self.checkUrlMd5(page_content):
                continue
            if page_content == False:
                continue
            # 解析该页面
            try:
                site_handle = globals()[SITES_DICT[domain]['class']](SITES_DICT[domain], current_url, page_content, self.mongodb)
                site_handle.findProductFromFile()
            except:
                self.logger.exception("init parser error")
            # 分析出站内链接
            spider_urls = findUrlFromPage([current_url, page_content], True, False, domain1)
            if not spider_urls or len(spider_urls) == 0:
                self.logger.warning("no urls in %s" % current_url)
                continue
            # 加入队列
            for surl in spider_urls:
                self.url_queue.put(surl)
            c = c + 1
            time.sleep(0.1)
        self.logger.info("worker finish %d success url" % c)
        mongodbDisconnect()
        return

if __name__ == "__main__":
    LOGGER = createLogger()
    signal.signal(signal.SIGTERM, sigintHandler)
    signal.signal(signal.SIGINT, sigintHandler)
    main()