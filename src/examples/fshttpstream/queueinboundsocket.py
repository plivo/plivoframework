# -*- coding: utf-8 -*-
import gevent
import gevent.queue
from telephonie.core.inboundsocket import InboundEventSocket
from telephonie.core.errors import ConnectError
from telephonie.utils.logger import StdoutLogger


class QueueInboundEventSocket(InboundEventSocket):
    """
    QueueInboundEventSocket class.
    
    All Freeswitch events are pushed to a internal queue. 

    All events can be consumed with wait_for_event method.
    """
    def __init__(self, host, port, password, filter="ALL", pool_size=500, connect_timeout=5, log=None):
        InboundEventSocket.__init__(self, host, port, password, filter, pool_size, connect_timeout)
        if not log:
            self.log = StdoutLogger()
        else:
            self.log = log
        self.event_queue = gevent.queue.Queue()

    def unbound_event(self, event):
        """
        Put all events in queue.
        """
        self.event_queue.put(event)

    def wait_for_event(self):
        """
        Wait until one event is available in queue.
        """
        return self.event_queue.get()

    def start(self):
        """
        Start inbound connection to Freeswitch with auto reconnection on failure.
        """
        self.log.info("Start QueueInboundEventSocket %s:%d with filter %s" \
            % (self.transport.host, self.transport.port, self._filter))
        while True:
            try:
                self.connect()
                self.log.info("QueueInboundEventSocket connected")
                self.serve_forever()
            except ConnectError, e:
                self.log.error("QueueInboundEventSocket ConnectError: %s" % e.message)
            except (SystemExit, KeyboardInterrupt): 
                break
            self.log.error("QueueInboundEventSocket closed, try to reconnect ...")
            gevent.sleep(1.0)
        self.log.info("QueueInboundEventSocket terminated")
        

if __name__ == '__main__':
    c = QueueInboundEventSocket('127.0.0.1', 8021, 'ClueCon')
    c.start()    

