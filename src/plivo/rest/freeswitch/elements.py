# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.


import os.path
from datetime import datetime
import re
import uuid
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from xml.etree.elementtree import ElementTree as etree

import gevent
from gevent import spawn_raw

from plivo.rest.freeswitch.helpers import is_valid_url, url_exists, \
                                        file_exists, normalize_url_space, \
                                        get_resource
from plivo.rest.freeswitch.exceptions import RESTFormatException, \
                                            RESTAttributeException, \
                                            RESTRedirectException, \
                                            RESTNoExecuteException, \
                                            RESTHangup


ELEMENTS_DEFAULT_PARAMS = {
        'Conference': {
                #'room': SET IN ELEMENT BODY
                'waitSound': '',
                'muted': 'false',
                'startConferenceOnEnter': 'true',
                'endConferenceOnExit': 'false',
                'maxMembers': 200,
                'enterSound': '',
                'exitSound': '',
                'timeLimit': 0 ,
                'hangupOnStar': 'false',
                'recordFilePath': '',
                'recordFileFormat': 'mp3',
                'recordFileName': '',
                'action': '',
                'method': 'POST',
                'callbackUrl': '',
                'callbackMethod': 'POST',
                'digitsMatch': ''
        },
        'Dial': {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                'method': 'POST',
                'hangupOnStar': 'false',
                #callerId: DYNAMIC! MUST BE SET IN METHOD,
                'timeLimit': 0,
                'confirmSound': '',
                'confirmKey': '',
                'dialMusic': '',
                'redirect': 'true',
                'callbackUrl': '',
                'callbackMethod': 'POST',
                'digitsMatch': ''
        },
        'GetDigits': {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                'method': 'POST',
                'timeout': 5,
                'finishOnKey': '#',
                'numDigits': 99,
                'retries': 1,
                'playBeep': 'false',
                'validDigits': '0123456789*#',
                'invalidDigitsSound': ''
        },
        'Hangup': {
                'reason': '',
                'schedule': 0
        },
        'Number': {
                #'gateways': DYNAMIC! MUST BE SET IN METHOD,
                #'gatewayCodecs': DYNAMIC! MUST BE SET IN METHOD,
                #'gatewayTimeouts': DYNAMIC! MUST BE SET IN METHOD,
                #'gatewayRetries': DYNAMIC! MUST BE SET IN METHOD,
                #'extraDialString': DYNAMIC! MUST BE SET IN METHOD,
                'sendDigits': '',
        },
        'Wait': {
                'length': 1
        },
        'Play': {
                #url: SET IN ELEMENT BODY
                'loop': 1
        },
        'PreAnswer': {
        },
        'Record': {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                'method': 'POST',
                'timeout': 15,
                'finishOnKey': '1234567890*#',
                'maxLength': 60,
                'playBeep': 'true',
                'filePath': '/usr/local/freeswitch/recordings/',
                'fileFormat': 'mp3',
                'fileName': '',
                'bothLegs': 'false'
        },
        'Redirect': {
                'method': 'POST'
        },
        'Speak': {
                'voice': 'slt',
                'language': 'en',
                'loop': 1,
                'engine': 'flite',
                'method': '',
                'type': ''
        }
    }


MAX_LOOPS = 10000


class Element(object):
    """Abstract Element Class to be inherited by all other elements"""

    def __init__(self):
        self.name = str(self.__class__.__name__)
        self.nestables = None
        self.attributes = {}
        self.text = ''
        self.children = []

    def parse_element(self, element, uri=None):
        self.prepare_attributes(element)
        self.prepare_text(element)

    def run(self, outbound_socket):
        outbound_socket.log.info("[%s] %s %s" \
            % (self.name, self.text, self.attributes))
        execute = getattr(self, 'execute', None)
        if not execute:
            outbound_socket.log.error("[%s] Element cannot be executed !" % self.name)
            raise RESTNoExecuteException("Element %s cannot be executed !" % self.name)
        try:
            outbound_socket.current_element = self.name
            result = execute(outbound_socket)
            outbound_socket.current_element = None
        except RESTHangup:
            outbound_socket.log.info("[%s] Done (Hangup)" % self.name)
            raise
        if not result:
            outbound_socket.log.info("[%s] Done" % self.name)
        else:
            outbound_socket.log.info("[%s] Done -- Result %s" % (self.name, result))

    def extract_attribute_value(self, item, default=None):
        try:
            item = self.attributes[item]
        except KeyError:
            item = default
        return item

    def prepare_attributes(self, element):
        element_dict = ELEMENTS_DEFAULT_PARAMS[self.name]
        if element.attrib and not element_dict:
            raise RESTFormatException("%s does not require any attributes!"
                                                                % self.name)
        self.attributes = dict(element_dict, **element.attrib)

    def prepare_text(self, element):
        text = element.text
        if not text:
            self.text = ''
        else:
            self.text = text.strip()

    def fetch_rest_xml(self, url, params={}, method='POST'):
        raise RESTRedirectException(url, params, method)


