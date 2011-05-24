# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

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


RECOGNIZED_SOUND_FORMATS = ["audio/mpeg", "audio/wav", "audio/x-wav"]

GRAMMAR_DEFAULT_PARAMS = {
        "Conference": {
                "room": "",
        },
        "Dial": {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                "method": "POST",
                "hangupOnStar": "false",
                #callerId: DYNAMIC! MUST BE SET IN METHOD,
                "timeLimit": 0,
                "confirmSound": "",
                "confirmKey": "",
                "dialMusic": ""
        },
        "GetDigits": {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                "method": "POST",
                "timeout": 5,
                "finishOnKey": '#',
                "numDigits": 99,
                "retries": 1,
                "playBeep": 'false',
                "validDigits": '0123456789*#',
                "invalidDigitsSound": ''
        },
        "Hangup": {
        },
        "Number": {
                #"gateways": DYNAMIC! MUST BE SET IN METHOD,
                #"gatewayCodecs": DYNAMIC! MUST BE SET IN METHOD,
                #"gatewayTimeouts": DYNAMIC! MUST BE SET IN METHOD,
                #"gatewayRetries": DYNAMIC! MUST BE SET IN METHOD,
                #"extraDialString": DYNAMIC! MUST BE SET IN METHOD,
                "sendDigits": "",
        },
        "Wait": {
                "length": 1
        },
        "Play": {
                "loop": 1
        },
        "Preanswer": {
        },
        "Record": {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                "method": 'POST',
                "timeout": 15,
                "finishOnKey": "1234567890*#",
                "maxLength": 3600,
                "playBeep": 'true',
                "filePath": "/usr/local/freeswitch/recordings/",
                "format": "mp3",
                "prefix": ""
        },
        "RecordSession": {
                "filePath": "/usr/local/freeswitch/recordings/",
                "format": "mp3",
                "prefix": ""
        },
        "Redirect": {
                "method": "POST"
        },
        "Reject": {
                "reason": "rejected"
        },
        "Speak": {
                "voice": "slt",
                "language": "en",
                "loop": 1,
                "engine": "flite",
                "method": "",
                "type": ""
        },
        "ScheduleHangup": {
                "time": 0
        }
    }


class Grammar(object):
    """Abstract Grammar Class to be inherited by all Grammar elements
    """
    def __init__(self):
        self.name = str(self.__class__.__name__)
        self.nestables = None
        self.attributes = {}
        self.text = ''
        self.children = []

    def parse_grammar(self, element, uri=None):
        self.prepare_attributes(element)
        self.prepare_text(element)

    def run(self, outbound_socket):
        outbound_socket.log.info("[%s] %s %s" \
            % (self.name, self.text, self.attributes))
        execute = getattr(self, 'execute')
        if not execute:
            outbound_socket.log.error("[%s] cannot be executed !" % self.name)
            raise RESTExecuteException("%s cannot be executed !" % self.name)
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
        grammar_dict = GRAMMAR_DEFAULT_PARAMS[self.name]
        if element.attrib and not grammar_dict:
            raise RESTFormatException("%s does not require any attributes!"
                                                                % self.name)
        self.attributes = dict(grammar_dict, **element.attrib)

    def prepare_text(self, element):
        text = element.text
        if not text:
            self.text = ''
        else:
            self.text = text.strip()

    def fetch_rest_xml(self, url, params={}, method='POST'):
        raise RESTRedirectException(url, params, method)


