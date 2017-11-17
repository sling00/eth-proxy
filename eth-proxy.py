#!/usr/bin/env python
# -*- coding:utf-8 -*-

import time
import os
import sys
import socket
import subprocess
from stratum import settings
import re
import string
import stratum.logger
log = stratum.logger.get_logger('proxy')
proxywallet = subprocess.check_output(['/opt/ethos/sbin/ethos-readconf', 'proxywallet']).strip()
proxypool1 = subprocess.check_output(['/opt/ethos/sbin/ethos-readconf', 'proxypool1']).strip()
proxypool2 = subprocess.check_output(['/opt/ethos/sbin/ethos-readconf', 'proxypool2']).strip()
proxypool3 = subprocess.check_output(['/opt/ethos/sbin/ethos-readconf', 'proxypool3']).strip()
proxypool4 = subprocess.check_output(['/opt/ethos/sbin/ethos-readconf', 'proxypool4']).strip()
backuppool1 = None
backuppool2 = None
backuppool3 = None
if len(proxypool1):
	mainpool, mainport = proxypool1.split(':', 1)
	mainport = int(float(mainport))
if len(proxypool2):
	backuppool1, backupport1 = proxypool2.split(':', 1)
	backupport1 = int(float(backupport1))
if len(proxypool3):
	backuppool2, backupport2 = proxypool3.split(':', 1)
	backupport2 = int(float(backupport2))
if len(proxypool4):
	backuppool3, backupport3 = proxypool4.split(':', 1)
	backupport3 = int(float(backupport3))
if __name__ == '__main__':
    settings.CUSTOM_EMAIL = settings.MONITORING_EMAIL if settings.MONITORING_EMAIL and settings.MONITORING else ""

from twisted.internet import reactor, defer, protocol
from twisted.internet import reactor as reactor2
from stratum.socket_transport import SocketTransportFactory, SocketTransportClientFactory
from stratum.services import ServiceEventHandler
from twisted.web.server import Site
from stratum.custom_exceptions import TransportException

from mining_libs import getwork_listener
from mining_libs import client_service
from mining_libs import jobs
from mining_libs import version

def on_shutdown(f):
    '''Clean environment properly'''
    log.info("Shutting down proxy...")
    if os.path.isfile('eth-proxy.pid'):
        os.remove('eth-proxy.pid')
    f.is_reconnecting = False # Don't let stratum factory to reconnect again

# Support main connection
@defer.inlineCallbacks
def ping(f):
    if not f.is_reconnecting:
        return
    try:
        yield (f.rpc('eth_getWork', [], ''))
        if f.is_failover:
            reactor.callLater(30, ping, f)
        else:
            reactor.callLater(5, ping, f)
    except Exception:
        pass

@defer.inlineCallbacks
def on_connect(f):
    '''Callback when proxy get connected to the pool'''
    log.info("Connected to Stratum pool at %s:%d" % f.main_host)
    f.is_connected = True
    f.remote_ip = f.client._get_ip()
    #reactor.callLater(30, f.client.transport.loseConnection)

    # Hook to on_connect again
    f.on_connect.addCallback(on_connect)

    # Get first job and user_id
    debug = "_debug" if settings.DEBUG else ""
    initial_job = (yield f.rpc('eth_submitLogin', [proxywallet, settings.CUSTOM_EMAIL], 'Proxy_'+version.VERSION+debug))

    reactor.callLater(0, ping, f)

    defer.returnValue(f)

def on_disconnect(f):
    '''Callback when proxy get disconnected from the pool'''
    log.info("Disconnected from Stratum pool at %s:%d" % f.main_host)
    f.is_connected = False
    f.on_disconnect.addCallback(on_disconnect)

