# -*- coding: utf-8  -*-
"""
Mechanics to slow down wiki read and/or write rate.
"""
#
# (C) Pywikipedia bot team, 2008
#
# Distributed under the terms of the MIT license.
#
__version__ = '$Id: 08b1383aa58d7aa8424a0c03bd610646e206ed77 $'

import wikipedia as pywikibot
import config

import math
import threading
import time

pid = False     # global process identifier
                # when the first Throttle is instantiated, it will set this
                # variable to a positive integer, which will apply to all
                # throttle objects created by this process.


class Throttle(object):
    """Control rate of access to wiki server

    Calling this object blocks the calling thread until at least 'delay'
    seconds have passed since the previous call.

    The framework initiates two Throttle objects: get_throttle to control
    the rate of read access, and put_throttle to control the rate of write
    access.

    """
    def __init__(self, mindelay=None, maxdelay=None, writedelay=None,
                 multiplydelay=True, verbosedelay=False, write=False):
        self.lock = threading.RLock()
        self.mysite = None
        self.ctrlfilename = config.datafilepath('pywikibot', 'throttle.ctrl')
        self.mindelay = mindelay
        if self.mindelay is None:
            self.mindelay = config.minthrottle
        self.maxdelay = maxdelay
        if self.maxdelay is None:
            self.maxdelay = config.maxthrottle
        self.writedelay = writedelay
        if self.writedelay is None:
            self.writedelay = config.put_throttle
        self.last_read = 0
        self.last_write = 0
        self.next_multiplicity = 1.0
        self.checkdelay = 120  # Check logfile again after this many seconds
        self.dropdelay = 360   # Ignore processes that have not made
                               # a check in this many seconds
        self.releasepid = 1200 # Free the process id after this many seconds
        self.lastwait = 0.0
        self.delay = 0
        self.checktime = 0
        self.verbosedelay = verbosedelay
        self.multiplydelay = multiplydelay
        if self.multiplydelay:
            self.checkMultiplicity()
        self.setDelay()
        self.write = write

    def checkMultiplicity(self):
        """Count running processes for site and set process_multiplicity."""
        global pid
        self.lock.acquire()
        mysite = self.mysite = str(pywikibot.getSite())
        if pywikibot.verbose:
            pywikibot.output(u"Checking multiplicity: pid = %(pid)s" % globals())
        try:
            processes = []
            my_pid = pid or 1  # start at 1 if global pid not yet set
            count = 1
            # open throttle.log
            try:
                f = open(self.ctrlfilename, 'r')
            except IOError:
                if not pid:
                    pass
                else:
                    raise
            else:
                now = time.time()
                for line in f.readlines():
                    # parse line; format is "pid timestamp site"
                    try:
                        line = line.split(' ')
                        this_pid = int(line[0])
                        ptime = int(line[1].split('.')[0])
                        this_site = line[2].rstrip()
                    except (IndexError, ValueError):
                        continue    # Sometimes the file gets corrupted
                                    # ignore that line
                    if now - ptime > self.releasepid:
                        continue    # process has expired, drop from file
                    if now - ptime <= self.dropdelay \
                       and this_site == mysite \
                       and this_pid != pid:
                        count += 1
                    if this_site != self.mysite or this_pid != pid:
                        processes.append({'pid': this_pid,
                                          'time': ptime,
                                          'site': this_site})
                    if not pid and this_pid >= my_pid:
                        my_pid = this_pid+1 # next unused process id

            if not pid:
                pid = my_pid
            self.checktime = time.time()
            processes.append({'pid': pid,
                              'time': self.checktime,
                              'site': mysite})
            processes.sort(key=lambda p:(p['pid'], p['site']))
            try:
                f = open(self.ctrlfilename, 'w')
                for p in processes:
                    f.write("%(pid)s %(time)s %(site)s\n" % p)
            except IOError:
                pass
            else:
                f.close()
            self.process_multiplicity = count
            if self.verbosedelay or pywikibot.verbose:
                pywikibot.output(
                    u"Found %(count)s %(mysite)s processes running, including this one."
                    % locals())
        finally:
            self.lock.release()

    def setDelay(self, delay=None, writedelay=None, absolute=False):
        """Set the nominal delays in seconds. Defaults to config values."""
        self.lock.acquire()
        try:
            maxdelay = self.maxdelay
            if delay is None:
                delay = self.mindelay
            if writedelay is None:
                writedelay = config.put_throttle
            if absolute:
                self.maxdelay = delay
                self.mindelay = delay
            self.delay = delay
            self.writedelay = min(max(self.mindelay, writedelay),
                                  self.maxdelay)
            # Start the delay count now, not at the next check
            self.last_read = self.last_write = time.time()
        finally:
            self.lock.release()

    def getDelay(self, write=False):
        """Return the actual delay, accounting for multiple processes.

        This value is the maximum wait between reads/writes, not taking
        account of how much time has elapsed since the last access.

        """
        if write:
            thisdelay = self.writedelay
        else:
            thisdelay = self.delay
        if self.multiplydelay: # We're checking for multiple processes
            if time.time() > self.checktime + self.checkdelay:
                self.checkMultiplicity()
            if thisdelay < (self.mindelay * self.next_multiplicity):
                thisdelay = self.mindelay * self.next_multiplicity
            elif thisdelay > self.maxdelay:
                thisdelay = self.maxdelay
            thisdelay *= self.process_multiplicity
        return thisdelay

    def waittime(self, write=False):
        """Return waiting time in seconds if a query would be made right now"""
        # Take the previous requestsize in account calculating the desired
        # delay this time
        thisdelay = self.getDelay(write=write)
        now = time.time()
        if write:
            ago = now - self.last_write
        else:
            ago = now - self.last_read
        if ago < thisdelay:
            delta = thisdelay - ago
            return delta
        else:
            return 0.0

    def drop(self):
        """Remove me from the list of running bot processes."""
        # drop all throttles with this process's pid, regardless of site
        self.checktime = 0
        processes = []
        try:
            f = open(self.ctrlfilename, 'r')
        except IOError:
            return
        else:
            now = time.time()
            for line in f.readlines():
                try:
                    line = line.split(' ')
                    this_pid = int(line[0])
                    ptime = int(line[1].split('.')[0])
                    this_site = line[2].rstrip()
                except (IndexError,ValueError):
                    continue    # Sometimes the file gets corrupted
                                # ignore that line
                if now - ptime <= self.releasepid \
                   and this_pid != pid:
                    processes.append({'pid': this_pid,
                                      'time': ptime,
                                      'site': this_site})
        processes.sort(key=lambda p:p['pid'])
        try:
            f = open(self.ctrlfilename, 'w')
            for p in processes:
                f.write("%(pid)s %(time)s %(site)s\n" % p)
        except IOError:
            return
        f.close()

    def __call__(self, requestsize=1, write=False):
        """Block the calling program if the throttle time has not expired.

        Parameter requestsize is the number of Pages to be read/written;
        multiply delay time by an appropriate factor.

        Because this seizes the throttle lock, it will prevent any other
        thread from writing to the same site the script started with
        until the wait expires.

        """
        if pywikibot.simulate:
            pywikibot.output(u'\03{lightyellow}SIMULATION: %s_throttle skipped.\03{default}'%\
                             {True: u'put', False: u'get'}[write])
            return

        self.lock.acquire()
        try:
            wait = self.waittime(write=write or self.write)
            # Calculate the multiplicity of the next delay based on how
            # big the request is that is being posted now.
            # We want to add "one delay" for each factor of two in the
            # size of the request. Getting 64 pages at once allows 6 times
            # the delay time for the server.
            self.next_multiplicity = math.log(1+requestsize)/math.log(2.0)
            # Announce the delay if it exceeds a preset limit
            if wait > 0:
                if wait > config.noisysleep or pywikibot.verbose:
                    pywikibot.output(
                        u"Sleeping for %(wait).1f seconds, %(now)s"
                        % {'wait': wait,
                           'now' : time.strftime("%Y-%m-%d %H:%M:%S",
                                                 time.localtime())
                        } )
                time.sleep(wait)
            if write or self.write:
                self.last_write = time.time()
            else:
                self.last_read = time.time()
        finally:
            self.lock.release()

    def lag(self, lagtime):
        """Seize the throttle lock due to server lag.

        This will prevent any thread from accessing this site.

        """
        started = time.time()
        self.lock.acquire()
        try:
            # start at 1/2 the current server lag time
            # wait at least 5 seconds but not more than 120 seconds
            delay = min(max(5, lagtime//2), 120)
            # account for any time we waited while acquiring the lock
            wait = delay - (time.time() - started)
            if wait > 0:
                if wait > config.noisysleep:
                    pywikibot.output(
                        u"Sleeping for %(wait).1f seconds, %(now)s"
                        % {'wait': wait,
                           'now': time.strftime("%Y-%m-%d %H:%M:%S",
                                                time.localtime())
                        } )
                time.sleep(wait)
        finally:
            self.lock.release()

