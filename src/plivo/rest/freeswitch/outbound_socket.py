# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

import traceback
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from xml.etree.elementtree import ElementTree as etree

import gevent
import gevent.queue

from plivo.core.freeswitch.eventtypes import Event
from plivo.rest.freeswitch.helpers import HTTPRequest
from plivo.core.freeswitch.outboundsocket import OutboundEventSocket
from plivo.rest.freeswitch import grammar
from plivo.rest.freeswitch.rest_exceptions import RESTFormatException, \
                                    RESTSyntaxException, \
                                    UnrecognizedGrammarException, \
                                    RESTRedirectException


MAX_REDIRECT = 10000


class RequestLogger(object):
    """
    Class RequestLogger

    This Class allows a quick way to log a message with request ID
    """
    def __init__(self, logger, request_id=0):
        self.logger = logger
        self.request_id = request_id

    def info(self, msg):
        """Log info level"""
        self.logger.info('(%s) %s' % (self.request_id, str(msg)))

    def warn(self, msg):
        """Log warn level"""
        self.logger.warn('(%s) %s' % (self.request_id, str(msg)))

    def error(self, msg):
        """Log error level"""
        self.logger.error('(%s) %s' % (self.request_id, str(msg)))

    def debug(self, msg):
        """Log debug level"""
        self.logger.debug('(%s) %s' % (self.request_id, str(msg)))



