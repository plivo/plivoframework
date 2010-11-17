# -*- coding: utf-8 -*-
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

    def eventplain(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#event"
        return self._protocol_send('event plain', args)

    def event(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#event"
        return self._protocol_send("event", args)

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

    def verbose_events(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_verbose_events

        >>> verbose_events()
        """
        return self._protocol_sendmsg('verbose_events', lock=True)

    def auth(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#auth
        
        This method is allowed only for Inbound connections."""
        return self._protocol_send("auth", args)

    def myevents(self, uuid=""):
        """For Inbound connection, please refer to http://wiki.freeswitch.org/wiki/Event_Socket#Special_Case_-_.27myevents.27

        For Outbound connection, please refer to http://wiki.freeswitch.org/wiki/Event_Socket_Outbound#Events

        For Inbound connection, uuid argument is mandatory."""
        return self._protocol_send("myevents", uuid)

    def answer(self):
        "Please refer to http://wiki.freeswitch.org/wiki/Event_Socket_Outbound#Using_Netcat"
        return self._protocol_sendmsg("answer", lock=True)

    def bridge(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Event_Socket_Outbound
        
        >>> bridge("{ignore_early_media=true}sofia/gateway/myGW/177808")
        """
        return self._protocol_sendmsg("bridge", args, lock=True)

    def hangup(self, reason=""):
        """Hangup may be used by both Inbound and Outbound connections.
        
        When used by Inbound connections, you may add the extra `reason`
        argument. Please refer to http://wiki.freeswitch.org/wiki/Event_Socket#hangup
        for details.
        
        When used by Outbound connections, the `reason` argument must be ignored.
        
        Please refer to http://wiki.freeswitch.org/wiki/Event_Socket_Outbound for
        details.
        """
        return self._protocol_sendmsg("hangup", reason, lock=True)

    def sched_api(self, args):
        "Please refer to http://wiki.freeswitch.org/wiki/Mod_commands#sched_api"
        return self._protocol_sendmsg("sched_api", args, lock=True)

    def ring_ready(self):
        "Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_ring_ready"
        return self._protocol_sendmsg("ring_ready")

    def record_session(self, filename):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_record_session
        
        >>> record_session("/tmp/dump.gsm")
        """
        return self._protocol_sendmsg("record_session", filename, lock=True)

    def bind_meta_app(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_bind_meta_app
        
        >>> bind_meta_app("2 ab s record_session::/tmp/dump.gsm")
        """
        return self._protocol_sendmsg("bind_meta_app", args, lock=True)

    def wait_for_silence(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_wait_for_silence
        
        >>> wait_for_silence("200 15 10 5000")
        """
        return self._protocol_sendmsg("wait_for_silence", args, lock=True)

    def sleep(self, milliseconds):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_sleep
        
        >>> sleep(5000)
        >>> sleep("5000")
        """
        return self._protocol_sendmsg("sleep", milliseconds, lock=True)

    def vmd(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_vmd
        
        >>> vmd("start")
        >>> vmd("stop")
        """
        return self._protocol_sendmsg("vmd", args, lock=True)

    def set(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_set
        
        >>> set("ringback=${us-ring}")
        """
        return self._protocol_sendmsg("set", args, lock=True)

    def set_global(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_set_global
        
        >>> set_global("global_var=value")
        """
        return self._protocol_sendmsg("set_global", args, lock=True)

    def unset(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_unset
        
        >>> unset("ringback")
        """
        return self._protocol_sendmsg("unset", args, lock=True)

    def start_dtmf(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_start_dtmf

        >>> start_dtmf()
        """
        return self._protocol_sendmsg("start_dtmf", lock=True)

    def stop_dtmf(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_stop_dtmf

        >>> stop_dtmf()
        """
        return self._protocol_sendmsg("stop_dtmf", lock=True)

    def start_dtmf_generate(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_start_dtmf_generate

        >>> start_dtmf_generate()
        """
        return self._protocol_sendmsg("start_dtmf_generate", "true", lock=True)

    def stop_dtmf_generate(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_stop_dtmf_generate

        >>> stop_dtmf_generate()
        """
        return self._protocol_sendmsg("stop_dtmf_generate", lock=True)

    def queue_dtmf(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_queue_dtmf

        Enqueue each received dtmf, that'll be sent once the call is bridged.

        >>> queue_dtmf("0123456789")
        """
        return self._protocol_sendmsg("queue_dtmf", args, lock=True)

    def flush_dtmf(self):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_flush_dtmf

        >>> flush_dtmf()
        """
        return self._protocol_sendmsg("flush_dtmf", lock=True)

    def play_fsv(self, filename):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_fsv
        
        >>> play_fsv("/tmp/video.fsv")
        """
        return self._protocol_sendmsg("play_fsv", filename, lock=True)

    def record_fsv(self, filename):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_fsv
        
        >>> record_fsv("/tmp/video.fsv")
        """
        return self._protocol_sendmsg("record_fsv", filename, lock=True)

    def playback(self, filename, terminators=None):
        """Please refer to http://wiki.freeswitch.org/wiki/Mod_playback
        
        The optional argument `terminators` may contain a string with
        the characters that will terminate the playback.
        
        >>> playback("/tmp/dump.gsm", terminators="#8")
        
        In this case, the audio playback is automatically terminated 
        by pressing either '#' or '8'.
        """
        self.set("playback_terminators=%s" % terminators or "none")
        return self._protocol_sendmsg("playback", filename, lock=True)

    def transfer(self, args):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_transfer

        >>> transfer("3222 XML default")
        """
        return self._protocol_sendmsg("transfer", args, lock=True)

    def att_xfer(self, url):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_att_xfer
        
        >>> att_xfer("user/1001")
        """
        return self._protocol_sendmsg("att_xfer", url, lock=True)

    def endless_playback(self, filename):
        """Please refer to http://wiki.freeswitch.org/wiki/Misc._Dialplan_Tools_endless_playback
        
        >>> endless_playback("/tmp/dump.gsm")
        """
        return self._protocol_sendmsg("endless_playback", filename, lock=True)

