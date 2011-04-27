# Copyright (c) 2011 Plivo Team. See LICENSE for details.

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from datetime import date

from restexceptions import *
from helpers import is_valid_url


RECOGNIZED_SOUND_FORMATS = ["audio/mpeg", "audio/wav", "audio/x-wav"]

VERB_DEFAULT_PARAMS = {
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
        "Gather": {
                #action: DYNAMIC! MUST BE SET IN METHOD,
                "method": "POST",
                "timeout": 5,
                "finishOnKey": '#',
                "numDigits": 999,
                "pause": 0,
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
        "Pause": {
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
                "filePath": "/usr/local/freeswitch/sounds/",
                "format": "mp3"
        },
        "RecordSession": {
                        "filePath": "/usr/local/freeswitch/sounds/",
                        "format": "mp3"
        },
        "Redirect": {
                "method": "POST"
        },
        "Reject": {
                "reason": "rejected"
        },
        "Say": {
                "voice": "kal",
                "language": "en",
                "loop": 1,
                "engine": "flite"
        }
    }


class Verb(object):
    """
    Abstract Verb Class to be inherited by all verbs
    """
    def __init__(self):
        self.name = str(self.__class__.__name__)
        self.nestables = None
        self.attributes = {}
        self.children = []

    def parse_verb(self, element, uri=None):
        self.prepare_attributes(element)

    def run(self, outbound_socket):
        pass

    def extract_attribute_value(self, item):
        try:
            item = self.attributes[item]
        except KeyError:
            item = None
        return item

    def prepare_attributes(self, element):
        verb_dict = VERB_DEFAULT_PARAMS[self.name]
        if element.attrib and not verb_dict:
            raise RESTFormatException("%s does not require any attributes!" % self.name)
        self.attributes = dict(verb_dict, **element.attrib)

    def fetch_rest_xml(self, outbound_socket, url):
        # Set Answer URL to Redirect URL
        outbound_socket.answer_url = url
        # Reset all the previous response and verbs
        outbound_socket.xml_response = ""
        outbound_socket.parsed_verbs = []
        outbound_socket.lexed_xml_response = []
        outbound_socket.log.info("Redirecting to %s to fetch RESTXML" %outbound_socket.answer_url)
        outbound_socket.process_call()


class Dial(Verb):
    """
    Dial another phone number and connect it to this call

    action: submit the result of the dial to this URL
    method: submit to 'action' url using GET or POST
    hangupOnStar: hangup the bleg is a leg presses start and this is true
    callerId: caller id to be send to the dialed number
    timeLimit: hangup the call after these many seconds. 0 means no timeLimit
    confirmSound: Sound to be played to b leg before call is bridged
    confirmKey: Key to be pressed to bridge the call.
    dialMusic: Play this music to a-leg while doing a dial to bleg
    """
    def __init__(self):
        Verb.__init__(self)
        self.nestables = ['Number']
        self.method = ""
        self.action = ""
        self.hangup_on_star = False
        self.caller_id = ''
        self.time_limit = 0
        self.dial_str = ""
        self.confirm_sound = ""
        self.confirm_key = ""
        self.dial_music = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        self.action = self.extract_attribute_value("action")
        self.caller_id = self.extract_attribute_value("callerId")
        self.time_limit = int(self.extract_attribute_value("timeLimit"))
        self.confirm_sound = self.extract_attribute_value("confirmSound")
        self.confirm_key = self.extract_attribute_value("confirmKey")
        self.dial_music = self.extract_attribute_value("dialMusic")
        hangup_on_star = self.extract_attribute_value("hangupOnStar")
        if hangup_on_star == 'true':
            self.hangup_on_star = True
        method = self.extract_attribute_value("method")
        if method != 'GET' and method != 'POST':
            raise RESTAttributeException("Invalid method parameter, must be 'GET' or 'POST'")
        self.method = method

    # create a concatenated gw string for a number
    def create_numberstring(self, number, gateways, gateway_codecs, gateway_timeouts, \
                            gateway_retries, extra_dial_string):
        number_str = ""
        base_str = "[%s" % (extra_dial_string)
        for i in range(0,len(gateways)):
            if base_str == "[":
                param_str = "%sabsolute_codec_string=%s,leg_timeout=%s]" \
                            %(base_str, gateway_codecs[i], gateway_timeouts[i])
            else:
                param_str = "%s,absolute_codec_string=%s,leg_timeout=%s]" \
                            %(base_str, gateway_codecs[i], gateway_timeouts[i])
            # add the same gateway retry number of times
            for j in range(0, int(gateway_retries[i])):
                if not number_str:
                    number_str =  "%s%s%s" %(param_str, gateways[i], number)
                else:
                    number_str =  "%s|%s%s%s" %(number_str, param_str, gateways[i], number)
        return number_str

    def run(self, outbound_socket):
        for child_instance in self.children:
            if isinstance(child_instance, Number):
                number_str = self.create_numberstring(child_instance.number , child_instance.gateways, \
                            child_instance.gateway_codecs, child_instance.gateway_timeouts, \
                            child_instance.gateway_retries, child_instance.extra_dial_string)
                if not self.dial_str:
                    self.dial_str = number_str
                else:
                    self.dial_str = "%s,%s" % (self.dial_str, number_str)

        outbound_socket.set("hangup_after_bridge=false")
        #outbound_socket.set("call_timeout=20")
        caller_id = "effective_caller_id_number=%s" %self.caller_id
        outbound_socket.set(caller_id)
        if self.time_limit:
            hangup_str = "execute_on_answer=sched_hangup +%s alloted_timeout" %self.time_limit
            outbound_socket.set(hangup_str)
        if self.hangup_on_star:
            outbound_socket.set("bridge_terminate_key=*")
        # Play Dial music or bride the early media accordingly
        if self.dial_music:
            outbound_socket.set("campon=true")
            music_str = "campon_hold_music=%s" %self.dial_music
            outbound_socket.set(music_str)
        else:
            outbound_socket.set("bridge_early_media=true")
        if self.confirm_sound:
            confirm_music_str = "group_confirm_file=%s" %self.confirm_sound
            # use confirm key if present else just play music
            if self.confirm_key:
                confirm_key_str = "group_confirm_key=%s" %self.confirm_key
            else:
                confirm_key_str = "group_confirm_key=exec"
            # Cancel the leg timeout after the call is answered
            outbound_socket.set("group_confirm_cancel_timeout=1")
            outbound_socket.set(confirm_music_str)
            outbound_socket.set(confirm_key_str)
        outbound_socket.log.info("Dial Started")
        outbound_socket.bridge(self.dial_str)
        event = outbound_socket._action_queue.get()
        hangup_cause = outbound_socket.get_var('bridge_hangup_cause')
        outbound_socket.log.info("Dial Finished with reason: %s" %hangup_cause)
        if hangup_cause == 'NORMAL_CLEARING':
            if self.action and is_valid_url(self.action):
                 # Call Parent Class Function
                self.fetch_rest_xml(outbound_socket, self.action)


class Gather(Verb):
    """
    Gather digits from the caller's keypad

    action: URL to which the digits entered will be sent
    method: submit to 'action' url using GET or POST
    numDigits: how many digits to gather before returning
    timeout: wait for this many seconds before retry or returning
    finish_on_key: key that triggers the end of caller input
    pause: number of seconds to pause in between multiple say or play nested within
    tries: number of tries to execute all says and plays one by one
    playBeep: play a after all plays and says finish
    validDigits: digits which are allowed to be pressed
    invalidDigitsSound: Sound played when invalid digit pressed
    """

    def __init__(self):
        Verb.__init__(self)
        self.nestables = ['Play', 'Say']
        self.num_digits = None
        self.timeout = None
        self.finish_on_key = None
        self.action = None
        self.play_beep = ""
        self.valid_digits = ""
        self.invalid_digits_sound = ""
        self.retries = None
        self.pause = None
        self.sound_files = []
        self.method = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        num_digits = int(self.extract_attribute_value("numDigits"))
        timeout = int(self.extract_attribute_value("timeout"))
        finish_on_key = self.extract_attribute_value("finishOnKey")
        play_beep = self.extract_attribute_value("playBeep")
        self.invalid_digits_sound = self.extract_attribute_value("invalidDigitsSound")
        self.valid_digits = self.extract_attribute_value("validDigits")
        action = self.extract_attribute_value("action")
        retries = int(self.extract_attribute_value("retries"))
        pause = int(self.extract_attribute_value("pause"))
        method = self.extract_attribute_value("method")
        if method != 'GET' and method != 'POST':
            raise RESTAttributeException("Invalid method parameter, must be 'GET' or 'POST'")
        self.method = method

        if num_digits < 1:
            raise RESTFormatException("NumDigits must be greater than 1")
        if retries < 0:
            raise RESTFormatException("Retries must be greater than 0")
        if pause < 0:
            raise RESTFormatException("Pause must be greater than 0")
        if timeout < 0:
            raise RESTFormatException("Timeout must be a positive integer")
        if play_beep == 'true':
            self.play_beep = True
        else:
            self.play_beep = False
        if action and is_valid_url(action):
            self.action = action
        else:
            self.action = uri
        self.num_digits = num_digits
        self.timeout = (timeout*1000)
        self.finish_on_key = finish_on_key
        self.pause = (pause*1000)
        self.retries = retries

    def prepare(self):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare verbs concurrently
                child_instance.prepare()

    def run(self, outbound_socket):
        for child_instance in self.children:
            try:
                sound_file = child_instance.sound_file_path
                loop = child_instance.loop_times
                if loop == 0:
                    loop = 50  # Add a high number to Play infinitely
                # Play the file loop number of times
                for i in range(0, loop):
                    self.sound_files.append(sound_file)
            except Exception:
                pass
        outbound_socket.log.info("Running Gather %s " %self.sound_files)
        outbound_socket.log.info("Play beep %s " %self.play_beep)
        outbound_socket.play_and_get_digits(max_digits=self.num_digits, max_tries=self.retries, \
                            timeout=self.timeout, terminators=self.finish_on_key, \
                            sound_files=self.sound_files, invalid_file=self.invalid_digits_sound, \
                            valid_digits=self.valid_digits, play_beep=self.play_beep, pause=self.pause)
        event = outbound_socket._action_queue.get()
        digits = outbound_socket.get_var('pagd_input')
        outbound_socket.params.update({'Digits': digits})
        if digits is not None:
            if self.action:
                # Call Parent Class Function
                self.fetch_rest_xml(outbound_socket, self.action)


class Hangup(Verb):
    """
    Hangup the call
    """
    def __init__(self):
        Verb.__init__(self)

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)

    def run(self, outbound_socket):
        outbound_socket.hangup()
        outbound_socket.log.info("Channel Hangup Done")