class Conference(Grammar):
    """Go to a Conference Room
    room name is body text of Conference element.

    waitSound: sound to play while alone in conference
    muted: enter conference muted
    startConferenceOnEnter: the conference start when this member joins
    endConferenceOnExit: close conference after this user leaves
    maxMembers: max members in conference (0 for no limit)
    beep: if 0, disabled
          if 1, play one beep when a member enters/leaves
          if 2 play two beeps when a member enters/leaves
          (default 0)
    """
    def __init__(self):
        Grammar.__init__(self)
        self.room = ''
        self.moh_sound = None
        self.muted = False
        self.start_on_enter = True
        self.end_on_exit = False
        self.max_members = 200
        self.play_beep = 0

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        room = self.text
        if not room:
            raise RESTFormatException("Conference Room must be defined")
        self.room = room + '@plivo'
        self.moh_sound = self.extract_attribute_value("waitSound", None)
        self.muted = self.extract_attribute_value("muted", 'false') \
                        == 'true'
        self.start_on_enter = self.extract_attribute_value("startConferenceOnEnter", 'true') \
                                == 'true'
        self.end_on_exit = self.extract_attribute_value("endConferenceOnExit", 'false') \
                                == 'true'
        try:
            self.max_members = int(self.extract_attribute_value("maxMembers", 200))
        except ValueError:
            self.max_members = 200
        try:
            self.play_beep = int(self.extract_attribute_value("endConferenceOnExit", 0))
        except ValueError:
            self.play_beep = 0

    def execute(self, outbound_socket):
        flags = []
        outbound_socket.set("conference_controls=none")
        if self.moh_sound:
            outbound_socket.set("conference_moh_sound=%s" % self.moh_sound)
        else:
            outbound_socket.unset("conference_moh_sound")
        if self.play_beep == 1:
            outbound_socket.set("conference_enter_sound='tone_stream://%(300,200,700)'")
            outbound_socket.set("conference_exit_sound='tone_stream://%(300,200,700)'")
        elif self.play_beep == 2:
            outbound_socket.set("conference_enter_sound='tone_stream://L=2;%(300,200,700)'")
            outbound_socket.set("conference_exit_sound='tone_stream://L=2;%(300,200,700)'")
        else:
            outbound_socket.unset("conference_enter_sound")
            outbound_socket.unset("conference_exit_sound")
        if self.max_members > 0:
            outbound_socket.set("max-members=%d" % self.max_members)
        else:
            outbound_socket.unset("max-members")
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
            outbound_socket.unset("conference_moh_sound")
        outbound_socket.log.info("Entering Conference: Room %s (flags %s)" \
                                        % (str(self.room), flags_opt))
        outbound_socket.conference(str(self.room))
        event = outbound_socket.wait_for_action()
        outbound_socket.log.info("Leaving Conference: Room %s" \
                                        % str(self.room))