class Conference(Element):
    """Go to a Conference Room
    room name is body text of Conference element.

    waitSound: sound to play while alone in conference
          Can be a list of sound files separated by comma.
          (default no sound)
    muted: enter conference muted
          (default false)
    startConferenceOnEnter: the conference start when this member joins
          (default true)
    endConferenceOnExit: close conference after this member leaves
          (default false)
    maxMembers: max members in conference
          (0 for max : 200)
    enterSound: sound to play when a member enters
          if empty, disabled
          if 'beep:1', play one beep
          if 'beep:2', play two beeps
          (default disabled)
    exitSound: sound to play when a member exits
          if empty, disabled
          if 'beep:1', play one beep
          if 'beep:2', play two beeps
          (default disabled)
    timeLimit: max time in seconds before closing conference
          (default 0, no timeLimit)
    hangupOnStar: exit conference when member press '*'
          (default false)
    recordFilePath: path where recording is saved.
        (default "" so recording wont happen)
    recordFileFormat: file format in which recording tis saved
        (default mp3)
    recordFileName: By default empty, if provided this name will be used for the recording
        (any unique name)
    action: redirect to this URL after leaving conference
    method: submit to 'action' url using GET or POST
    callbackUrl: url to request when call enters/leaves conference
            or has pressed digits matching (digitsMatch)
    callbackMethod: submit to 'callbackUrl' url using GET or POST
    digitsMatch: a list of matching digits to send with callbackUrl
            Can be a list of digits patterns separated by comma.
    """
    DEFAULT_TIMELIMIT = 0
    DEFAULT_MAXMEMBERS = 200

    def __init__(self):
        Element.__init__(self)
        self.full_room = ''
        self.room = ''
        self.moh_sound = None
        self.muted = False
        self.start_on_enter = True
        self.end_on_exit = False
        self.time_limit = self.DEFAULT_TIMELIMIT
        self.max_members = self.DEFAULT_MAXMEMBERS
        self.enter_sound = ''
        self.exit_sound = ''
        self.hangup_on_star = False
        self.record_file_path = ""
        self.record_file_format = "mp3"
        self.record_filename = ""
        self.action = ''
        self.method = ''
        self.callback_url = ''
        self.callback_method = ''
        self.conf_id = ''
        self.member_id = ''

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        room = self.text
        if not room:
            raise RESTFormatException('Conference Room must be defined')
        self.full_room = room + '@plivo'
        self.room = room
        self.moh_sound = self.extract_attribute_value('waitSound')
        self.muted = self.extract_attribute_value('muted') \
                        == 'true'
        self.start_on_enter = self.extract_attribute_value('startConferenceOnEnter') \
                                == 'true'
        self.end_on_exit = self.extract_attribute_value('endConferenceOnExit') \
                                == 'true'
        self.hangup_on_star = self.extract_attribute_value('hangupOnStar') \
                                == 'true'
        try:
            self.time_limit = int(self.extract_attribute_value('timeLimit',
                                                          self.DEFAULT_TIMELIMIT))
        except ValueError:
            self.time_limit = self.DEFAULT_TIMELIMIT
        if self.time_limit <= 0:
            self.time_limit = self.DEFAULT_TIMELIMIT
        try:
            self.max_members = int(self.extract_attribute_value('maxMembers',
                                                        self.DEFAULT_MAXMEMBERS))
        except ValueError:
            self.max_members = self.DEFAULT_MAXMEMBERS
        if self.max_members <= 0 or self.max_members > self.DEFAULT_MAXMEMBERS:
            self.max_members = self.DEFAULT_MAXMEMBERS

        self.enter_sound = self.extract_attribute_value('enterSound')
        self.exit_sound = self.extract_attribute_value('exitSound')

        self.record_file_path = self.extract_attribute_value("recordFilePath")
        if self.record_file_path:
            self.record_file_path = os.path.normpath(self.record_file_path)\
                                                                    + os.sep
        self.record_file_format = \
                            self.extract_attribute_value("recordFileFormat")
        if self.record_file_format not in ('wav', 'mp3'):
            raise RESTFormatException("Format must be 'wav' or 'mp3'")
        self.record_filename = \
                            self.extract_attribute_value("recordFileName")

        self.method = self.extract_attribute_value("method")
        if not self.method in ('GET', 'POST'):
            raise RESTAttributeException("method must be 'GET' or 'POST'")
        self.action = self.extract_attribute_value("action")

        self.callback_method = self.extract_attribute_value("callbackMethod")
        if not self.callback_method in ('GET', 'POST'):
            raise RESTAttributeException("callbackMethod must be 'GET' or 'POST'")
        self.callback_url = self.extract_attribute_value("callbackUrl")
        self.digits_match = self.extract_attribute_value("digitsMatch")

    def _prepare_moh(self, outbound_socket):
        sound_files = []
        if not self.moh_sound:
            return sound_files
        outbound_socket.log.info('Fetching remote sound from restxml %s' % self.moh_sound)
        try:
            response = outbound_socket.send_to_url(self.moh_sound, params={}, method='POST')
            doc = etree.fromstring(response)
            if doc.tag != 'Response':
                outbound_socket.log.warn('No Response Tag Present')
                return sound_files

            # build play string from remote restxml
            for element in doc:
                # Play element
                if element.tag == 'Play':
                    child_instance = Play()
                    child_instance.parse_element(element)
                    child_instance.prepare(outbound_socket)
                    sound_file = child_instance.sound_file_path
                    if sound_file:
                        loop = child_instance.loop_times
                        if loop == 0:
                            loop = MAX_LOOPS  # Add a high number to Play infinitely
                        # Play the file loop number of times
                        for i in range(loop):
                            sound_files.append(sound_file)
                        # Infinite Loop, so ignore other children
                        if loop == MAX_LOOPS:
                            break
                # Wait element
                elif element.tag == 'Wait':
                    child_instance = Wait()
                    child_instance.parse_element(element)
                    pause_secs = child_instance.length
                    pause_str = 'file_string://silence_stream://%s' % (pause_secs * 1000)
                    sound_files.append(pause_str)
        except Exception, e:
            outbound_socket.log.warn('Fetching remote sound from restxml failed: %s' % str(e))
        finally:
            outbound_socket.log.info('Fetching remote sound from restxml done')
            return sound_files

    def _notify_enter_conf(self, outboundsocket):
        if not self.callback_url or not self.conf_id or not self.member_id:
            return
        params = {}
        params['ConferenceName'] = self.room
        params['ConferenceUUID'] = self.conf_id or ''
        params['ConferenceMemberID'] = self.member_id or ''
        params['ConferenceAction'] = 'enter'
        spawn_raw(outboundsocket.send_to_url, self.callback_url, params, self.callback_method)

    def _notify_exit_conf(self, outboundsocket):
        if not self.callback_url or not self.conf_id or not self.member_id:
            return
        params = {}
        params['ConferenceName'] = self.room
        params['ConferenceUUID'] = self.conf_id or ''
        params['ConferenceMemberID'] = self.member_id or ''
        params['ConferenceAction'] = 'exit'
        spawn_raw(outboundsocket.send_to_url, self.callback_url, params, self.callback_method)

    def execute(self, outbound_socket):
        flags = []
        # settings for conference room
        outbound_socket.set("conference_controls=none")
        if self.max_members > 0:
            outbound_socket.set("max-members=%d" % self.max_members)
        else:
            outbound_socket.unset("max-members")

        if self.record_file_path:
            file_path = os.path.normpath(self.record_file_path) + os.sep
            if self.record_filename:
                filename = self.record_filename
            else:
                filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"),
                                      outbound_socket.get_channel_unique_id())
            record_file = "%s%s.%s" % (file_path, filename,
                                        self.record_file_format)
        else:
            record_file = None

        # set moh sound
        mohs = self._prepare_moh(outbound_socket)
        if mohs:
            outbound_socket.set("playback_delimiter=!")
            play_str = '!'.join(mohs)
            play_str = "file_string://silence_stream://1!%s" % play_str
            outbound_socket.set("conference_moh_sound=%s" % play_str)
        else:
            outbound_socket.unset("conference_moh_sound")
        # set member flags
        if self.muted:
            flags.append("mute")
        if self.start_on_enter:
            flags.append("moderator")
        else:
            flags.append("wait-mod")
        if self.end_on_exit:
            flags.append("endconf")
        flags_opt = ','.join(flags)
        if flags_opt:
            outbound_socket.set("conference_member_flags=%s" % flags_opt)
        else:
            outbound_socket.unset("conference_member_flags")
        # set new kickall scheduled task if timeLimit > 0
        if self.time_limit > 0:
            # set timeLimit scheduled group name for the room
            sched_group_name = "conf_%s" % self.room
            # always clean old kickall tasks for the room
            outbound_socket.api("sched_del %s" % sched_group_name)
            # set new kickall task for the room
            outbound_socket.api("sched_api +%d %s conference %s kick all" \
                                % (self.time_limit, sched_group_name, self.room))
            outbound_socket.log.warn("Conference: Room %s, timeLimit set to %d seconds" \
                                    % (self.room, self.time_limit))
        # really enter conference room
        outbound_socket.log.info("Entering Conference: Room %s (flags %s)" \
                                        % (self.room, flags_opt))
        res = outbound_socket.conference(self.full_room, lock=False)
        if not res.is_success():
            outbound_socket.log.error("Conference: Entering Room %s Failed" \
                                % (self.room))
            return
        # get next event
        event = outbound_socket.wait_for_action()

        # if event is add-member, get Member-ID
        # and set extra features for conference
        # else conference element ending here
        try:
            digit_realm = ''
            if event['Event-Subclass'] == 'conference::maintenance' \
                and event['Action'] == 'add-member':
                self.member_id = event['Member-ID']
                self.conf_id = event['Conference-Unique-ID']
                outbound_socket.log.debug("Entered Conference: Room %s with Member-ID %s" \
                                % (self.room, self.member_id))
                # notify channel has entered room
                self._notify_enter_conf(outbound_socket)

                # set bind digit actions
                if self.digits_match and self.callback_url:
                    # create event template
                    event_template = "Event-Name=CUSTOM,Event-Subclass=conference::maintenance,Action=digits-match,Unique-ID=%s,Callback-Url=%s,Callback-Method=%s,Member-ID=%s,Conference-Name=%s,Conference-Unique-ID=%s" \
                        % (outbound_socket.get_channel_unique_id(), self.callback_url, self.callback_method, self.member_id, self.room, self.conf_id)
                    digit_realm = "plivo_bda_%s" % outbound_socket.get_channel_unique_id()
                    # for each digits match, set digit binding action
                    for dmatch in self.digits_match.split(','):
                        dmatch = dmatch.strip()
                        if dmatch:
                            raw_event = "%s,Digits-Match=%s" % (event_template, dmatch)
                            cmd = "%s,%s,exec:event,'%s'" % (digit_realm, dmatch, raw_event)
                            outbound_socket.bind_digit_action(cmd)
                # set hangup on star
                if self.hangup_on_star:
                    # create event template
                    raw_event = "Event-Name=CUSTOM,Event-Subclass=conference::maintenance,Action=kick,Unique-ID=%s,Member-ID=%s,Conference-Name=%s,Conference-Unique-ID=%s" \
                        % (outbound_socket.get_channel_unique_id(), self.member_id, self.room, self.conf_id)
                    digit_realm = "plivo_bda_%s" % outbound_socket.get_channel_unique_id()
                    cmd = "%s,*,exec:event,'%s'" % (digit_realm, raw_event)
                    outbound_socket.bind_digit_action(cmd)
                # set digit realm
                if digit_realm:
                    outbound_socket.digit_action_set_realm(digit_realm)

                # play beep on enter if enabled
                if self.member_id:
                    if self.enter_sound == 'beep:1':
                        outbound_socket.bgapi("conference %s play tone_stream://%%(300,200,700) async" % self.room)
                    elif self.enter_sound == 'beep:2':
                        outbound_socket.bgapi("conference %s play tone_stream://L=2;%%(300,200,700) async" % self.room)

                # record conference if set
                if record_file:
                    outbound_socket.bgapi("conference %s record %s" % (self.room, record_file))
                    outbound_socket.log.info("Conference: Room %s, recording to file %s" \
                                    % (self.room, record_file))

                # wait conference ending for this member
                outbound_socket.log.debug("Conference: Room %s, waiting end ..." % self.room)
                event = outbound_socket.wait_for_action()

                # play beep on exit if enabled
                if self.member_id:
                    if self.exit_sound == 'beep:1':
                        outbound_socket.api("conference %s play tone_stream://%%(300,200,700) async" % self.room)
                    elif self.exit_sound == 'beep:2':
                        outbound_socket.api("conference %s play tone_stream://L=2;%%(300,200,700) async" % self.room)
            # unset digit realm
            if digit_realm:
                outbound_socket.clear_digit_action(digit_realm)

        finally:
            # notify channel has left room
            self._notify_exit_conf(outbound_socket)
            outbound_socket.log.info("Leaving Conference: Room %s" % self.room)
            # If action is set, redirect to this url
            # Otherwise, continue to next Element
            if self.action and is_valid_url(self.action):
                params = {}
                params['ConferenceName'] = self.room
                params['ConferenceUUID'] = self.conf_id or ''
                params['ConferenceMemberID'] = self.member_id or ''
                if record_file:
                    params['RecordFile'] = record_file
                self.fetch_rest_xml(self.action, params, method=self.method)