@defer.inlineCallbacks
def main():
    reactor.disconnectAll()

    log.warning("Ethereum Stratum proxy version: %s" % version.VERSION)

    # Connect to Stratum pool, main monitoring connection
    log.warning("Trying to connect to Stratum pool at %s:%d" % (mainpool, mainport))
    f = SocketTransportClientFactory(mainpool, mainport,
                debug=settings.DEBUG, proxy=None,
                event_handler=client_service.ClientMiningService)

    f1 = None
    f2 = None
    f3 = None
    if settings.POOL_FAILOVER_ENABLE:
        if not (backuppool1 is None):
            log.warning("Trying to connect to failover Stratum pool-1 at %s:%d" % (backuppool1, backupport1))
            f1 = SocketTransportClientFactory(backuppool1, backupport1,
                    debug=settings.DEBUG, proxy=None,
                    event_handler=client_service.ClientMiningService)
            f1.is_failover = True
            
        if not (backuppool2 is None):
            log.warning("Trying to connect to failover Stratum pool-2 at %s:%d" % (backuppool2, backupport2))
            f2 = SocketTransportClientFactory(backuppool2, backupport2,
                    debug=settings.DEBUG, proxy=None,
                    event_handler=client_service.ClientMiningService)
            f2.is_failover = True
        if not (backuppool3 is None):    
            log.warning("Trying to connect to failover Stratum pool-3 at %s:%d" % (backuppool3, backupport3))
            f3 = SocketTransportClientFactory(backuppool3, backupport3,
                    debug=settings.DEBUG, proxy=None,
                    event_handler=client_service.ClientMiningService)
            f3.is_failover = True

    job_registry = jobs.JobRegistry(f,f1,f2,f3)
    client_service.ClientMiningService.job_registry = job_registry
    client_service.ClientMiningService.reset_timeout()

    f.on_connect.addCallback(on_connect)
    f.on_disconnect.addCallback(on_disconnect)
    # Cleanup properly on shutdown
    reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f)
    if f1:
        f1.on_connect.addCallback(on_connect)
        f1.on_disconnect.addCallback(on_disconnect)
        reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f1)

    if f2:
        f2.on_connect.addCallback(on_connect)
        f2.on_disconnect.addCallback(on_disconnect)
        reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f2)

    if f3:
        f3.on_connect.addCallback(on_connect)
        f3.on_disconnect.addCallback(on_disconnect)
        reactor.addSystemEventTrigger('before', 'shutdown', on_shutdown, f3)


    # Block until proxy connect to the pool
    try:
        yield f.on_connect
    except TransportException:
        log.error("First pool server must be online during proxy startup.  Dying Gracefully.")
	reactor.stop()
	reactor.removeAll()
        return

    if len(proxywallet)!=42 and len(proxywallet)!=40:
        conn = reactor.listenTCP(settings.PORT, Site(getwork_listener.Root(job_registry, False)), interface=settings.HOST)
    else: 
        conn = reactor.listenTCP(settings.PORT, Site(getwork_listener.Root(job_registry, settings.ENABLE_WORKER_ID)), interface=settings.HOST)
    try:
        conn.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) # Enable keepalive packets
        conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 60) # Seconds before sending keepalive probes
        conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 1) # Interval in seconds between keepalive probes
        conn.socket.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 5) # Failed keepalive probles before declaring other end dead
    except:
        pass # Some socket features are not available on all platforms (you can guess which one)

    log.warning("-----------------------------------------------------------------------")
    if settings.HOST == '0.0.0.0':
        log.warning("PROXY IS LISTENING ON ALL IPs ON PORT %d" % settings.PORT)
    else:
        log.warning("LISTENING FOR MINERS ON http://%s:%d" % (settings.HOST, settings.PORT))
    log.warning("-----------------------------------------------------------------------")
    log.warning("Wallet: %s" % proxywallet)
    if len(proxywallet)!=42 and len(proxywallet)!=40:
        log.warning("Wallet is not 40/42 Characters in Length, WORKER ID DISABLED")
        log.warning("OK if using non-eth address based pool authentication")
        log.warning("Otherwise - BAD ETH WALLET")
    else:
	log.warning("Worker ID enabled: %s" % settings.ENABLE_WORKER_ID)
    if settings.MONITORING:
        log.warning("Email monitoring on %s" % settings.MONITORING_EMAIL)
    else:
        log.warning("Email monitoring disabled")
    log.warning("Failover enabled: %s" % settings.POOL_FAILOVER_ENABLE)
    log.warning("-----------------------------------------------------------------------")

if __name__ == '__main__':
    fp = file("/var/run/eth-proxy.pid", 'w')
    fp.write(str(os.getpid()))
    fp.close()
    main()
    reactor.run()