class Number(Verb):
    """
    Specify phone number in a nested Dial element.

    number: number to dial
    send_digits: key to press after connecting to the number
    url: url to be called to fetch the XML for actions upon call answer
    gateways: gaetway string separated by comma to dialout the number
    gatewayCodecs: codecs for each gatway separated by comma
    gatewayTimeouts: timeouts for each gateway separated by comma
    gatewayRetries: number of times to retry each gateway separated by comma
    extraDialString: extra dialstring which will be added to while dialing out to number
    """
    def __init__(self):
        Verb.__init__(self)
        self.number = ""
        self.url = ""
        self.gateways = []
        self.gateway_codecs = []
        self.gateway_timeouts = []
        self.gateway_retries = []
        self.extra_dial_string = ""
        self.send_digits = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        self.number = element.text.strip()
        self.url = self.extract_attribute_value("length")
        self.extra_dial_string = self.extract_attribute_value("extraDialString")
        self.url = self.extract_attribute_value("url")
        self.send_digits = self.extract_attribute_value("sendDigits")

        gateways = self.extract_attribute_value("gateways")
        gateway_codecs = self.extract_attribute_value("gatewayCodecs")
        gateway_timeouts = self.extract_attribute_value("gatewayTimeouts")
        gateway_retries = self.extract_attribute_value("gatewayRetries")

        if gateways:
            self.gateways = gateways.split(',')
        # split gw codecs by , but only outside the ''
        if gateway_codecs:
            self.gateway_codecs = re.split(''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', gateway_codecs)
        if gateway_timeouts:
            self.gateway_timeouts = gateway_timeouts.split(',')
        if gateway_retries:
            self.gateway_retries = gateway_retries.split(',')


class Pause(Verb):
    """
    Pause the call

    length: length of pause in seconds
    """
    def __init__(self):
        Verb.__init__(self)
        self.length = 0

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        length = int(self.extract_attribute_value("length"))
        if length < 0:
            raise RESTFormatException("Pause Length must be a positive integer")
        self.length = length

    def run(self, outbound_socket):
        outbound_socket.sleep(str(self.length*1000))
        outbound_socket.log.info("Pause Executed for %s seconds" % self.length)


class Play(Verb):
    """
    Play audio file at a URL

    url: url of audio file, MIME type on file must be set correctly
    loop: number of time to play the audio - loop = 0 means infinite
    Currently only supports local path
    """
    def __init__(self):
        Verb.__init__(self)
        self.audio_directory =  ""
        self.loop_times = 1
        self.file_url = ""
        self.sound_file_path = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)

        # Extract Loop attribute
        loop = int(self.extract_attribute_value("loop"))
        if loop < 0:
            raise RESTFormatException("Play loop must be a positive integer")
        self.loop_times = loop
        # Pull out the text within the element
        audio_path = element.text.strip()

        if audio_path is None:
            raise RESTFormatException("No File URL given!")

        if not is_valid_url(audio_path):
            self.sound_file_path = audio_path
            self.file_url = None
        else:
            self.file_url = audio_path
            raise RESTFormatException("Currently only local files are supported. URLs not allowed")

    def prepare(self):
        # TODO: If Sound File Path is None then goto Audio URL then check file type format
        # Download the file and move to audio directory and set sound file path
        # Create MD5 hash to identify the text with filename to reuse the file if same text
        pass

    def run(self, outbound_socket):
        if self.is_infinite():
            # Play sound infinitely
            outbound_socket.endless_playback(self.sound_file_path)
            # Log playback execute response
            outbound_socket.log.info("Endless Playback started")
            outbound_socket._action_queue.get()
        else:
            for i in range(0, self.loop_times):
                outbound_socket.playback(self.sound_file_path)
                event = outbound_socket._action_queue.get()
                # Log playback execute response
                outbound_socket.log.info("Playback finished once (%s)" \
                                        % str(event.get_header('Application-Response')))

    def is_infinite(self):
        if self.loop_times == 0:
            return True
        return False


