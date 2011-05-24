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
from plivo.rest.freeswitch.exceptions import RESTFormatException, \
                                    RESTSyntaxException, \
                                    UnrecognizedGrammarException, \
                                    RESTRedirectException


MAX_REDIRECT = 10000



class Hangup(Exception): pass


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
    WAIT_FOR_ACTIONS = ('playback',
                        'record',
                        'play_and_get_digits',
                        'bridge',
                        'say',
                        'sleep',
                        'speak',
                        'conference',
                       )

    def __init__(self, socket, address, log,
                 default_answer_url=None,
                 default_hangup_url=None,
                 default_http_method = "POST",
                 auth_id="",
                 auth_token="",
                 request_id=0,
                 filter=None):
        # the request id
        self._request_id = request_id
        # set logger
        self._log = log
        self.log = RequestLogger(logger=self._log, request_id=self._request_id)
        # set auth id/token
        self.auth_id = auth_id
        self.auth_token = auth_token
        # set all settings empty
        self.xml_response = ""
        self.parsed_grammar = []
        self.lexed_xml_response = []
        self.target_url = ""
        self.hangup_url = ""
        self.direction = ""
        self.session_params = {}
        self._hangup_cause = ''
        # create queue for waiting actions
        self._action_queue = gevent.queue.Queue()
        # set default answer url
        self.default_answer_url = default_answer_url
        # set default hangup_url
        if default_hangup_url:
            self.default_hangup_url = default_hangup_url
        else:
            self.default_hangup_url = self.default_answer_url
        # set default http method POST or GET
        self.default_http_method = default_http_method
        # set answered flag
        self.answered = False
        self.no_answer_grammar = ['Wait', 'Reject', 'Preanswer', 'Dial']
        # inherits from outboundsocket
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocol_send(self, command, args=""):
        """Access parent method _protocol_send
        """
        self.log.debug("Execute: %s args='%s'" % (command, args))
        response = super(PlivoOutboundEventSocket, self)._protocol_send(
                                                                command, args)
        self.log.debug("Response: %s" % str(response))
        if self.has_hangup():
            raise Hangup()
        return response

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1):
        """Access parent method _protocol_sendmsg
        """
        self.log.debug("Execute: %s args=%s, uuid='%s', lock=%s, loops=%d" \
                      % (name, str(args), uuid, str(lock), loops))
        response = super(PlivoOutboundEventSocket, self)._protocol_sendmsg(
                                                name, args, uuid, lock, loops)
        self.log.debug("Response: %s" % str(response))
        if self.has_hangup():
            raise Hangup()
        return response

    def wait_for_action(self):
        """
        Wait until an action is over
        """
        return self._action_queue.get()

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
        if event['Application'] in self.WAIT_FOR_ACTIONS:
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
            self.session_params['HangupCause'] = self._hangup_cause
            self.session_params['CallStatus'] = 'completed'
            self.log.info("Sending hangup to %s" % hangup_url)
            gevent.spawn(self.send_to_url, hangup_url)

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
            aleg_request_uuid = channel.get_header('variable_plivo_request_uuid')
            # Look for target url in order below :
            #  get transfer_url from channel variable
            #  get answer_url from channel variable
            xfer_url = channel.get_header('variable_plivo_transfer_url')
            answer_url = channel.get_header('variable_plivo_answer_url')
            if xfer_url:
                self.target_url = xfer_url
                self.log.info("Using Call TransferUrl %s" % self.target_url)
            elif answer_url:
                self.target_url = answer_url
                self.log.info("Using Call AnswerUrl %s" % self.target_url)
            else:
                self.log.error("Aborting -- No Call Url found !")
                return
            # Look for a sched_hangup_id
            sched_hangup_id = channel.get_header('variable_plivo_sched_hangup_id')
            # Don't post hangup in outbound direction
            self.default_hangup_url = None
            self.hangup_url = None
            call_state = 'in-progress'
        else:
            # Look for target url in order below :
            #  get transfer_url from channel variable
            #  get answer_url from channel variable
            #  get default answer_url
            xfer_url = self.get_var('plivo_transfer_url')
            answer_url = self.get_var('plivo_answer_url')
            default_answer_url = self.default_answer_url
            if xfer_url:
                self.target_url = xfer_url
                self.log.info("Using Call TransferUrl %s" % self.target_url)
            elif answer_url:
                self.target_url = answer_url
                self.log.info("Using Call AnswerUrl %s" % self.target_url)
            elif default_answer_url:
                self.target_url = default_answer_url
                self.log.info("Using Call DefaultAnswerUrl %s" % self.target_url)
            else:
                self.log.error("Aborting -- No Call Url found !")
                return
            # Look for a sched_hangup_id
            sched_hangup_id = self.get_var('plivo_sched_hangup_id')
            # Look for hangup_url
            self.hangup_url = self.get_var('plivo_hangup_url')
            call_state = 'ringing'

        if not sched_hangup_id:
            sched_hangup_id = ""

        # Post to ANSWER URL and get XML Response
        self.session_params = {
                  'CallUUID': self.call_uuid,
                  'To': called_no,
                  'From': from_no,
                  'Direction': self.direction,
                  'CallStatus' : call_state
        }
        # Add Params if present
        if aleg_uuid:
            self.session_params['ALegUUID'] = aleg_uuid
        if aleg_request_uuid:
            self.session_params['ALegRequestUUID'] = aleg_request_uuid
        if sched_hangup_id:
            self.session_params['ScheduledHangupId'] = sched_hangup_id

        # Remove sched_hangup_id from channel vars
        if sched_hangup_id:
            self.unset("plivo_sched_hangup_id")
        # Run application
        self.log.info("Processing Call")
        try:
            self.process_call()
            return
        except Hangup:
            self.log.warn("Channel has hung up, breaking Processing Call")
        except Exception, e:
            self.log.error("Processing Call Failure !")
            # If error occurs during xml parsing
            # log exception and break
            self.log.error(str(e))
            [ self.log.error(line) for line in \
                        traceback.format_exc().splitlines() ]
        self.log.info("Processing Call Ended")

    def process_call(self):
        """Method to proceed on the call
        This will fetch the XML, validate the response
        Parse the XML and Execute it
        """
        params = {}
        for x in range(MAX_REDIRECT):
            try:
                if self.has_hangup():
                    raise Hangup()
                self.fetch_xml(params=params)
                if not self.xml_response:
                    self.log.warn("No XML Response")
                    return
                self.lex_xml()
                self.parse_xml()
                self.execute_xml()
                self.log.info("End of RESTXML")
                return
            except RESTRedirectException, redirect:
                if self.has_hangup():
                    raise Hangup()
                # Set target URL to Redirect URL
                # Set method to Redirect method
                # Set additional params to Redirect params
                self.target_url = redirect.get_url()
                fetch_method = redirect.get_method()
                params = redirect.get_params()
                if not fetch_method:
                    fetch_method = 'POST'
                # Reset all the previous response and grammar
                self.xml_response = ""
                self.parsed_grammar = []
                self.lexed_xml_response = []
                self.log.info("Redirecting to %s to fetch RESTXML" \
                                            % self.target_url)
                gevent.sleep(0.010)
                continue
        self.log.warn("Max Redirect Reached !")

    def fetch_xml(self, params={}, method=None):
        """
        This method will retrieve the xml from the answer_url
        The url result expected is an XML content which will be stored in
        xml_response
        """
        self.log.info("Fetching %s RESTXML from %s with %s" \
                                % (method, self.target_url, params))
        self.xml_response = self.send_to_url(self.target_url, params, method)
        self.log.info("Requested RESTXML to %s with %s" \
                                % (self.target_url, params))

    def send_to_url(self, url=None, params={}, method=None):
        """
        This method will do an http POST or GET request to the Url
        """
        if method is None:
            method = self.default_http_method

        if not url:
            self.log.warn("Cannot send, no url !")
            return None
        params.update(self.session_params)
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        try:
            data = http_obj.fetch_response(url, params, method)
            self.log.info("Posted to %s with %s -- Result: %s" \
                                            % (url, params, data))
            return data
        except Exception, e:
            self.log.error("Post to %s with %s -- Error: %s" \
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
            raise RESTSyntaxException("Invalid RESTXML Response Syntax: %s" \
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
            grammar_instance.parse_grammar(element, self.target_url)
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