class Dial(Element):
    """Dial another phone number and connect it to this call

    action: submit the result of the dial and redirect to this URL
    method: submit to 'action' url using GET or POST
    hangupOnStar: hangup the b leg if a leg presses start and this is true
    callerId: caller id to be send to the dialed number
    timeLimit: hangup the call after these many seconds. 0 means no timeLimit
    confirmSound: Sound to be played to b leg before call is bridged
    confirmKey: Key to be pressed to bridge the call.
    dialMusic: Play music to a leg while doing a dial to b leg
                Can be a list of files separated by comma
    redirect: if 'false', don't redirect to 'action', only request url
        and continue to next element. (default 'true')
    callbackUrl: url to request when bridge starts and bridge ends
    callbackMethod: submit to 'callbackUrl' url using GET or POST
    """
    DEFAULT_TIMEOUT = 30
    DEFAULT_TIMELIMIT = 14400

    def __init__(self):
        Element.__init__(self)
        self.nestables = ('Number',)
        self.method = ''
        self.action = ''
        self.hangup_on_star = False
        self.caller_id = ''
        self.time_limit = self.DEFAULT_TIMELIMIT
        self.timeout = self.DEFAULT_TIMEOUT
        self.dial_str = ''
        self.confirm_sound = ''
        self.confirm_key = ''
        self.dial_music = ''
        self.redirect = False

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        self.action = self.extract_attribute_value('action')
        self.caller_id = self.extract_attribute_value('callerId')
        try:
            self.time_limit = int(self.extract_attribute_value('timeLimit',
                                  self.DEFAULT_TIMELIMIT))
        except ValueError:
            self.time_limit = self.DEFAULT_TIMELIMIT
        if self.time_limit <= 0:
            self.time_limit = self.DEFAULT_TIMELIMIT
        try:
            self.timeout = int(self.extract_attribute_value("timeout",
                               self.DEFAULT_TIMEOUT))
        except ValueError:
            self.timeout = self.DEFAULT_TIMEOUT
        if self.timeout <= 0:
            self.timeout = self.DEFAULT_TIMEOUT
        self.confirm_sound = self.extract_attribute_value("confirmSound")
        self.confirm_key = self.extract_attribute_value("confirmKey")
        self.dial_music = self.extract_attribute_value("dialMusic")
        self.hangup_on_star = self.extract_attribute_value("hangupOnStar") \
                                                                == 'true'
        self.redirect = self.extract_attribute_value("redirect") == 'true'

        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("method must be 'GET' or 'POST'")
        self.method = method

        self.callback_url = self.extract_attribute_value("callbackUrl")
        self.callback_method = self.extract_attribute_value("callbackMethod")
        if not self.callback_method in ('GET', 'POST'):
            raise RESTAttributeException("callbackMethod must be 'GET' or 'POST'")
        self.digits_match = self.extract_attribute_value("digitsMatch")

    def _prepare_play_string(self, outbound_socket, remote_url):
        sound_files = []
        if not remote_url:
            return sound_files
        outbound_socket.log.info('Fetching remote sound from restxml %s' % remote_url)
        try:
            response = outbound_socket.send_to_url(remote_url, params={}, method='POST')
            doc = etree.fromstring(response)
            if doc.tag != 'Response':
                outbound_socket.log.warn('No Response Tag Present')
                return sound_files

            # build play string from remote restxml
            for element in doc:
                # Play element
                if element.tag == 'Play':
                    child_instance = Play()
                    child_instance.parse_element(element)
                    child_instance.prepare(outbound_socket)
                    sound_file = child_instance.sound_file_path
                    if sound_file:
                        loop = child_instance.loop_times
                        if loop == 0:
                            loop = MAX_LOOPS  # Add a high number to Play infinitely
                        # Play the file loop number of times
                        for i in range(loop):
                            sound_files.append(sound_file)
                        # Infinite Loop, so ignore other children
                        if loop == MAX_LOOPS:
                            break
                # Speak element
                elif element.tag == 'Speak':
                    child_instance = Speak()
                    child_instance.parse_element(element)
                    text = child_instance.text
                    # escape simple quote
                    text = text.replace("'", "\\'")
                    loop = child_instance.loop_times
                    child_type = child_instance.item_type
                    method = child_instance.method
                    say_str = ''
                    if child_type and method:
                        language = child_instance.language
                        say_args = "%s.wav %s %s %s '%s'" \
                                        % (language, language, child_type, method, text)
                        say_str = "${say_string %s}" % say_args
                    else:
                        engine = child_instance.engine
                        voice = child_instance.voice
                        say_str = "say:%s:%s:'%s'" % (engine, voice, text)
                    if not say_str:
                        continue
                    for i in range(loop):
                        sound_files.append(say_str)
                # Wait element
                elif element.tag == 'Wait':
                    child_instance = Wait()
                    child_instance.parse_element(element)
                    pause_secs = child_instance.length
                    pause_str = 'file_string://silence_stream://%s' % (pause_secs * 1000)
                    sound_files.append(pause_str)
        except Exception, e:
            outbound_socket.log.warn('Fetching remote sound from restxml failed: %s' % str(e))
        finally:
            outbound_socket.log.info('Fetching remote sound from restxml done for %s' % remote_url)
            return sound_files

    def create_number(self, number_instance, outbound_socket):
        num_gw = []
        # skip number object without gateway or number
        if not number_instance.gateways:
            outbound_socket.log.error("Gateway not defined on Number object !")
            return ''
        if not number_instance.number:
            outbound_socket.log.error("Number not defined on Number object  !")
            return ''
        if number_instance.send_digits:
            option_send_digits = "api_on_answer='uuid_recv_dtmf ${uuid} %s'" \
                                                % number_instance.send_digits
        else:
            option_send_digits = ''
        count = 0
        for gw in number_instance.gateways:
            num_options = []

            if self.callback_url and self.callback_method:
                num_options.append('plivo_dial_callback_url=%s' % self.callback_url)
                num_options.append('plivo_dial_callback_method=%s' % self.callback_method)
                num_options.append('plivo_dial_callback_aleg=%s' % outbound_socket.get_channel_unique_id())

            if option_send_digits:
                num_options.append(option_send_digits)
            try:
                gw_codec = number_instance.gateway_codecs[count]
                num_options.append('absolute_codec_string=%s' % gw_codec)
            except IndexError:
                pass
            try:
                gw_timeout = int(number_instance.gateway_timeouts[count], 0)
                if gw_timeout > 0:
                    num_options.append('leg_timeout=%d' % gw_timeout)
            except (IndexError, ValueError):
                pass
            try:
                gw_retries = int(number_instance.gateway_retries[count], 1)
                if gw_retries <= 0:
                    gw_retries = 1
            except (IndexError, ValueError):
                gw_retries = 1
            extra_dial_string = number_instance.extra_dial_string
            if extra_dial_string:
                num_options.append(extra_dial_string)
            if num_options:
                options = '[%s]' % (','.join(num_options))
            else:
                options = ''
            num_str = "%s%s/%s" % (options, gw, number_instance.number)
            dial_num = '|'.join([num_str for retry in range(gw_retries)])
            num_gw.append(dial_num)
            count += 1
        result = '|'.join(num_gw)
        return result

    def execute(self, outbound_socket):
        numbers = []
        # Set timeout
        outbound_socket.set("call_timeout=%d" % self.timeout)
        outbound_socket.set("answer_timeout=%d" % self.timeout)
        # Set callerid or unset if not provided
        if self.caller_id:
            outbound_socket.set("effective_caller_id_number=%s" % self.caller_id)
        else:
            outbound_socket.unset("effective_caller_id_number")
        # Set continue on fail
        outbound_socket.set("continue_on_fail=true")
        # Set ring flag if dial will ring.
        # But first set plivo_dial_rang to false
        # to be sure we don't get it from an old Dial
        outbound_socket.set("plivo_dial_rang=false")
        outbound_socket.set("execute_on_ring=set::plivo_dial_rang=true")
        # Set numbers to dial from Number nouns
        for child in self.children:
            if isinstance(child, Number):
                dial_num = self.create_number(child, outbound_socket)
                if not dial_num:
                    continue
                numbers.append(dial_num)
        if not numbers:
            outbound_socket.log.error("Dial Aborted, No Number to dial !")
            return
        # Create dialstring
        self.dial_str = ':_:'.join(numbers)

        # Don't hangup after bridge !
        outbound_socket.set("hangup_after_bridge=false")

        # Set time limit: when reached, B Leg is hung up
        sched_hangup_id = str(uuid.uuid1())
        dial_time_limit = "api_on_answer='sched_api +%d %s 'uuid_transfer %s -bleg hangup:ALLOTTED_TIMEOUT inline''" \
                      % (self.time_limit, sched_hangup_id, outbound_socket.get_channel_unique_id())

        # Set confirm sound and key or unset if not provided
        dial_confirm = ''
        if self.confirm_sound:
            confirm_sounds = self._prepare_play_string(outbound_socket, self.confirm_sound)
            if confirm_sounds:
                play_str = '!'.join(confirm_sounds)
                play_str = "file_string://silence_stream://1!%s" % play_str
                # Use confirm key if present else just play music
                if self.confirm_key:
                    confirm_music_str = "group_confirm_file=%s" % play_str
                    confirm_key_str = "group_confirm_key=%s" % self.confirm_key
                else:
                    confirm_music_str = "group_confirm_file=playback %s" % play_str
                    confirm_key_str = "group_confirm_key=exec"
                # Cancel the leg timeout after the call is answered
                confirm_cancel = "group_confirm_cancel_timeout=1"
                dial_confirm = ",%s,%s,%s,playback_delimiter=!" % (confirm_music_str, confirm_key_str, confirm_cancel)

        # Append time limit and group confirm to dial string
        self.dial_str = '<%s%s>%s' % (dial_time_limit, dial_confirm, self.dial_str)
        # Ugly hack to force use of enterprise originate because simple originate lacks speak support in ringback
        if len(numbers) < 2:
            self.dial_str += ':_:'

        # Set hangup on '*' or unset if not provided
        if self.hangup_on_star:
            outbound_socket.set("bridge_terminate_key=*")
        else:
            outbound_socket.unset("bridge_terminate_key")

        # Play Dial music or bridge the early media accordingly
        ringbacks = ''
        if self.dial_music:
            ringbacks = self._prepare_play_string(outbound_socket, self.dial_music)
            if ringbacks:
                outbound_socket.set("playback_delimiter=!")
                play_str = '!'.join(ringbacks)
                play_str = "file_string://silence_stream://1!%s" % play_str
                outbound_socket.set("bridge_early_media=true")
                outbound_socket.set("instant_ringback=true")
                outbound_socket.set("ringback=%s" % play_str)
        if not ringbacks:
            outbound_socket.set("bridge_early_media=true")
            outbound_socket.unset("instant_ringback")
            outbound_socket.unset("ringback")

        # Start dial
        bleg_uuid = ''
        dial_rang = ''
        digit_realm = ''
        hangup_cause = 'NORMAL_CLEARING'
        outbound_socket.log.info("Dial Started %s" % self.dial_str)
        try:
            # execute bridge
            outbound_socket.bridge(self.dial_str, lock=False)

            # set bind digit actions
            if self.digits_match and self.callback_url:
                # create event template
                event_template = "Event-Name=CUSTOM,Event-Subclass=plivo::dial,Action=digits-match,Unique-ID=%s,Callback-Url=%s,Callback-Method=%s" \
                    % (outbound_socket.get_channel_unique_id(), self.callback_url, self.callback_method)
                digit_realm = "plivo_bda_dial_%s" % outbound_socket.get_channel_unique_id()
                # for each digits match, set digit binding action
                for dmatch in self.digits_match.split(','):
                    dmatch = dmatch.strip()
                    if dmatch:
                        raw_event = "%s,Digits-Match=%s" % (event_template, dmatch)
                        cmd = "%s,%s,exec:event,'%s'" % (digit_realm, dmatch, raw_event)
                        outbound_socket.bind_digit_action(cmd)
            # set digit realm
            if digit_realm:
                outbound_socket.digit_action_set_realm(digit_realm)

            # waiting event
            event = outbound_socket.wait_for_action()

            # parse received events
            if event['Event-Name'] == 'CHANNEL_UNBRIDGE':
                bleg_uuid = event['variable_bridge_uuid'] or ''
                event = outbound_socket.wait_for_action()
            reason = None
            originate_disposition = event['variable_originate_disposition']
            hangup_cause = originate_disposition
            if hangup_cause == 'ORIGINATOR_CANCEL':
                reason = '%s (A leg)' % hangup_cause
            else:
                reason = '%s (B leg)' % hangup_cause
            if not hangup_cause or hangup_cause == 'SUCCESS':
                hangup_cause = outbound_socket.get_hangup_cause()
                reason = '%s (A leg)' % hangup_cause
                if not hangup_cause:
                    hangup_cause = outbound_socket.get_var('bridge_hangup_cause')
                    reason = '%s (B leg)' % hangup_cause
                    if not hangup_cause:
                        hangup_cause = outbound_socket.get_var('hangup_cause')
                        reason = '%s (A leg)' % hangup_cause
                        if not hangup_cause:
                            hangup_cause = 'NORMAL_CLEARING'
                            reason = '%s (A leg)' % hangup_cause
            outbound_socket.log.info("Dial Finished with reason: %s" \
                                     % reason)
            # Unschedule hangup task
            outbound_socket.bgapi("sched_del %s" % sched_hangup_id)
            # Get ring status
            dial_rang = outbound_socket.get_var("plivo_dial_rang") == 'true'
        finally:
            # If action is set, redirect to this url
            # Otherwise, continue to next Element
            if self.action and is_valid_url(self.action):
                params = {}
                if dial_rang:
                    params['DialRingStatus'] = 'true'
                else:
                    params['DialRingStatus'] = 'false'
                params['DialHangupCause'] = hangup_cause
                params['DialALegUUID'] = outbound_socket.get_channel_unique_id()
                if bleg_uuid:
                    params['DialBLegUUID'] = bleg_uuid
                else:
                    params['DialBLegUUID'] = ''
                if self.redirect:
                    self.fetch_rest_xml(self.action, params, method=self.method)
                else:
                    spawn_raw(outbound_socket.send_to_url, self.action, params, method=self.method)


