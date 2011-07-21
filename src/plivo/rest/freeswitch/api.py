# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

import base64
import re
import uuid
import os
import os.path
from datetime import datetime
try:
    import xml.etree.cElementTree as etree
except ImportError:
    from xml.etree.elementtree import ElementTree as etree

import flask
from flask import request
from werkzeug.exceptions import Unauthorized

from plivo.rest.freeswitch.helpers import is_valid_url, get_conf_value, \
                                                            get_post_param

def auth_protect(decorated_func):
    def wrapper(obj):
        if obj._validate_http_auth() and obj._validate_ip_auth():
            return decorated_func(obj)
    wrapper.__name__ = decorated_func.__name__
    wrapper.__doc__ = decorated_func.__doc__
    return wrapper



class Gateway(object):
    __slots__ = ('__weakref__',
                 'request_uuid',
                 'to', 'gw', 'codecs',
                 'timeout', 'extra_dial_string'
                )

    def __init__(self, request_uuid, to, gw, codecs,
                 timeout, extra_dial_string):
        self.request_uuid = request_uuid
        self.to = to
        self.gw = gw
        self.codecs = codecs
        self.timeout = timeout
        self.extra_dial_string = extra_dial_string


class CallRequest(object):
    __slots__ = ('__weakref__',
                 'request_uuid',
                 'gateways',
                 'answer_url',
                 'ring_url',
                 'hangup_url',
                 'state_flag',
                )

    def __init__(self, request_uuid, gateways,
                 answer_url, ring_url, hangup_url):
        self.request_uuid = request_uuid
        self.gateways = gateways
        self.answer_url = answer_url
        self.ring_url = ring_url
        self.hangup_url = hangup_url
        self.state_flag = None



