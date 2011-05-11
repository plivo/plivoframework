# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

import traceback
import urllib
import urllib2

try:
    import xml.etree.cElementTree as etree
except ImportError:
    from xml.etree.elementtree import ElementTree as etree

import gevent
import gevent.queue

from plivo.core.freeswitch.eventtypes import Event
from plivo.core.freeswitch.outboundsocket import OutboundEventSocket
from plivo.rest.freeswitch import verbs
from plivo.rest.freeswitch.rest_exceptions import RESTFormatException, \
                                    RESTSyntaxException, \
                                    UnrecognizedVerbException



class RequestLogger(object):
    def __init__(self, logger, request_id=0):
        self.logger = logger
        self.request_id = request_id

    def info(self, msg):
        self.logger.info('(%s) %s' % (self.request_id, str(msg)))

    def warn(self, msg):
        self.logger.warn('(%s) %s' % (self.request_id, str(msg)))

    def error(self, msg):
        self.logger.error('(%s) %s' % (self.request_id, str(msg)))

    def debug(self, msg):
        self.logger.debug('(%s) %s' % (self.request_id, str(msg)))



class PlivoOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, default_answer_url, filter=None, request_id=0):
        self._request_id = request_id
        self._log = log
        self.log = RequestLogger(logger=self._log, request_id=self._request_id)
        self.xml_response = ""
        self.parsed_verbs = []
        self.lexed_xml_response = []
        self.answer_url = ""
        self.direction = ""
        self.params = None
        self._action_queue = gevent.queue.Queue()
        self.default_answer_url = default_answer_url
        self.answered = False
        self.no_answer_verbs = ['Pause', 'Reject', 'Preanswer', 'Dial']
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocol_send(self, command, args=""):
        self.log.debug("Execute: %s args='%s'" % (command, args))
        response = super(PlivoOutboundEventSocket, self)._protocol_send(
                                                                command, args)
        self.log.debug("Response: %s" % str(response))
        return response

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1):
        self.log.debug("Execute: %s args=%s, uuid='%s', lock=%s, loops=%d" \
                      % (name, str(args), uuid, str(lock), loops))
        response = super(PlivoOutboundEventSocket, self)._protocol_sendmsg(
                                                name, args, uuid, lock, loops)
        self.log.debug("Response: %s" % str(response))
        return response

    # Commands like `playback`, `record` etc. return +OK "immediately".
    # However, the only way to know if the audio file played has finished,
    # is by handling CHANNEL_EXECUTE_COMPLETE events.
    #
    # Such events are received by the on_channel_execute_complete method
    #
    # In order to "block" the execution of our service until the
    # playback is finished, we use a syncronized queue from gevent
    # and wait for such event to come. The on_channel_execute_complete
    # method will put that event in the queue, then we may continue working.
    #
    # However, other events will still come, like for instance, DTMF.
    def on_channel_execute_complete(self, event):
        if event.get_header('Application') == 'playback' or \
            event.get_header('Application') == 'record' or \
            event.get_header('Application') == 'play_and_get_digits' or \
            event.get_header('Application') == 'bridge' or \
            event.get_header('Application') == 'speak':
            self._action_queue.put(event)

    def on_channel_hangup(self, event):
        hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s has hung up (%s)' % (self.get_channel_unique_id(), hangup_cause))

    def on_channel_hangup_complete(self, event):
        hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s hangup complete (%s)' % (self.get_channel_unique_id(), hangup_cause))

    def disconnect(self):
        self.log.debug("Releasing connection ...")
        super(PlivoOutboundEventSocket, self).disconnect()
        # prevent command to be stuck while waiting response
        self._action_queue.put_nowait(Event())
        self.log.debug("Releasing connection done")

    def run(self):
        # Only catch events for this channel
        self.myevents()
        # Linger to get all remaining events before closing
        self.linger()

        channel = self.get_channel()
        self.call_uuid = self.get_channel_unique_id()
        called_no = channel.get_header('Caller-Destination-Number')
        from_no = channel.get_header('Caller-Caller-ID-Number')
        self.direction = channel.get_header('Call-Direction')

        aleg_uuid = ""
        aleg_request_uuid = ""
        if self.direction == 'outbound':
            aleg_uuid = channel.get_header('Caller-Unique-ID')
            aleg_request_uuid = channel.get_header('variable_request_uuid')
            self.answer_url = channel.get_header('variable_answer_url')
        else:
            self.answer_url = self.default_answer_url

        # Post to ANSWER URL and get XML Response
        self.params = {
                  'call_uuid': self.call_uuid,
                  'called_no': called_no,
                  'from_no': from_no,
                  'direction': self.direction,
                  'aleg_uuid': aleg_uuid,
                  'aleg_request_uuid': aleg_request_uuid
        }
        self.log.debug("Processing call ...")
        self.process_call()
        self.log.debug("Processing call done")

    def process_call(self):
        self.fetch_xml()
        if self.xml_response:
            try:
                self.lex_xml()
                self.parse_xml()
                self.execute_xml()
            except Exception, e:
                # if error occurs during xml parsing
                # log exception and hangup
                self.log.error(str(e))
                [self.log.error(line) for line in \
                                            traceback.format_exc().splitlines()]
                self.log.error("xml error, hanging up !")
                self.hangup(cause="DESTINATION_OUT_OF_ORDER")
        else:
            self.log.warn("No xml response, hanging up !")
            self.hangup()

    def fetch_xml(self):
        encoded_params = urllib.urlencode(self.params)
        request = urllib2.Request(self.answer_url, encoded_params)
        try:
            self.xml_response = urllib2.urlopen(request).read()
            self.log.info("Posted to %s with %s" % (self.answer_url,
                                                                self.params))
        except Exception, e:
            self.log.error("Post to %s with %s --Error: %s" \
                                        % (self.answer_url, self.params, e))

    def lex_xml(self):
        # 1. Parse XML into a doctring
        xml_str = ' '.join(self.xml_response.split())
        try:
            doc = etree.fromstring(xml_str)
        except Exception, e:
            raise RESTSyntaxException("Invalid RESTXML Response Syntax: %s" % str(e))

        # 2. Make sure the document has a <Response> root
        if doc.tag != "Response":
            raise RESTFormatException("No Response Tag Present")

        # 3. Make sure we recognize all the Verbs in the xml
        for element in doc:
            invalid_verbs = []
            if not hasattr(verbs, element.tag):
                invalid_verbs.append(element.tag)
            else:
                self.lexed_xml_response.append(element)
            if invalid_verbs:
                raise UnrecognizedVerbException("Unrecognized verbs: %s"
                                                        % invalid_verbs)

    def parse_xml(self):
        # Check all Verb names
        for element in self.lexed_xml_response:
            verb = getattr(verbs, str(element.tag), None)
            verb_instance = verb()
            verb_instance.parse_verb(element, self.answer_url)
            self.parsed_verbs.append(verb_instance)
            # Validate, Parse and store the nested childrens inside main verb
            self.validate_verb(element, verb_instance)

    def validate_verb(self, element, verb_instance):
        children = element.getchildren()
        if children and not verb_instance.nestables:
            raise RESTFormatException("%s cannot have any children!"
                                                        % verb_instance.name)
        for child in children:
            if child.tag not in verb_instance.nestables:
                raise RESTFormatException("%s is not nestable inside %s"
                                                % (child, verb_instance.name))
            else:
                self.parse_children(child, verb_instance)

    def parse_children(self, child_element, parent_instance):
        child_verb = getattr(verbs, str(child_element.tag), None)
        child_verb_instance = child_verb()
        child_verb_instance.parse_verb(child_element, None)
        parent_instance.children.append(child_verb_instance)

    def execute_xml(self):
        for verb in self.parsed_verbs:
            if hasattr(verbs, "prepare"):
                # :TODO Prepare verbs concurrently
                verb.prepare()
            # Check If inbound call
            if self.direction == 'inbound':
                # Dont answer the call if verb is a reject, pause or preanswer
                # Only execute the verbs
                if self.answered == False and \
                    verb.name not in self.no_answer_verbs:
                    self.answer()
                    self.answered = True
            verb.run(self)
