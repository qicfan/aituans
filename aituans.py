#!/usr/bin/env python2.7
#coding: utf-8
'''
Created on 2011-5-13

@author: zeroq
'''
import BeautifulSoup
import logging
import os
import re
import platform
import pymongo
import sys
import threading
import urllib2
import xml.etree.ElementTree as ET
import pickle
import hashlib
import Queue
import time


ROOT_PATH = os.path.abspath(os.path.dirname(__file__))
MONGODB_HOST = "127.0.0.1"
MONGODB_PORT = 27017
MONGODB_USER = "aituans"
MONGODB_PASSWD = "qazwsxedc!@#123"
MONGODB_CONN = None


def initLogger(log_file_name):
    """
    1初始化一个日志对象
    1通过传入的文件名来返回日志对象
    """
    global LOGGER, ROOT_PATH
    logdir = "%s/log" % ROOT_PATH
    try:
        if os.path.isdir(logdir) == False:
            os.mkdir(logdir)
    except:
        return False
    logfile = "%s/%s.log" % (logdir, log_file_name)
    logger = logging.getLogger(log_file_name)
    handler = logging.FileHandler(logfile)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    LOGGER = (logger, handler)
    return LOGGER

def deamon(logger):
    """
    1以后台进程方式启动程序
    """
    global LOGGER
    if platform.platform().lower().find("windows") >= 0:
        # WINDOWS系统，直接返回
        logger[0].info(u"不能在WINDOWS系统下以fork模式运行，会自动切换到thread模式")
        return False
    global ROOT_PATH
    LOGGER[0].info(u"[main]开启deamon模式")
    try:
        pid = os.fork()
        if pid > 0:
            # exit first parent
            sys.exit(0)
    except OSError, e:
        LOGGER[0].error("[main]fork #1 failed: %d (%s)" % (e.errno, e))
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
            LOGGER[0].info("Daemon PID %d" % pid)
            sys.exit(0)
    except OSError, e:
        LOGGER[0].error("fork #2 failed: %d (%s)" % (e.errno, e))
        sys.exit(1)
    # start the daemon main loop
    # 写入pid
    pidfile = open("%s/a.pid" % ROOT_PATH, "w")
    pidfile.write(os.getpid())
    pidfile.close()
    return

def mongodbConnection():
    """
    返回一个验证过的mongodb的数据库 链接
    """
    global LOGGER
    global MONGODB_HOST, MONGODB_PORT, MONGODB_USER, MONGODB_PASSWD, MONGODB_CONN
    # 初始化数据库连接
    if isinstance(MONGODB_PORT, int) == False:
        LOGGER[0].error(u"mongodb端口错误，需要int型")
        pass
    try:
        MONGODB_CONN = pymongo.Connection(MONGODB_HOST, MONGODB_PORT)
    except Exception, e:
        LOGGER[0].error(u"mongodb连接失败：%s" % e)
        return False
    # 选择数据库
    db = MONGODB_CONN.aituans
    try:
        db.authenticate(MONGODB_USER, MONGODB_PASSWD)
    except Exception, e:
        LOGGER[0].error(u"mongodb验证失败：%s:%s/aituans" % (MONGODB_HOST, MONGODB_PORT))
        return False
    return db

def mongodbDisconnect():
    """
    关闭数据库连接
    """
    global LOGGER
    global MONGODB_CONN
    try:
        MONGODB_CONN.disconnect()
    except Exception, e:
        LOGGER[0].error(u"关闭数据库连接失败: %s" % e)
    return True

def getSites():
    """
    1从XML中读取要采集的站点配置信息
    """
    global ROOT_PATH, LOGGER
    site_xml = "%s/site/beijing.xml" % ROOT_PATH
    try:
        dom = ET.parse(site_xml)
        root = dom.getroot();
        sites = root.findall("site")
    except Exception, e:
        LOGGER[0].error(u"读取XML文件(%s)失败: %s" % (site_xml, e))
        return False
    # 声明返回值
    rs = []
    for site in sites:            
        name    = site.find('name').text# get name node
        url     = site.find('url').text# get url node            
        classs  = site.find('class').text# get class node            
        domain  = site.find('domain').text# get domain node
        rs.append({'name': name, 'url': url, 'class': classs, 'domain': domain, 'area': '北京'})
    return rs

