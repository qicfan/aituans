#!/usr/bin/env python2.7
#coding:utf-8
'''
Created on 2011-5-13

@author: zeroq
'''
import unittest
import aituans
import os

LOGGER = aituans.initLogger("spider")

class AituansTest(unittest.TestCase):
        
    def testSpider(self):
        spider = aituans.Spider({"class":"test", "name":"test", "url":"http://www.manzuo.com/beijing/index.htm","domain":"www.manzuo.com"}, os.path.abspath(os.path.dirname(__file__)))
        spider.start()
        spider.join()
        #assert aituans.spiderMain() == True
        pass
    
    def testUpdater(self):
        assert aituans.updaterMain() == True
        pass
    
    def testGetSites(self):
        """
        1测试能否取得要抓取的SITES，sites是一个list
        """
        #logger = aituans.initLogger("test")
        #sites = aituans.getSites(logger)
        #assert isinstance(sites, list)
        pass
    
    def testHttpGetUrlContent(self):
        """
        测试抓取网页内容是否可以正常运行
        """
        #logger = aituans.initLogger("test")
        #assert aituans.httpGetUrlContent("http://www.manzuo.com/beijing/index.htm", logger)
        pass
    
    def testFindAllUrl(self):
        """
        测试分析页面上的链接，并且返回全部链接
        """
        pass
        #logger = aituans.initLogger("test")
        #assert aituans.findUrlFromPageContent(aituans.httpGetUrlContent("http://www.manzuo.com/beijing/index.htm", logger), logger, "www.manzuo.com", True)
        
    def testFindLocalUrl(self):
        """
        测试分析页面上的链接，并且只返回站内链接
        """
        #logger = aituans.initLogger("test")
        #assert aituans.findUrlFromPageContent(aituans.httpGetUrlContent("http://www.manzuo.com/beijing/index.htm", logger), logger, "www.manzuo.com", False)
        pass

    def testSaveAndLoadPickle(self):
        """
        测试通过pickle持久化对象
        """
        #self.failUnless(aituans.saveByPickle("/home/zeroq/workspace/pydev/src/log/test.data", {"a“：”test"}))
        #assert aituans.loadByPickle("/home/zeroq/workspace/pydev/src/log/test.data")
        pass
    
    def testMd5String(self):
        #assert aituans.encodeByMd5(u"我是谁")
        pass

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()