class Preanswer(Verb):
    """
    Answer the call in Early Media Mode and execute nested verbs
    """
    def __init__(self):
        Verb.__init__(self)
        self.nestables = ['Play', 'Say', 'Gather']

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)

    def prepare(self):
        for child_instance in self.children:
            if hasattr(child_instance, "prepare"):
                # :TODO Prepare verbs concurrently
                child_instance.prepare()

    def run(self, outbound_socket):
        for child_instance in self.children:
            if hasattr(child_instance, "run"):
                child_instance.run()
        outbound_socket.log.info("Preanswer Completed")


class Record(Verb):
    """
    Record audio from caller

    action: submit to this URL once recording finishes
    method: submit to 'action' url using GET or POST
    max_length: maximum number of seconds to record
    timeout: seconds of silence before considering the recording complete
    finishOnKey: Stop recording on this key
    """
    def __init__(self):
        Verb.__init__(self)
        self.silence_threshold = 500
        self.action = ""
        self.method = ""
        self.max_length = None
        self.timeout = None
        self.finish_on_key = ""
        self.file_path = ""
        self.play_beep = ""
        self.format = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        max_length = self.extract_attribute_value("maxLength")
        timeout = self.extract_attribute_value("timeout")
        action = self.extract_attribute_value("action")
        finish_on_key = self.extract_attribute_value("finishOnKey")
        self.file_path = self.extract_attribute_value("filePath")
        self.play_beep = self.extract_attribute_value("playBeep")
        self.format = self.extract_attribute_value("format")
        method = self.extract_attribute_value("method")
        if method != 'GET' and method != 'POST':
            raise RESTAttributeException("Invalid method parameter, must be 'GET' or 'POST'")
        self.method = method

        if max_length < 0:
            raise RESTFormatException("Max Length must be a positive integer")
        self.max_length = max_length
        if timeout < 0:
            raise RESTFormatException("Silence Timeout must be a positive integer")
        self.timeout = timeout
        if action and is_valid_url(action):
            self.action = action
        else:
            self.action = uri
        # :TODO Validate Finish on Key
        self.finish_on_key =  finish_on_key

    def run(self, outbound_socket):
        filename = "%s-%s" %(str(date.today()), outbound_socket.call_uuid)
        record_file = "%s%s.%s" %(self.file_path, filename, self.format)
        if self.play_beep == 'true':
            beep = 'tone_stream://%(300,200,700)'
            outbound_socket.playback(beep)
            event = outbound_socket._action_queue.get()
            # Log playback execute response
            outbound_socket.log.info("Finished Playing beep (%s)" \
                                        % str(event.get_header('Application-Response')))
        outbound_socket.start_dtmf()
        outbound_socket.log.info("Starting Recording")
        outbound_socket.record(record_file, self.max_length, self.silence_threshold, \
                            self.timeout, self.finish_on_key)
        event = outbound_socket._action_queue.get()
        outbound_socket.log.info("Recording Completed")
        outbound_socket.stop_dtmf()


