# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.
from gevent import monkey; monkey.patch_all()
import gevent.queue
import gevent
import xml.etree.cElementTree as etree
import urllib, urllib2

from plivo.core.freeswitch.outboundsocket import OutboundEventSocket

import verbs
from restexceptions import *


class XMLOutboundEventSocket(OutboundEventSocket):
    def __init__(self, socket, address, log, default_answer_url, filter=None):
        self.log = log
        self.xml_response = ""
        self.default_response = '''<?xml version="1.0" encoding="UTF-8" ?>
            <Response>
                <Play loop="2">/usr/local/freeswitch/sounds/en/us/callie/ivr/8000/ivr-hello.wav
                </Play>
                <Hangup/>
            </Response>
        '''
        self.parsed_verbs = []
        self.lexed_xml_response = []
        self.answer_url = ""
        self.direction = ""
        self.params  = None
        self._action_queue = gevent.queue.Queue()
        self.default_answer_url = default_answer_url
        self.answered = False
        self.no_answer_verbs = ['Pause', 'Reject', 'Preanswer', 'Dial']
        OutboundEventSocket.__init__(self, socket, address, filter)

    def _protocol_send(self, command, args=""):
        self.log.info("[%s] args='%s'" % (command, args))
        response = super(XMLOutboundEventSocket, self)._protocol_send(command, args)
        self.log.info(str(response))
        return response

    def _protocol_sendmsg(self, name, args=None, uuid="", lock=False, loops=1):
        self.log.info("[%s] args=%s, uuid='%s', lock=%s, loops=%d" \
                      % (name, str(args), uuid, str(lock), loops))
        response = super(XMLOutboundEventSocket, self)._protocol_sendmsg(name, args, uuid, lock, loops)
        self.log.info(str(response))
        return response

    # Commands like `playback` and `record` will return +OK from the server, "immediately".
    # However, the only way to know that the audio file being played has finished,
    # is by handling CHANNEL_EXECUTE_COMPLETE events.
    #
    # Such events are received by the on_channel_execute_complete method
    #
    # In order to "block" the execution of our service until the
    # playback is finished, we use a syncronized queue from gevent
    # and wait for such event to come. The on_channel_execute_complete
    # method will put that event in the queue, then we may continue working.
    #
    # However, other events will still come, like for instance, DTMF.
    def on_channel_execute_complete(self, event):
        if event.get_header('Application') == 'playback' or \
            event.get_header('Application') == 'record' or \
            event.get_header('Application') == 'play_and_get_digits' or \
            event.get_header('Application') == 'bridge':
            self._action_queue.put(event)

    def run(self):
        # Only catch events for this channel
        self.myevents()

        channel = self.get_channel()
        self.call_uuid = self.get_channel_unique_id()
        called_no = channel.get_header('Caller-Destination-Number')
        from_no = channel.get_header('Caller-Caller-ID-Number')
        self.direction = channel.get_header('Call-Direction')

        aleg_uuid = ""
        aleg_request_uuid = ""
        if self.direction == 'outbound':
            aleg_uuid = channel.get_header('Caller-Unique-ID')
            aleg_request_uuid = channel.get_header('variable_request_uuid')
            self.answer_url = channel.get_header('variable_answer_url')
        else:
            self.answer_url = self.default_answer_url

        # Post to ANSWER URL and get XML Response
        self.params = {
                  'call_uuid': self.call_uuid,
                  'called_no': called_no,
                  'from_no': from_no,
                  'direction': self.direction,
                  'aleg_uuid': aleg_uuid,
                  'aleg_request_uuid': aleg_request_uuid
        }
        self.process_call()

    def process_call(self):
        self.fetch_xml()
        if not self.xml_response:
            # Play a default message
            self.xml_response = self.default_response
        self.lex_xml()
        self.parse_xml()
        self.execute_xml()

    def fetch_xml(self):
        encoded_params = urllib.urlencode(self.params)
        request = urllib2.Request(self.answer_url, encoded_params)
        try:
            self.xml_response = urllib2.urlopen(request).read()
            self.log.info("Posted to %s with %s" %(self.answer_url, self.params))
        except Exception, e:
            self.log.error("Post to %s with %s --Error: %s" %(self.answer_url, self.params, e))

    def lex_xml(self):
        # 1. Parse XML into a doctring
        xmlStr = ' '.join(self.xml_response.split())
        try:
            doc = etree.fromstring(xmlStr)
        except Exception:
            raise exceptions.RESTSyntaxException("Invalid RESTXML Response Syntax")

        # 2. Make sure the document has a <Response> root else raise format exception
        if doc.tag != "Response":
            raise exceptions.RESTFormatException("No Response Tag Present")

        # 3. Make sure we recognize all the Verbs in the xml
        if len(doc):
            for element in doc:
                invalid_verbs = []
                if not hasattr(verbs, element.tag):
                    invalid_verbs.append(element.tag)
                else:
                    self.lexed_xml_response.append(element)
                if invalid_verbs:
                    raise exceptions.UnrecognizedVerbException("Unrecognized verbs: %s" % invalid_verbs)

    def parse_xml(self):
        # Check all Verb names
        for element in self.lexed_xml_response:
            verb = getattr(verbs, str(element.tag), None)
            verb_instance = verb()
            verb_instance.parse_verb(element, self.answer_url)
            self.parsed_verbs.append(verb_instance)
            # Validate, Parse and store the nested childrens inside this main verb
            self.validate_verb(element, verb_instance)

    def validate_verb(self, element, verb_instance):
        children = element.getchildren()
        if children and not verb_instance.nestables:
            raise RESTFormatException("%s is not nestable verb. It cannot have any children!" % verb_instance.name)
        for child in children:
            if child.tag not in verb_instance.nestables:
                raise RESTFormatException("%s is not nestable inside %s" % (child, verb_instance.name))
            else:
                self.parse_children(child, verb_instance)

    def parse_children(self, child_element, parent_instance):
        child_verb = getattr(verbs, str(child_element.tag), None)
        child_verb_instance = child_verb()
        child_verb_instance.parse_verb(child_element, None)
        parent_instance.children.append(child_verb_instance)

    def execute_xml(self):
        for verb in self.parsed_verbs:
            if hasattr(verbs, "prepare"):
                # :TODO Prepare verbs concurrently
                verb.prepare()
            # Check If inbound call
            if self.direction == 'inbound':
                # Dont answer the call if the verb is a reject, pause or preanswer
                # Only execute the verbs
                if self.answered == False and verb.name not in self.no_answer_verbs:
                    self.answer()
                    self.answered = True
            verb.run(self)
