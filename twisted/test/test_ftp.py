# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from pyunit import unittest
from twisted.protocols import ftp, loopback
from twisted.internet import reactor
from twisted.protocols.protocol import Protocol

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO
import sys, types, os.path

FTP_PORT = 2121

class FTPTest(unittest.TestCase):
    def setUp(self):
        """Creates an FTP server
        
        The FTP will serve files from the directory this module resides in.
        """
        self.serverFactory = ftp.FTPFactory()
        import test_ftp         # Myself
        serverPath = os.path.dirname(test_ftp.__file__)
        self.serverFactory.root = serverPath

        self.serverPort = reactor.listenTCP(FTP_PORT, self.serverFactory)

    def tearDown(self):
        self.serverPort.loseConnection()
        # Make sure the port really is closed, to avoid "address already in use"
        # errors.
        reactor.iterate()


class FTPClientTests(FTPTest):
    """These test the FTP Client against the FTP Server"""
    passive = 0
    
    def errback(self, failure):
        try:
            self.fail('Errback called: ' + str(failure))
        except self.failureException, e:
            self.error = sys.exc_info()
            raise

    def callback(self, result):
        self.result = result
        
    def testFileListings(self):
        if hasattr(self, 'result'):
            del self.result

        # Connect
        client = ftp.FTPClient(passive=self.passive)
        reactor.clientTCP('localhost', FTP_PORT, client)

        # Issue the command and set the callbacks
        fileList = ftp.FTPFileListProtocol()
        d = client.list('.', fileList)
        d.addCallbacks(self.callback, self.errback)
        d.arm()

        # Wait for the result
        reactor.callLater(5, self.errback, "timed out") # timeout so we don't freeze
        while not hasattr(self, 'result') and not hasattr(self, 'error'):
            reactor.iterate()
        
        error = getattr(self, 'error', None)
        if error:
            raise error[0], error[1], error[2]

        # Check that the listing contains this file (test_ftp.py)
        filenames = map(lambda file: file['filename'], fileList.files)
        self.failUnless('test_ftp.py' not in filenames, 
                        'test_ftp.py not in file listing')

    def testRetr(self):
        if hasattr(self, 'result'):
            del self.result

        # Connect
        client = ftp.FTPClient(passive=self.passive)
        reactor.clientTCP('localhost', FTP_PORT, client)

        # Download this module's file (test_ftp.py/.pyc/.pyo)
        import test_ftp
        thisFile = test_ftp.__file__
        class BufferProtocol(Protocol):
            def __init__(self):
                self.buf = StringIO()
            def dataReceived(self, data):
                self.buf.write(data)
        
        proto = BufferProtocol()
        d = client.retr(os.path.basename(thisFile), proto)
        d.addCallbacks(self.callback, self.errback)
        d.arm()

        # Wait for a result
        reactor.callLater(5, self.errback, "timed out") # timeout so we don't freeze
        while not hasattr(self, 'result') and not hasattr(self, 'error'):
            reactor.iterate()

        error = getattr(self, 'error', None)
        if error:
            raise error[0], error[1], error[2]

        # Check that the file is the same as read directly off the disk
        self.failUnless(type(self.result) == types.ListType,
                        'callback result is wrong type: ' + str(self.result))
        data = proto.buf.getvalue()
        self.failUnless(data == open(thisFile, "rb").read(),
                        'RETRieved file does not match original')

        
    def testBadLogin(self):
        client = ftp.FTPClient(passive=self.passive, username='badperson')

        # Deferreds catch Exceptions raised in callbacks, which interferes with
        # unittest.TestCases, so we jump through a few hoops to make sure the
        # failure is triggered correctly.
        self.callbackException = None
        def badResult(result, self=self):
            try:
                self.fail('Got this file listing when login should have failed: ' +
                          str(result))
            except self.failureException, e:
                self.callbackException = sys.exc_info()
                raise

        errors = [None, None]
        def gotError(failure, x, errors_=errors):
            errors_[x] = failure

        # These LIST commands should should both fail
        d = client.list('.', ftp.FTPFileListProtocol()) 
        d.addCallbacks(badResult, gotError, errbackArgs=(0,)).arm()
        d = client.list('.', ftp.FTPFileListProtocol()) 
        d.addCallbacks(badResult, gotError, errbackArgs=(1,)).arm()

        reactor.clientTCP('localhost', FTP_PORT, client)
        while None in errors and not self.callbackException:
            reactor.iterate()

        if self.callbackException:
            ce = self.callbackException
            raise ce[0], ce[1], ce[2]


class FTPPassiveClientTests(FTPClientTests):
    """Identical to FTPClientTests, except with passive transfers.
    
    That's right ladies and gentlemen!  I double the number of tests with a
    trivial subclass!  Hahaha!
    """
    passive = 1


class FTPFileListingTests(unittest.TestCase):
    def testOneLine(self):
        # This example line taken from the docstring for FTPFileListProtocol
        fileList = ftp.FTPFileListProtocol()
        class PrintLine(Protocol):
            def connectionMade(self):
                self.transport.write('-rw-r--r--   1 root     other        531 Jan 29 03:26 README\n')
                self.transport.loseConnection()
        loopback.loopback(PrintLine(), fileList)
        file = fileList.files[0]
        self.failUnless(file['filetype'] == '-', 'misparsed fileitem')
        self.failUnless(file['perms'] == 'rw-r--r--', 'misparsed perms')
        self.failUnless(file['owner'] == 'root', 'misparsed fileitem')
        self.failUnless(file['group'] == 'other', 'misparsed fileitem')
        self.failUnless(file['size'] == 531, 'misparsed fileitem')
        self.failUnless(file['date'] == 'Jan 29 03:26', 'misparsed fileitem')
        self.failUnless(file['filename'] == 'README', 'misparsed fileitem')


if __name__ == '__main__':
    unittest.main()