class PlivoRestApi(object):
    _config = None
    _rest_inbound_socket = None

    def _validate_ip_auth(self):
        """Verify request is from allowed ips
        """
        allowed_ips = get_conf_value(self._config, 'rest_server',
                                     'ALLOWED_IPS')
        if not allowed_ips:
            return True
        for ip in allowed_ips.split(','):
            if ip.strip() == request.remote_addr.strip():
                return True
        raise Unauthorized("IP Auth Failed")

    def _validate_http_auth(self):
        """Verify http auth request with values in "Authorization" header
        """
        key = get_conf_value(self._config, 'rest_server', 'AUTH_ID')
        secret = get_conf_value(self._config, 'rest_server', 'AUTH_TOKEN')
        if not key or not secret:
            return True
        try:
            auth_type, encoded_auth_str = \
                request.headers['Authorization'].split(' ', 1)
            if auth_type == 'Basic':
                decoded_auth_str = base64.decodestring(encoded_auth_str)
                auth_id, auth_token = decoded_auth_str.split(':', 1)
                if auth_id == key and secret == auth_token:
                    return True
        except (KeyError, ValueError, TypeError):
            pass
        raise Unauthorized("HTTP Auth Failed")

    @auth_protect
    def index(self):
        message = """
        Welcome to Plivo - http://www.plivo.org/<br>
        <br>
        Plivo is a Communication Framework to rapidly build Voice based apps,
        to make and receive calls, using your existing web development skills
        and infrastructure.<br>
        <br>
        <br>
        For further information please visit our website :
        http://www.plivo.org/ <br>
        <br>
        <br>
        """
        return message

    def _prepare_call_request(self, caller_id, to, extra_dial_string, gw, gw_codecs,
                                gw_timeouts, gw_retries, send_digits, time_limit,
                                hangup_on_ring, answer_url, ring_url, hangup_url):
        gateways = []
        gw_retry_list = []
        gw_codec_list = []
        gw_timeout_list = []
        args_list = []
        sched_hangup_id = None
        # don't allow "|" and "," in 'to' (destination) to avoid call injection
        to = re.split(',|\|', to)[0]
        # build gateways list removing trailing '/' character
        gw_list = [ gateway.rstrip('/').strip() for gateway in gw.split(',') ]
        # split gw codecs by , but only outside the ''
        if gw_codecs:
            gw_codec_list = re.split(''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''',
                                                                    gw_codecs)
        if gw_timeouts:
            gw_timeout_list = gw_timeouts.split(',')
        if gw_retries:
            gw_retry_list = gw_retries.split(',')

        # create a new request uuid
        request_uuid = str(uuid.uuid1())
        # append args
        args_list.append("plivo_request_uuid=%s" % request_uuid)
        args_list.append("plivo_answer_url=%s" % answer_url)
        args_list.append("origination_caller_id_number=%s" % caller_id)

        # set extra_dial_string
        if extra_dial_string:
             args_list.append(extra_dial_string)

        # set hangup_on_ring
        try:
            hangup_on_ring = int(hangup_on_ring)
        except ValueError:
            hangup_on_ring = -1
        if hangup_on_ring == 0:
            args_list.append("execute_on_ring='hangup ORIGINATOR_CANCEL'")
        elif hangup_on_ring > 0:
                args_list.append("execute_on_ring='sched_hangup +%d ORIGINATOR_CANCEL'" \
                                                                % hangup_on_ring)

        # set send_digits
        if send_digits:
            args_list.append("execute_on_answer='send_dtmf %s'" \
                                                % send_digits)

        # set time_limit
        try:
            time_limit = int(time_limit)
        except ValueError:
            time_limit = -1
        if time_limit > 0:
            # create sched_hangup_id
            sched_hangup_id = str(uuid.uuid1())
            args_list.append("api_on_answer='sched_api +%d %s hupall ALLOTTED_TIMEOUT plivo_request_uuid %s'" \
                                                % (time_limit, sched_hangup_id, request_uuid))
            args_list.append("plivo_sched_hangup_id=%s" % sched_hangup_id)

        # build originate string
        args_str = ','.join(args_list)

        for gw in gw_list:
            try:
                codecs = gw_codec_list.pop(0)
            except (ValueError, IndexError):
                codecs = ''
            try:
                retry = int(gw_retry_list.pop(0))
            except (ValueError, IndexError):
                retry = 1
            try:
                timeout = int(gw_timeout_list.pop(0))
            except (ValueError, IndexError):
                timeout = 60 # TODO allow no timeout ?
            for i in range(retry):
                gateway = Gateway(request_uuid, to, gw, codecs, timeout, args_str)
                gateways.append(gateway)

        call_req = CallRequest(request_uuid, gateways, answer_url, ring_url, hangup_url)
        return call_req

    @staticmethod
    def _parse_conference_xml_list(xmlstr, member_filter=None, uuid_filter=None, mute_filter=False, deaf_filter=False):
        res = {}
        if member_filter:
            mfilter = tuple( [ mid.strip() for mid in member_filter.split(',') if mid != '' ])
        else:
            mfilter = ()
        if uuid_filter:
            ufilter = tuple( [ uid.strip() for uid in uuid_filter.split(',') if uid != '' ])
        else:
            ufilter = ()

        doc = etree.fromstring(xmlstr)

        if doc.tag != 'conferences':
            raise Exception("Root tag must be 'conferences'")
        for conf in doc:
            conf_name = conf.get("name", None)
            if not conf_name:
                continue
            res[conf_name] = {}
            res[conf_name]['ConferenceUUID'] = conf.get("uuid")
            res[conf_name]['ConferenceRunTime'] = conf.get("run_time")
            res[conf_name]['ConferenceName'] = conf_name
            res[conf_name]['ConferenceMemberCount'] = conf.get("member-count")
            res[conf_name]['Members'] = []
            for member in conf.findall('members/member'):
                m = {}
                member_id = member.find('id').text
                call_uuid = member.find("uuid").text
                is_muted = member.find("flags/can_speak").text == "false"
                is_deaf = member.find("flags/can_hear").text == "false"
                if not member_id or not call_uuid:
                    continue
                filter_match = 0
                if not mfilter and not ufilter and not mute_filter and not deaf_filter:
                    filter_match = 1
                else:
                    if mfilter and member_id in mfilter:
                        filter_match += 1
                    if ufilter and call_uuid in ufilter:
                        filter_match += 1
                    if mute_filter and is_muted:
                        filter_match += 1
                    if deaf_filter and is_deaf:
                        filter_match += 1
                if filter_match == 0:
                    continue
                m["MemberID"] = member_id
                m["Deaf"] = is_deaf
                m["Muted"] = is_muted
                m["CallUUID"] = call_uuid
                m["CallName"] = member.find("caller_id_name").text
                m["CallNumber"] = member.find("caller_id_number").text
                m["JoinTime"] = member.find("join_time").text
                res[conf_name]['Members'].append(m)
        return res

    @auth_protect
    def reload_config(self):
        """Reload plivo config for rest server
        """
        msg = "Plivo config reload failed"
        result = False

        if self._rest_inbound_socket:
            try:
                self._rest_inbound_socket.reload_config()
                extra = "rest_server"
                outbound_pidfile = self._rest_inbound_socket.get_server().fs_out_pidfile
                if outbound_pidfile:
                    try:
                        pid = int(open(outbound_pidfile, 'r').read().strip())
                        os.kill(pid, 1)
                        extra += " and outbound_server"
                    except Exception, e:
                        extra += ", failed for outbound_server (%s)" % str(e)
                else:
                    extra += ", failed for outbound_server (no pidfile)"
                msg = "Plivo config reloaded : %s" % extra
                result = True
            except Exception, e:
                msg += ' : %s' % str(e)
                result = False

        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def call(self):
        """Make Outbound Call
        Allow initiating outbound calls via the REST API. To make an
        outbound call, make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The number to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        AnswerUrl: The URL that should be requested for XML when the call
        connects

        TimeLimit: Define the max time of the call

        Optional Parameters - You may POST the following parameters:

        [HangupUrl]: URL that Plivo will notify to, with POST params when
        calls ends

        [RingUrl]: URL that Plivo will notify to, with POST params when
        calls starts ringing

        [HangupOnRing]: If Set to 0 we will hangup as soon as the number ring,
        if set to value X we will wait X seconds when start ringing and then
        hang up

        [OriginateDialString]: Additional Originate dialstring to be executed
        while making the outbound call

        [SendDigits]: A string of keys to dial after connecting to the number.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Very useful, if you want to connect to a company phone number,
        and wanted to dial extension 1234 and then the pound key,
        use SendDigits=1234#.
        Remember to URL-encode this string, since the '#' character has
        special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w'
        or 'W' characters. Each 'w' character waits 0.5 seconds and each 'W'
        character waits for 1.0 seconds instead of sending a digit.
        """
        msg = ""
        result = False
        request_uuid = ""

        caller_id = get_post_param(request, 'From')
        to = get_post_param(request, 'To')
        gw = get_post_param(request, 'Gateways')
        answer_url = get_post_param(request, 'AnswerUrl')

        if not caller_id or not to or not gw or not answer_url:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "AnswerUrl is not Valid"
        else:
            hangup_url = get_post_param(request, 'HangupUrl')
            ring_url = get_post_param(request, 'RingUrl')
            if hangup_url and not is_valid_url(hangup_url):
                msg = "HangupUrl is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "RingUrl is not Valid"
            else:
                extra_dial_string = get_post_param(request, 'ExtraDialString')
                gw_codecs = get_post_param(request, 'GatewayCodecs')
                gw_timeouts = get_post_param(request, 'GatewayTimeouts')
                gw_retries = get_post_param(request, 'GatewayRetries')
                send_digits = get_post_param(request, 'SendDigits')
                time_limit = get_post_param(request, 'TimeLimit')
                hangup_on_ring = get_post_param(request, 'HangupOnRing')

                call_req = self._prepare_call_request(
                                    caller_id, to, extra_dial_string,
                                    gw, gw_codecs, gw_timeouts, gw_retries,
                                    send_digits, time_limit, hangup_on_ring,
                                    answer_url, ring_url, hangup_url)

                request_uuid = call_req.request_uuid
                self._rest_inbound_socket.call_requests[request_uuid] = call_req
                self._rest_inbound_socket.spawn_originate(request_uuid)
                msg = "Call Request Executed"
                result = True

        return flask.jsonify(Success=result,
                             Message=msg,
                             RequestUUID=request_uuid)

    @auth_protect
    def bulk_call(self):
        """Make Bulk Outbound Calls in one request
        Allow initiating bulk outbound calls via the REST API. To make a
        bulk outbound call, make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The number to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        AnswerUrl: The URL that should be requested for XML when the call
        connects. Similar to the URL for your inbound calls

        TimeLimit: Define the max time of the calls

        Optional Parameters - You may POST the following parameters:

        [HangupUrl]: URL that Plivo will notify to, with POST params when
        calls ends

        [RingUrl]: URL that Plivo will notify to, with POST params when
        calls starts ringing

        [HangupOnRing]: If Set to 0 we will hangup as soon as the number ring,
        if set to value X we will wait X seconds when start ringing and then
        hang up

        [OriginateDialString]: Additional Originate dialstring to be executed
        while making the outbound call

        [SendDigits]: A string of keys to dial after connecting to the number.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Very useful, if you want to connect to a company phone number,
        and wanted to dial extension 1234 and then the pound key,
        use SendDigits=1234#.
        Remember to URL-encode this string, since the '#' character has
        special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w'
        characters. Each 'w' character waits 0.5 seconds instead of sending a
        digit.
        """
        msg = ""
        result = False
        request_uuid = ""

        request_uuid_list = []
        i = 0

        caller_id = get_post_param(request, 'From')
        to_str = get_post_param(request, 'To')
        gw_str = get_post_param(request, 'Gateways')
        answer_url = get_post_param(request, 'AnswerUrl')
        delimiter = get_post_param(request, 'Delimiter')

        if delimiter in (',', '/'):
            msg = "This Delimiter is not allowed"
        elif not caller_id or not to_str or not gw_str or not answer_url or\
            not delimiter:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "AnswerUrl is not Valid"
        else:
            hangup_url = get_post_param(request, 'HangupUrl')
            ring_url = get_post_param(request, 'RingUrl')
            if hangup_url and not is_valid_url(hangup_url):
                msg = "HangupUrl is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "RingUrl is not Valid"
            else:
                extra_dial_string = get_post_param(request,
                                                        'ExtraDialString')
                # Is a string of strings
                gw_codecs_str = get_post_param(request, 'GatewayCodecs')
                gw_timeouts_str = get_post_param(request, 'GatewayTimeouts')
                gw_retries_str = get_post_param(request, 'GatewayRetries')
                send_digits_str = get_post_param(request, 'SendDigits')
                time_limit_str = get_post_param(request, 'TimeLimit')
                hangup_on_ring_str = get_post_param(request, 'HangupOnRing')

                to_str_list = to_str.split(delimiter)
                gw_str_list = gw_str.split(delimiter)
                gw_codecs_str_list = gw_codecs_str.split(delimiter)
                gw_timeouts_str_list = gw_timeouts_str.split(delimiter)
                gw_retries_str_list = gw_retries_str.split(delimiter)
                send_digits_list = send_digits_str.split(delimiter)
                time_limit_list = time_limit_str.split(delimiter)
                hangup_on_ring_list = hangup_on_ring_str.split(delimiter)

                if len(to_str_list) < 2:
                    msg = "BulkCalls should be used for at least 2 numbers"
                elif len(to_str_list) != len(gw_str_list):
                    msg = "'To' parameter length does not match 'GW' Length"
                else:
                    for to in to_str_list:
                        try:
                            gw_codecs = gw_codecs_str_list[i]
                        except IndexError:
                            gw_codecs = ""
                        try:
                            gw_timeouts = gw_timeouts_str_list[i]
                        except IndexError:
                            gw_timeouts = ""
                        try:
                            gw_retries = gw_retries_str_list[i]
                        except IndexError:
                            gw_retries = ""
                        try:
                            send_digits = send_digits_list[i]
                        except IndexError:
                            send_digits = ""
                        try:
                            time_limit = time_limit_list[i]
                        except IndexError:
                            time_limit = ""
                        try:
                            hangup_on_ring = hangup_on_ring_list[i]
                        except IndexError:
                            hangup_on_ring = ""

                        call_req = self._prepare_call_request(
                                    caller_id, to, extra_dial_string,
                                    gw_str_list[i], gw_codecs, gw_timeouts, gw_retries,
                                    send_digits, time_limit, hangup_on_ring,
                                    answer_url, ring_url, hangup_url)
                        request_uuid = call_req.request_uuid
                        request_uuid_list.append(request_uuid)
                        self._rest_inbound_socket.call_requests[request_uuid] = call_req
                        i += 1

                    # now do the calls !
                    if self._rest_inbound_socket.bulk_originate(request_uuid_list):
                        msg = "BulkCalls Requests Executed"
                        result = True
                    else:
                        msg = "BulkCalls Requests Failed"
                        request_uuid_list = []

        return flask.jsonify(Success=result, Message=msg,
                             RequestUUID=request_uuid_list)

    @auth_protect
    def hangup_call(self):
        """Hangup Call
        Realtime call hangup allows you to interrupt an in-progress
        call and terminate it.

        To terminate a live call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        The following parameters are available for you to POST when modifying
        a phone call:

        Call ID Parameters: One of these parameters must be supplied :

        CallUUID: Unique Call ID to which the action should occur to.

        RequestUUID: Unique request ID which was given on a API response. This
        should be used for calls which are currently in progress and have no CallUUID.
        """
        msg = ""
        result = False

        call_uuid = get_post_param(request, 'CallUUID')
        request_uuid= get_post_param(request, 'RequestUUID')

        if not call_uuid and not request_uuid:
            msg = "CallUUID or RequestUUID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        elif call_uuid and request_uuid:
            msg = "Both CallUUID and RequestUUID Parameters cannot be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.hangup_call(call_uuid, request_uuid)
        if res:
            msg = "Hangup Call Executed"
            result = True
        else:
            msg = "Hangup Call Failed"
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def transfer_call(self):
        """Transfer Call
        Realtime call transfer allows you to interrupt an in-progress
        call and place it another scenario.

        To transfer a live call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        The following parameters are available for you to POST when transfering
        a phone call:

        CallUUID: Unique Call ID to which the action should occur to.

        Url: A valid URL that returns RESTXML. Plivo will immediately fetch
              the XML and continue the call as the new XML.
        """
        msg = ""
        result = False

        call_uuid = get_post_param(request, 'CallUUID')
        new_xml_url = get_post_param(request, 'Url')

        if not call_uuid:
            msg = "CallUUID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        elif not new_xml_url:
            msg = "Url Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        elif not is_valid_url(new_xml_url):
            msg = "Url is not Valid"
            return flask.jsonify(Success=result, Message=msg)

        res = self._rest_inbound_socket.transfer_call(new_xml_url,
                                                      call_uuid)
        if res:
            msg = "Transfer Call Executed"
            result = True
        else:
            msg = "Transfer Call Failed"
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def hangup_all_calls(self):
        """Hangup All Live Calls in the system
        """
        msg = "All Calls Hungup"
        self._rest_inbound_socket.hangup_all_calls()
        return flask.jsonify(Success=True, Message=msg)

    @auth_protect
    def schedule_hangup(self):
        """Schedule Call Hangup
        Schedule an hangup on a call in the future.

        To schedule a hangup, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        The following parameters are available for you to POST when transfering
        a phone call:

        CallUUID: Unique Call ID to which the action should occur to.

        Time: When hanging up call in seconds.


        Returns a scheduled task with id SchedHangupId that you can use to cancel hangup.
        """

        msg = ""
        result = False
        sched_id = ""

        time = get_post_param(request, 'Time')
        call_uuid = get_post_param(request, 'CallUUID')

        if not call_uuid:
            msg = "CallUUID Parameter must be present"
        elif not time:
            msg = "Time Parameter must be present"
        else:
            try:
                time = int(time)
                if time <= 0:
                    msg = "Time Parameter must be > 0 !"
                else:
                    sched_id = str(uuid.uuid1())
                    res = self._rest_inbound_socket.api("sched_api %s +%d uuid_kill %s ALLOTTED_TIMEOUT" \
                                                        % (sched_id, time, call_uuid))
                    if res.is_success():
                        msg = "Scheduled Hangup Done with SchedHangupId %s" % sched_id
                        result = True
                    else:
                        msg = "Scheduled Hangup Failed: %s" % res.get_response()
            except ValueError:
                msg = "Invalid Time Parameter !"
        return flask.jsonify(Success=result, Message=msg, SchedHangupId=sched_id)

    @auth_protect
    def cancel_scheduled_hangup(self):
        """Cancel a Scheduled Call Hangup
        Unschedule an hangup on a call.

        To unschedule a hangup, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        The following parameters are available for you to POST when transfering
        a phone call:

        SchedHangupId: id of the scheduled hangup.
        """
        msg = ""
        result = False

        sched_id = get_post_param(request, 'SchedHangupId')
        if not sched_id:
            msg = "Id Parameter must be present"
        else:
            res = self._rest_inbound_socket.api("sched_del %s" % sched_id)
            if res.is_success():
                msg = "Scheduled Hangup Canceled"
                result = True
            else:
                msg = "Scheduled Hangup Cancelation Failed: %s" % res.get_response()
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def record_start(self):
        """RecordStart
        Start Recording a call

        POST Parameters
        ---------------
        CallUUID: Unique Call ID to which the action should occur to.
        FileFormat: file format, can be be "mp3" or "wav" (default "mp3")
        FilePath: complete file path to save the file to
        Filename: Default empty, if given this will be used for the recording
        TimeLimit: Max recording duration in seconds
        """
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        fileformat = get_post_param(request, 'FileFormat')
        filepath = get_post_param(request, 'FilePath')
        filename = get_post_param(request, 'Filename')
        timelimit = get_post_param(request, 'TimeLimit')
        if not calluuid:
            msg = "CallUUID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not fileformat:
            fileformat = "mp3"
        if not fileformat in ("mp3", "wav"):
            msg = "FileFormat Parameter must be 'mp3' or 'wav'"
            return flask.jsonify(Success=result, Message=msg)
        if not timelimit:
            timelimit = 3600
        else:
            try:
                timelimit = int(timelimit)
            except ValueError:
                msg = "RecordStart Failed: invalid TimeLimit '%s'" % str(timelimit)
                return flask.jsonify(Success=result, Message=msg)

        if filepath:
            filepath = os.path.normpath(filepath) + os.sep
        if not filename:
            filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), room)
        recordfile = "%s%s.%s" % (filepath, filename, fileformat)
        res = self._rest_inbound_socket.api("uuid_record %s start %s %d" \
                % (calluuid, recordfile, timelimit))
        if res.is_success():
            msg = "RecordStart Executed with RecordFile %s" % recordfile
            result = True
            return flask.jsonify(Success=result, Message=msg, RecordFile=recordfile)

        msg = "RecordStart Failed: %s" % res.get_response()
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def record_stop(self):
        """RecordStop
        Stop Recording a call

        POST Parameters
        ---------------
        CallUUID: Unique Call ID to which the action should occur to.
        RecordFile: full file path to the recording file (the one returned by RecordStart)
                    or 'all' to stop all current recordings on this call
        """
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        recordfile = get_post_param(request, 'RecordFile')
        if not calluuid:
            msg = "CallUUID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not recordfile:
            msg = "RecordFile Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.api("uuid_record %s stop %s" \
                % (calluuid, recordfile))
        if res.is_success():
            msg = "RecordStop Executed"
            result = True
            return flask.jsonify(Success=result, Message=msg)

        msg = "RecordStop Failed: %s" % res.get_response()
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_mute(self):
        """ConferenceMute
        Mute a Member in a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' to mute all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "mute %s" % member_id, async=False)
        if not res:
            msg = "Conference Mute Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Mute %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Mute Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_unmute(self):
        """ConferenceUnmute
        Unmute a Member in a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' to unmute all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "unmute %s" % member_id, async=False)
        if not res:
            msg = "Conference Unmute Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Unmute %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Unmute Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_kick(self):
        """ConferenceKick
        Kick a Member from a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' for kicking all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "kick %s" % member_id, async=False)
        if not res:
            msg = "Conference Kick Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Kick %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Kick Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_hangup(self):
        """ConferenceHangup
        Hangup a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' for hanging up all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "hup %s" % member_id, async=False)
        if not res:
            msg = "Conference Hangup Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Hangup %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Hangup Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_deaf(self):
        """ConferenceDeaf
        Deaf a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' for kicking all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "deaf %s" % member_id, async=False)
        if not res:
            msg = "Conference Deaf Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Deaf %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Deaf Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_undeaf(self):
        """ConferenceUndeaf
        Undeaf a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or 'all' for kicking all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        elif not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        res = self._rest_inbound_socket.conference_api(room, "undeaf %s" % member_id)
        if not res:
            msg = "Conference Undeaf Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Undeaf %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Undeaf Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_record_start(self):
        """ConferenceRecordStart
        Start Recording Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        FileFormat: file format, can be be "mp3" or "wav" (default "mp3")
        FilePath: complete file path to save the file to
        Filename: Default empty, if given this will be used for the recording
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        fileformat = get_post_param(request, 'FileFormat')
        filepath = get_post_param(request, 'FilePath')
        filename = get_post_param(request, 'Filename')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not fileformat:
            fileformat = "mp3"
        if not fileformat in ("mp3", "wav"):
            msg = "FileFormat Parameter must be 'mp3' or 'wav'"
            return flask.jsonify(Success=result, Message=msg)

        if filepath:
            filepath = os.path.normpath(filepath) + os.sep
        if not filename:
            filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), room)
        recordfile = "%s%s.%s" % (filepath, filename, fileformat)

        res = self._rest_inbound_socket.conference_api(room, "record %s" % recordfile, async=False)
        if not res:
            msg = "Conference RecordStart Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference RecordStart %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference RecordStart Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_record_stop(self):
        """ConferenceRecordStop
        Stop Recording Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        RecordFile: full file path to the recording file (the one returned by ConferenceRecordStart)
                    or 'all' to stop all current recordings on conference
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        recordfile = get_post_param(request, 'RecordFile')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not recordfile:
            msg = "RecordFile Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)

        res = self._rest_inbound_socket.conference_api(room, "norecord %s" % recordfile)
        if not res:
            msg = "Conference RecordStop Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference RecordStop %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference RecordStop Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_play(self):
        """ConferencePlay
        Play something into Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        FilePath: full path to file to be played
        MemberID: conference member id or 'all' to play file to all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        filepath = get_post_param(request, 'FilePath')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not filepath:
            msg = "FilePath Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if member_id == 'all':
            arg = "async"
        else:
            arg = member_id
        res = self._rest_inbound_socket.conference_api(room, "play %s %s" % (filepath, arg), async=False)
        if not res:
            msg = "Conference Play Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Play %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Play Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_speak(self):
        """ConferenceSpeak
        Say something into Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        Text: text to say in conference
        MemberID: conference member id or 'all' to say text to all members
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        text = get_post_param(request, 'Text')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not text:
            msg = "Text Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if member_id == 'all':
            res = self._rest_inbound_socket.conference_api(room, "say %s" % text, async=False)
        else:
            res = self._rest_inbound_socket.conference_api(room, "saymember %s %s" % (text, member_id), async=False)
        if not res:
            msg = "Conference Speak Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Speak %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        msg = "Conference Speak Executed"
        result = True
        return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_list_members(self):
        """ConferenceListMembers
        List all or some members in a conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberFilter: a list of MemberID separated by comma.
                If set only get the members matching the MemberIDs in list.
                (default empty)
        CallUUIDFilter: a list of CallUUID separated by comma.
                If set only get the channels matching the CallUUIDs in list.
                (default empty)
        MutedFilter: 'true' or 'false', only get muted members or not (default 'false')
        DeafFilter: 'true' or 'false', only get deaf members or not (default 'false')

        All Filter parameters can be mixed.
        """
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        members = get_post_param(request, 'MemberFilter')
        calluuids = get_post_param(request, 'CallUUIDFilter')
        onlymuted = get_post_param(request, 'MutedFilter') == 'true'
        onlydeaf = get_post_param(request, 'DeafFilter') == 'true'

        if not room:
            msg = "ConferenceName Parameter must be present"
            return flask.jsonify(Success=result, Message=msg)
        if not members:
            members = None
        res = self._rest_inbound_socket.conference_api(room, "xml_list", async=False)
        if not res:
            msg = "Conference ListMembers Failed"
            result = False
            return flask.jsonify(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference ListMembers %s" % str(res)
            result = False
            return flask.jsonify(Success=result, Message=msg)
        try:
            member_list = self._parse_conference_xml_list(res, member_filter=members, 
                                uuid_filter=calluuids, mute_filter=onlymuted, deaf_filter=onlydeaf)
            msg = "Conference ListMembers Executed"
            result = True
            return flask.jsonify(Success=result, Message=msg, List=member_list)
        except Exception, e:
            msg = "Conference ListMembers Failed to parse result"
            result = False
            self._rest_inbound_socket.log.error("Conference ListMembers Failed -- %s" % str(e))
            return flask.jsonify(Success=result, Message=msg)

    @auth_protect
    def conference_list(self):
        """ConferenceList
        List all conferences with members

        POST Parameters
        ---------------
        MemberFilter: a list of MemberID separated by comma.
                If set only get the members matching the MemberIDs in list.
                (default empty)
        CallUUIDFilter: a list of CallUUID separated by comma.
                If set only get the channels matching the CallUUIDs in list.
                (default empty)
        MutedFilter: 'true' or 'false', only get muted members or not (default 'false')
        DeafFilter: 'true' or 'false', only get deaf members or not (default 'false')

        All Filter parameters can be mixed.
        """
        msg = ""
        result = False

        members = get_post_param(request, 'MemberFilter')
        calluuids = get_post_param(request, 'CallUUIDFilter')
        onlymuted = get_post_param(request, 'MutedFilter') == 'true'
        onlydeaf = get_post_param(request, 'DeafFilter') == 'true'

        res = self._rest_inbound_socket.conference_api(room='', command="xml_list", async=False)
        if res:
            try:
                confs = self._parse_conference_xml_list(res, member_filter=members, 
                                uuid_filter=calluuids, mute_filter=onlymuted, deaf_filter=onlydeaf)
                msg = "Conference List Executed"
                result = True
                return flask.jsonify(Success=result, Message=msg, List=confs)
            except Exception, e:
                msg = "Conference List Failed to parse result"
                result = False
                self._rest_inbound_socket.log.error("Conference List Failed -- %s" % str(e))
                return flask.jsonify(Success=result, Message=msg)
        msg = "Conference List Failed"
        return flask.jsonify(Success=result, Message=msg)

