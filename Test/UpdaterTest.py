'''
Created on 2011-5-17

@author: zeroq
'''
import unittest
import aituans



class UpdaterTest(unittest.TestCase):


    def testUpdate(self):
        self.failUnless(aituans.updaterMain())
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()