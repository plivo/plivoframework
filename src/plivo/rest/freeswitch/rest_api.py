# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

import base64
import re
import uuid

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
        ip_list = allowed_ips.split(',')
        for ip in ip_list:
            if str(ip) == str(request.remote_addr):
                return True
        raise Unauthorized("IP Auth Failed")

    def _validate_http_auth(self):
        """Verify http auth request with values in "Authorization" header
        """
        key = get_conf_value(self._config, 'rest_server', 'AUTH_ID')
        secret = get_conf_value(self._config, 'rest_server', 'AUTH_TOKEN')
        if not key or not secret:
            return True
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization'].split()
            if auth_header[0] == 'Basic':
                encoded_auth_str = auth_header[1]
                decoded_auth_str = base64.decodestring(encoded_auth_str)
                auth_list = decoded_auth_str.split(':')
                auth_id = auth_list[0]
                auth_token = auth_list[1]
                if auth_id == key and secret == auth_token:
                    return True
        raise Unauthorized("HTTP Auth Failed")

    def test_config(self):
        '''Test to get config parameter'''
        return get_conf_value(self._config, 'freeswitch', 'FS_INBOUND_ADDRESS')

    def index(self):
        message = """
        Plivo REST<br>
        <br>
        Plivo is an Open Source Communication Framework that enables to
        create Voice applications using REST Apis <br>
        <br>
        For Documentation check http://www.plivo.org/documentation/ <br>
        ~~~~~~~~~~~~~~~<br>
        <br>
        <br>
        """
        return message

    def prepare_request(self, caller_id, to, extra_dial_string, gw, gw_codecs,
                        gw_timeouts, gw_retries, answer_url, hangup_url,
                        ring_url, send_digits):

        gw_retry_list = []
        gw_codec_list = []
        gw_timeout_list = []

        gw_list = gw.split(',')
        # split gw codecs by , but only outside the ''
        if gw_codecs:
            gw_codec_list = re.split(''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''',
                                                                    gw_codecs)
        if gw_timeouts:
            gw_timeout_list = gw_timeouts.split(',')
        if gw_retries:
            gw_retry_list = gw_retries.split(',')

        request_uuid = str(uuid.uuid1())
        args_list = []
        args_list.append("request_uuid=%s" % request_uuid)
        args_list.append("answer_url=%s" % answer_url)
        args_list.append("origination_caller_id_number=%s" % caller_id)
        if extra_dial_string:
             args_list.append(extra_dial_string)
        if send_digits:
            args_list.append("execute_on_answer='send_dtmf %s'" \
                                                % send_digits)
        args_str = ','.join(args_list)
        originate_str = ''.join(["originate {", args_str])

        gw_try_number = 0
        request_params = [originate_str, to, gw_try_number, gw_list,
                          gw_codec_list, gw_timeout_list, gw_retry_list,
                          answer_url, hangup_url, ring_url]
        self._rest_inbound_socket.call_request[request_uuid] = request_params
        keystring = "%s-%s" % (to, caller_id)
        self._rest_inbound_socket.ring_map[keystring] = request_uuid

        return request_uuid

    @auth_protect
    def calls(self):
        """Making Outbound Calls
        Allow initiating outbound calls via the REST API. To make an
        outbound call, make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The number to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        AnswerUrl: The URL that should be requested for XML when the call
        connects. Similiar to the URL for your inbound calls.


        Optional Parameters - You may POST the following parameters:

        HangUpUrl: A URL that Plivo will notify to, with POST params when
        calls ends

        RingUrl:A URL that Plivo will notify to, with POST params when
        calls starts ringing

        OriginateDialString: Additional Originate dialstring to be executed
        while making the outbound call

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        SendDigits: A string of keys to dial after connecting to the number.
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
        result = "Error"
        request_uuid = ""

        caller_id = get_post_param(request, 'From')
        to = get_post_param(request, 'To')
        gw = get_post_param(request, 'Gateways')
        answer_url = get_post_param(request, 'AnswerUrl')

        if not caller_id or not to or not gw or not answer_url:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "Answer URL is not Valid"
        else:
            hangup_url = get_post_param(request, 'HangUpUrl')
            ring_url = get_post_param(request, 'RingUrl')
            if hangup_url and not is_valid_url(hangup_url):
                msg = "Hangup URL is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "Ring URL is not Valid"
            else:
                extra_dial_string = get_post_param(request, 'OriginateDialString')
                gw_codecs = get_post_param(request, 'GatewayCodecs')
                gw_timeouts = get_post_param(request, 'GatewayTimeouts')
                gw_retries = get_post_param(request, 'GatewayRetries')
                send_digits = get_post_param(request, 'SendDigits')

                request_uuid = self.prepare_request(caller_id, to,
                            extra_dial_string, gw, gw_codecs, gw_timeouts,
                            gw_retries, answer_url, hangup_url, ring_url,
                            send_digits)

                self._rest_inbound_socket.spawn_originate(request_uuid)
                msg = "Call Request Executed"
                result = "Success"

        return flask.jsonify(Result=result, Message=msg,
                                                    RequestUUID=request_uuid)

    @auth_protect
    def bulk_calls(self):
        """Making Bulk Outbound Calls in one request
        Allow initiating bulk outbound calls via the REST API. To make a
        bulk outbound call, make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The number to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        AnswerUrl: The URL that should be requested for XML when the call
        connects. Similiar to the URL for your inbound calls.


        Optional Parameters - You may POST the following parameters:

        HangUpUrl: A URL that Plivo will notify to, with POST params when
        calls ends

        RingUrl:A URL that Plivo will notify to, with POST params when
        calls starts ringing

        OriginateDialString: Additional Originate dialstring to be executed
        while making the outbound call

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        SendDigits: A string of keys to dial after connecting to the number.
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
        result = "Error"
        request_uuid = ""

        caller_id = get_post_param(request, 'From')
        to_str = get_post_param(request, 'To')
        gw_str = get_post_param(request, 'Gateways')
        answer_url = get_post_param(request, 'AnswerUrl')

        if not caller_id or not to_str or not gw_str or not answer_url:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "Answer URL is not Valid"
        else:
            hangup_url = get_post_param(request, 'HangUpUrl')
            ring_url = get_post_param(request, 'RingUrl')
            if hangup_url and not is_valid_url(hangup_url):
                msg = "Hangup URL is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "Ring URL is not Valid"
            else:
                extra_dial_string = get_post_param(request,
                                                        'OriginateDialString')
                delimiter = get_post_param(request, 'Delimiter')
                # Is a string of strings
                gw_codecs_str = get_post_param(request, 'GatewayCodecs')
                gw_timeouts_str = get_post_param(request, 'GatewayTimeouts')
                gw_retries_str = get_post_param(request, 'GatewayRetries')
                send_digits_str = get_post_param(request, 'SendDigits')
                request_uuid_list = []
                i = 0

                to_str_list = to_str.split(delimiter)
                gw_str_list = gw_str.split(delimiter)
                gw_codecs_str_list = gw_codecs_str.split(delimiter)
                gw_timeouts_str_list = gw_timeouts_str.split(delimiter)
                gw_retries_str_list = gw_retries_str.split(delimiter)
                send_digits_list = send_digits_str.split(delimiter)

                if len(to_str_list) != len(gw_str_list):
                    msg = "Gateway length does not match with number length"
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

                        request_uuid = self.prepare_request(caller_id, to,
                                    extra_dial_string, gw_str_list[i],
                                    gw_codecs, gw_timeouts, gw_retries,
                                    answer_url, hangup_url, ring_url,
                                    send_digits)

                        i += 1
                        request_uuid_list.append(request_uuid)

                self._rest_inbound_socket.bulk_originate(request_uuid_list)
                msg = "Bulk Call Requests Executed"
                result = "Success"

        return flask.jsonify(Result=result, Message=msg,
                                        RequestUUID=str(request_uuid_list))

    @auth_protect
    def modify_call(self):
        """Modifying Live Calls
        Realtime call modification allows you to interrupt an in-progress
        call and terminate it. This is useful for any application where you
        want to asynchronously change the behavior of a running call.
        For example: forcing hangup, etc.

        To terminate a live call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        The following parameters are available for you to POST when modifying
        a phone call:

        Call ID Parameters: One of these parameters must be supplied
        CallUUID: Unique Call ID to which the action should occur to.

        RequestUUID: Unique request ID which was given on a API response. This
        should be used for calls which are currently in progress and have no
        CallUUID.

        Optional
        Status: Specifying 'completed' will attempt to hang up the call.

        Not Implemented
        Url: A valid URL that returns RESTXML. Plivo will immediately fetch
        the XML and continue the call as the new XML. (Will be added in V2)
        """
        msg = ""
        result = "Error"

        status = get_post_param(request, 'Status')
        call_uuid = get_post_param(request, 'CallUUID')
        request_uuid= get_post_param(request, 'RequestUUID')
        new_xml_url = get_post_param(request, 'URL')

        if not call_uuid and not request_uuid:
            msg = "One of the Call ID Parameters must be present"
        elif call_uuid and request_uuid:
            msg = "Both Call ID Parameters cannot be present"
        elif not status and not new_xml_url:
            msg = "One of the optional Parameters must be present"
        elif status and new_xml_url:
            msg = "Both the optional Parameters cannot be present"
        else:
            if new_xml_url and not is_valid_url(new_xml_url):
                msg = "URL is not Valid"
            elif new_xml_url and is_valid_url(new_xml_url) and not call_uuid:
                    msg = "Call UUID must be present with URL"
            elif status and status != 'completed':
                msg = "Invalid Value for Status"
            else:
                self._rest_inbound_socket.modify_call(new_xml_url, status,
                                                    call_uuid, request_uuid)
                msg = "Modify Request Executed"
                result = "Success"

        return flask.jsonify(Result=result, Message=msg, RequestUUID="")

    @auth_protect
    def hangup_all_calls(self):
        """Hangup All Live Calls in the system
        """
        msg = "All Calls Hungup"
        self._rest_inbound_socket.hangup_all_calls()
        return flask.jsonify(Result="Success", Message=msg, RequestUUID="")
