#!/usr/bin/env python

# Author: Wojciech Walczak <wojtek.gminick.walczak@gmail.com>
# Copyright 2008 Wojciech Walczak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


"""
procpy.py module provides three classes:

   - Proc:
     import procpy
     procs = procpy.Proc()
     procs.pids # a tuple with all the PIDs found in /proc
     procs.procs # a dictionary; each PID is a key:
                 # procs.procs[PID]
     procs.pidinfo(<PID>) # same as procs.procs[PID]
     procs.update() # re-read the /proc directory

   - ProcRT:
     import procpy
     procs = procpy.ProcRT()
     procs.pids # a tuple with all the PIDs found in /proc
     procs.pidinfo(<PID>) # returns a dictionary with info for the given PID

   - Pid:
     import procpy
     proc = procpy.Pid(<PID>)
     ### Pid instance has no dictionaries or functions; the data is being
     ### kept in attributes:
     proc.cmd # returns 'python'
     proc.cwd # returns current working directory
     proc.environ # returns a dictionary of environment variables

The dictionary returned by pidinfo() method (for both Proc and ProcRT classes)
as well as the attributes of Pid instance are:

   cwd -> current working directory
   exe -> executed program
   root -> /proc/root
   maps -> files mapped by the process (as in /proc/PID/maps)
   fds -> a dictionary: { file_desriptor=file_name, ... }

The only difference is that Pid class instance has 'parent' attribute:
   import procpy
   proc = procpy.Pid(<PID>)
   proc.parent.cmd # command of the parent process
   proc.parent.environ # and so on...
"""

import os
import sys

# do not import the _procpy module in here when running doctests
if __name__ != '__main__':
   from _procpy import error, meminfo, uptime, readproc,\
                       readproc_by_pid, readproc_dict

class _ProcDirInternals(object):
   def __getmaps__(self, pid):
      """Parse the /proc/PID/maps file. Return a list of mapped files
      for the PID 'pid'.
      Usage:
      >>> import procpy
      >>> proc_table = procpy.Proc()
      >>> last_pid = proc_table.pids[-1]
      >>> proc = proc_table.pidinfo(last_pid)
      >>> proc.has_key('maps')
      True

      """

      maps = []

      try:
         mapsfile = open("/proc/%d/maps" % (pid), 'r')
      except IOError:
         return maps

      for line in mapsfile:
         try:
            fname = line.split()[5]
         except IndexError:
            continue

         if fname not in maps:
            maps.append(fname)

      mapsfile.close()
      return maps

   def __getlink__(self, pid, fnam):
      """Read links for /proc/PID/[cwd, exe, root].
      Usage:
      >>> import os
      >>> import procpy
      >>> proc_table = procpy.Proc()
      >>> last_pid = proc_table.pids[-1]
      >>> proc_table.procs[last_pid]['cwd'] == os.getcwd()
      True

      """
      try:
         return os.readlink("/proc/%d/%s" % (pid, fnam))
      except:
         return ''

   def __getfds__(self, pid):
      """Read the contents of /proc/PID/fd/ directory. Return a directory:
      { 'file_descriptor': 'file_link', ... }
      Usage:
      >>> import procpy
      >>> proc_table=procpy.Proc()
      >>> last_pid = proc_table.pids[-1]
      >>> fds = proc_table.pidinfo(last_pid)['fds']
      >>> fds.has_key(0) # stdin
      True
      >>> fds.has_key(1) # stdout
      True
      >>> fds.has_key(2) # stderr
      True
      """
      
      fds = {}

      try:
         dir_entries = os.listdir("/proc/%d/fd/" % (pid))
      except:
         return fds

      for dir_entry in dir_entries:
         if dir_entry == '.' or dir_entry == '..':
            continue
         
         try:
            fds[int(dir_entry)] = os.readlink('/proc/%d/fd/%s' % (pid, dir_entry))
         except:
            continue

      del dir_entries
      return fds


class _InitProc(_ProcDirInternals):
   """This class is inherited by Proc class. Basically it contains
   update method used by Proc class at its initialization."""

   def __getpids__(self):
      """Returns a tuple of all the PIDs found in /proc directory"""

      pids = []
      for p in self.procs:
         pids.append(p)
      return tuple(sorted(pids))

   def update(self):
      """Sets self.procs as a dictionary of dictionaries:
         { PID:  { 'tid': ..., 'ppid': ..., 'cmdline': ..., ... }, 
           PID2: { 'tid': ..., 'ppid': ..., 'cmdline': ..., ... }, 
           ... }"""
      self.procs = readproc_dict()
      self.pids = self.__getpids__()

      for pid in self.pids:
         self.procs[pid]['maps'] = self.__getmaps__(pid)
         self.procs[pid]['cwd'] = self.__getlink__(pid, 'cwd')
         self.procs[pid]['exe'] = self.__getlink__(pid, 'exe')
         self.procs[pid]['root'] = self.__getlink__(pid, 'root')
         self.procs[pid]['fds'] = self.__getfds__(pid)