class PlivoOutboundEventSocket(OutboundEventSocket):
    """Class PlivoOutboundEventSocket

    An instance of this class is created every time an incoming call is received.
    The instance requests for a XML grammar set to execute the call and acts as a
    bridge between Event_Socket and the web application
    """
    def __init__(self, socket, address, log,
                 default_answer_url=None,
                 default_hangup_url=None,
                 auth_id="",
                 auth_token="",
                 request_id=0,
                 filter=None):
        self._request_id = request_id
        self._log = log
        self.log = RequestLogger(logger=self._log, request_id=self._request_id)
        self.xml_response = ""
        self.parsed_grammar = []
        self.lexed_xml_response = []
        self.answer_url = ""
        self.hangup_url = ""
        self.direction = ""
        self.params = None
        self._action_queue = gevent.queue.Queue()
        self.default_answer_url = default_answer_url
        self.default_hangup_url = default_hangup_url
        self.answered = False
        self._hangup_cause = ''
        self.no_answer_grammar = ['Wait', 'Reject', 'Preanswer', 'Dial']
        self.auth_id = auth_id
        self.auth_token = auth_token
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocol_send(self, command, args=""):
        """Access parent method _protocol_send
        """
        self.log.debug("Execute: %s args='%s'" % (command, args))
        response = super(PlivoOutboundEventSocket, self)._protocol_send(
                                                                command, args)
        self.log.debug("Response: %s" % str(response))
        return response

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1):
        """Access parent method _protocol_sendmsg
        """
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
    # playback is finished, we use a synchronized queue from gevent
    # and wait for such event to come. The on_channel_execute_complete
    # method will put that event in the queue, then we may continue working.
    #
    # However, other events will still come, like for instance, DTMF.
    def on_channel_execute_complete(self, event):
        if event.get_header('Application') == 'playback' or \
            event.get_header('Application') == 'record' or \
            event.get_header('Application') == 'play_and_get_digits' or \
            event.get_header('Application') == 'bridge' or \
            event.get_header('Application') == 'say' or \
            event.get_header('Application') == 'speak':
            self._action_queue.put(event)

    def on_channel_hangup(self, event):
        self._hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s has hung up (%s)' %
                      (self.get_channel_unique_id(), self._hangup_cause))
        if self.hangup_url:
            hangup_url = self.hangup_url
        elif self.default_hangup_url:
            hangup_url = self.default_hangup_url
        if hangup_url:
            self.params.update({'hangupCause': self._hangup_cause})
            self.log.info("Posting hangup to %s" % hangup_url)
            self.post_to_url(hangup_url, params)

    def on_channel_hangup_complete(self, event):
        if not self._hangup_cause:
            self._hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s hangup completed (%s)' %
                      (self.get_channel_unique_id(), self._hangup_cause))

    def has_hangup(self):
        if self._hangup_cause:
            return True
        return False

    def get_hangup_cause(self):
        return self._hangup_cause

    def disconnect(self):
        self.log.debug("Releasing Connection ...")
        super(PlivoOutboundEventSocket, self).disconnect()
        # Prevent command to be stuck while waiting response
        self._action_queue.put_nowait(Event())
        self.log.debug("Releasing Connection Done")

    def run(self):
        self.resume()
        # Only catch events for this channel
        self.myevents()
        # Linger to get all remaining events before closing
        self.linger()

        self.set("hangup_after_bridge=false")

        channel = self.get_channel()
        self.call_uuid = self.get_channel_unique_id()
        called_no = channel.get_header('Caller-Destination-Number')
        from_no = channel.get_header('Caller-Caller-ID-Number')
        self.direction = channel.get_header('Call-Direction')
        aleg_uuid = ""
        aleg_request_uuid = ""

        if self.direction == 'outbound':
            # Look for variables in channel headers
            aleg_uuid = channel.get_header('Caller-Unique-ID')
            aleg_request_uuid = channel.get_header('variable_request_uuid')
            self.answer_url = channel.get_header('variable_answer_url')
            sched_hangup_id = channel.get_header('variable_sched_hangup_id')
            # Don't post hangup in outbound direction
            self.default_hangup_url = None
            self.hangup_url = None
        else:
            # Look for an answer url in order below :
            #  get transfer_url from channel variable
            #  get answer_url from channel variable
            #  get default answer_url
            self.answer_url = self.get_var('transfer_url')
            if not self.answer_url:
                self.answer_url = self.get_var('answer_url')
            if not self.answer_url:
                self.answer_url = self.default_answer_url
            # Look for a sched_hangup_id
            sched_hangup_id = self.get_var('sched_hangup_id')
            # Look for hangup_url
            self.hangup_url = self.get_var('hangup_url')

        if not sched_hangup_id:
            sched_hangup_id = ""

        # Post to ANSWER URL and get XML Response
        self.params = {
                  'call_uuid': self.call_uuid,
                  'called_no': called_no,
                  'from_no': from_no,
                  'direction': self.direction,
                  'aleg_uuid': aleg_uuid,
                  'aleg_request_uuid': aleg_request_uuid,
                  'sched_hangup_id': sched_hangup_id
        }
        # Remove sched_hangup_id from channel vars
        if sched_hangup_id:
            self.unset("sched_hangup_id")
        # Run application
        self.log.debug("Processing Call")
        self.process_call()
        self.log.debug("Processing Call Done")

    def process_call(self):
        """Method to proceed on the call
        This will fetch the XML, validate the response
        Parse the XML and Execute it
        """
        for x in range(MAX_REDIRECT):
            try:
                if self.has_hangup():
                    self.log.warn("Channel has hung up, breaking Processing Call")
                    return
                self.fetch_xml(method='POST')
                if not self.xml_response:
                    self.log.warn("No XML Response")
                    return
                self.lex_xml()
                self.parse_xml()
                self.execute_xml()
                self.log.info("End of RESTXML")
                return
            except RESTRedirectException, redirect:
                # Set Answer URL to Redirect URL
                self.answer_url = redirect.get_url()
                fetch_method = redirect.get_method()
                # Reset all the previous response and grammar
                self.xml_response = ""
                self.parsed_grammar = []
                self.lexed_xml_response = []
                self.log.info("Redirecting to %s to fetch RESTXML" \
                                            % self.answer_url)
                gevent.sleep(0.010)
                continue
            except Exception, e:
                # If error occurs during xml parsing
                # log exception and break
                self.log.error(str(e))
                [ self.log.error(line) for line in \
                            traceback.format_exc().splitlines() ]
                self.log.error("XML error")
                return
        self.log.warn("Max Redirect reached !")

    def fetch_xml(self, method='POST'):
        """
        This method will retrieve the xml from the answer_url
        The url result expected is an XML content which will be stored in
        xml_response
        """
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        self.xml_response = http_obj.fetch_response(self.answer_url,
                                                    self.params, method)
        self.log.info("Requested RESTXML to %s with %s" \
                                % (self.answer_url, self.params))

    def post_to_url(self, url=None, params={}):
        """
        This method will do an http POST request to the Url
        """
        if not url:
            return None
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        try:
            data = http_obj.fetch_response(url, params, method='POST')
            self.log.info("Posted to %s with %s --Result: %s"
                                            % (url, params, data))
            return data
        except Exception, e:
            self.log.error("Post to %s with %s --Error: %s"
                                            % (url, params, e))
        return None

    def lex_xml(self):
        """
        Validate the XML document and make sure we recognize all Grammar
        """
        # Parse XML into a doctring
        xml_str = ' '.join(self.xml_response.split())
        try:
            #convert the string into an Element instance
            doc = etree.fromstring(xml_str)
        except Exception, e:
            raise RESTSyntaxException("Invalid RESTXML Response Syntax: %s"
                        % str(e))

        # Make sure the document has a <Response> root
        if doc.tag != "Response":
            raise RESTFormatException("No Response Tag Present")

        # Make sure we recognize all the Grammar in the xml
        for element in doc:
            invalid_grammar = []
            if not hasattr(grammar, element.tag):
                invalid_grammar.append(element.tag)
            else:
                self.lexed_xml_response.append(element)
            if invalid_grammar:
                raise UnrecognizedGrammarException("Unrecognized Grammar: %s"
                                                        % invalid_grammar)

    def parse_xml(self):
        """
        This method will parse the XML and add the Grammar into parsed_grammar
        """
        # Check all Grammar element names
        for element in self.lexed_xml_response:
            grammar_element = getattr(grammar, str(element.tag), None)
            grammar_instance = grammar_element()
            grammar_instance.parse_grammar(element, self.answer_url)
            self.parsed_grammar.append(grammar_instance)
            # Validate, Parse & Store the nested children
            # inside the main grammar element
            self.validate_grammar(element, grammar_instance)

    def validate_grammar(self, element, grammar_instance):
        children = element.getchildren()
        if children and not grammar_instance.nestables:
            raise RESTFormatException("%s cannot have any children!"
                                            % grammar_instance.name)
        for child in children:
            if child.tag not in grammar_instance.nestables:
                raise RESTFormatException("%s is not nestable inside %s"
                                            % (child, grammar_instance.name))
            else:
                self.parse_children(child, grammar_instance)

    def parse_children(self, child_element, parent_instance):
        child_grammar_element = getattr(grammar, str(child_element.tag), None)
        child_grammar_instance = child_grammar_element()
        child_grammar_instance.parse_grammar(child_element, None)
        parent_instance.children.append(child_grammar_instance)

    def execute_xml(self):
        for grammar_element in self.parsed_grammar:
            if hasattr(grammar, "prepare"):
                # TODO Prepare grammar concurrently
                grammar_element.prepare()
            # Check if it's an inbound call
            if self.direction == 'inbound':
                # Don't answer the call if grammar is of type no answer
                # Only execute the grammar
                if self.answered == False and \
                    grammar_element.name not in self.no_answer_grammar:
                    self.answer()
                    self.answered = True
            grammar_element.run(self)