class GetDigits(Element):
    """Get digits from the caller's keypad

    action: URL to which the digits entered will be sent
    method: submit to 'action' url using GET or POST
    numDigits: how many digits to gather before returning
    timeout: wait for this many seconds before retry or returning
    finishOnKey: key that triggers the end of caller input
    tries: number of tries to execute all says and plays one by one
    playBeep: play a after all plays and says finish
    validDigits: digits which are allowed to be pressed
    invalidDigitsSound: Sound played when invalid digit pressed
    """
    DEFAULT_MAX_DIGITS = 99
    DEFAULT_TIMEOUT = 5

    def __init__(self):
        Element.__init__(self)
        self.nestables = ('Speak', 'Play', 'Wait')
        self.num_digits = None
        self.timeout = None
        self.finish_on_key = None
        self.action = None
        self.play_beep = ""
        self.valid_digits = ""
        self.invalid_digits_sound = ""
        self.retries = None
        self.sound_files = []
        self.method = ""

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        try:
            num_digits = int(self.extract_attribute_value('numDigits',
                             self.DEFAULT_MAX_DIGITS))
        except ValueError:
            num_digits = self.DEFAULT_MAX_DIGITS
        if num_digits > self.DEFAULT_MAX_DIGITS:
            num_digits = self.DEFAULT_MAX_DIGITS
        if num_digits < 1:
            raise RESTFormatException("GetDigits 'numDigits' must be greater than 0")
        try:
            timeout = int(self.extract_attribute_value("timeout", self.DEFAULT_TIMEOUT))
        except ValueError:
            timeout = self.DEFAULT_TIMEOUT * 1000
        if timeout < 1:
            raise RESTFormatException("GetDigits 'timeout' must be a positive integer")

        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.play_beep = self.extract_attribute_value("playBeep") == 'true'
        self.invalid_digits_sound = \
                            self.extract_attribute_value("invalidDigitsSound")
        self.valid_digits = self.extract_attribute_value("validDigits")
        action = self.extract_attribute_value("action")

        try:
            retries = int(self.extract_attribute_value("retries"))
        except ValueError:
            retries = 1
        if retries <= 0:
            raise RESTFormatException("GetDigits 'retries' must be greater than 0")

        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("method must be 'GET' or 'POST'")
        self.method = method

        if action and is_valid_url(action):
            self.action = action
        else:
            self.action = uri
        self.num_digits = num_digits
        self.timeout = timeout * 1000
        self.finish_on_key = finish_on_key
        self.retries = retries

    def prepare(self, outbound_socket):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare Element concurrently
                child_instance.prepare(outbound_socket)

    def execute(self, outbound_socket):
        for child_instance in self.children:
            if isinstance(child_instance, Play):
                sound_file = child_instance.sound_file_path
                if sound_file:
                    loop = child_instance.loop_times
                    if loop == 0:
                        loop = MAX_LOOPS  # Add a high number to Play infinitely
                    # Play the file loop number of times
                    for i in range(loop):
                        self.sound_files.append(sound_file)
                    # Infinite Loop, so ignore other children
                    if loop == MAX_LOOPS:
                        break
            elif isinstance(child_instance, Wait):
                pause_secs = child_instance.length
                pause_str = 'file_string://silence_stream://%s'\
                                % (pause_secs * 1000)
                self.sound_files.append(pause_str)
            elif isinstance(child_instance, Speak):
                text = child_instance.text
                # escape simple quote
                text = text.replace("'", "\\'")
                loop = child_instance.loop_times
                child_type = child_instance.item_type
                method = child_instance.method
                say_str = ''
                if child_type and method:
                    language = child_instance.language
                    say_args = "%s.wav %s %s %s '%s'" \
                                    % (language, language, child_type, method, text)
                    say_str = "${say_string %s}" % say_args
                else:
                    engine = child_instance.engine
                    voice = child_instance.voice
                    say_str = "say:%s:%s:'%s'" % (engine, voice, text)
                if not say_str:
                    continue
                for i in range(loop):
                    self.sound_files.append(say_str)

        outbound_socket.log.info("GetDigits Started %s" % self.sound_files)
        if self.play_beep:
            outbound_socket.log.debug("GetDigits play Beep enabled")
        outbound_socket.play_and_get_digits(max_digits=self.num_digits,
                            max_tries=self.retries, timeout=self.timeout,
                            terminators=self.finish_on_key,
                            sound_files=self.sound_files,
                            invalid_file=self.invalid_digits_sound,
                            valid_digits=self.valid_digits,
                            play_beep=self.play_beep)
        event = outbound_socket.wait_for_action()
        digits = outbound_socket.get_var('pagd_input')
        if digits is not None and self.action:
            outbound_socket.log.info("GetDigits, Digits '%s' Received" % str(digits))
            # Redirect
            params = {'Digits': digits}
            self.fetch_rest_xml(self.action, params, self.method)
        else:
            outbound_socket.log.info("GetDigits, No Digits Received")