class RecordSession(Verb):
    """
    Record call session

    filePath: complete file path to save the file to
    """
    def __init__(self):
        Verb.__init__(self)
        self.file_path = ""
        self.format = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        self.file_path = self.extract_attribute_value("filePath")
        self.format = self.extract_attribute_value("format")

    def run(self, outbound_socket):
        outbound_socket.set("RECORD_STEREO=true")
        outbound_socket.set("media_bug_answer_req=true")
        filename = "%s-%s.%s" %(str(date.today()), outbound_socket.call_uuid, self.format)
        outbound_socket.record_session("%s%s" %(self.file_path, filename))
        outbound_socket.log.info("Call Recording command issued")


class Redirect(Verb):
    """
    Redirect call flow to another URL

    url: redirect url
    """
    def __init__(self):
        Verb.__init__(self)
        self.method = ""
        self.url  = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        method = self.extract_attribute_value("method")
        if method != 'GET' and method != 'POST':
            raise RESTAttributeException("Invalid method parameter, must be 'GET' or 'POST'")
        self.method = method
        url = element.text.strip()
        if not url:
            raise RESTFormatException("Redirect must have a URL")
        if not is_valid_url(url):
            raise RESTFormatException("Redirect URL not valid!")
        self.url = url

    def run(self, outbound_socket):
        # Call Parent Class Function
        self.fetch_rest_xml(outbound_socket, self.url)


