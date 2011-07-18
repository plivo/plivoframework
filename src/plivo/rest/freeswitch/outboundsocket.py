# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

import os.path
import traceback
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from xml.etree.elementtree import ElementTree as etree

import gevent
import gevent.queue
from gevent import spawn_raw

from plivo.core.freeswitch.eventtypes import Event
from plivo.rest.freeswitch.helpers import HTTPRequest, get_substring
from plivo.core.freeswitch.outboundsocket import OutboundEventSocket
from plivo.rest.freeswitch import elements
from plivo.rest.freeswitch.exceptions import RESTFormatException, \
                                    RESTSyntaxException, \
                                    UnrecognizedElementException, \
                                    RESTRedirectException, \
                                    RESTHangup


MAX_REDIRECT = 1000


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
    The instance requests for a XML element set to execute the call and acts as a
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
                        'park',
                       )
    NO_ANSWER_ELEMENTS = ('Wait',
                          'PreAnswer',
                          'Dial',
                          'Hangup',
                         )

    def __init__(self, socket, address, log,
                 default_answer_url=None,
                 default_hangup_url=None,
                 default_http_method='POST',
                 extra_fs_vars=None,
                 auth_id='',
                 auth_token='',
                 request_id=0,
                 trace=False):
        # the request id
        self._request_id = request_id
        # set logger
        self._log = log
        self.log = RequestLogger(logger=self._log, request_id=self._request_id)
        # set auth id/token
        self.auth_id = auth_id
        self.auth_token = auth_token
        # set all settings empty
        self.xml_response = ''
        self.parsed_element = []
        self.lexed_xml_response = []
        self.target_url = ''
        self.hangup_url = ''
        self.session_params = {}
        self._hangup_cause = ''
        # flag to track current element
        self.current_element = None
        # create queue for waiting actions
        self._action_queue = gevent.queue.Queue()
        # set default answer url
        self.default_answer_url = default_answer_url
        # set default hangup_url
        self.default_hangup_url = default_hangup_url
        # set default http method POST or GET
        self.default_http_method = default_http_method
        # identify the extra FS variables to be passed along
        self.extra_fs_vars = extra_fs_vars
        # set answered flag
        self.answered = False
        # inherits from outboundsocket
        OutboundEventSocket.__init__(self, socket, address, filter=None,
                                     eventjson=True, pool_size=200, trace=trace)

    def _protocol_send(self, command, args=''):
        """Access parent method _protocol_send
        """
        self.log.debug("Execute: %s args='%s'" % (command, args))
        response = super(PlivoOutboundEventSocket, self)._protocol_send(
                                                                command, args)
        self.log.debug("Response: %s" % str(response))
        if self.has_hangup():
            raise RESTHangup()
        return response

    def _protocol_sendmsg(self, name, args=None, uuid='', lock=False, loops=1):
        """Access parent method _protocol_sendmsg
        """
        self.log.debug("Execute: %s args=%s, uuid='%s', lock=%s, loops=%d" \
                      % (name, str(args), uuid, str(lock), loops))
        response = super(PlivoOutboundEventSocket, self)._protocol_sendmsg(
                                                name, args, uuid, lock, loops)
        self.log.debug("Response: %s" % str(response))
        if self.has_hangup():
            raise RESTHangup()
        return response

    def wait_for_action(self):
        """
        Wait until an action is over
        and return action event.
        """
        return self._action_queue.get()

    # In order to "block" the execution of our service until the
    # command is finished, we use a synchronized queue from gevent
    # and wait for such event to come. The on_channel_execute_complete
    # method will put that event in the queue, then we may continue working.
    # However, other events will still come, like for instance, DTMF.
    def on_channel_execute_complete(self, event):
        if event['Application'] in self.WAIT_FOR_ACTIONS:
            # If transfer has begun, put empty event to break current action
            if event['variable_plivo_transfer_progress'] == 'true':
                self._action_queue.put(Event())
            else:
                self._action_queue.put(event)

    def on_channel_hangup(self, event):
        """
        Capture Channel Hangup
        """
        self._hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s has hung up (%s)' %
                      (self.get_channel_unique_id(), self._hangup_cause))
        if self.hangup_url:
            hangup_url = self.hangup_url
        elif self.default_hangup_url:
            hangup_url = self.default_hangup_url
        else:
            hangup_url = None
        if hangup_url:
            self.session_params['HangupCause'] = self._hangup_cause
            self.session_params['CallStatus'] = 'completed'
            self.log.info("Sending hangup to %s" % hangup_url)
            spawn_raw(self.send_to_url, hangup_url)
        # post record if found
        record_file = event['variable_plivo_record_file']
        if record_file:
            try:
                params = {}
                filepath, filename = os.path.split(record_file)
                filename, fileformat = os.path.splitext(filename)
                fileformat = fileformat.lstrip('.')
                action = event["variable_plivo_record_action"]
                method = event["variable_plivo_record_method"]
                both_legs = event["variable_plivo_record_both_legs"]
                try:
                    record_ms = int(event["variable_record_ms"])
                except ValueError:
                    record_ms = "-1"
                digits = event["variable_playback_terminator_used"]
                if not digits:
                    digits = ""
                params['RecordingFileFormat'] = fileformat
                params['RecordingFilePath'] = filepath
                params['RecordingFilename'] = filename
                params['RecordingFullFilePath'] = record_file
                params['RecordingDuration'] = record_ms
                params['Digits'] = digits
                self.log.warn('Send record info after hangup: %s' % str(params))
                spawn_raw(self.send_to_url, action, params, method)
            except Exception, e:
                self.log.error('Failed to send record info after hangup: %s' % str(e))
        # Prevent command to be stuck while waiting response
        self._action_queue.put_nowait(Event())

    def on_custom(self, event):
        if self.current_element == 'Conference':
            # special case to get Member-ID for Conference
            if event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'add-member' \
                and event['Unique-ID'] == self.get_channel_unique_id():
                self.log.debug("Entered conference")
                self._action_queue.put(event)
            # special case for hangupOnStar in Conference
            elif event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'kick' \
                and event['Unique-ID'] == self.get_channel_unique_id():
                room = event['Conference-Name']
                member_id = event['Member-ID']
                if room and member_id:
                    self.bgapi("conference %s kick %s" % (room, member_id))
                    self.log.warn("Conference Room %s, member %s pressed '*', kicked now !" \
                            % (room, member_id))
            # special case to send callback for Conference
            elif event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'digits-match' \
                and event['Unique-ID'] == self.get_channel_unique_id():
                self.log.debug("Digits match on conference")
                digits_action = event['Callback-Url'] 
                digits_method = event['Callback-Method']
                if digits_action and digits_method:
                    params = {}
                    params['ConferenceMemberID'] = event['Member-ID'] or ''
                    params['ConferenceUUID'] = event['Conference-Unique-ID'] or ''
                    params['ConferenceName'] = event['Conference-Name'] or ''
                    params['ConferenceDigitsMatch'] = event['Digits-Match'] or ''
                    params['ConferenceAction'] = 'digits'
                    spawn_raw(self.send_to_url, digits_action, params, digits_method)

    '''
    def on_dtmf(self, event):
        # special case to hangupOnStar in conference
        if self.current_element == 'Conference' and event['DTMF-Digit'] == '*':
            self._action_queue.put(event)
    '''

    def has_hangup(self):
        if self._hangup_cause:
            return True
        return False

    def get_hangup_cause(self):
        return self._hangup_cause

    def get_extra_fs_vars(self):
        channel = self.get_channel()
        if self.extra_fs_vars is not None:
            extra_vars = self.extra_fs_vars.split(',')
            for var in extra_vars:
                var = var.strip()
                val = channel.get_header(var)
                if var and val:
                    self.session_params[var] = val

    def disconnect(self):
        # Prevent command to be stuck while waiting response
        try:
            self._action_queue.put_nowait(Event())
        except gevent.queue.Full:
            pass
        self.log.debug('Releasing Connection ...')
        super(PlivoOutboundEventSocket, self).disconnect()
        self.log.debug('Releasing Connection Done')

    def run(self):
        try:
            self._run()
        except RESTHangup:
            self.log.warn('Hangup')

    def _run(self):
        self.connect()
        #self.filter('Event-Name /(CHANNEL_HANGUP|CHANNEL_EXECUTE_COMPLETE|CUSTOM)/')
        self.resume()
        # Linger to get all remaining events before closing
        self.linger()
        self.myevents()
        if self._is_eventjson:
            self.eventjson('CUSTOM conference::maintenance')
        else:
            self.eventplain('CUSTOM conference::maintenance')
        # Set plivo app flag
        self.set('plivo_app=true')
        # Don't hangup after bridge
        self.set('hangup_after_bridge=false')
        channel = self.get_channel()
        self.call_uuid = self.get_channel_unique_id()
        called_no = channel.get_header('Caller-Destination-Number')
        from_no = channel.get_header('Caller-Caller-ID-Number')
        # Set To to Session Params
        self.session_params['To'] = called_no.lstrip('+')
        # Set From to Session Params
        self.session_params['From'] = from_no.lstrip('+')
        # Set CallUUID to Session Params
        self.session_params['CallUUID'] = self.call_uuid
        # Set Direction to Session Params
        self.session_params['Direction'] = channel.get_header('Call-Direction')
        aleg_uuid = ''
        aleg_request_uuid = ''
        forwarded_from = get_substring(':', '@',
                            channel.get_header('variable_sip_h_Diversion'))

        if self.session_params['Direction'] == 'outbound':
            # Look for variables in channel headers
            aleg_uuid = channel.get_header('Caller-Unique-ID')
            aleg_request_uuid = channel.get_header('variable_plivo_request_uuid')
            # Look for target url in order below :
            #  get plivo_transfer_url from channel var
            #  get plivo_answer_url from channel var
            xfer_url = channel.get_header('variable_plivo_transfer_url')
            answer_url = channel.get_header('variable_plivo_answer_url')
            if xfer_url:
                self.target_url = xfer_url
                self.log.info("Using TransferUrl %s" % self.target_url)
            elif answer_url:
                self.target_url = answer_url
                self.log.info("Using AnswerUrl %s" % self.target_url)
            else:
                self.log.error('Aborting -- No Call Url found !')
                return
            # Look for a sched_hangup_id
            sched_hangup_id = channel.get_header('variable_plivo_sched_hangup_id')
            # Don't post hangup in outbound direction 
            # because it is handled by inboundsocket
            self.default_hangup_url = None
            self.hangup_url = None
            self.log.info("HangupUrl not set for outbound call")
            # Set CallStatus to Session Params
            self.session_params['CallStatus'] = 'in-progress'
        else:
            # Look for target url in order below :
            #  get plivo_transfer_url from channel var
            #  get plivo_answer_url from channel var
            #  get default answer_url from config
            xfer_url = self.get_var('plivo_transfer_url')
            answer_url = self.get_var('plivo_answer_url')
            if xfer_url:
                self.target_url = xfer_url
                self.log.info("Using TransferUrl %s" % self.target_url)
            elif answer_url:
                self.target_url = answer_url
                self.log.info("Using AnswerUrl %s" % self.target_url)
            elif self.default_answer_url:
                self.target_url = self.default_answer_url
                self.log.info("Using DefaultAnswerUrl %s" % self.target_url)
            else:
                self.log.error('Aborting -- No Call Url found !')
                return
            # Look for a sched_hangup_id
            sched_hangup_id = self.get_var('plivo_sched_hangup_id')
            # Look for hangup_url in order below :
            # get plivo_hangup_url from channel var if found
            # get default_hangup_url from config if found
            # get plivo_answer_url from channel var if found
            # get default_answer_url from config if found
            hangup_url = self.get_var('plivo_hangup_url')
            if hangup_url:
                self.hangup_url = hangup_url
                self.log.info("Using HangupUrl %s from plivo_hangup_url channel var" % self.hangup_url)
            elif self.default_hangup_url:
                self.hangup_url = self.default_hangup_url
                self.log.info("Using HangupUrl %s from hangup url in config" % self.hangup_url)
            elif answer_url:
                self.hangup_url = answer_url
                self.log.info("Using HangupUrl %s from plivo_answer_url channel var" % self.hangup_url)
            elif self.default_answer_url:
                self.hangup_url = self.default_answer_url
                self.log.info("Using HangupUrl %s from answer url in config" % self.hangup_url)
            # Set CallStatus to Session Params
            self.session_params['CallStatus'] = 'ringing'

        if not sched_hangup_id:
            sched_hangup_id = ''

        # Add more Session Params if present
        if aleg_uuid:
            self.session_params['ALegUUID'] = aleg_uuid
        if aleg_request_uuid:
            self.session_params['ALegRequestUUID'] = aleg_request_uuid
        if sched_hangup_id:
            self.session_params['ScheduledHangupId'] = sched_hangup_id
        if forwarded_from:
            self.session_params['ForwardedFrom'] = forwarded_from.lstrip('+')

        self.get_extra_fs_vars()

        # Remove sched_hangup_id from channel vars
        if sched_hangup_id:
            self.unset('plivo_sched_hangup_id')

        # Run application
        self.log.info('Processing Call')
        try:
            self.process_call()
        except RESTHangup:
            self.log.warn('Channel has hung up, breaking Processing Call')
        except Exception, e:
            self.log.error('Processing Call Failure !')
            # If error occurs during xml parsing
            # log exception and break
            self.log.error(str(e))
            [ self.log.error(line) for line in \
                        traceback.format_exc().splitlines() ]
        self.log.info('Processing Call Ended')

    def process_call(self):
        """Method to proceed on the call
        This will fetch the XML, validate the response
        Parse the XML and Execute it
        """
        params = {}
        for x in range(MAX_REDIRECT):
            try:
                if self.has_hangup():
                    raise RESTHangup()
                self.fetch_xml(params=params)
                if not self.xml_response:
                    self.log.warn('No XML Response')
                    return
                self.lex_xml()
                self.parse_xml()
                self.execute_xml()
                self.log.info('End of RESTXML')
                return
            except RESTRedirectException, redirect:
                if self.has_hangup():
                    raise RESTHangup()
                # Set target URL to Redirect URL
                # Set method to Redirect method
                # Set additional params to Redirect params
                self.target_url = redirect.get_url()
                fetch_method = redirect.get_method()
                params = redirect.get_params()
                if not fetch_method:
                    fetch_method = 'POST'
                # Reset all the previous response and element
                self.xml_response = ""
                self.parsed_element = []
                self.lexed_xml_response = []
                self.log.info("Redirecting to %s %s to fetch RESTXML" \
                                        % (fetch_method, self.target_url))
                gevent.sleep(0.010)
                continue
        self.log.warn('Max Redirect Reached !')

    def fetch_xml(self, params={}, method=None):
        """
        This method will retrieve the xml from the answer_url
        The url result expected is an XML content which will be stored in
        xml_response
        """
        self.log.info("Fetching RESTXML from %s with %s" \
                                % (self.target_url, params))
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
            self.log.warn("Cannot send %s, no url !" % method)
            return None
        params.update(self.session_params)
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        try:
            data = http_obj.fetch_response(url, params, method)
            self.log.info("Sent to %s %s with %s -- Result: %s" \
                                            % (method, url, params, data))
            return data
        except Exception, e:
            self.log.error("Sending to %s %s with %s -- Error: %s" \
                                            % (method, url, params, e))
        return None

    def lex_xml(self):
        """
        Validate the XML document and make sure we recognize all Element
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
        if doc.tag != 'Response':
            raise RESTFormatException('No Response Tag Present')

        # Make sure we recognize all the Element in the xml
        for element in doc:
            invalid_element = []
            if not hasattr(elements, element.tag):
                invalid_element.append(element.tag)
            else:
                self.lexed_xml_response.append(element)
            if invalid_element:
                raise UnrecognizedElementException("Unrecognized Element: %s"
                                                        % invalid_element)

    def parse_xml(self):
        """
        This method will parse the XML
        and add the Elements into parsed_element
        """
        # Check all Elements tag name
        for element in self.lexed_xml_response:
            element_class = getattr(elements, str(element.tag), None)
            element_instance = element_class()
            element_instance.parse_element(element, self.target_url)
            self.parsed_element.append(element_instance)
            # Validate, Parse & Store the nested children
            # inside the main element element
            self.validate_element(element, element_instance)

    def validate_element(self, element, element_instance):
        children = element.getchildren()
        if children and not element_instance.nestables:
            raise RESTFormatException("%s cannot have any children!"
                                            % element_instance.name)
        for child in children:
            if child.tag not in element_instance.nestables:
                raise RESTFormatException("%s is not nestable inside %s"
                                            % (child, element_instance.name))
            else:
                self.parse_children(child, element_instance)

    def parse_children(self, child_element, parent_instance):
        child_element_class = getattr(elements, str(child_element.tag), None)
        child_element_instance = child_element_class()
        child_element_instance.parse_element(child_element, None)
        parent_instance.children.append(child_element_instance)

    def execute_xml(self):
        for element_instance in self.parsed_element:
            if hasattr(element_instance, 'prepare'):
                # TODO Prepare element concurrently
                element_instance.prepare()
            # Check if it's an inbound call
            if self.session_params['Direction'] == 'inbound':
                # Don't answer the call if element is of type no answer
                # Only execute the element
                if not self.answered and \
                    not element_instance.name in self.NO_ANSWER_ELEMENTS:
                    self.log.debug("Answering because Element %s need it" \
                        % element_instance.name)
                    self.answer()
                    self.answered = True
            # execute Element
            element_instance.run(self)
        # If transfer is in progress, don't hangup call
        if not self.has_hangup():
            xfer_progress = self.get_var('plivo_transfer_progress') == 'true'
            if not xfer_progress:
                self.log.warn('No more Elements, Hangup Now !')
                self.session_params['CallStatus'] = 'completed'
                self.hangup()
                if self.hangup_url:
                    hangup_url = self.hangup_url
                elif self.default_hangup_url:
                    hangup_url = self.default_hangup_url
                else:
                    hangup_url = None
                if hangup_url:
                    self.session_params['HangupCause'] = 'NORMAL_CLEARING'
                    self.session_params['CallStatus'] = 'completed'
                    self.log.info("Sending hangup to %s" % hangup_url)
                    spawn_raw(self.send_to_url, hangup_url)
            else:
                self.log.warn('No more Elements, Transfer In Progress !')