class Hangup(Element):
    """Hangup the call
    schedule: schedule hangup in X seconds (default 0, immediate hangup)
    reason: rejected, busy or "" (default "", no reason)

    Note: when hangup is scheduled, reason is not taken into account.
    """
    def __init__(self):
        Element.__init__(self)
        self.reason = ""
        self.schedule = 0

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        self.schedule = self.extract_attribute_value("schedule", 0)
        reason = self.extract_attribute_value("reason")
        if reason == 'rejected':
            self.reason = 'CALL_REJECTED'
        elif reason == 'busy':
            self.reason = 'USER_BUSY'
        else:
            self.reason = ""

    def execute(self, outbound_socket):
        try:
            self.schedule = int(self.schedule)
        except ValueError:
            outbound_socket.log.error("Hangup (scheduled) Failed: bad value for 'schedule'")
            return
        # Schedule the call for hangup at a later time if 'schedule' param > 0
        if self.schedule > 0:
            res = outbound_socket.sched_hangup("+%d ALLOTTED_TIMEOUT" % self.schedule,
                                               lock=True)
            if res.is_success():
                outbound_socket.log.info("Hangup (scheduled) will be fired in %d secs !" \
                                                            % self.schedule)
            else:
                outbound_socket.log.error("Hangup (scheduled) Failed: %s"\
                                                    % str(res.get_response()))
            return "Scheduled in %d secs" % self.schedule
        # Immediate hangup
        else:
            if not self.reason:
                reason = "NORMAL_CLEARING"
            else:
                reason = self.reason
            outbound_socket.log.info("Hanging up now (%s)" % reason)
            outbound_socket.hangup(reason)
        return self.reason


