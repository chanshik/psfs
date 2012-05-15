#!/usr/bin/python

import fuse
import os
import sys
import stat
import errno
import logging
import re
import procpy

fuse.fuse_python_api = (0, 2)

def setUpLogging():
	def exceptionCallback(eType, eValue, eTraceBack):
		import cgitb

		txt = cgitb.text((eType, eValue, eTraceBack))

		logging.fatal(txt)
	
	logging.basicConfig(level=logging.DEBUG, format = '%(asctime)s %(levelname)s %(message)s',
			filename = '/tmp/psfs.log',
			filemode = 'a')

	consoleHandler = logging.StreamHandler(sys.stdout)
	consoleHandler.setLevel(logging.DEBUG)

	consoleFormatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
	consoleHandler.setFormatter(consoleFormatter)

	logging.getLogger().addHandler(consoleHandler)

	sys.excepthook = exceptionCallback

	logging.debug('Logging and exception handling has been set up')


class PsStat(fuse.Stat):
	def __init__(self):
		self.st_mode = 0
		self.st_ino = 0
		self.st_dev = 0
		self.st_nlink = 0
		self.st_uid = 0
		self.st_gid = 0
		self.st_size = 0
		self.st_atime = 0
		self.st_mtime = 0
		self.st_ctime = 0
		self.st_blocks = 0
		self.st_blksize = 0
		self.st_rdev = 0


class PsFS(fuse.Fuse):

	infoFiles = ['USER', 'PID', 'CPU', 'MEM', 'TTY', 'START', 'TIME', 'COMMAND']

	def __init__(self, *args, **kw):
		fuse.Fuse.__init__(self, *args, **kw)

	def getPid(self, procName):
		try:
			return int(re.search('\w+\((?P<num>\d+)\)', procName).group('num'))
		except AttributeError:
			return 0

	def getProcessInfo(self, pid):
		return procpy.readproc_by_pid(pid)

	def getChildProcessInfo(self, pid):
		results = []
		for proc in procpy.readproc():
			if proc['ppid'] == pid:
				results.append(proc)
		
		return results
	
	def isExist(self, parent, child):
		ppid = self.getPid(parent)
		pid = self.getPid(child)

		if ppid == 0 or pid == 0:
			return False

		info = self.getProcessInfo(pid)
		if info['ppid'] <> ppid:
			return False

		return True
	
	def makeProcName(self, procName, pid):
		return procName + '(' + str(pid) + ')'
			
	def readdir(self, path, offset):
		yield fuse.Direntry('.')
		yield fuse.Direntry('..')

		if path == "/":
			dentry = fuse.Direntry('init(1)')
			dentry.type = stat.S_IFDIR
			yield dentry
		else:
			for info in self.infoFiles:
				dentry = fuse.Direntry(info)
				dentry.type = stat.S_IFREG | 0444
				yield dentry

			elem = path.split('/')
			pid = self.getPid(elem[-1])
			results = self.getChildProcessInfo(pid)

			for child in results:
				childProc = self.makeProcName(child['cmd'], child['tid'])
				dentry = fuse.Direntry(childProc)
				dentry.type = stat.S_IFDIR
				yield dentry
	
	def getattr(self, path):
		st = PsStat()
		elem = path.split('/')

		for info in self.infoFiles:
			if elem[-1] == info:
				st.st_mode = stat.S_IFREG | 0444
				st.st_ino = 0
				
				pid = self.getPid(elem[-2])
				st.st_size = len(self.getFileInfo(pid, info)) + 1
				return st

		if path == "/":
			st.st_mode = stat.S_IFDIR | 0555
			st.st_nlink = 2
			return st
		elif path == "/init(1)":
			st.st_mode = stat.S_IFDIR | 0555
			st.st_ino = 1
			st.st_nlink = 2
			return st
		else:
			if self.isExist(elem[-2], elem[-1]):
				st.st_mode = stat.S_IFDIR | 0555
				st.st_nlink = 1
				return st
			
		return -errno.ENOENT
	
	def open(self, path, flags):
		if path == '/':
			return -errno.ENOENT

		elem = path.split('/')

		for info in self.infoFiles:
			if elem[-1] == info:
				return 0;

		return -errno.ENOENT
	
	def getFileInfo(self, pid, info):
		proc = self.getProcessInfo(pid)

		if info == "PID":
			return str(proc['tid'])
		elif info == "USER":
			return proc['ruser']
		elif info == "CPU":
			return proc['pcpustr']
		elif info == "MEM":
			return proc['pmemstr']
		elif info == "TTY":
			return proc['ttynam']
		elif info == "START":
			return "%02d:%02d" % (proc['start'][3], proc['start'][4])
		elif info == "TIME":
			return "%4d:%02d" % (proc['time'][0], proc['time'][1])
		elif info == "COMMAND":
			return ' '.join(proc['cmdline'])
		else:
			return ''


	def read(self, path, size, offset):
		if path == '/':
			return -errno.ENOENT

		elem = path.split('/')

		for info in self.infoFiles:
			if elem[-1] == info:
				pid = self.getPid(elem[-2])
				if pid == 0:
					return -errno.ENOENT

				return self.getFileInfo(pid, info) + '\n'

		return -errno.ENOENT
	
	def rmdir(self, path):
		elem = path.split('/')
		if elem[-1] == 'init(1)':
			return -errno.EINVAL

		pid = self.getPid(elem[-1])
		if pid == 0:
			return -errno.EINVAL

		killcmd = 'kill -9 ' + str(pid)
		os.system(killcmd)

		return 0


if __name__ == '__main__':

	setUpLogging()

	fs = PsFS()
	fs.parse(errex = 1)
	fs.flags = 0
	fs.multithreaded = 0
	fs.main()

