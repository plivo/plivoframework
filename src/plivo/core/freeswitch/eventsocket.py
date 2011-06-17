# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

"""
Event Socket class
"""

from uuid import uuid1

import gevent
import gevent.event
import gevent.socket as socket
from gevent.coros import RLock
import gevent.pool
from gevent import GreenletExit

from plivo.core.freeswitch.commands import Commands
from plivo.core.freeswitch.eventtypes import Event, CommandResponse, ApiResponse, BgapiResponse, JsonEvent
from plivo.core.errors import LimitExceededError, ConnectError


EOL = "\n"
MAXLINES_PER_EVENT = 1000



class InternalSyncError(Exception):
    pass


class EventSocket(Commands):
    '''EventSocket class'''
    def __init__(self, filter="ALL", eventjson=True, pool_size=5000, trace=False):
        self._is_eventjson = eventjson
        # Callbacks for reading events and sending responses.
        self._response_callbacks = {'api/response':self._api_response,
                                    'command/reply':self._command_reply,
                                    'text/disconnect-notice':self._disconnect_notice,
                                    'text/event-json':self._event_json,
                                    'text/event-plain':self._event_plain
                                   }
        # Closing state flag
        self._closing_state = False
        # Default event filter.
        self._filter = filter
        # Commands pool list
        self._commands_pool = []
        # Lock to force eventsocket commands to be sequential.
        self._lock = RLock()
        # Sets connected to False.
        self.connected = False
        # Sets greenlet handler to None
        self._g_handler = None
        # Build events callbacks dict
        self._event_callbacks = {}
        for meth in dir(self):
            if meth[:3] == 'on_':
                event_name = meth[3:].upper()
                func = getattr(self, meth, None)
                if func:
                    self._event_callbacks[event_name] = func
        unbound = getattr(self, 'unbound_event', None)
        self._event_callbacks['unbound_event'] = unbound
        # Set greenlet spawner
        if pool_size > 0:
            self.pool = gevent.pool.Pool(pool_size)
            self._spawn = self.pool.spawn
        else:
            self._spawn = gevent.spawn_raw
        # set tracer
        try:
            logger = self.log
        except AttributeError:
            logger = None
        if logger and trace is True:
            self.trace = self._trace
        else:
            self.trace = self._notrace

    def _trace(self, msg):
        self.log.debug("[TRACE] %s" % str(msg))

    def _notrace(self, msg):
        pass

    def is_connected(self):
        '''
        Checks if connected and authenticated to eventsocket.

        Returns True or False.
        '''
        return self.connected

    def start_event_handler(self):
        '''
        Starts Event handler in background.
        '''
        self._g_handler = gevent.spawn(self.handle_events)

    def stop_event_handler(self):
        '''
        Stops Event handler.
        '''
        if self._g_handler and not self._g_handler.ready():
            self._g_handler.kill()

    def handle_events(self):
        '''
        Gets and Dispatches events in an endless loop using gevent spawn.
        '''
        self.trace("handle_events started")
        while True:
            # Gets event and dispatches to handler.
            try:
                self.get_event()
                gevent.sleep(0)
                if not self.connected:
                    self.trace("Not connected !")
                    break
            except LimitExceededError:
                break
            except ConnectError:
                break
            except socket.error, se:
                break
            except GreenletExit, e:
                break
            except Exception, ex:
                self.trace("handle_events error => %s" % str(ex))
        self.trace("handle_events stopped now")
        self.connected = False
        # prevent any pending request to be stuck
        self._flush_commands()
        return

    def read_event(self):
        '''
        Reads one Event from socket until EOL.

        Returns Event instance.

        Raises LimitExceededError if MAXLINES_PER_EVENT is reached.
        '''
        buff = ''
        for x in range(MAXLINES_PER_EVENT):
            line = self.transport.read_line()
            if line == '':
                self.trace("no more data in read_event !")
                raise ConnectError("connection closed")
            elif line == EOL:
                # When matches EOL, creates Event and returns it.
                return Event(buff)
            else:
                # Else appends line to current buffer.
                buff = "%s%s" % (buff, line)
        raise LimitExceededError("max lines per event (%d) reached" % MAXLINES_PER_EVENT)

    def read_raw(self, event):
        '''
        Reads raw data based on Event Content-Length.

        Returns raw string or None if not found.
        '''
        length = event.get_content_length()
        # Reads length bytes if length > 0
        if length:
            res = self.transport.read(int(length))
            if not res or len(res) != int(length):
                raise ConnectError("no more data in read_raw !")
            return res
        return None

    def read_raw_response(self, event, raw):
        '''
        Extracts raw response from raw buffer and length based on Event Content-Length.

        Returns raw string or None if not found.
        '''
        length = event.get_content_length()
        if length:
            return raw[-length:]
        return None

    def get_event(self):
        '''
        Gets complete Event, and processes response callback.
        '''
        self.trace("read_event")
        event = self.read_event()
        self.trace("read_event done")
        # Gets callback response for this event
        try:
            func = self._response_callbacks[event.get_content_type()]
        except KeyError:
            self.trace("no callback for %s" % str(event))
            return
        self.trace("callback %s" % str(func))
        # If callback response found, starts this method to get final event.
        event = func(event)
        self.trace("callback %s done" % str(func))
        if event and event['Event-Name']:
            self.trace("dispatch")
            self._spawn(self.dispatch_event, event)
            self.trace("dispatch done")

    def _api_response(self, event):
        '''
        Receives api/response callback.
        '''
        # Gets raw data for this event.
        raw = self.read_raw(event)
        # If raw was found, this is our Event body.
        if raw:
            event.set_body(raw)
        # Wake up waiting command.
        try:
            _cmd_uuid, _async_res = self._commands_pool.pop(0)
        except (IndexError, ValueError):
            raise InternalSyncError("Cannot wakeup command !")
        _async_res.set((_cmd_uuid, event))
        return None

    def _command_reply(self, event):
        '''
        Receives command/reply callback.
        '''
        # Wake up waiting command.
        try:
            _cmd_uuid, _async_res = self._commands_pool.pop(0)
        except (IndexError, ValueError):
            raise InternalSyncError("Cannot wakeup command !")
        _async_res.set((_cmd_uuid, event))
        return None

    def _event_plain(self, event):
        '''
        Receives text/event-plain callback.
        '''
        # Gets raw data for this event
        raw = self.read_raw(event)
        # If raw was found drops current event
        # and replaces with Event created from raw
        if raw:
            event = Event(raw)
            # Gets raw response from Event Content-Length header
            # and raw buffer
            raw_response = self.read_raw_response(event, raw)
            # If rawresponse was found, this is our Event body
            if raw_response:
                event.set_body(raw_response)
        # Returns Event
        return event

    def _event_json(self, event):
        '''
        Receives text/event-json callback.
        '''
        # Gets json data for this event
        json_data = self.read_raw(event)
        # If raw was found drops current event
        # and replaces with JsonEvent created from json_data
        if json_data:
            event = JsonEvent(json_data)
        # Returns Event
        return event

    def _disconnect_notice(self, event):
        '''
        Receives text/disconnect-notice callback.
        '''
        self._closing_state = True
        # Gets raw data for this event
        raw = self.read_raw(event)
        if raw:
            event = Event(raw)
            # Gets raw response from Event Content-Length header
            # and raw buffer
            raw_response = self.read_raw_response(event, raw)
            # If rawresponse was found, this is our Event body
            if raw_response:
                event.set_body(raw_response)
        return None

    def dispatch_event(self, event):
        '''
        Dispatches one event with callback.

        E.g. Receives Background_Job event and calls on_background_job function.
        '''
        # When no callbacks found, try unbound_event.
        try:
            callback = self._event_callbacks[event['Event-Name']]
        except KeyError:
            callback = self._event_callbacks['unbound_event']
        if not callback:
            return
        # Calls callback.
        try:
            callback(event)
        except:
            self.callback_failure(event)

    def callback_failure(self, event):
        '''
        Called when callback to an event fails.

        Can be implemented by the subclass.
        '''
        pass

    def connect(self):
        '''
        Connects to eventsocket.
        '''
        self._closing_state = False

    def disconnect(self):
        '''
        Disconnect and release socket and finally kill event handler.
        '''
        self.connected = False
        self.trace("releasing ...")
        try:
            # avoid handler stuck
            self._g_handler.get(block=True, timeout=2.0)
        except:
            self.trace("releasing forced")
            self._g_handler.kill()
        self.trace("releasing done")
        # prevent any pending request to be stuck
        self._flush_commands()

    def _flush_commands(self):
        # Flush all commands pending
        for _cmd_uuid, _async_res in self._commands_pool:
            _async_res.set((_cmd_uuid, Event()))

    def _send(self, cmd):
        self.transport.write(cmd + EOL*2)

    def _sendmsg(self, name, arg=None, uuid="", lock=False, loops=1, async=False):
        msg = "sendmsg %s\ncall-command: execute\nexecute-app-name: %s\n" \
                % (uuid, name)
        if lock is True:
            msg += "event-lock: true\n"
        if loops > 1:
            msg += "loops: %d\n" % loops
        if async is True:
            msg += "async: true\n"
        if arg:
            arglen = len(arg)
            msg += "content-type: text/plain\ncontent-length: %d\n\n%s\n" % (arglen, arg)
        self.transport.write(msg + EOL)

    def _protocol_send(self, command, args=""):
        if self._closing_state:
            return Event()
        self.trace("_protocol_send %s %s" % (command, args))
        # Append command to pool
        # and send it to eventsocket
        _cmd_uuid = str(uuid1())
        _async_res = gevent.event.AsyncResult()
        with self._lock:
            self._commands_pool.append((_cmd_uuid, _async_res))
            self._send("%s %s" % (command, args))
        self.trace("_protocol_send %s wait ..." % command)
        _uuid, event = _async_res.get()
        if _cmd_uuid != _uuid:
            raise InternalSyncError("in _protocol_send")
        # Casts Event to appropriate event type :
        # Casts to ApiResponse, if event is api
        if command == 'api':
            event = ApiResponse.cast(event)
        # Casts to BgapiResponse, if event is bgapi
        elif command == "bgapi":
            event = BgapiResponse.cast(event)
        # Casts to CommandResponse by default
        else:
            event = CommandResponse.cast(event)
        self.trace("_protocol_send %s done" % command)
        return event

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1, async=False):
        if self._closing_state:
            return Event()
        self.trace("_protocol_sendmsg %s" % name)
        # Append command to pool
        # and send it to eventsocket
        _cmd_uuid = str(uuid1())
        _async_res = gevent.event.AsyncResult()
        with self._lock:
            self._commands_pool.append((_cmd_uuid, _async_res))
            self._sendmsg(name, args, uuid, lock, loops, async)
        self.trace("_protocol_sendmsg %s wait ..." % name)
        _uuid, event = _async_res.get()
        if _cmd_uuid != _uuid:
            raise InternalSyncError("in _protocol_sendmsg")
        self.trace("_protocol_sendmsg %s done" % name)
        # Always casts Event to CommandResponse
        return CommandResponse.cast(event)