class Number(Element):
    """Specify phone number in a nested Dial element.

    number: number to dial
    sendDigits: key to press after connecting to the number
    gateways: gateway string separated by comma to dialout the number
    gatewayCodecs: codecs for each gateway separated by comma
    gatewayTimeouts: timeouts for each gateway separated by comma
    gatewayRetries: number of times to retry each gateway separated by comma
    extraDialString: extra freeswitch dialstring to be added while dialing out to number
    """
    def __init__(self):
        Element.__init__(self)
        self.number = ''
        self.gateways = []
        self.gateway_codecs = []
        self.gateway_timeouts = []
        self.gateway_retries = []
        self.extra_dial_string = ''
        self.send_digits = ''

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        self.number = element.text.strip()
        # don't allow "|" and "," in a number noun to avoid call injection
        self.number = re.split(',|\|', self.number)[0]
        self.extra_dial_string = \
                                self.extract_attribute_value('extraDialString')
        self.send_digits = self.extract_attribute_value('sendDigits')

        gateways = self.extract_attribute_value('gateways')
        gateway_codecs = self.extract_attribute_value('gatewayCodecs')
        gateway_timeouts = self.extract_attribute_value('gatewayTimeouts')
        gateway_retries = self.extract_attribute_value('gatewayRetries')

        if gateways:
            # get list of gateways removing trailing '/' if found
            self.gateways = [ gw.rstrip('/').strip() for gw in gateways.split(',') ]
        # split gw codecs by , but only outside the ''
        if gateway_codecs:
            self.gateway_codecs = \
                            re.split(''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''',
                                                            gateway_codecs)
        if gateway_timeouts:
            self.gateway_timeouts = gateway_timeouts.split(',')
        if gateway_retries:
            self.gateway_retries = gateway_retries.split(',')



class Wait(Element):
    """Wait for some time to further process the call

    length: length of wait time in seconds
    transferEnabled: break Wait on transfer or hangup
                    (true/false default false)
    """
    def __init__(self):
        Element.__init__(self)
        self.length = 1

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        try:
            length = int(self.extract_attribute_value('length'))
        except ValueError:
            raise RESTFormatException("Wait 'length' must be an integer")
        self.transfer = self.extract_attribute_value("transferEnabled") \
                            == 'true'
        if length < 1:
            raise RESTFormatException("Wait 'length' must be a positive integer")
        self.length = length

    def execute(self, outbound_socket):
        outbound_socket.log.info("Wait Started for %d seconds" \
                                                    % self.length)
        if self.transfer:
            outbound_socket.log.warn("Wait with transfer enabled")
            pause_str = 'file_string://silence_stream://%s'\
                                    % str(self.length * 1000)
            outbound_socket.playback(pause_str)
        else:
            outbound_socket.sleep(str(self.length * 1000), lock=False)
        event = outbound_socket.wait_for_action()


class Play(Element):
    """Play local audio file or at a URL

    url: url of audio file, MIME type on file must be set correctly
    loop: number of time to play the audio - (0 means infinite)
    """
    def __init__(self):
        Element.__init__(self)
        self.audio_directory = ''
        self.loop_times = 1
        self.sound_file_path = ''
        self.temp_audio_path = ''

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        # Extract Loop attribute
        try:
            loop = int(self.extract_attribute_value("loop", 1))
        except ValueError:
            loop = 1
        if loop < 0:
            raise RESTFormatException("Play 'loop' must be a positive integer or 0")
        if loop == 0 or loop > MAX_LOOPS:
            self.loop_times = MAX_LOOPS
        else:
            self.loop_times = loop
        # Pull out the text within the element
        audio_path = element.text.strip()

        if not audio_path:
            raise RESTFormatException("No File to play set !")

        if not is_valid_url(audio_path):
            if file_exists(audio_path):
                self.sound_file_path = audio_path
        else:
            # set to temp path for prepare to process audio caching async
            self.temp_audio_path = audio_path

    def prepare(self, outbound_socket):
        if not self.sound_file_path:
            url = normalize_url_space(self.temp_audio_path)
            if url_exists(url):
                self.sound_file_path = get_resource(outbound_socket, url)

    def execute(self, outbound_socket):
        if self.sound_file_path:
            if self.loop_times == 1:
                play_str = self.sound_file_path
            else:
                outbound_socket.set("playback_delimiter=!")
                play_str = "file_string://silence_stream://1!"
                play_str += '!'.join([ self.sound_file_path for x in range(self.loop_times) ])
            outbound_socket.log.debug("Playing %d times" % self.loop_times)
            res = outbound_socket.playback(play_str)
            if res.is_success():
                event = outbound_socket.wait_for_action()
                if event.is_empty():
                    outbound_socket.log.warn("Play Break (empty event)")
                    return
                outbound_socket.log.debug("Play done (%s)" \
                        % str(event['Application-Response']))
            else:
                outbound_socket.log.error("Play Failed - %s" \
                                % str(res.get_response()))
            outbound_socket.log.info("Play Finished")
            return
        else:
            outbound_socket.log.error("Invalid Sound File - Ignoring Play")


class PreAnswer(Element):
    """Answer the call in Early Media Mode and execute nested element
    """
    def __init__(self):
        Element.__init__(self)
        self.nestables = ('Play', 'Speak', 'GetDigits', 'Wait')

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)

    def prepare(self, outbound_socket):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                child_instance.prepare(outbound_socket)

    def execute(self, outbound_socket):
        outbound_socket.preanswer()
        for child_instance in self.children:
            if hasattr(child_instance, "run"):
                child_instance.run(outbound_socket)
        outbound_socket.log.info("PreAnswer Completed")


class Record(Element):
    """Record audio from caller

    action: submit the result of the record to this URL
    method: submit to 'action' url using GET or POST
    maxLength: maximum number of seconds to record (default 60)
    timeout: seconds of silence before considering the recording complete (default 500)
            Only used when bothLegs is 'false' !
    playBeep: play a beep before recording (true/false, default true)
            Only used when bothLegs is 'false' !
    finishOnKey: Stop recording on this key
    fileFormat: file format (default mp3)
    filePath: complete file path to save the file to
    fileName: Default empty, if given this will be used for the recording
    bothLegs: record both legs (true/false, default false)
              no beep will be played
    """
    def __init__(self):
        Element.__init__(self)
        self.silence_threshold = 500
        self.max_length = None
        self.timeout = None
        self.finish_on_key = ""
        self.file_path = ""
        self.play_beep = ""
        self.file_format = ""
        self.filename = ""
        self.both_legs = False
        self.action = ''
        self.method = ''

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        max_length = self.extract_attribute_value("maxLength")
        timeout = self.extract_attribute_value("timeout")
        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.file_path = self.extract_attribute_value("filePath")
        if self.file_path:
            self.file_path = os.path.normpath(self.file_path) + os.sep
        self.play_beep = self.extract_attribute_value("playBeep") == 'true'
        self.file_format = self.extract_attribute_value("fileFormat")
        if self.file_format not in ('wav', 'mp3'):
            raise RESTFormatException("Format must be 'wav' or 'mp3'")
        self.filename = self.extract_attribute_value("fileName")
        self.both_legs = self.extract_attribute_value("bothLegs") == 'true'

        self.action = self.extract_attribute_value("action")
        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("method must be 'GET' or 'POST'")
        self.method = method

        # Validate maxLength
        try:
            max_length = int(max_length)
        except (ValueError, TypeError):
            raise RESTFormatException("Record 'maxLength' must be a positive integer")
        if max_length < 1:
            raise RESTFormatException("Record 'maxLength' must be a positive integer")
        self.max_length = str(max_length)
        # Validate timeout
        try:
            timeout = int(timeout)
        except (ValueError, TypeError):
            raise RESTFormatException("Record 'timeout' must be a positive integer")
        if timeout < 1:
            raise RESTFormatException("Record 'timeout' must be a positive integer")
        self.timeout = str(timeout)
        # Finish on Key
        self.finish_on_key = finish_on_key

    def execute(self, outbound_socket):
        if self.filename:
            filename = self.filename
        else:
            filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"),
                                outbound_socket.get_channel_unique_id())
        record_file = "%s%s.%s" % (self.file_path, filename, self.file_format)

        if self.both_legs:
            outbound_socket.set("RECORD_STEREO=true")
            outbound_socket.set("media_bug_answer_req=true")
            outbound_socket.record_session(record_file)
            outbound_socket.api("sched_api +%s none uuid_record %s stop %s" \
                                % (self.max_length,
                                   outbound_socket.get_channel_unique_id(),
                                   record_file)
                               )
            outbound_socket.log.info("Record Both Executed")
        else:
            if self.play_beep:
                beep = 'tone_stream://%(300,200,700)'
                outbound_socket.playback(beep)
                event = outbound_socket.wait_for_action()
                # Log playback execute response
                outbound_socket.log.debug("Record Beep played (%s)" \
                                % str(event.get_header('Application-Response')))
            outbound_socket.start_dtmf()
            outbound_socket.log.info("Record Started")
            outbound_socket.record(record_file, self.max_length,
                                self.silence_threshold, self.timeout,
                                self.finish_on_key)
            event = outbound_socket.wait_for_action()
            outbound_socket.stop_dtmf()
            outbound_socket.log.info("Record Completed")

        # If action is set, redirect to this url
        # Otherwise, continue to next Element
        if self.action and is_valid_url(self.action):
            params = {}
            params['RecordingFileFormat'] = self.file_format
            params['RecordingFilePath'] = self.file_path
            params['RecordingFileName'] = filename
            params['RecordFile'] = record_file
            # case bothLegs is True
            if self.both_legs:
                # RecordingDuration not available for bothLegs because recording is in progress
                # Digits is empty for the same reason
                params['RecordingDuration'] = "-1"
                params['Digits'] = ""
            # case bothLegs is False
            else:
                try:
                    record_ms = event.get_header('variable_record_ms')
                    if not record_ms:
                        record_ms = "-1"
                    else:
                        record_ms = str(int(record_ms)) # check if integer
                except (ValueError, TypeError):
                    outbound_socket.log.warn("Invalid 'record_ms' : '%s'" % str(record_ms))
                    record_ms = "-1"
                params['RecordingDuration'] = record_ms
                record_digits = event.get_header("variable_playback_terminator_used")
                if record_digits:
                    params['Digits'] = record_digits
                else:
                    params['Digits'] = ""
            # fetch xml
            self.fetch_rest_xml(self.action, params, method=self.method)


class Redirect(Element):
    """Redirect call flow to another Url.
    Url is set in element body
    method: GET or POST
    """
    def __init__(self):
        Element.__init__(self)
        self.method = ""
        self.url = ""

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("Method must be 'GET' or 'POST'")
        self.method = method
        url = element.text.strip()
        if not url:
            raise RESTFormatException("Redirect must have a URL")
        if not is_valid_url(url):
            raise RESTFormatException("Redirect URL not valid!")
        self.url = url

    def execute(self, outbound_socket):
        self.fetch_rest_xml(self.url, method=self.method)


class Speak(Element):
    """Speak text

    text: text to say
    voice: voice to be used based on engine
    language: language to use
    loop: number of times to say this text (0 for unlimited)
    engine: voice engine to be used for Speak (flite, cepstral)

    Extended params - Currently uses Callie (Female) Voice
    type: NUMBER, ITEMS, PERSONS, MESSAGES, CURRENCY, TIME_MEASUREMENT,
          CURRENT_DATE, CURRENT_TIME, CURRENT_DATE_TIME, TELEPHONE_NUMBER,
          TELEPHONE_EXTENSION, URL, IP_ADDRESS, EMAIL_ADDRESS, POSTAL_ADDRESS,
          ACCOUNT_NUMBER, NAME_SPELLED, NAME_PHONETIC, SHORT_DATE_TIME
    method: PRONOUNCED, ITERATED, COUNTED

    Flite Voices  : slt, rms, awb, kal
    Cepstral Voices : (Use any voice here supported by cepstral)
    """
    valid_methods = ('PRONOUNCED', 'ITERATED', 'COUNTED')
    valid_types = ('NUMBER', 'ITEMS', 'PERSONS', 'MESSAGES',
                   'CURRENCY', 'TIME_MEASUREMENT', 'CURRENT_DATE', ''
                   'CURRENT_TIME', 'CURRENT_DATE_TIME', 'TELEPHONE_NUMBER',
                   'TELEPHONE_EXTENSION', 'URL', 'IP_ADDRESS', 'EMAIL_ADDRESS',
                   'POSTAL_ADDRESS', 'ACCOUNT_NUMBER', 'NAME_SPELLED',
                   'NAME_PHONETIC', 'SHORT_DATE_TIME')

    def __init__(self):
        Element.__init__(self)
        self.loop_times = 1
        self.language = "en"
        self.sound_file_path = ""
        self.engine = ""
        self.voice = ""
        self.item_type = ""
        self.method = ""

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        # Extract Loop attribute
        try:
            loop = int(self.extract_attribute_value("loop", 1))
        except ValueError:
            loop = 1
        if loop < 0:
            raise RESTFormatException("Speak 'loop' must be a positive integer or 0")
        if loop == 0 or loop > MAX_LOOPS:
            self.loop_times = MAX_LOOPS
        else:
            self.loop_times = loop
        self.engine = self.extract_attribute_value("engine")
        self.language = self.extract_attribute_value("language")
        self.voice = self.extract_attribute_value("voice")
        item_type = self.extract_attribute_value("type")
        if item_type in self.valid_types:
            self.item_type = item_type
        method = self.extract_attribute_value("method")
        if method in self.valid_methods:
            self.method = method

    def execute(self, outbound_socket):
        if self.item_type and self.method:
            say_args = "%s %s %s %s" \
                    % (self.language, self.item_type,
                       self.method, self.text)
        else:
            say_args = "%s|%s|%s" % (self.engine, self.voice, self.text)
        if self.item_type and self.method:
            res = outbound_socket.say(say_args, loops=self.loop_times)
        else:
            res = outbound_socket.speak(say_args, loops=self.loop_times)
        if res.is_success():
            for i in range(self.loop_times):
                outbound_socket.log.debug("Speaking %d times ..." % (i+1))
                event = outbound_socket.wait_for_action()
                if event.is_empty():
                    outbound_socket.log.warn("Speak Break (empty event)")
                    return
                outbound_socket.log.debug("Speak %d times done (%s)" \
                            % ((i+1), str(event['Application-Response'])))
                gevent.sleep(0.01)
            outbound_socket.log.info("Speak Finished")
            return
        else:
            outbound_socket.log.error("Speak Failed - %s" \
                            % str(res.get_response()))
            return