def httpGetUrlContent(url):
    """
    使用urllib2抓取指定的URL的页面内容
    """
    global LOGGER
    try:
        headers = {"User-Agent": "aituans tuangou spider/1.0(+http://petmerry.com/test)"}
        req = urllib2.Request(url, None, headers)
        response = urllib2.urlopen(req)
        page_content = response.read()
        response.close()
    except Exception, e:
        LOGGER[0].error("error for get %s: %s" % (url, e))
        return False
    if isinstance(page_content, unicode) == True:
        return page_content
    if type(page_content).__name__ == "str":
        # 一个普通字符串，转化为unicode
        return page_content

def findHostFromUrl(url):
    """
    利用正则，从一个URL中获取到主机名(域名）
    """
    r = re.compile("http\:\/\/([a-z0-9\.]?)")
    rs = r.find(url)
    if len(rs) > 0:
        return rs[0]
    return False

def findUrlFromPageContent(page_content, domain, return_all_urls = True ):
    """
    利用BeautifulSoup从页面内容中寻找特定domain开头的URL，如果没指定domain，则查找全部有效的URL
    """
    global LOGGER
    if page_content == "" or page_content == None:
        LOGGER[0].error(u"要分析连接的网页内容为空")
        return False
    try:
        links = BeautifulSoup.SoupStrainer("a")
        urls_list = list(BeautifulSoup.BeautifulSoup(page_content, parseOnlyThese=links))
    except Exception, e:
        LOGGER[0].error(u"BeautifullSoup解析错误:%s" % e)
        return False
    if len(urls_list) == 0:
        LOGGER[0].warning(u"页面上没有找到任何链接")
        return False
    urls = []  # 用来存放过滤完毕后的url列表
    for url in urls_list:
        if not url.has_key("href"):
            continue
        if url['href'].find("/") == 0:
            url['href'] = "http://%s%s" % (domain, url['href'])
        if url in urls:
            continue
        if return_all_urls == True:
            urls.append(url['href'])
            continue
        if url['href'].find("http://%s" % domain) == 0:
            # 找到指定domain开头的URL
            urls.append(url['href'])
    return urls

def saveByPickle(file_name, pickle_data):
    """
    如果失败则会抛出一个异常，一般都是因为文件权限问题引起的IO错误
    """
    pickle_file = open(file_name, "w")
    pickle.dump(pickle_data, pickle_file)
    pickle_file.close()
    return True

def loadByPickle(file_name):
    if os.path.isfile(file_name):
        pickle_file = open(file_name, "r")
        pickle_data = pickle.load(pickle_file)
        pickle_file.close()
        return pickle_data
    return False

def encodeByMd5(string):
    try:
        md5 = hashlib.md5(string)
        md5.digest()
        md5_string = md5.hexdigest()
    except:
        return False
    return md5_string


