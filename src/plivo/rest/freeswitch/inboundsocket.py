# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey
monkey.patch_all()

from gevent import spawn_raw
from gevent import pool

from plivo.core.freeswitch.inboundsocket import InboundEventSocket
from plivo.rest.freeswitch.helpers import HTTPRequest, get_substring


EVENT_FILTER = "BACKGROUND_JOB CHANNEL_PROGRESS CHANNEL_PROGRESS_MEDIA CHANNEL_HANGUP CHANNEL_STATE SESSION_HEARTBEAT"


class RESTInboundSocket(InboundEventSocket):
    """
    Interface between REST API and the InboundSocket
    """
    def __init__(self, host, port, password,
                 outbound_address='',
                 auth_id='', auth_token='',
                 log=None, default_http_method='POST', call_heartbeat_url=None,
                 trace=False):
        InboundEventSocket.__init__(self, host, port, password, filter=EVENT_FILTER,
                                    trace=trace)
        self.fs_outbound_address = outbound_address
        self.log = log
        self.auth_id = auth_id
        self.auth_token = auth_token
        # Mapping of Key: job-uuid - Value: request_uuid
        self.bk_jobs = {}
        # Transfer jobs: call_uuid - Value: inline dptools to execute
        self.xfer_jobs = {}
        # Call Requests
        self.call_requests = {}
        self.default_http_method = default_http_method
        self.call_heartbeat_url = call_heartbeat_url

    def on_background_job(self, event):
        """
        Capture Job Event
        Capture background job only for originate,
        and ignore all other jobs
        """
        job_cmd = event['Job-Command']
        job_uuid = event['Job-UUID']
        if job_cmd == 'originate' and job_uuid:
            try:
                status, reason = event.get_body().split(' ', 1)
            except ValueError:
                return
            request_uuid = self.bk_jobs.pop(job_uuid, None)
            if not request_uuid:
                return
            try:
                call_req = self.call_requests[request_uuid]
            except KeyError:
                return
            # Handle failure case of originate
            # This case does not raise a on_channel_hangup event.
            # All other failures will be captured by on_channel_hangup
            status = status.strip()
            reason = reason.strip()
            if status[:3] != '+OK':
                # In case ring/early state done, just warn
                # releasing call request will be done in hangup event
                if call_req.state_flag in ('Ringing', 'EarlyMedia'):
                    self.log.error("Call Attempt Done (%s) for RequestUUID %s but Failed (%s)" \
                                                    % (call_req.state_flag, request_uuid, reason))
                    return
                # If no more gateways, release call request
                elif not call_req.gateways:
                    self.log.error("Call Failed for RequestUUID %s but No More Gateways (%s)" \
                                                    % (request_uuid, reason))
                    # set an empty call_uuid
                    call_uuid = ''
                    hangup_url = call_req.hangup_url
                    self.set_hangup_complete(request_uuid, call_uuid,
                                             reason, event, hangup_url)
                    return
                # If there are gateways and call request state_flag is not set
                # try again a call
                elif call_req.gateways:
                    self.log.warn("Call Failed without Ringing/EarlyMedia for RequestUUID %s - Retrying Now (%s)" \
                                                    % (request_uuid, reason))
                    self.spawn_originate(request_uuid)

    def on_channel_progress(self, event):
        request_uuid = event['variable_plivo_request_uuid']
        direction = event['Call-Direction']
        # Detect ringing state
        if request_uuid and direction == 'outbound':
            try:
                call_req = self.call_requests[request_uuid]
            except (KeyError, AttributeError):
                return
            # only send if not already ringing/early state
            if not call_req.state_flag:
                # set state flag to true
                call_req.state_flag = 'Ringing'
                # clear gateways to avoid retry
                call_req.gateways = []
                called_num = event['Caller-Destination-Number']
                caller_num = event['Caller-Caller-ID-Number']
                self.log.info("Call from %s to %s Ringing for RequestUUID %s" \
                                % (caller_num, called_num, request_uuid))
                # send ring if ring_url found
                ring_url = call_req.ring_url
                if ring_url:
                    params = {
                            'To': called_num,
                            'RequestUUID': request_uuid,
                            'Direction': direction,
                            'CallStatus': 'ringing',
                            'From': caller_num
                        }
                    spawn_raw(self.send_to_url, ring_url, params)

    def on_channel_progress_media(self, event):
        request_uuid = event['variable_plivo_request_uuid']
        direction = event['Call-Direction']
        # Detect early media state
        # See http://wiki.freeswitch.org/wiki/Early_media#Early_Media_And_Dialing_Out
        if request_uuid and direction == 'outbound':
            try:
                call_req = self.call_requests[request_uuid]
            except (KeyError, AttributeError):
                return
            # only send if not already ringing/early state
            if not call_req.state_flag:
                # set state flag to true
                call_req.state_flag = 'EarlyMedia'
                # clear gateways to avoid retry
                call_req.gateways = []
                called_num = event['Caller-Destination-Number']
                caller_num = event['Caller-Caller-ID-Number']
                self.log.info("Call from %s to %s in EarlyMedia for RequestUUID %s" \
                                % (caller_num, called_num, request_uuid))
                # send ring if ring_url found
                ring_url = call_req.ring_url
                if ring_url:
                    params = {
                            'To': called_num,
                            'RequestUUID': request_uuid,
                            'Direction': direction,
                            'CallStatus': 'ringing',
                            'From': caller_num
                        }
                    spawn_raw(self.send_to_url, ring_url, params)

    def on_channel_hangup(self, event):
        """Capture Channel Hangup
        """
        request_uuid = event['variable_plivo_request_uuid']
        direction = event['Call-Direction']
        if not request_uuid and direction != 'outbound':
            return
        call_uuid = event['Unique-ID']
        reason = event['Hangup-Cause']
        try:
            call_req = self.call_requests[request_uuid]
        except KeyError:
            return
        # If there are gateways to try again, spawn originate
        if call_req.gateways:
            self.log.debug("Call Failed for RequestUUID %s - Retrying (%s)" \
                            % (request_uuid, reason))
            self.spawn_originate(request_uuid)
            return
        # Else clean call request
        hangup_url = call_req.hangup_url
        self.set_hangup_complete(request_uuid, call_uuid, reason, event,
                                                    hangup_url)

    def on_channel_state(self, event):
        # When tranfer is ready to start,
        # channel goes in state CS_RESET
        if event['Channel-State'] == 'CS_RESET':
            call_uuid = event['Unique-ID']
            xfer = self.xfer_jobs.pop(call_uuid, None)
            if not xfer:
                return
            self.log.info("TransferCall In Progress for %s" % call_uuid)
            # unset transfer progress flag
            self.set_var("plivo_transfer_progress", "false", uuid=call_uuid)
            # really transfer now
            res = self.api("uuid_transfer %s '%s' inline" % (call_uuid, xfer))
            if res.is_success():
                self.log.info("TransferCall Done for %s" % call_uuid)
            else:
                self.log.info("TransferCall Failed for %s: %s" \
                               % (call_uuid, res.get_response()))
        # On state CS_HANGUP, remove transfer job linked to call_uuid
        elif event['Channel-State'] == 'CS_HANGUP':
            call_uuid = event['Unique-ID']
            # try to clean transfer call
            xfer = self.xfer_jobs.pop(call_uuid, None)
            if xfer:
                self.log.warn("TransferCall Aborted (hangup) for %s" % call_uuid)

    def on_session_heartbeat(self, event):
        """Capture every heartbeat event in a session and post info
        """
        params = {}
        answer_seconds_since_epoch = float(event['Caller-Channel-Answered-Time'])/1000000
        # using UTC here .. make sure FS is using UTC also
        params['AnsweredTime'] = str(answer_seconds_since_epoch)
        heartbeat_seconds_since_epoch = float(event['Event-Date-Timestamp'])/1000000
        # using UTC here .. make sure FS is using UTC also
        params['HeartbeatTime'] = str(heartbeat_seconds_since_epoch)
        params['ElapsedTime'] = str(heartbeat_seconds_since_epoch - answer_seconds_since_epoch)
        params['To'] = event['Caller-Destination-Number'].lstrip('+')
        params['From'] = event['Caller-Caller-ID-Number'].lstrip('+')
        params['CallUUID'] = event['Unique-ID']
        params['Direction'] = event['Call-Direction']
        forwarded_from = get_substring(':', '@',
                            event['variable_sip_h_Diversion'])
        if forwarded_from:
            params['ForwardedFrom'] = forwarded_from.lstrip('+')
        if event['Channel-State'] == 'CS_EXECUTE':
            params['CallStatus'] = 'in-progress'
        # RequestUUID through which this call was initiated if outbound
        request_uuid = event['variable_plivo_request_uuid']
        if request_uuid:
            params['RequestUUID'] = request_uuid
            
        self.log.debug("Got Session Heartbeat from Freeswitch: %s" % params)
        
        if self.call_heartbeat_url:
            self.log.debug("Sending heartbeat to calalback: %s" % self.call_heartbeat_url)
            spawn_raw(self.send_to_url, self.call_heartbeat_url, params)

    def set_hangup_complete(self, request_uuid, call_uuid, reason, event, hangup_url):
        self.log.info("Call %s Completed, Reason %s, Request uuid %s"
                                        % (call_uuid, reason, request_uuid))
        try:
            self.call_requests[request_uuid] = None
            del self.call_requests[request_uuid]
        except KeyError, AttributeError:
            pass
        self.log.debug("Call Cleaned up for RequestUUID %s" % request_uuid)
        if hangup_url:
            called_num = event['Caller-Destination-Number']
            caller_num = event['Caller-Caller-ID-Number']
            params = {
                    'RequestUUID': request_uuid,
                    'CallUUID': call_uuid or '',
                    'HangupCause': reason,
                    'Direction': 'outbound',
                    'To': called_num or '',
                    'CallStatus': 'completed',
                    'From': caller_num or ''
                }
            spawn_raw(self.send_to_url, hangup_url, params)
        else:
            self.log.debug("No hangupUrl for RequestUUID %s" % request_uuid)

    def send_to_url(self, url=None, params={}, method=None):
        if method is None:
            method = self.default_http_method

        if not url:
            self.log.warn("Cannot send %s, no url !" % method)
            return None
        http_obj = HTTPRequest(self.auth_id, self.auth_token)
        try:
            data = http_obj.fetch_response(url, params, method)
            self.log.info("Sent to %s %s with %s -- Result: %s"
                                            % (method, url, params, data))
            return data
        except Exception, e:
            self.log.error("Sending to %s %s with %s -- Error: %s"
                                            % (method, url, params, e))
        return None

    def spawn_originate(self, request_uuid):
        try:
            call_req = self.call_requests[request_uuid]
        except KeyError:
            self.log.warn("Call Request not found for RequestUUID %s" % request_uuid)
            return
        try:
            gw = call_req.gateways.pop(0)
        except IndexError:
            self.log.warn("No more Gateways to call for RequestUUID %s" % request_uuid)
            try:
                self.call_requests[request_uuid] = None
                del self.call_requests[request_uuid]
            except KeyError:
                pass
            return

        _options = []
        # Set plivo app flag
        _options.append("plivo_app=true")
        if gw.codecs:
            _options.append("absolute_codec_string=%s" % gw.codecs)
        if gw.timeout:
            _options.append("originate_timeout=%s" % gw.timeout)
        _options.append("ignore_early_media=true")
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
            self.log.info("BulkCall for RequestUUIDs %s" % str(request_uuid_list))
            job_pool = pool.Pool(len(request_uuid_list))
            [ job_pool.spawn(self.spawn_originate, request_uuid)
                                        for request_uuid in request_uuid_list ]
            return True
        self.log.error("BulkCall Failed -- No RequestUUID !")
        return False

    def transfer_call(self, new_xml_url, call_uuid):
        # Set transfer progress flag to prevent hangup
        # when the current outbound_socket flow will end
        self.set_var("plivo_transfer_progress", "true", uuid=call_uuid)
        # Set transfer url
        self.set_var("plivo_transfer_url", new_xml_url, uuid=call_uuid)
        # Link inline dptools (will be run when ready to start transfer)
        # to the call_uuid job
        outbound_str = "socket:%s async full" \
                        % (self.fs_outbound_address)
        self.xfer_jobs[call_uuid] = outbound_str
        # Transfer into sleep state a little waiting for real transfer
        res = self.api("uuid_transfer %s 'sleep:5000' inline" % call_uuid)
        if res.is_success():
            self.log.info("TransferCall Spawned for %s" % call_uuid)
            return True
        # On failure, remove the job and log error
        try:
            del self.xfer_jobs[call_uuid]
        except KeyError:
            pass
        self.log.error("TransferCall Spawning Failed for %s : %s" \
                        % (call_uuid, str(res.get_response())))
        return False

    def hangup_call(self, call_uuid="", request_uuid=""):
        if not call_uuid and not request_uuid:
            self.log.error("Call Hangup Failed -- Missing CallUUID or RequestUUID")
            return False
        if call_uuid:
            callid = "CallUUID %s" % call_uuid
            cmd = "uuid_kill %s NORMAL_CLEARING" % call_uuid
        else:  # Use request uuid
            callid = "RequestUUID %s" % request_uuid
            try:
                call_req = self.call_requests[request_uuid]
            except (KeyError, AttributeError):
                self.log.error("Call Hangup Failed -- %s not found" \
                            % (callid))
                return False
            callid = "RequestUUID %s" % request_uuid
            cmd = "hupall NORMAL_CLEARING plivo_request_uuid %s" % request_uuid
        res = self.api(cmd)
        if not res.is_success():
            self.log.error("Call Hangup Failed for %s -- %s" \
                % (callid, res.get_response()))
            return False
        self.log.info("Executed Call Hangup for %s" % callid)
        return True

    def hangup_all_calls(self):
        bg_api_response = self.bgapi("hupall NORMAL_CLEARING")
        job_uuid = bg_api_response.get_job_uuid()
        if not job_uuid:
            self.log.error("Hangup All Calls Failed -- JobUUID not received")
            return
        self.log.info("Executed Hangup for all calls")
