# -*- coding: utf-8 -*-
# Initial code for this file derived from eventsocket project - (https://github.com/fiorix/eventsocket),
# which is distributed under the Mozilla Public License Version 1.1

"""
FreeSWITCH Commands class

Please refer to http://wiki.freeswitch.org/wiki/Mod_event_socket#Command_documentation
"""


class Commands(object):
    def api(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#api"
        return self._protocol_send("api", args)

    def bgapi(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#bgapi"
        return self._protocol_send("bgapi", args)

    def exit(self):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#exit"
        return self._protocol_send("exit")

    def resume(self):
        """Socket resume for Outbound connection only.
        
        If enabled, the dialplan will resume execution with the next action 
        
        after the call to the socket application.
        
        If there is a bridge active when the disconnect happens, it is killed.
        """
        return self._protocol_send("resume")

    def eventplain(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#event"
        return self._protocol_send('event plain', args)

    def event(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#event"
        return self._protocol_send("event", args)

    def execute(self, command, args=''):
        return self._protocol_sendmsg(command, args, uuid='', lock=True)

    def get_var(self, var, uuid=""):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Mod_commands#uuid_getvar

        For Inbound connection, uuid argument is mandatory.
        """
        if not uuid:
            uuid = self.get_channel_unique_id()
        api_response = self.api("uuid_getvar %s %s" % (uuid, var))
        result = api_response.get_body().strip()
        if result == '_undef_':
            result = None
        return result

    def set_var(self, var, value, uuid=""):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Mod_commands#uuid_setvar

        For Inbound connection, uuid argument is mandatory.
        """
        if not value:
            value = ''
        if not uuid:
            uuid = self.get_channel_unique_id()
        api_response = self.api("uuid_setvar %s %s %s" % (uuid, var, str(value)))
        result = api_response.get_body()
        if not result:
            result = ''
        result = result.strip()
        return result

    def filter(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#filter

        The user might pass any number of values to filter an event for. But, from the point
        filter() is used, just the filtered events will come to the app - this is where this
        function differs from event().

        >>> filter('Event-Name MYEVENT')
        >>> filter('Unique-ID 4f37c5eb-1937-45c6-b808-6fba2ffadb63')
        """
        return self._protocol_send('filter', args)

    def filter_delete(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#filter_delete

        >>> filter_delete('Event-Name MYEVENT')
        """
        return self._protocol_send('filter delete', args)

    def divert_events(self, flag):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#divert_events

        >>> divert_events("off")
        >>> divert_events("on")
        """
        return self._protocol_send('divert_events', flag)

    def sendevent(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#sendevent

        >>> sendevent("CUSTOM\nEvent-Name: CUSTOM\nEvent-Subclass: myevent::test\n")

        This example will send event :
          Event-Subclass: myevent%3A%3Atest
          Command: sendevent%20CUSTOM
          Event-Name: CUSTOM
        """
        return self._protocol_send('sendevent', args)

    def auth(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#auth

        This method is only used for Inbound connections.
        """
        return self._protocol_send("auth", args)

    def myevents(self, uuid=""):
        """For Inbound connection, please refer to http://wiki.freeswitch.org/wiki/Event_Socket#Special_Case_-_.27myevents.27

        For Outbound connection, please refer to http://wiki.freeswitch.org/wiki/Event_Socket_Outbound#Events

        >>> myevents()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_send("myevents", uuid)

    def linger(self):
        """Tell Freeswitch to wait for the last channel event before ending the connection

        Can only be used with Outbound connection.

        >>> linger()

        """
        return self._protocol_send("linger")

    def verbose_events(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_verbose_events

        >>> verbose_events()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("verbose_events", "", uuid, lock)

    def answer(self, uuid="", lock=True):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_answer

        >>> answer()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("answer", "", uuid, lock)

    def bridge(self, args, uuid="", lock=True):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_bridge

        >>> bridge("{ignore_early_media=true}sofia/gateway/myGW/177808")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("bridge", args, uuid, lock)

    def hangup(self, cause="", uuid="", lock=True):
        """Hangup call.

        Hangup `cause` list : http://wiki.freeswitch.org/wiki/Hangup_Causes (Enumeration column)

        >>> hangup()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("hangup", cause, uuid, lock)

    def ring_ready(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_ring_ready

        >>> ring_ready()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("ring_ready", "", uuid)

    def record_session(self, filename, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_record_session

        >>> record_session("/tmp/dump.gsm")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("record_session", filename, uuid, lock)

    def bind_meta_app(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_bind_meta_app

        >>> bind_meta_app("2 ab s record_session::/tmp/dump.gsm")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("bind_meta_app", args, uuid, lock)

    def wait_for_silence(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_wait_for_silence

        >>> wait_for_silence("200 15 10 5000")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("wait_for_silence", args, uuid, lock)

    def sleep(self, milliseconds, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_sleep

        >>> sleep(5000)
        >>> sleep("5000")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("sleep", milliseconds, uuid, lock)

    def vmd(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_vmd

        >>> vmd("start")
        >>> vmd("stop")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("vmd", args, uuid, lock)

    def set(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_set

        >>> set("ringback=${us-ring}")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("set", args, uuid, lock)

    def set_global(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_set_global

        >>> set_global("global_var=value")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("set_global", args, uuid, lock)

    def unset(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_unset

        >>> unset("ringback")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("unset", args, uuid, lock)

    def start_dtmf(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_start_dtmf

        >>> start_dtmf()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("start_dtmf", "", uuid, lock)

    def stop_dtmf(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_stop_dtmf

        >>> stop_dtmf()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("stop_dtmf", "", uuid, lock)

    def start_dtmf_generate(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_start_dtmf_generate

        >>> start_dtmf_generate()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("start_dtmf_generate", "true", uuid, lock)

    def stop_dtmf_generate(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_stop_dtmf_generate

        >>> stop_dtmf_generate()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("stop_dtmf_generate", "", uuid, lock)

    def queue_dtmf(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_queue_dtmf

        Enqueue each received dtmf, that'll be sent once the call is bridged.

        >>> queue_dtmf("0123456789")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("queue_dtmf", args, uuid, lock)

    def flush_dtmf(self, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_flush_dtmf

        >>> flush_dtmf()

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("flush_dtmf", "", uuid, lock)

    def play_fsv(self, filename, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_fsv

        >>> play_fsv("/tmp/video.fsv")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("play_fsv", filename, uuid, lock)

    def record_fsv(self, filename, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_fsv

        >>> record_fsv("/tmp/video.fsv")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("record_fsv", filename, uuid, lock)

    def playback(self, filename, terminators=None, uuid="", lock=True, loops=1):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_playback

        The optional argument `terminators` may contain a string with
        the characters that will terminate the playback.

        >>> playback("/tmp/dump.gsm", terminators="#8")

        In this case, the audio playback is automatically terminated
        by pressing either '#' or '8'.

        For Inbound connection, uuid argument is mandatory.
        """
        if not terminators:
            terminators = 'none'
        self.set("playback_terminators=%s" % terminators, uuid)
        return self._protocol_sendmsg("playback", filename, uuid, lock, loops)

    def transfer(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_transfer

        >>> transfer("3222 XML default")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("transfer", args, uuid, lock)

    def att_xfer(self, url, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_att_xfer

        >>> att_xfer("user/1001")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("att_xfer", url, uuid, lock)

    def endless_playback(self, filename, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_endless_playback

        >>> endless_playback("/tmp/dump.gsm")

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("endless_playback", filename, uuid, lock)

    def record(self, filename, time_limit_secs="", silence_thresh="", \
                silence_hits="", terminators=None, uuid="", lock=True, loops=1):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_record

        """
        if terminators:
            self.set("playback_terminators=%s" % terminators)
        args = "%s %s %s %s" %(filename, time_limit_secs, silence_thresh, silence_hits)
        self._protocol_sendmsg("record", args=args, uuid=uuid, lock=True)

    def play_and_get_digits(self, min_digits=1, max_digits=1, max_tries=1, timeout=5000, \
                            terminators='', sound_files=[], invalid_file = "", var_name='pagd_input', \
                            valid_digits='0123456789*#', digit_timeout=None, play_beep=False):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_play_and_get_digits
        """

        if not sound_files:
            if play_beep:
                play_str = 'tone_stream://%(300,200,700)'
            else:
                play_str = 'silence_stream://200'
        elif len(sound_files) == 1:
            play_str = sound_files[0]
            if play_beep:
                beep = 'tone_stream://%(300,200,700)'
                self.set("playback_delimiter=!")
                self.set("playback_sleep_val=%s" % pause)
                play_str = "file_string://%s!%s" % (play_str, beep)
        else:
            self.set("playback_delimiter=!")
            play_str = "file_string://%s" % sound_files[0]
            for i in range(1,len(sound_files)):
                play_str = "%s!%s" % (play_str, sound_files[i])
            if play_beep:
                beep = 'tone_stream://%(300,200,700)'
                play_str = "file_string://%s!%s" % (play_str, beep)

        if not invalid_file:
            invalid_file='silence_stream://150'
        if digit_timeout is None:
            digit_timeout = timeout
        reg = []
        for d in valid_digits:
            if d == '*':
                d = '\*'
            reg.append(d)
        regexp = '|'.join(reg)
        regexp = '(%s)+' % regexp

        args = "%d %d %d %d '%s' %s %s %s %s %d" % (min_digits, max_digits, max_tries, \
                                                    timeout, terminators, play_str,
                                                    invalid_file, var_name, regexp,
                                                    digit_timeout)
        self.execute('play_and_get_digits', args)

    def preanswer(self):
        """
        Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_pre_answer

        Can only be used for outbound connection
        """
        self.execute("pre_answer")

    def speak(self, text, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/TTS

        >>> "set" data="tts_engine=flite"
        >>> "set" data="tts_voice=kal"
        >>> speak(text)

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("speak", text, uuid, lock)

    def hupall(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Mod_commands#hupall"
        return self._protocol_sendmsg("hupall", args, uuid='', lock=True)

    def say(self, args, uuid="", lock=True):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_say

        >>> say(en number pronounced 12345)

        For Inbound connection, uuid argument is mandatory.
        """
        return self._protocol_sendmsg("say", args, uuid, lock)