class Proc(_InitProc):
   """   Read /proc directory for all the processes running at the momment.

   An instance of Proc class keeps the data gathered at initialization
   and does not update it automatically. Thus, you actually work with
   a process table that might be out of date at the momment of initializing
   an instance.
   Two situations are common here. First: one of the processes has finished
   its execution right after creation of an instance of Proc class but it
   still is present in self.procs dictionary). Second: a new process was
   executed right after creation of an instance of Proc class. You will not
   be noticed about this.
   You can update a process table in instance by calling update method.

   pp = procpy.Proc()

   and that's it. pp instance keeps some static data about your processes
   that were running at the momment of creating this class instance.
   You can of course update the informations kept by pp instance but you
   have to do it manually:

   pp.update()

   In case you need real-time access to process table see ProcRT class.
   """
   def __init__(self):
      self.update()

   def pidinfo(self, pid):
      return self.procs[pid]


class _InitProcRT(object):
   def __getpids__(self):
      import os, re
      pids = []
      for d in os.listdir("/proc/"):
         if re.match("\d+", d):
            pids.append(int(d))

      return tuple(pids)


class ProcRT(_InitProcRT, _ProcDirInternals):
   """Read /proc directory for all the processes running at the momment.

   ProcRT class makes it possible to work with real-time process table.
   This class is more cpu-time and memory consuming. The gain is that
   you always have accurate informations about processes running in your
   system.

#   >>> pp = procpy.ProcRT()
#   >>> pp.pids
#   ('1', '2', '3', [...all the rest of PIDS...], '3504', '3511')
#   >>> [we execute new bash process]
#   >>> pp.pids
#   ('1', '2', '3', [...all the rest of PIDS...], '3504', '3511', '3532')
#   >>> pp.pidinfo(3532)['cmdline']
#   ('/bin/bash',)
#   >>> [we close this bash process (PID==3532)]
#   >>> pp.pids
#   ('1', '2', '3', [...all the rest of PIDS...], '3504', '3511')
#   >>> pp.pidinfo(3532)['cmdline']
#   Traceback (most recent call last):
#     File "<stdin>", line 1, in <module>
#     File "procpy.py", line 105, in pidinfo
#       pids = property(update_pids, doc="Read /proc [...]")
#   procpy.error: PID not found.
#   >>>

   >>> import os
   >>> import procpy
   >>> pp = procpy.ProcRT()
   >>> pp.pids[0] == 1
   True
   >>> isinstance(pp.pidinfo(os.getpid())['cmdline'], tuple)
   True
"""

   def __init__(self):
      pass

   def __update_pids(self):
      return self.__getpids__()

   pids = property(__update_pids, doc="Read /proc everytime self.pids is called")

   def pidinfo(self, pid):
      self.pinfo = readproc_by_pid(pid)
      self.pinfo['maps'] = self.__getmaps__(pid)
      self.pinfo['cwd'] = self.__getlink__(pid, 'cwd')
      self.pinfo['exe'] = self.__getlink__(pid, 'exe')
      self.pinfo['root'] = self.__getlink__(pid, 'root')
      self.pinfo['fds'] = self.__getfds__(pid)

      return self.pinfo


class _Parent(_ProcDirInternals):
   """Used by Pid class. Creates and fills pid.parent attribute"""

   def __init__(self, ppid):
      self.pid = ppid
      pinfo = readproc_by_pid(ppid)
      pinfo['maps'] = self.__getmaps__(ppid)
      pinfo['cwd'] = self.__getlink__(ppid, 'cwd')
      pinfo['exe'] = self.__getlink__(ppid, 'exe')
      pinfo['root'] = self.__getlink__(ppid, 'root')
      pinfo['fds'] = self.__getfds__(ppid)

      for key in pinfo:
         setattr(self, key, pinfo[key])

      del pinfo


class Pid(_ProcDirInternals):
   """
   >>> import os
   >>> import procpy
   >>> pid = procpy.Pid(os.getpid())
   >>> isinstance(pid.cmdline, tuple)
   True
   >>> hasattr(pid, 'environ')
   True
   >>> hasattr(pid, 'parent')
   True
   >>> hasattr(pid.parent, 'environ')
   True
   >>> pid.parent.fds.has_key(0)
   True
   >>> pid.parent.fds.has_key(1)
   True
   >>> pid.parent.fds.has_key(2)
   True
   """
   def __init__(self, pid):
      self.pid = pid
      pinfo = readproc_by_pid(pid)
      pinfo['maps'] = self.__getmaps__(pid)
      pinfo['cwd'] = self.__getlink__(pid, 'cwd')
      pinfo['exe'] = self.__getlink__(pid, 'exe')
      pinfo['root'] = self.__getlink__(pid, 'root')
      pinfo['fds'] = self.__getfds__(pid)

      for key in pinfo:
         setattr(self, key, pinfo[key])

      if pinfo['ppid'] > 0:
         self.parent = _Parent(pinfo['ppid'])

      del pinfo

def _test():
   import doctest
   os.symlink('build/_procpy.so', '_procpy.so')

   try:
      import _procpy
   except ImportError:
      print '_procpy module not found. Try to run install.py module first.'
      os.remove('_procpy.so')
      sys.exit(1)

   doctest.testmod()
   os.remove('_procpy.so')

if __name__ == '__main__':
   _test()