class Reject(Verb):
    """
    Reject the call - This wont answer the call, and should be the first verb

    reason: reject reason/code
    """
    def __init__(self):
        Verb.__init__(self)
        self.reason = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        reason = self.extract_attribute_value("reason")
        if reason == 'rejected':
            self.reason = 'CALL_REJECTED'
        elif reason == 'busy':
            self.reason = 'USER_BUSY'
        else:
            raise RESTAttributeException("Wrong Attribute Value for %s" % self.name)

    def run(self, outbound_socket):
        outbound_socket.hangup(self.reason)
        outbound_socket.log.info("Call Rejection Done with reason: %s" % self.reason)


# Currently Broken - Needs to be implemented
class Say(Verb):
    """
    Say text

    text: text to say
    voice: MAN or WOMAN
    language: language to use
    loop: number of times to say this text
    """
    def __init__(self):
        Verb.__init__(self)
        self.loop_times = 1
        self.text = ""
        self.language = ""
        self.sound_file_path = ""

    def parse_verb(self, element, uri=None):
        Verb.parse_verb(self, element, uri)
        loop = int(self.extract_attribute_value("loop"))
        self.language = self.extract_attribute_value("language")

        if loop < 0:
            raise RESTFormatException("Say loop must be a positive integer")
        if loop == 0:
            self.loop_times = 999
        else:
            self.loop_times = loop
        # Pull out the text within the element
        self.text = element.text.strip()

    def prepare(self):
        url = "http://translate.google.com/translate_tts?tl=%s" %self.language
        url = "url&q=%s" %self.text
        # Download the file and move to audio directory and set sound file path
        # Create MD5 hash to identify the text with filename to reuse the file if same text
        #self.sound_file_path = url
        #self.sound_file_path = "shout://%s" %self.sound_file_path

    def run(self, outbound_socket):
        for i in range(0, self.loop_times):
            pass
            #outbound_socket.speak(self.text, )
            #event = outbound_socket._action_queue.get()
            # Log playback execute response
            #outbound_socket.log.info("Speak finished once (%s)" \
            #                        % str(event.get_header('Application-Response')))
