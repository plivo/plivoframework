# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

import urllib
import urllib2

import gevent
from gevent import pool

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.rest.freeswitch.helpers import HTTPRequest


class RESTInboundSocket(InboundEventSocket):
    """
    Interface between REST API and the InboundSocket
    ...
    ...
    """
    def __init__(self, host, port, password,
                 outbound_address='',
                 auth_id='', auth_token='',
                 filter="ALL", log=None):
        InboundEventSocket.__init__(self, host, port, password, filter)
        self.fs_outbound_address = outbound_address
        self.log = log
        self.auth_id = auth_id
        self.auth_token = auth_token
        # Mapping of Key: job-uuid - Value: request_uuid
        self.bk_jobs = {}
        # Transfer jobs: call_uuid - Value: where to transfer
        self.xfer_jobs = {}
        # Call Requests
        self.call_requests = {}

    def on_background_job(self, ev):
        """
        Capture Job Event
        Capture background job only for originate,
        and ignore all other jobs
        """
        job_cmd = ev['Job-Command']
        job_uuid = ev['Job-UUID']
        if job_cmd == "originate" and job_uuid:
            try:
                status, reason = ev.get_body().split(' ', 1)
            except ValueError:
                return
            request_uuid = self.bk_jobs.pop(job_uuid, None)
            # Handle failure case of originate - USER_NOT_REGISTERED
            # This case does not raise a on_channel_hangup event.
            # All other failiures will be captured by on_channel_hangup
            if not request_uuid:
                self.log.debug("No RequestUUID found !")
                return
            try:
                call_req = self.call_requests[request_uuid]
            except KeyError:
                return
            status = status.strip()
            reason = reason.strip()
            if status[:4] == '-ERR':
                # In case ring was done, just warn
                # releasing call request will be done in hangup event
                if call_req.ring_flag is True:
                    self.log.warn("Call Rang for RequestUUID %s but Failed (%s)" \
                                                    % (request_uuid, reason))
                    return
                # If no more gateways, release call request
                elif not call_req.gateways:
                    self.log.warn("Call Failed for RequestUUID %s but No More Gateways (%s)" \
                                                    % (request_uuid, reason))
                    # set an empty call_uuid
                    call_uuid = ''
                    hangup_url = call_req.hangup_url
                    self.set_hangup_complete(self, request_uuid, call_uuid,
                                             reason, ev, hangup_url)
                    return
                # If there are gateways and call request ring_flag is False
                #  try again: spawn originate
                elif call_req.gateways:
                    self.log.debug("Call Failed for RequestUUID %s - Retrying (%s)" \
                                                    % (request_uuid, reason))
                    self.spawn_originate(request_uuid)

    def on_channel_originate(self, ev):
        request_uuid = ev['variable_plivo_request_uuid']
        answer_state = ev['Answer-State']
        direction = ev['Call-Direction']
        to = ev['Caller-Destination-Number']
        if request_uuid and answer_state == 'ringing' and direction == 'outbound':
            try:
                call_req = self.call_requests[request_uuid]
                call_req.gateways = [] # clear gateways to avoid retry
            except (KeyError, AttributeError):
                return
            ring_url = call_req.ring_url
            # set ring flag to true
            call_req.ring_flag = True
            self.log.info("Call Ringing for %s with RequestUUID  %s" \
                            % (to, request_uuid))
            if ring_url:
                params = {
                        'To': to,
                        'RequestUUID': request_uuid,
                        'Direction': 'outbound',
                        'CallStatus': 'ringing',
                        'From': ev['Caller-Caller-ID-Number']
                    }
                gevent.spawn(self.post_to_url, ring_url, params)

    def on_channel_hangup(self, ev):
        """
        Capture Channel Hangup
        """
        request_uuid = ev['variable_plivo_request_uuid']
        if not request_uuid:
            return
        call_uuid = ev['Unique-ID']
        reason = ev['Hangup-Cause']
        try:
            call_req = self.call_requests[request_uuid]
        except KeyError:
            self.log.warn("CallRequest not found for RequestUUID %s" \
                            % request_uuid)
            return
        # If there are gateways to try again, spawn originate
        if call_req.gateways:
            self.log.debug("Call Failed for RequestUUID %s - Retrying (%s)" \
                            % (request_uuid, reason))
            self.spawn_originate(request_uuid)
        # Else clean call request
        else:
            hangup_url = call_req.hangup_url
            self.set_hangup_complete(request_uuid, call_uuid, reason, ev,
                                                        hangup_url)

    def on_channel_state(self, ev):
        if ev['Channel-State'] == 'CS_RESET':
            call_uuid = ev['Unique-ID']
            xfer = self.xfer_jobs.pop(call_uuid, None)
            if not xfer:
                return
            self.log.info("Executing Live Call Transfer for %s" % call_uuid)
            res = self.api("uuid_transfer %s '%s' inline" % (call_uuid, xfer))
            if res.is_success():
                self.log.info("Executing Live Call Transfer Done for %s" % call_uuid)
            else:
                self.log.info("Executing Live Call Transfer Failed for %s: %s" \
                               % (call_uuid, res.get_response()))
        elif ev['Channel-State'] == 'CS_HANGUP':
            call_uuid = ev['Unique-ID']
            self.xfer_jobs.pop(call_uuid, None)

    def set_hangup_complete(self, request_uuid, call_uuid, reason, ev, hangup_url):
        self.log.info("Call %s Completed, Reason %s, Request uuid %s"
                                        % (call_uuid, reason, request_uuid))
        try:
            self.call_requests[request_uuid] = None
            del self.call_requests[request_uuid]
        except KeyError, AttributeError:
            pass
        self.log.debug("Call Cleaned up for RequestUUID %s" % request_uuid)
        if hangup_url:
            to = ev['Caller-Destination-Number']
            params = {
                    'RequestUUID': request_uuid,
                    'CallUUID': call_uuid,
                    'HangupCause': reason,
                    'Direction': 'outbound',
                    'To': to,
                    'CallStatus': 'completed',
                    'From': ev['Caller-Caller-ID-Number']
                }
            gevent.spawn(self.post_to_url, hangup_url, params)

    def post_to_url(self, url=None, params={}, method='POST'):
        if not url:
            self.log.warn("Cannot post No url found !")
            return None
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        try:
            data = http_obj.fetch_response(url, params, method)
            self.log.info("Posted to %s with %s -- Result: %s"
                                            % (url, params, data))
            return data
        except Exception, e:
            self.log.error("Post to %s with %s -- Error: %s"
                                            % (url, params, e))
        return None

    def spawn_originate(self, request_uuid):
        try:
            call_req = self.call_requests[request_uuid]
        except KeyError:
            self.log.warn("CallRequest not found for RequestUUID %s" % request_uuid)
            return
        try:
            gw = call_req.gateways.pop(0)
        except IndexError:
            self.log.warn("No more gateway to call for RequestUUID %s" % request_uuid)
            try:
                self.call_requests[request_uuid] = None
                del self.call_requests[request_uuid]
            except KeyError:
                pass
            return

        _options = []
        if gw.codecs:
            _options.append("absolute_codec_string=%s" % gw.codecs)
        if gw.timeout:
            _options.append("originate_timeout=%s" % gw.timeout)
        options = ','.join(_options)
        outbound_str = "'socket:%s async full' inline" \
                        % self.fs_outbound_address

        dial_str = "originate {%s,%s}%s/%s %s" \
            % (gw.extra_dial_string, options, gw.gw, gw.to, outbound_str)

        bg_api_response = self.bgapi(dial_str)
        job_uuid = bg_api_response.get_job_uuid()
        self.bk_jobs[job_uuid] = request_uuid
        if not job_uuid:
            self.log.error("Call Failed for RequestUUID %s -- JobUUID not received" \
                                                            % request_uuid)

    def bulk_originate(self, request_uuid_list):
        if request_uuid_list:
            self.log.info("Bulk Calls for RequestUUIDs %s" % str(request_uuid_list))
            job_pool = pool.Pool(len(request_uuid_list))
            [ job_pool.spawn(self.spawn_originate, request_uuid)
                                        for request_uuid in request_uuid_list ]
            return True
        self.log.error("Bulk Calls Failed -- No RequestUUID !")
        return False

    def transfer_call(self, new_xml_url, call_uuid):
        self.set_var("plivo_transfer_url", new_xml_url, uuid=call_uuid)
        outbound_str = "socket:%s async full" \
                        % (self.fs_outbound_address)
        self.xfer_jobs[call_uuid] = outbound_str
        res = self.api("uuid_transfer %s 'sleep:5000' inline" % call_uuid)
        if res.is_success():
            self.log.info("Spawning Live Call Transfer for %s" % call_uuid)
            return True
        try:
            del self.xfer_jobs[call_uuid]
        except KeyError:
            pass
        self.log.error("Spawning Live Call Transfer Failed for %s : %s" \
                        % (call_uuid, str(res.get_response())))
        return False

    def hangup_call(self, call_uuid="", request_uuid=""):
        if not call_uuid and not request_uuid:
            self.log.error("Call Hangup Failed -- Missing call_uuid or request_uuid")
            return
        if call_uuid:
            callid = "CallUUID %s" % call_uuid
            args = "NORMAL_CLEARING uuid %s" % call_uuid
        else:  # Use request uuid
            callid = "RequestUUID %s" % request_uuid
            args = "NORMAL_CLEARING plivo_request_uuid %s" % request_uuid
        bg_api_response = self.bgapi("hupall %s" % args)
        job_uuid = bg_api_response.get_job_uuid()
        if not job_uuid:
            self.log.error("Call Hangup Failed for %s -- JobUUID not received" % callid)
            return False
        self.log.info("Executed Call hangup for %s" % callid)
        return True

    def hangup_all_calls(self):
        bg_api_response = self.bgapi("hupall NORMAL_CLEARING")
        job_uuid = bg_api_response.get_job_uuid()
        if not job_uuid:
            self.log.error("Hangup All Calls Failed -- JobUUID not received")
            return
        self.log.info("Executed Hangup for all calls")
