#!/usr/bin/env python2.7
#coding:utf-8
'''
Created on 2011-5-16

@author: zeroq
'''
import sys
import unittest
import aituans
import os
import rule
LOGGER = aituans.initLogger("spider")

class ParserTest(unittest.TestCase):
    def testgetFiles(self):
        sites = aituans.getSites()
        ps = rule.ParserBase(sites[0])
        files = ps.getFiles()
        assert files
    
    def testGetFileContent(self):
        sites = aituans.getSites()
        ps = rule.ParserBase(sites[0])
        files = ps.getFiles()
        pd = ps.getPageContentFromFile(files[0])
        assert pd
    
    def testGetAttrs(self):
        sites = aituans.getSites()
        ps = rule.ParserBase(sites[0])
        assert ps.getAttrs()
    
    def testFindProduct(self):
        sites = aituans.getSites()
        ps = rule.ParserBase(sites[0])
        assert ps.findProductFromFile()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()