class Spider(threading.Thread):
    """
    对网页的抓取采用多线程方式来实现
    高IO对CPU的需求不大，虽然python具有全局锁，无法使用多CPU，但是也足够使用了，瓶颈依然是在带宽上
    操作步骤：
    1、先分析出要采集的URL列表，然后将之加入一个队列
    2、遍历队列，将URL的内容下载到本地
        a、保存到本地的文件名是将URL地址进行MD5以后的32位字符串
        b、本地文件的第一行是该页面的URL
    Attribute:
        site_data 要采集的网站的基本信息dict，包括：
                网站的名称site_data['name']、要采集的地址site_data['url']、网站的匹配域名site_data['domain']、对应的内容分析器要使用的类名site_data['class']、所属的地域site-data['area']
        ROOT_PATH 文件所在文件夹的全路径，一个字符串
        urls_queue 存放要采集的URL的队列
    """
    
    site_data = None
    mongodb = None
    logger = None
    root_path = None
    urls_queue = None
    
    def __init__(self, site_data, root_path):
        global LOGGER
        if isinstance(site_data, dict) == False:
            raise TypeError("site_data参数需要一个字典类型")
        if isinstance(root_path, str) == False:
            raise TypeError(u"root_path参数需要一个字符串")
        if os.path.isdir(root_path) == False:
            raise IOError(u"root_path必须是一个真实存在的路径")
        self.site_data = site_data
        self.logger = LOGGER
        self.root_path = root_path
        threading.Thread.__init__(self)
        return
    
    def createUrlsQueen(self):
        """
        获取到URL列表之后，循环列表，检查链接是否已经采集过，生成一个未采集过的链接队列
        采集过的地址载分析器分析完成后会更新到old.urls文件
        """
        urls = findUrlFromPageContent(httpGetUrlContent(self.site_data['url']), self.site_data['domain'], False)
        if not urls:
            return False
        old_urls = loadByPickle("%s/site/old.urls" % self.root_path)
        if not old_urls:
            old_urls = []
        self.urls_queue = Queue.Queue()
        for url in urls:
            if url in old_urls:
                continue
            try:
                self.urls_queue.put(url)
            except Exception, e:
                self.logger[0].error(u"[%s]urls_queue队列操作失败：%s" % (self.name, e))
                return False
        return True
    
    def savePage(self, url):
        page_data = httpGetUrlContent(url)
        if page_data == "" or not page_data:
            self.logger[0].error(u"[%s]URL采集结果为空：%s" % (self.name, url))
            return False
        page_dir = "%s/page/%s" % (self.root_path, self.site_data["domain"])
        if not os.path.isdir(page_dir):
            try:
                os.mkdir(page_dir)
            except:
                self.logger[0].error(u"[%s]创建目录失败：%s" % (self.name, page_dir))
                return False
        page_file = "%s/%s" % (page_dir, encodeByMd5(url))
        if os.path.isfile(page_file):
            self.logger[0].error(u"[%s]URL文件已经存在：%s" % (self.name, url))
            return False
        try:
            pf = open(page_file, "w")
            pf.write(u"%s\n%s\n%s\n%s" % (url, self.site_data["class"], self.site_data["name"], page_data.decode("utf-8")))
            pf.close()
        except Exception, e:
            self.logger[0].error(u"[%s]URL采集保存文件失败：%s-%s-%s" % (self.name, url, page_file, e))
            return False
        return True
    
    def run(self):
        if not self.createUrlsQueen():
            self.logger[0].error(u"[%s]Failed: 无法抓取网页内容或者无法分析出网页上的URL" % self.name)
            return False
        _count = 0
        while 1:
            if self.urls_queue.empty():
                break
            url = self.urls_queue.get()
            if not self.savePage(url):
                continue
            _count = _count + 1
        self.logger[0].info(u"[%s] 抓取网页结束，成功抓取到%d个网页" % (self.name, _count))
        return

def spider_main():
    global ROOT_PATH, MONGODB_CONN, LOGGER
    """
    1启动爬虫
    1、生成数据库连接
    2、生成爬虫对象
    3、循环执行
    """
    
    while 1:
#        db = mongodbConnection(logger)
#        if db == False:
#            logger[0].error(u"无法连接mongodb，结束进程")
#            return False
        sites = getSites()
        sites_count = len(sites)
        if sites == False or sites_count == 0:
            LOGGER[0].error(u"没有读取到sites记录")
            return False
        j = 0
        k = 0
        spider_threads_list = []
        while 1:
            if j < 10 and k < sites_count:    
                try:
                    spider_instance = Spider(sites[k], ROOT_PATH)
                except TypeError, e:
                    LOGGER[0].error(u"无法初始化Spider对象：%s" % e)
                    continue
                except IOError, e:
                    LOGGER[0].error(u"无法初始化Spider对象：%s" % e)
                    continue
                spider_instance.start()
                spider_threads_list.append(spider_instance)
                del spider_instance
                j = j + 1
                k = k + 1
            else:
                for stl in spider_threads_list:
                    stl.join()
                j = 0
                if k >= sites_count:
                    k = 0
                    break
        del spider_threads_list
        del sites
        LOGGER[0].info(u"休息6个小时再抓取")
        #logger[0].removeHandler(logger[1])
        #mongodbDisconnect()
        #time.sleep(60*60*6)
        break
    return True

def updater():
    return True

def main():
    args = sys.argv[1:]
    try:
        args.index("fork" )
        #deamon(logger)
    except ValueError:
        pass
    # 执行spider
    spider_main()
    # 执行updater
    return


if __name__ == '__main__':
    LOGGER = initLogger("spider")
    main()