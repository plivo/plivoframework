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
from gevent.event import AsyncResult

from plivo.utils.encode import safe_str
from plivo.core.freeswitch.eventtypes import Event
from plivo.rest.freeswitch.helpers import HTTPRequest, get_substring
from plivo.core.freeswitch.outboundsocket import OutboundEventSocket
from plivo.rest.freeswitch import elements
from plivo.rest.freeswitch.exceptions import RESTFormatException, \
                                    RESTSyntaxException, \
                                    UnrecognizedElementException, \
                                    RESTRedirectException, \
                                    RESTSIPTransferException, \
                                    RESTHangup


MAX_REDIRECT = 9999


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
        self.logger.info('(%s) %s' % (self.request_id, safe_str(msg)))

    def warn(self, msg):
        """Log warn level"""
        self.logger.warn('(%s) %s' % (self.request_id, safe_str(msg)))

    def error(self, msg):
        """Log error level"""
        self.logger.error('(%s) %s' % (self.request_id, safe_str(msg)))

    def debug(self, msg):
        """Log debug level"""
        self.logger.debug('(%s) %s' % (self.request_id, safe_str(msg)))



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
                          'Hangup',
                          'Dial',
                         )

    def __init__(self, socket, address,
                 log, cache,
                 default_answer_url=None,
                 default_hangup_url=None,
                 default_http_method='POST',
                 extra_fs_vars=None,
                 auth_id='',
                 auth_token='',
                 request_id=0,
                 trace=False,
                 proxy_url=None):
        # the request id
        self._request_id = request_id
        # set logger
        self._log = log
        self.log = RequestLogger(logger=self._log, request_id=self._request_id)
        # set auth id/token
        self.key = auth_id
        self.secret = auth_token
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
        # set proxy url
        self.proxy_url =  proxy_url
        # set default http method POST or GET
        self.default_http_method = default_http_method
        # identify the extra FS variables to be passed along
        self.extra_fs_vars = extra_fs_vars
        # set answered flag
        self.answered = False
        self.cache = cache
        # inherits from outboundsocket
        OutboundEventSocket.__init__(self, socket, address, filter=None,
                                     eventjson=True, pool_size=200, trace=trace)

    def _protocol_send(self, command, args=''):
        """Access parent method _protocol_send
        """
        self.log.debug("Execute: %s args='%s'" % (command, safe_str(args)))
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
                      % (name, safe_str(args), uuid, str(lock), loops))
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

    def on_channel_hangup_complete(self, event):
        """
        Capture Channel Hangup Complete
        """
        self._hangup_cause = event['Hangup-Cause']
        self.log.info('Event: channel %s has hung up (%s)' %
                      (self.get_channel_unique_id(), self._hangup_cause))
        self.session_params['HangupCause'] = self._hangup_cause
        self.session_params['CallStatus'] = 'completed'
        # Prevent command to be stuck while waiting response
        self._action_queue.put_nowait(Event())

    def on_channel_unbridge(self, event):
        # special case to get bleg uuid for Dial
        if self.current_element == 'Dial':
            self._action_queue.put(event)

    def on_detected_speech(self, event):
        # detect speech for GetSpeech
        if self.current_element == 'GetSpeech' \
            and event['Speech-Type'] == 'detected-speech':
            self._action_queue.put(event)

    def on_custom(self, event):
        # case conference event
        if self.current_element == 'Conference':
            # special case to get Member-ID for Conference
            if event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'add-member' \
                and event['Unique-ID'] == self.get_channel_unique_id():
                self.log.debug("Entered Conference")
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
                self.log.debug("Digits match on Conference")
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
            # special case to send callback when Member take the floor in Conference
            # but only if member can speak (not muted)
            elif event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'floor-change' \
                and event['Unique-ID'] == self.get_channel_unique_id() \
                and event['Speak'] == 'true':
                self._action_queue.put(event)

        # case dial event
        elif self.current_element == 'Dial':
            if event['Event-Subclass'] == 'plivo::dial' \
                and event['Action'] == 'digits-match' \
                and event['Unique-ID'] == self.get_channel_unique_id():
                self.log.debug("Digits match on Dial")
                digits_action = event['Callback-Url']
                digits_method = event['Callback-Method']
                if digits_action and digits_method:
                    params = {}
                    params['DialDigitsMatch'] = event['Digits-Match'] or ''
                    params['DialAction'] = 'digits'
                    params['DialALegUUID'] = event['Unique-ID']
                    params['DialBLegUUID'] = event['variable_bridge_uuid']
                    spawn_raw(self.send_to_url, digits_action, params, digits_method)

    def has_hangup(self):
        if self._hangup_cause:
            return True
        return False

    def ready(self):
        if self.has_hangup():
            return False
        return True

    def has_answered(self):
        return self.answered

    def get_hangup_cause(self):
        return self._hangup_cause

    def get_extra_fs_vars(self, event):
        params = {}
        if not event or not self.extra_fs_vars:
            return params
        for var in self.extra_fs_vars.split(','):
            var = var.strip()
            if var:
                val = event.get_header(var)
                if val is None:
                    val = ''
                params[var] = val
        return params

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
        except Exception, e:
            [ self.log.error(line) for line in \
                        traceback.format_exc().splitlines() ]
            raise e


    def _run(self):
        self.connect()
        self.resume()
        # Linger to get all remaining events before closing
        self.linger()
        self.myevents()
        self.divert_events('on')
        if self._is_eventjson:
            self.eventjson('CUSTOM conference::maintenance plivo::dial')
        else:
            self.eventplain('CUSTOM conference::maintenance plivo::dial')
        # Set plivo app flag
        self.set('plivo_app=true')
        # Don't hangup after bridge
        self.set('hangup_after_bridge=false')
        channel = self.get_channel()
        self.call_uuid = self.get_channel_unique_id()
        # Set CallerName to Session Params
        self.session_params['CallerName'] = channel.get_header('Caller-Caller-ID-Name') or ''
        # Set CallUUID to Session Params
        self.session_params['CallUUID'] = self.call_uuid
        # Set Direction to Session Params
        self.session_params['Direction'] = channel.get_header('Call-Direction')
        aleg_uuid = ''
        aleg_request_uuid = ''
        forwarded_from = get_substring(':', '@',
                            channel.get_header('variable_sip_h_Diversion'))

        # Case Outbound
        if self.session_params['Direction'] == 'outbound':
            # Set To / From
            called_no = channel.get_header("variable_plivo_to")
            if not called_no or called_no == '_undef_':
                called_no = channel.get_header('Caller-Destination-Number')
            called_no = called_no or ''
            from_no = channel.get_header("variable_plivo_from")
            if not from_no or from_no == '_undef_':
                from_no = channel.get_header('Caller-Caller-ID-Number') or ''
            # Set To to Session Params
            self.session_params['To'] = called_no.lstrip('+')
            # Set From to Session Params
            self.session_params['From'] = from_no.lstrip('+')

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
                if not self.has_hangup():
                    self.hangup()
                    raise RESTHangup()
                return
            # Look for a sched_hangup_id
            sched_hangup_id = channel.get_header('variable_plivo_sched_hangup_id')
            # Don't post hangup in outbound direction
            # because it is handled by inboundsocket
            self.default_hangup_url = None
            self.hangup_url = None
            # Set CallStatus to Session Params
            self.session_params['CallStatus'] = 'in-progress'
            accountsid = channel.get_header("variable_plivo_accountsid")
            if accountsid:
                self.session_params['AccountSID'] = accountsid
        # Case Inbound
        else:
            # Set To / From
            called_no = channel.get_header("variable_plivo_destination_number")
            if not called_no or called_no == '_undef_':
                called_no = channel.get_header('Caller-Destination-Number')
            called_no = called_no or ''
            from_no = channel.get_header('Caller-Caller-ID-Number') or ''
            # Set To to Session Params
            self.session_params['To'] = called_no.lstrip('+')
            # Set From to Session Params
            self.session_params['From'] = from_no.lstrip('+')
            
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
                if not self.has_hangup():
                    self.hangup()
                    raise RESTHangup()
                return
            # Look for a sched_hangup_id
            sched_hangup_id = self.get_var('plivo_sched_hangup_id')
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
                # update call status if needed
                if self.has_hangup():
                    self.session_params['CallStatus'] = 'completed'
                # case answer url, add extra vars to http request :
                if x == 0:
                    params = self.get_extra_fs_vars(event=self.get_channel())
                # fetch remote restxml
                self.fetch_xml(params=params)
                # check hangup
                if self.has_hangup():
                    raise RESTHangup()
                if not self.xml_response:
                    self.log.warn('No XML Response')
                    if not self.has_hangup():
                        self.hangup()
                    raise RESTHangup()
                # parse and execute restxml
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
                # If transfer is in progress, break redirect
                xfer_progress = self.get_var('plivo_transfer_progress') == 'true'
                if xfer_progress:
                    self.log.warn('Transfer in progress, breaking redirect to %s %s' \
                                  % (fetch_method, self.target_url))
                    return
                gevent.sleep(0.010)
                continue
            except RESTSIPTransferException, sip_redirect:
                self.session_params['SIPTransfer'] = 'true'
                self.session_params['SIPTransferURI'] = sip_redirect.get_sip_url() \
                            or ''
                self.log.info("End of RESTXML -- SIPTransfer done to %s" % sip_redirect.get_sip_url())
                return
        self.log.warn('Max Redirect Reached !')

    def fetch_xml(self, params={}, method=None):
        """
        This method will retrieve the xml from the answer_url
        The url result expected is an XML content which will be stored in
        xml_response
        """
        self.log.info("Fetching RESTXML from %s" % self.target_url)
        self.xml_response = self.send_to_url(self.target_url, params, method)
        self.log.info("Requested RESTXML to %s" % self.target_url)

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
        try:
            http_obj = HTTPRequest(self.key, self.secret, proxy_url=self.proxy_url)
            data = http_obj.fetch_response(url, params, method, log=self.log)
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
                element_instance.prepare(self)
            # Check if it's an inbound call
            if self.session_params['Direction'] == 'inbound':
                # Answer the call if element need it
                if not self.answered and \
                    not element_instance.name in self.NO_ANSWER_ELEMENTS:
                    self.log.debug("Answering because Element %s need it" \
                        % element_instance.name)
                    self.answer()
                    self.answered = True
                    # After answer, update callstatus to 'in-progress'
                    self.session_params['CallStatus'] = 'in-progress'
            # execute Element
            element_instance.run(self)
        # If transfer is in progress, don't hangup call
        if not self.has_hangup():
            xfer_progress = self.get_var('plivo_transfer_progress') == 'true'
            if not xfer_progress:
                self.log.info('No more Elements, Hangup Now !')
                self.session_params['CallStatus'] = 'completed'
                self.session_params['HangupCause'] = 'NORMAL_CLEARING'
                self.hangup()
            else:
                self.log.info('No more Elements, Transfer In Progress !')
