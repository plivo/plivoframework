# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

import gevent
import os.path
from datetime import datetime
import re
import uuid
from plivo.rest.freeswitch.helpers import is_valid_url, url_exists, \
                                                        file_exists
from plivo.rest.freeswitch.exceptions import RESTFormatException, \
                                            RESTAttributeException, \
                                            RESTRedirectException, \
                                            RESTNoExecuteException


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
                'hangupOnStar': 'false'
        },
        'Dial': {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                'method': 'POST',
                'hangupOnStar': 'false',
                #callerId: DYNAMIC! MUST BE SET IN METHOD,
                'timeLimit': 0,
                'confirmSound': '',
                'confirmKey': '',
                'dialMusic': ''
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
                'timeout': 15,
                'finishOnKey': '1234567890*#',
                'maxLength': 60,
                'playBeep': 'true',
                'filePath': '/usr/local/freeswitch/recordings/',
                'format': 'mp3',
                'prefix': '',
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


class Element(object):
    """Abstract Element Class to be inherited by all Element elements"""

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
        result = execute(outbound_socket)
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
        try:
            self.enter_sound = self.extract_attribute_value('enterSound')
        except ValueError:
            self.enter_sound = ''
        try:
            self.exit_sound = self.extract_attribute_value('exitSound')
        except ValueError:
            self.exit_sound = ''

    def _prepare_moh(self):
        mohs = []
        if not self.moh_sound:
            return mohs
        for audio_path in self.moh_sound.split(','):
            if not is_valid_url(audio_path):
                if file_exists(audio_path):
                    mohs.append(audio_path)
            else:
                if url_exists(audio_path):
                    if audio_path[-4:].lower() != '.mp3':
                        raise RESTFormatException("Only mp3 files allowed for remote file play")
                    if audio_path[:7].lower() == 'http://':
                        audio_path = audio_path[7:]
                    elif audio_path[:8].lower() == 'https://':
                        audio_path = audio_path[8:]
                    elif audio_path[:6].lower() == 'ftp://':
                        audio_path = audio_path[6:]
                    else:
                        pass
                    mohs.append("shout://%s" % audio_path)
        return mohs

    def execute(self, outbound_socket):
        flags = []
        # settings for conference room
        outbound_socket.set("conference_controls=none")
        if self.max_members > 0:
            outbound_socket.set("max-members=%d" % self.max_members)
        else:
            outbound_socket.unset("max-members")
        # set moh sound
        mohs = self._prepare_moh()
        if not mohs:
            outbound_socket.unset("conference_moh_sound")
        else:
            outbound_socket.set("playback_delimiter=!")
            play_str = "file_string://silence_stream://1"
            for moh in mohs:
                play_str = "%s!%s" % (play_str, moh)
            outbound_socket.set("conference_moh_sound=%s" % play_str)
        # set member flags
        if self.muted:
            flags.append("muted")
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
        # wait for action event
        event = outbound_socket.wait_for_action()
        # if event is add-member, get Member-ID
        # and set extra features for conference
        if event['Event-Subclass'] == 'conference::maintenance' \
            and event['Action'] == 'add-member':
            member_id = event['Member-ID']
            outbound_socket.log.debug("Entered Conference: Room %s with Member-ID %s" \
                            % (self.room, member_id))
            # set digit binding if hangupOnStar is enabled
            if member_id and self.hangup_on_star:
                bind_digit_realm = "conf_%s" % outbound_socket.get_channel_unique_id()
                outbound_socket.bind_digit_action("%s,*,exec:conference,%s kick %s" \
                            % (bind_digit_realm, self.room, member_id), lock=True)
            # set beep on enter/exit if enabled
            if member_id:
                if self.enter_sound == 'beep:1':
                    outbound_socket.api("conference %s enter_sound file tone_stream://%%(300,200,700)" % self.room)
                elif self.enter_sound == 'beep:2':
                    outbound_socket.api("conference %s enter_sound file tone_stream://L=2;%%(300,200,700)" % self.room)
                if self.exit_sound == 'beep:1':
                    outbound_socket.api("conference %s exit_sound file tone_stream://%%(300,200,700)" % self.room)
                elif self.exit_sound == 'beep:2':
                    outbound_socket.api("conference %s exit_sound file tone_stream://L=2;%%(300,200,700)" % self.room)
            # now really wait conference ending for this member
            event = outbound_socket.wait_for_action()
        outbound_socket.log.info("Leaving Conference: Room %s" % self.room)


class Dial(Element):
    """Dial another phone number and connect it to this call

    action: submit the result of the dial to this URL
    method: submit to 'action' url using GET or POST
    hangupOnStar: hangup the b leg if a leg presses start and this is true
    callerId: caller id to be send to the dialed number
    timeLimit: hangup the call after these many seconds. 0 means no timeLimit
    confirmSound: Sound to be played to b leg before call is bridged
    confirmKey: Key to be pressed to bridge the call.
    dialMusic: Play music to a leg while doing a dial to b leg
                Can be a list of files separated by comma
    """
    DEFAULT_TIMEOUT = 30
    DEFAULT_TIMELIMIT = 14400

    def __init__(self):
        Element.__init__(self)
        self.nestables = ['Number']
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
        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("Method, must be 'GET' or 'POST'")
        self.method = method

    def _prepare_moh(self):
        mohs = []
        if not self.dial_music:
            return mohs
        for audio_path in self.dial_music.split(','):
            if not is_valid_url(audio_path):
                if file_exists(audio_path):
                    mohs.append(audio_path)
            else:
                if url_exists(audio_path):
                    if audio_path[-4:].lower() != '.mp3':
                        raise RESTFormatException("Only mp3 files allowed for remote file play")
                    if audio_path[:7].lower() == "http://":
                        audio_path = audio_path[7:]
                    elif audio_path[:8].lower() == "https://":
                        audio_path = audio_path[8:]
                    elif audio_path[:6].lower() == "ftp://":
                        audio_path = audio_path[6:]
                    else:
                        pass
                    mohs.append("shout://%s" % audio_path)
        return mohs

    def create_number(self, number_instance):
        num_gw = []
        # skip number object without gateway or number
        if not number_instance.gateways or not number_instance.number:
            return ''
        if number_instance.send_digits:
            option_send_digits = "api_on_answer='uuid_recv_dtmf ${uuid} %s'" \
                                                % number_instance.send_digits
        else:
            option_send_digits = ''
        count = 0
        for gw in number_instance.gateways:
            num_options = []
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
        result = ','.join(num_gw)
        return result

    def execute(self, outbound_socket):
        dial_options = []
        numbers = []
        # Set timeout
        outbound_socket.set("call_timeout=%d" % self.timeout)
        outbound_socket.set("answer_timeout=%d" % self.timeout)
        # Set callerid or unset if not provided
        if self.caller_id:
            caller_id = "effective_caller_id_number=%s" % self.caller_id
            dial_options.append(caller_id)
        else:
            outbound_socket.unset("effective_caller_id_number")
        # Set ring flag if dial will ring. 
        # But first set plivo_dial_rang to false
        # to be sure we don't get it from an old Dial
        outbound_socket.set("plivo_dial_rang=false")
        outbound_socket.set("execute_on_ring=eval ${uuid_setvar(%s plivo_dial_rang true}" \
                            % outbound_socket.get_channel_unique_id())
        # Set numbers to dial from Number nouns
        for child in self.children:
            if isinstance(child, Number):
                dial_num = self.create_number(child)
                if not dial_num:
                    continue
                numbers.append(dial_num)
        if not numbers:
            outbound_socket.log.error("Dial Aborted, No Number to dial !")
            return
        # Create dialstring
        self.dial_str = '{'
        self.dial_str += ','.join(dial_options)
        self.dial_str += '}'
        self.dial_str += ','.join(numbers)
        # Don't hangup after bridge !
        outbound_socket.set("hangup_after_bridge=false")
        # Set time limit: when reached, B Leg is hung up
        sched_hangup_id = str(uuid.uuid1())
        hangup_str = "api_on_answer=sched_api +%d %s uuid_transfer %s -bleg 'hangup:ALLOTTED_TIMEOUT' inline" \
                      % (self.time_limit, sched_hangup_id,
                         outbound_socket.get_channel_unique_id())
        outbound_socket.set(hangup_str)
        # Set hangup on '*' or unset if not provided
        if self.hangup_on_star:
            outbound_socket.set("bridge_terminate_key=*")
        else:
            outbound_socket.unset("bridge_terminate_key")
        # Play Dial music or bridge the early media accordingly
        mohs = self._prepare_moh()
        if not mohs:
            outbound_socket.set("bridge_early_media=true")
            outbound_socket.unset("instant_ringback")
            outbound_socket.unset("ringback")
        else:
            outbound_socket.set("playback_delimiter=!")
            play_str = "file_string://silence_stream://1"
            for moh in mohs:
                play_str = "%s!%s" % (play_str, moh)
            outbound_socket.set("bridge_early_media=true")
            outbound_socket.set("instant_ringback=true")
            outbound_socket.set("ringback=%s" % play_str)
        # Set confirm sound and key or unset if not provided
        if self.confirm_sound:
            # Use confirm key if present else just play music
            if self.confirm_key:
                confirm_music_str = "group_confirm_file=%s" % self.confirm_sound
                confirm_key_str = "group_confirm_key=%s" % self.confirm_key
            else:
                confirm_music_str = "group_confirm_file=playback %s" % self.confirm_sound
                confirm_key_str = "group_confirm_key=exec"
            # Cancel the leg timeout after the call is answered
            outbound_socket.set("group_confirm_cancel_timeout=1")
            outbound_socket.set(confirm_music_str)
            outbound_socket.set(confirm_key_str)
        else:
            outbound_socket.unset("group_confirm_cancel_timeout")
            outbound_socket.unset("group_confirm_file")
            outbound_socket.unset("group_confirm_key")
        # Start dial
        outbound_socket.log.info("Dial Started %s" % self.dial_str)
        outbound_socket.bridge(self.dial_str)
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
        outbound_socket.log.info("Dial Finished with reason: %s" \
                                 % reason)
        # Unschedule hangup task
        outbound_socket.bgapi("sched_del %s" % sched_hangup_id)
        # Get ring status
        dial_rang = outbound_socket.get_var("plivo_dial_rang") == 'true'
        # If action is set, redirect to this url
        # Otherwise, continue to next Element
        if self.action and is_valid_url(self.action):
            params = {}
            if dial_rang:
                params['RingStatus'] = 'true'
            else:
                params['RingStatus'] = 'false'
            params['HangupCause'] = hangup_cause
            self.fetch_rest_xml(self.action, params, method=self.method)


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
        self.nestables = ['Speak', 'Play', 'Wait']
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
            raise RESTAttributeException("Method, must be 'GET' or 'POST'")
        self.method = method

        if action and is_valid_url(action):
            self.action = action
        else:
            self.action = uri
        self.num_digits = num_digits
        self.timeout = timeout * 1000
        self.finish_on_key = finish_on_key
        self.retries = retries

    def prepare(self):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare Element concurrently
                child_instance.prepare()

    def execute(self, outbound_socket):
        for child_instance in self.children:
            if isinstance(child_instance, Play):
                sound_file = child_instance.sound_file_path
                if sound_file:
                    loop = child_instance.loop_times
                    if loop == 0:
                        loop = 99  # Add a high number to Play infinitely
                    # Play the file loop number of times
                    for i in range(loop):
                        self.sound_files.append(sound_file)
                    # Infinite Loop, so ignore other children
                    if loop == 99:
                        break
            elif isinstance(child_instance, Wait):
                pause_secs = child_instance.length
                pause_str = play_str = 'silence_stream://%s'\
                                                        % (pause_secs * 1000)
                self.sound_files.append(pause_str)
            elif isinstance(child_instance, Speak):
                text = child_instance.text
                loop = child_instance.loop_times
                child_type = child_instance.item_type
                method = child_instance.method
                if child_type and method:
                    language = child_instance.language
                    say_args = "%s.wav %s %s %s '%s'" \
                                    % (language, language, child_type, method, text)
                    say_str = "${say_string %s}" % say_args
                else:
                    engine = child_instance.engine
                    voice = child_instance.voice
                    say_str = "say:%s:%s:'%s'" % (engine, voice, text)
                for i in range(loop):
                    self.sound_files.append(say_str)
            else:
                pass  # Ignore invalid nested Element

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
            outbound_socket.info("GetDigits, Digits '%s' Pressed" % str(digits))
            # Redirect
            params = {'Digits': digits}
            self.fetch_rest_xml(self.action, params, self.method)
        else:
            outbound_socket.info("GetDigits, No Digits Pressed" % str(digits))


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
    gatewayCodecs: codecs for each gatway separated by comma
    gatewayTimeouts: timeouts for each gateway separated by comma
    gatewayRetries: number of times to retry each gateway separated by comma
    extraDialString: extra freeswitch dialstring to be added while dialing out to number
    """
    def __init__(self):
        Element.__init__(self)
        self.number = ""
        self.gateways = []
        self.gateway_codecs = []
        self.gateway_timeouts = []
        self.gateway_retries = []
        self.extra_dial_string = ""
        self.send_digits = ""

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        self.number = element.text.strip()
        # don't allow "|" and "," in a number noun to avoid call injection
        self.number = re.split(',|\|', self.number)[0]
        self.extra_dial_string = \
                                self.extract_attribute_value("extraDialString")
        self.send_digits = self.extract_attribute_value("sendDigits")

        gateways = self.extract_attribute_value("gateways")
        gateway_codecs = self.extract_attribute_value("gatewayCodecs")
        gateway_timeouts = self.extract_attribute_value("gatewayTimeouts")
        gateway_retries = self.extract_attribute_value("gatewayRetries")

        if gateways:
            self.gateways = gateways.split(',')
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
            length = int(self.extract_attribute_value("length"))
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
            pause_str = 'silence_stream://%s'\
                                    % str(self.length * 1000)
            outbound_socket.playback(pause_str)
        else:
            outbound_socket.sleep(str(self.length * 1000), lock=False)
        event = outbound_socket.wait_for_action()


class Play(Element):
    """Play audio file at a URL

    url: url of audio file, MIME type on file must be set correctly
    loop: number of time to play the audio - (0 means infinite)
    """
    def __init__(self):
        Element.__init__(self)
        self.audio_directory = ""
        self.loop_times = 1
        self.sound_file_path = ""

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        # Extract Loop attribute
        try:
            loop = int(self.extract_attribute_value("loop", 1))
        except ValueError:
            loop = 1
        if loop < 0:
            raise RESTFormatException("Play 'loop' must be a positive integer or 0")
        self.loop_times = loop
        # Pull out the text within the element
        audio_path = element.text.strip()

        if not audio_path:
            raise RESTFormatException("No File to play set !")

        if not is_valid_url(audio_path):
            if file_exists(audio_path):
                self.sound_file_path = audio_path
        else:
            if url_exists(audio_path):
                if audio_path[-4:].lower() != '.mp3':
                    raise RESTFormatException("Only mp3 files allowed for remote file play")
                if audio_path[:7].lower() == "http://":
                    audio_path = audio_path[7:]
                elif audio_path[:8].lower() == "https://":
                    audio_path = audio_path[8:]
                elif audio_path[:6].lower() == "ftp://":
                    audio_path = audio_path[6:]
                else:
                    pass
                self.sound_file_path = "shout://%s" % audio_path

    def prepare(self):
        # TODO: If Sound File is Audio URL then Check file type format
        # Download the file, move to audio directory and set sound file path
        # Create MD5 hash to identify the with filename for caching
        pass

    def execute(self, outbound_socket):
        if self.sound_file_path:
            if self.is_infinite():
                # Play sound infinitely
                outbound_socket.endless_playback(self.sound_file_path)
                # Log playback execute response
                outbound_socket.log.info("Infinite Play started")
                outbound_socket.wait_for_action()
            else:
                for i in range(self.loop_times):
                    res = outbound_socket.playback(self.sound_file_path)
                    if res.is_success():
                        gevent.sleep(0)
                        event = outbound_socket.wait_for_action()
                        gevent.sleep(0.01)
                    else:
                        outbound_socket.log.error("Play Failed - %s" \
                                        % str(res.get_response()))
                        return
                # Log playback execute response
                outbound_socket.log.info("Play finished")
        else:
            outbound_socket.log.error("Invalid Sound File - Ignoring Play")

    def is_infinite(self):
        if self.loop_times <= 0:
            return True
        return False


class PreAnswer(Element):
    """Answer the call in Early Media Mode and execute nested element
    """
    def __init__(self):
        Element.__init__(self)
        self.nestables = ['Play', 'Speak', 'GetDigits', 'Wait']

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)

    def prepare(self):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare element concurrently
                child_instance.prepare()

    def execute(self, outbound_socket):
        outbound_socket.preanswer()
        for child_instance in self.children:
            if hasattr(child_instance, "run"):
                child_instance.run(outbound_socket)
        outbound_socket.log.info("PreAnswer Completed")


class Record(Element):
    """Record audio from caller

    maxLength: maximum number of seconds to record (default 60)
    timeout: seconds of silence before considering the recording complete (default 500)
    playBeep: play a beep before recording (true/false, default true)
    format: file format (default mp3)
    filePath: complete file path to save the file to
    finishOnKey: Stop recording on this key
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
        self.format = ""
        self.prefix = ""
        self.both_legs = False

    def parse_element(self, element, uri=None):
        Element.parse_element(self, element, uri)
        max_length = self.extract_attribute_value("maxLength")
        timeout = self.extract_attribute_value("timeout")
        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.file_path = self.extract_attribute_value("filePath")
        if self.file_path:
            self.file_path = os.path.normpath(self.file_path) + os.sep
        self.play_beep = self.extract_attribute_value("playBeep") == 'true'
        self.format = self.extract_attribute_value("format")
        self.prefix = self.extract_attribute_value("prefix")
        self.both_legs = self.extract_attribute_value("bothLegs") == 'true'

        if max_length < 1:
            raise RESTFormatException("Record 'maxLength' must be a positive integer")
        self.max_length = max_length
        if timeout < 1:
            raise RESTFormatException("Record 'timeout' must be a positive integer")
        self.timeout = timeout
        # :TODO Validate Finish on Key
        self.finish_on_key = finish_on_key

    def execute(self, outbound_socket):
        filename = "%s%s-%s" % (self.prefix,
                                datetime.now().strftime("%Y%m%d-%H%M%S"),
                                outbound_socket.call_uuid)
        record_file = "%s%s.%s" % (self.file_path, filename, self.format)
        if self.both_legs:
            outbound_socket.set("RECORD_STEREO=true")
            outbound_socket.set("media_bug_answer_req=true")
            outbound_socket.record_session(record_file)
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
    DEFAULT_LOOP = 1

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
        try:
            self.loop_times = int(self.extract_attribute_value("loop", self.DEFAULT_LOOP))
        except ValueError:
            self.loop_times = self.DEFAULT_LOOP
        if self.loop_times <= 0:
            self.loop_times = 999
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

        for i in range(self.loop_times):
            if self.item_type and self.method:
                outbound_socket.say(say_args)
            else:
                outbound_socket.speak(say_args)
            event = outbound_socket.wait_for_action()
            # Log Speak execute response
            outbound_socket.log.info("Speak %d times - (%s)" \
                    % ((i+1), str(event.get_header('Application-Response'))))