class Dial(Grammar):
    """Dial another phone number and connect it to this call

    action: submit the result of the dial to this URL
    method: submit to 'action' url using GET or POST
    hangupOnStar: hangup the bleg is a leg presses start and this is true
    callerId: caller id to be send to the dialed number
    timeLimit: hangup the call after these many seconds. 0 means no timeLimit
    confirmSound: Sound to be played to b leg before call is bridged
    confirmKey: Key to be pressed to bridge the call.
    dialMusic: Play this music to a-leg while doing a dial to bleg
    """
    DEFAULT_TIMEOUT = 30
    DEFAULT_TIMELIMIT = 14400

    def __init__(self):
        Grammar.__init__(self)
        self.nestables = ['Number']
        self.method = ""
        self.action = ""
        self.hangup_on_star = False
        self.caller_id = ''
        self.time_limit = self.DEFAULT_TIMELIMIT
        self.timeout = self.DEFAULT_TIMEOUT
        self.dial_str = ""
        self.confirm_sound = ""
        self.confirm_key = ""
        self.dial_music = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        self.action = self.extract_attribute_value("action")
        self.caller_id = self.extract_attribute_value("callerId")
        try:
            self.time_limit = int(self.extract_attribute_value("timeLimit",
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
        # Set callerid
        if self.caller_id:
            caller_id = "effective_caller_id_number=%s" % self.caller_id
            dial_options.append(caller_id)
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
        # Set hangup on '*'
        if self.hangup_on_star:
            outbound_socket.set("bridge_terminate_key=*")
        # Play Dial music or bridge the early media accordingly
        if self.dial_music:
            outbound_socket.set("bridge_early_media=true")
            outbound_socket.set("instant_ringback=true")
            outbound_socket.set("ringback=file_string://%s" % self.dial_music)
        else:
            outbound_socket.set("bridge_early_media=true")
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
        # Unsched hangup
        outbound_socket.bgapi("sched_del %s" % sched_hangup_id)
        # Call url action
        if self.action and is_valid_url(self.action):
            self.fetch_rest_xml(self.action, method=self.method)


class GetDigits(Grammar):
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
        Grammar.__init__(self)
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

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        try:
            num_digits = int(self.extract_attribute_value("numDigits",
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
        if timeout < 0:
            raise RESTFormatException("GetDigits 'timeout' must be a positive integer")

        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.play_beep = self.extract_attribute_value("playBeep", 'false') == 'true'
        self.invalid_digits_sound = \
                            self.extract_attribute_value("invalidDigitsSound")
        self.valid_digits = self.extract_attribute_value("validDigits")
        action = self.extract_attribute_value("action")

        try:
            retries = int(self.extract_attribute_value("retries", 1))
        except ValueError:
            retries = 1
        if retries < 0:
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
                # :TODO Prepare Grammar concurrently
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
                pass  # Ignore invalid nested Grammar

        outbound_socket.log.info("GetDigits Started %s" % self.sound_files)
        if self.play_beep:
            outbound_socket.log.debug("GetDigits will play a beep")
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
            # Redirect
            params = {'Digits': digits}
            self.fetch_rest_xml(self.action, params, self.method)


class Hangup(Grammar):
    """Hangup the call
    """
    def __init__(self):
        Grammar.__init__(self)

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)

    def execute(self, outbound_socket):
        outbound_socket.hangup()


class Number(Grammar):
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
        Grammar.__init__(self)
        self.number = ""
        self.gateways = []
        self.gateway_codecs = []
        self.gateway_timeouts = []
        self.gateway_retries = []
        self.extra_dial_string = ""
        self.send_digits = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
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



class Wait(Grammar):
    """Wait for some time to further process the call

    length: length of wait time in seconds
    """
    def __init__(self):
        Grammar.__init__(self)
        self.length = 0

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        try:
            length = int(self.extract_attribute_value("length", 0))
        except ValueError:
            raise RESTFormatException("Wait length must be an integer")
        transfer = self.extract_attribute_value("transferEnabled")
        if transfer == 'true':
            self.transfer = True
        else:
            self.transfer = False
        if length < 0:
            raise RESTFormatException("Wait length must be a positive integer")
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
            outbound_socket.sleep(str(self.length * 1000))
        event = outbound_socket.wait_for_action()


class Play(Grammar):
    """Play audio file at a URL

    url: url of audio file, MIME type on file must be set correctly
    loop: number of time to play the audio - loop = 0 means infinite
    """
    def __init__(self):
        Grammar.__init__(self)
        self.audio_directory = ""
        self.loop_times = 1
        self.sound_file_path = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)

        # Extract Loop attribute
        try:
            loop = int(self.extract_attribute_value("loop", 1))
        except ValueError:
            loop = 1
        if loop < 0:
            raise RESTFormatException("Play loop must be a positive integer")
        self.loop_times = loop
        # Pull out the text within the element
        audio_path = element.text.strip()

        if audio_path is None:
            raise RESTFormatException("No File for play given!")

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
                    outbound_socket.playback(self.sound_file_path)
                    event = outbound_socket.wait_for_action()
                    # Log playback execute response
                    outbound_socket.log.info("Play finished once (%s)" \
                            % str(event.get_header('Application-Response')))
        else:
            outbound_socket.log.info("Invalid Sound File - Ignoring Play")

    def is_infinite(self):
        if self.loop_times <= 0:
            return True
        return False


class Preanswer(Grammar):
    """Answer the call in Early Media Mode and execute nested grammar
    """
    def __init__(self):
        Grammar.__init__(self)
        self.nestables = ['Play', 'Speak', 'GetDigits', 'Wait']

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)

    def prepare(self):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare grammar concurrently
                child_instance.prepare()

    def execute(self, outbound_socket):
        for child_instance in self.children:
            if hasattr(child_instance, "run"):
                child_instance.run(outbound_socket)
        outbound_socket.log.info("Preanswer Completed")


class Record(Grammar):
    """Record audio from caller

    action: submit to this URL once recording finishes
    method: submit to 'action' url using GET or POST
    maxLength: maximum number of seconds to record
    timeout: seconds of silence before considering the recording complete
    playBeep: play a beep before recording (true/false)
    format: file format
    filePath: complete file path to save the file to
    finishOnKey: Stop recording on this key
    """
    def __init__(self):
        Grammar.__init__(self)
        self.silence_threshold = 500
        self.action = ""
        self.method = ""
        self.max_length = None
        self.timeout = None
        self.finish_on_key = ""
        self.file_path = ""
        self.play_beep = ""
        self.format = ""
        self.prefix = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        max_length = self.extract_attribute_value("maxLength")
        timeout = self.extract_attribute_value("timeout")
        action = self.extract_attribute_value("action")
        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.file_path = self.extract_attribute_value("filePath")
        if self.file_path:
            self.file_path = os.path.normpath(self.file_path) + os.sep
        self.play_beep = self.extract_attribute_value("playBeep")
        self.format = self.extract_attribute_value("format")
        self.prefix = self.extract_attribute_value("prefix")
        method = self.extract_attribute_value("method")
        if not method in ('GET', 'POST'):
            raise RESTAttributeException("Method must be 'GET' or 'POST'")
        self.method = method

        if max_length < 0:
            raise RESTFormatException("Record 'maxLength' must be a positive integer")
        self.max_length = max_length
        if timeout < 0:
            raise RESTFormatException("Record 'timeout' must be positive")
        self.timeout = timeout
        if action and is_valid_url(action):
            self.action = action
        else:
            self.action = uri
        # :TODO Validate Finish on Key
        self.finish_on_key = finish_on_key

    def execute(self, outbound_socket):
        Grammar.run(self, outbound_socket)
        filename = "%s%s-%s" % (self.prefix,
                                datetime.now().strftime("%Y%m%d-%H%M%S"),
                                outbound_socket.call_uuid)
        record_file = "%s%s.%s" % (self.file_path, filename, self.format)
        if self.play_beep == 'true':
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


class RecordSession(Grammar):
    """Record call session

    format: file format
    filePath: complete file path to save the file to
    """
    def __init__(self):
        Grammar.__init__(self)
        self.file_path = ""
        self.format = ""
        self.prefix = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        self.file_path = self.extract_attribute_value("filePath")
        self.prefix = self.extract_attribute_value("prefix")
        if self.file_path:
            self.file_path = os.path.normpath(self.file_path) + os.sep
        self.format = self.extract_attribute_value("format")

    def execute(self, outbound_socket):
        outbound_socket.set("RECORD_STEREO=true")
        outbound_socket.set("media_bug_answer_req=true")
        filename = "%s%s-%s" % (self.prefix,
                                datetime.now().strftime("%Y%m%d-%H%M%S"),
                                outbound_socket.call_uuid)
        record_file = "%s%s%s.%s" % (self.file_path, filename, self.format)
        outbound_socket.record_session("%s%s" % (self.file_path, filename))
        outbound_socket.log.info("RecordSession Executed")


class Redirect(Grammar):
    """Redirect call flow to another URL

    url: redirect url
    """
    def __init__(self):
        Grammar.__init__(self)
        self.method = ""
        self.url = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
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


class Reject(Grammar):
    """Reject the call
    This wont answer the call, and should be the first grammar element

    reason: reject reason/code
    """
    def __init__(self):
        Grammar.__init__(self)
        self.reason = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        reason = self.extract_attribute_value("reason")
        if reason == 'rejected':
            self.reason = 'CALL_REJECTED'
        elif reason == 'busy':
            self.reason = 'USER_BUSY'
        else:
            raise RESTAttributeException("Reject Wrong Attribute Value for %s"
                                                                % self.name)

    def execute(self, outbound_socket):
        outbound_socket.hangup(self.reason)
        return self.reason


class Speak(Grammar):
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
    valid_methods = ['PRONOUNCED', 'ITERATED', 'COUNTED']
    valid_types = ['NUMBER', 'ITEMS', 'PERSONS', 'MESSAGES',
                   'CURRENCY', 'TIME_MEASUREMENT', 'CURRENT_DATE', ''
                   'CURRENT_TIME', 'CURRENT_DATE_TIME', 'TELEPHONE_NUMBER',
                   'TELEPHONE_EXTENSION', 'URL', 'IP_ADDRESS', 'EMAIL_ADDRESS',
                   'POSTAL_ADDRESS', 'ACCOUNT_NUMBER', 'NAME_SPELLED',
                   'NAME_PHONETIC', 'SHORT_DATE_TIME']
    DEFAULT_LOOP = 1

    def __init__(self):
        Grammar.__init__(self)
        self.loop_times = 1
        self.language = "en"
        self.sound_file_path = ""
        self.engine = ""
        self.voice = ""
        self.method = "POST"
        self.item_type = ""

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        try:
            loop = int(self.extract_attribute_value("loop", self.DEFAULT_LOOP))
        except ValueError:
            loop = self.DEFAULT_LOOP
        if loop <= 0:
            self.loop_times = 999
        else:
            self.loop_times = loop
        self.engine = self.extract_attribute_value("engine")
        self.language = self.extract_attribute_value("language")
        self.voice = self.extract_attribute_value("voice")
        item_type = self.extract_attribute_value("type")
        if item_type and (item_type in self.valid_types):
            self.item_type = item_type
        method = self.extract_attribute_value("method")
        if method and (method in self.valid_methods):
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
            outbound_socket.log.info("Speak %s times - (%s)" \
                    % ((i+1), str(event.get_header('Application-Response'))))


class ScheduleHangup(Grammar):
    """Hangup the call after certain time

   time: time in seconds to hangup the call after
    """
    def __init__(self):
        Grammar.__init__(self)
        self.time = 0

    def parse_grammar(self, element, uri=None):
        Grammar.parse_grammar(self, element, uri)
        self.time = self.extract_attribute_value("time", 0)

    def execute(self, outbound_socket):
        try:
            self.time = int(self.time)
        except ValueError:
            outbound_socket.log.error("ScheduleHangup Failed: bad value for 'time'")
            return
        if self.time > 0:
            res = outbound_socket.api("sched_api +%d uuid_kill %s ALLOTTED_TIMEOUT" \
                        % (self.time, outbound_socket.get_channel_unique_id()))
            if res.is_success():
                outbound_socket.log.info("ScheduleHangup after %s secs" \
                                                                    % self.time)
                return
            else:
                outbound_socket.log.error("ScheduleHangup Failed: %s"\
                                                    % str(res.get_response()))
                return
        outbound_socket.log.error("ScheduleHangup Failed: 'time' must be > 0 !")
        return
