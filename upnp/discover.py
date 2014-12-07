#!/usr/bin/python

# This file is part of pulseaudio-dlna.

# pulseaudio-dlna is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# pulseaudio-dlna is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with pulseaudio-dlna.  If not, see <http://www.gnu.org/licenses/>.

import socket as s
import renderer
import contextlib
import struct
import threading
import Queue
import time
import logging


class UpnpMediaRendererDiscover(object):

    SSDP_ADDRESS = '239.255.255.250'
    SSDP_PORT = 1900
    _threads = []

    MSEARCH = 'M-SEARCH * HTTP/1.1\r\n' + \
              'HOST: {}:{}\r\n'.format(SSDP_ADDRESS, SSDP_PORT) + \
              'MAN: "ssdp:discover"\r\n' + \
              'MX: 2\r\n' + \
              'ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n'
#              'MX: 5\r\n' + \
#              'ST: ssdp:all\r\n'

    def __init__(self, iface):
        logging.basicConfig(level=logging.DEBUG)

        self._queue = Queue.Queue()
        self.iface = iface
        self.renderers = []

    def startSearch(self, ttl=10, timeout=10):
        p = threading.Thread(target=self._poll, name="poll_for_MediaRenderer")
        t = threading.Thread(
            target=self._search,
            name="listen_for_MediaRenderer")
        self._threads.append(p)
        self._threads.append(t)
        p.start()
        t.start()

    def waitForFirstRenderer(self):
        logging.info("waitForFirstRenderer")
        if len(self.renderers) == 0:
            self._queue.get()
        logging.info("got first Renderer")

    def _poll(self, ttl=10, timeout=10):
        logging.info("start polling")
        s.setdefaulttimeout(timeout)
        sock = s.socket(s.AF_INET, s.SOCK_DGRAM, s.IPPROTO_UDP)
        sock.setsockopt(s.IPPROTO_IP, s.IP_MULTICAST_TTL, ttl)

        while True:
            logging.info("send discovery query")
            sock.sendto(self.MSEARCH, (self.SSDP_ADDRESS, self.SSDP_PORT))
            time.sleep(60)
        sock.close()

    def _search(self, ttl=10, timeout=10):
        logging.info("start receiving")
        s.setdefaulttimeout(timeout)
        rsock = s.socket(s.AF_INET, s.SOCK_DGRAM, s.IPPROTO_UDP)
        rsock.setsockopt(s.SOL_SOCKET, s.SO_REUSEADDR, 1)
        rsock.bind(('', self.SSDP_PORT))
        mreq = struct.pack("4sl", s.inet_aton(self.SSDP_ADDRESS), s.INADDR_ANY)

        rsock.setsockopt(s.IPPROTO_IP, s.IP_ADD_MEMBERSHIP, mreq)

        buffer_size = 1024
        while True:
            try:
                header, address = rsock.recvfrom(buffer_size)
                logging.debug("received response from " + str(address))
                self._header_received(header, address)
                if len(self.renderers) >= 1:
                    self._queue.put(1)
            except s.timeout:
                pass
        rsock.close()

    def _header_received(self, header, address):
        if "MediaRenderer" not in header:
            return

        (ip, port) = address
        try:
            upnp_device = renderer.UpnpMediaRendererFactory.from_header(
                address,
                header,
                renderer.CoinedUpnpMediaRenderer)
            logging.debug("found MediaRenderer at " + str(address))
            if upnp_device not in self.renderers:
                self.renderers.append(upnp_device)
            logging.debug(
                "Currently MediaRenderer at " + len(
                    self.renderers) + " registered.")
        except:
            pass
