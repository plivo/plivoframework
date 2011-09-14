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

import ujson as json
import flask
from flask import request
from werkzeug.exceptions import Unauthorized

from plivo.rest.freeswitch.helpers import is_valid_url, get_conf_value, \
                                            get_post_param, get_resource, \
                                            HTTPRequest

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

    def __repr__(self):
        return "<Gateway RequestUUID=%s To=%s Gw=%s Codecs=%s Timeout=%s ExtraDialString=%s>" \
            % (self.request_uuid, self.to, self.gw, self.codecs, self.timeout, self.extra_dial_string)


class CallRequest(object):
    __slots__ = ('__weakref__',
                 'request_uuid',
                 'gateways',
                 'answer_url',
                 'ring_url',
                 'hangup_url',
                 'state_flag',
                 'to',
                 '_from',
                )

    def __init__(self, request_uuid, gateways,
                 answer_url, ring_url, hangup_url, to='', _from=''):
        self.request_uuid = request_uuid
        self.gateways = gateways
        self.answer_url = answer_url
        self.ring_url = ring_url
        self.hangup_url = hangup_url
        self.state_flag = None
        self.to = to
        self._from = _from

    def __repr__(self):
        return "<CallRequest RequestUUID=%s To=%s From=%s Gateways=%s AnswerUrl=%s RingUrl=%s HangupUrl=%s StateFlag=%s>" \
            % (self.request_uuid, self.gateways, self.to, self._from,
               self.answer_url, self.ring_url, self.hangup_url, str(self.state_flag))



class PlivoRestApi(object):
    _config = None
    _rest_inbound_socket = None

    def _validate_ip_auth(self):
        """Verify request is from allowed ips
        """
        allowed_ips = self._config.get('rest_server', 'ALLOWED_IPS', default='')
        if not allowed_ips:
            return True
        for ip in allowed_ips.split(','):
            if ip.strip() == request.remote_addr.strip():
                return True
        raise Unauthorized("IP Auth Failed")

    def _validate_http_auth(self):
        """Verify http auth request with values in "Authorization" header
        """
        key = self._config.get('common', 'AUTH_ID', default='')
        secret = self._config.get('common', 'AUTH_TOKEN', default='')
        if not key or not secret:
            return True
        try:
            auth_type, encoded_auth_str = \
                request.headers['Authorization'].split(' ', 1)
            if auth_type == 'Basic':
                decoded_auth_str = base64.decodestring(encoded_auth_str)
                auth_id, auth_token = decoded_auth_str.split(':', 1)
                if auth_id == key and auth_token == secret:
                    return True
        except (KeyError, ValueError, TypeError):
            pass
        raise Unauthorized("HTTP Auth Failed")

    def send_response(self, Success, Message, **kwargs):
        if Success is True:
            self._rest_inbound_socket.log.info(Message)
            return flask.jsonify(Success=True, Message=Message, **kwargs)
        self._rest_inbound_socket.log.error(Message)
        return flask.jsonify(Success=False, Message=Message, **kwargs)

    def _prepare_call_request(self, caller_id, caller_name, to, extra_dial_string, gw, gw_codecs,
                                gw_timeouts, gw_retries, send_digits, send_preanswer, time_limit,
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
        args_list.append("plivo_ring_url=%s" % ring_url)
        args_list.append("plivo_hangup_url=%s" % hangup_url)
        args_list.append("origination_caller_id_number=%s" % caller_id)
        if caller_name:
            args_list.append("origination_caller_id_name=%s" % caller_name)

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
            if send_preanswer:
                args_list.append("execute_on_media='send_dtmf %s'" % send_digits)
            else:
                args_list.append("execute_on_answer='send_dtmf %s'" % send_digits)

        # set time_limit
        try:
            time_limit = int(time_limit)
        except ValueError:
            time_limit = -1
        if time_limit > 0:
            # create sched_hangup_id
            sched_hangup_id = str(uuid.uuid1())
            args_list.append("api_on_answer_%d='sched_api +%d %s 'hupall ALLOTTED_TIMEOUT plivo_request_uuid %s''" \
                                                % (api_answer_count, time_limit, sched_hangup_id, request_uuid))
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

        call_req = CallRequest(request_uuid, gateways, answer_url, ring_url, hangup_url, to=to, _from=caller_id)
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

    @auth_protect
    def reload_config(self):
        """Reload plivo config for rest server
        """
        self._rest_inbound_socket.log.debug("RESTAPI Reload with %s" \
                                        % str(request.form.items()))
        msg = "Plivo config reload failed"
        result = False

        if self._rest_inbound_socket:
            try:
                self._rest_inbound_socket.get_server().reload()
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

        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def reload_cache_config(self):
        """Reload plivo cache server config
        """
        self._rest_inbound_socket.log.debug("RESTAPI ReloadCacheConfig with %s" \
                                        % str(request.form.items()))
        msg = "ReloadCacheConfig Failed"
        result = False

        try:
            cache_api_url = self.cache['url']
        except KeyError:
            msg = "ReloadCacheConfig Failed -- CACHE_URL not found"
            result = False
            return self.send_response(Success=result, Message=msg)

        try:
            req = HTTPRequest(auth_id=self.auth_id, auth_token=self.auth_token)
            data = req.fetch_response(cache_api_url + '/ReloadConfig/', params={}, method='POST')
            res = json.loads(data)
            try:
                success = res['Success']
                msg = res['Message']
            except:
                success = False
                msg = "unknown"
            if success:
                msg = "Plivo Cache Server config reloaded"
                result = True
                self._rest_inbound_socket.log.info("ReloadCacheConfig Done")
            else:
                raise Exception(msg)

        except Exception, e:
            msg = "Plivo Cache Server config reload failed"
            self._rest_inbound_socket.log.error("ReloadCacheConfig Failed -- %s" % str(e))
            result = False

        return self.send_response(Success=result, Message=msg)


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


        Optional Parameters - You may POST the following parameters:

        [CallerName]: the caller name to use for call

        [TimeLimit]: Define the max time of the call

        [HangupUrl]: URL that Plivo will notify to, with POST params when
        calls ends

        [RingUrl]: URL that Plivo will notify to, with POST params when
        calls starts ringing

        [HangupOnRing]: If Set to 0 we will hangup as soon as the number ring,
        if set to value X we will wait X seconds when start ringing and then
        hang up

        [ExtraDialString]: Additional Originate dialstring to be executed
        while making the outbound call

        [SendDigits]: A string of keys to dial after connecting to the number.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Very useful, if you want to connect to a company phone number,
        and wanted to dial extension 1234 and then the pound key,
        use SendDigits=1234#.
        Remember to URL-encode this string, since the '#' character has
        special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w'
        characters. 
        Each 'w' character waits 0.5 seconds instead of sending a digit.
        Each 'W' character waits 1.0 seconds instead of sending a digit.
        You can also add the tone duration in ms by appending @[duration] after string.
        Eg. 1w2w3@1000

        [SendOnPreanswer]: SendDigits on early media instead of answer.
        """
        self._rest_inbound_socket.log.debug("RESTAPI Call with %s" \
                                        % str(request.form.items()))
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
                send_preanswer = get_post_param(request, 'SendOnPreanswer') == 'true'
                time_limit = get_post_param(request, 'TimeLimit')
                hangup_on_ring = get_post_param(request, 'HangupOnRing')
                caller_name = get_post_param(request, 'CallerName') or ''

                call_req = self._prepare_call_request(
                                    caller_id, caller_name, to, extra_dial_string,
                                    gw, gw_codecs, gw_timeouts, gw_retries,
                                    send_digits, send_preanswer, time_limit, hangup_on_ring,
                                    answer_url, ring_url, hangup_url)

                request_uuid = call_req.request_uuid
                self._rest_inbound_socket.call_requests[request_uuid] = call_req
                self._rest_inbound_socket.spawn_originate(request_uuid)
                msg = "Call Request Executed"
                result = True

        return self.send_response(Success=result,
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

        Delimiter: Any special character (with the exception of '/' and ',')
        which will be used as a delimiter for the string of parameters below. E.g. '<'

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The numbers to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        AnswerUrl: The URL that should be requested for XML when the call
        connects. Similar to the URL for your inbound calls

        Optional Parameters - You may POST the following parameters:

        [CallerName]: the caller name to use for call

        [TimeLimit]: Define the max time of the call

        [HangupUrl]: URL that Plivo will notify to, with POST params when
        calls ends

        [RingUrl]: URL that Plivo will notify to, with POST params when
        calls starts ringing

        [HangupOnRing]: If Set to 0 we will hangup as soon as the number ring,
        if set to value X we will wait X seconds when start ringing and then
        hang up

        [ExtraDialString]: Additional Originate dialstring to be executed
        while making the outbound call

        [SendDigits]: A string of keys to dial after connecting to the number.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Very useful, if you want to connect to a company phone number,
        and wanted to dial extension 1234 and then the pound key,
        use SendDigits=1234#.
        Remember to URL-encode this string, since the '#' character has
        special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w' or 'W' characters.
        Each 'w' character waits 0.5 seconds instead of sending a digit.
        Each 'W' character waits 1.0 seconds instead of sending a digit.
        You can also add the tone duration in ms by appending @[duration] after string.
        Eg. 1w2w3@1000

        [SendOnPreanswer]: SendDigits on early media instead of answer.
        """
        self._rest_inbound_socket.log.debug("RESTAPI BulkCall with %s" \
                                        % str(request.form.items()))
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
                send_preanswer_str = get_post_param(request, 'SendOnPreanswer')
                time_limit_str = get_post_param(request, 'TimeLimit')
                hangup_on_ring_str = get_post_param(request, 'HangupOnRing')
                caller_name_str = get_post_param(request, 'CallerName')

                to_str_list = to_str.split(delimiter)
                gw_str_list = gw_str.split(delimiter)
                gw_codecs_str_list = gw_codecs_str.split(delimiter)
                gw_timeouts_str_list = gw_timeouts_str.split(delimiter)
                gw_retries_str_list = gw_retries_str.split(delimiter)
                send_digits_list = send_digits_str.split(delimiter)
                send_preanswer_list = send_preanswer_str.split(delimiter)
                time_limit_list = time_limit_str.split(delimiter)
                hangup_on_ring_list = hangup_on_ring_str.split(delimiter)
                caller_name_list = caller_name_str.split(delimiter)

                if len(to_str_list) < 2:
                    msg = "BulkCalls should be used for at least 2 numbers"
                elif len(to_str_list) != len(gw_str_list):
                    msg = "'To' parameter length does not match 'Gateways' Length"
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
                            send_preanswer = send_preanswer_list[i] == 'true'
                        except IndexError:
                            send_preanswer = False
                        try:
                            time_limit = time_limit_list[i]
                        except IndexError:
                            time_limit = ""
                        try:
                            hangup_on_ring = hangup_on_ring_list[i]
                        except IndexError:
                            hangup_on_ring = ""
                        try:
                            caller_name = caller_name_list[i]
                        except IndexError:
                            caller_name = ""


                        call_req = self._prepare_call_request(
                                    caller_id, caller_name, to, extra_dial_string,
                                    gw_str_list[i], gw_codecs, gw_timeouts, gw_retries,
                                    send_digits, send_preanswer, time_limit, hangup_on_ring,
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

        return self.send_response(Success=result, Message=msg,
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
        Call ID Parameters: One of these parameters must be supplied :

        CallUUID: Unique Call ID to which the action should occur to.

        RequestUUID: Unique request ID which was given on a API response. This
        should be used for calls which are currently in progress and have no CallUUID.
        """
        self._rest_inbound_socket.log.debug("RESTAPI HangupCall with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        call_uuid = get_post_param(request, 'CallUUID')
        request_uuid= get_post_param(request, 'RequestUUID')

        if not call_uuid and not request_uuid:
            msg = "CallUUID or RequestUUID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        elif call_uuid and request_uuid:
            msg = "Both CallUUID and RequestUUID Parameters cannot be present"
            return self.send_response(Success=result, Message=msg)
        res = self._rest_inbound_socket.hangup_call(call_uuid, request_uuid)
        if res:
            msg = "Hangup Call Executed"
            result = True
        else:
            msg = "Hangup Call Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def transfer_call(self):
        """Transfer Call
        Realtime call transfer allows you to interrupt an in-progress
        call and place it another scenario.

        To transfer a live call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
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
            return self.send_response(Success=result, Message=msg)
        elif not new_xml_url:
            msg = "Url Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        elif not is_valid_url(new_xml_url):
            msg = "Url is not Valid"
            return self.send_response(Success=result, Message=msg)

        res = self._rest_inbound_socket.transfer_call(new_xml_url,
                                                      call_uuid)
        if res:
            msg = "Transfer Call Executed"
            result = True
        else:
            msg = "Transfer Call Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def hangup_all_calls(self):
        self._rest_inbound_socket.log.debug("RESTAPI HangupAllCalls with %s" \
                                        % str(request.form.items()))
        """Hangup All Live Calls in the system
        """
        msg = "All Calls Hungup"
        self._rest_inbound_socket.hangup_all_calls()
        return self.send_response(Success=True, Message=msg)

    @auth_protect
    def schedule_hangup(self):
        """Schedule Call Hangup
        Schedule an hangup on a call in the future.

        To schedule a hangup, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
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
                    res = self._rest_inbound_socket.api("sched_api +%d %s uuid_kill %s ALLOTTED_TIMEOUT" \
                                                        % (time, sched_id, call_uuid))
                    if res.is_success():
                        msg = "ScheduleHangup Done with SchedHangupId %s" % sched_id
                        result = True
                    else:
                        msg = "ScheduleHangup Failed: %s" % res.get_response()
            except ValueError:
                msg = "Invalid Time Parameter !"
        return self.send_response(Success=result, Message=msg, SchedHangupId=sched_id)

    @auth_protect
    def cancel_scheduled_hangup(self):
        """Cancel a Scheduled Call Hangup
        Unschedule an hangup on a call.

        To unschedule a hangup, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        SchedHangupId: id of the scheduled hangup.
        """
        self._rest_inbound_socket.log.debug("RESTAPI ScheduleHangup with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        sched_id = get_post_param(request, 'SchedHangupId')
        if not sched_id:
            msg = "SchedHangupId Parameter must be present"
        else:
            res = self._rest_inbound_socket.api("sched_del %s" % sched_id)
            if res.is_success():
                msg = "Scheduled Hangup Canceled"
                result = True
            else:
                msg = "Scheduled Hangup Cancelation Failed: %s" % res.get_response()
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def record_start(self):
        """RecordStart
        Start Recording a call

        POST Parameters
        ---------------
        CallUUID: Unique Call ID to which the action should occur to.
        FileFormat: file format, can be be "mp3" or "wav" (default "mp3")
        FilePath: complete file path to save the file to
        FileName: Default empty, if given this will be used for the recording
        TimeLimit: Max recording duration in seconds
        """
        self._rest_inbound_socket.log.debug("RESTAPI RecordStart with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        fileformat = get_post_param(request, 'FileFormat')
        filepath = get_post_param(request, 'FilePath')
        filename = get_post_param(request, 'FileName')
        timelimit = get_post_param(request, 'TimeLimit')
        if not calluuid:
            msg = "CallUUID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not fileformat:
            fileformat = "mp3"
        if not fileformat in ("mp3", "wav"):
            msg = "FileFormat Parameter must be 'mp3' or 'wav'"
            return self.send_response(Success=result, Message=msg)
        if not timelimit:
            timelimit = 60
        else:
            try:
                timelimit = int(timelimit)
            except ValueError:
                msg = "RecordStart Failed: invalid TimeLimit '%s'" % str(timelimit)
                return self.send_response(Success=result, Message=msg)

        if filepath:
            filepath = os.path.normpath(filepath) + os.sep
        if not filename:
            filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), calluuid)
        recordfile = "%s%s.%s" % (filepath, filename, fileformat)
        res = self._rest_inbound_socket.api("uuid_record %s start %s %d" \
                % (calluuid, recordfile, timelimit))
        if res.is_success():
            msg = "RecordStart Executed with RecordFile %s" % recordfile
            result = True
            return self.send_response(Success=result, Message=msg, RecordFile=recordfile)

        msg = "RecordStart Failed: %s" % res.get_response()
        return self.send_response(Success=result, Message=msg)

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
        self._rest_inbound_socket.log.debug("RESTAPI RecordStop with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        recordfile = get_post_param(request, 'RecordFile')
        if not calluuid:
            msg = "CallUUID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not recordfile:
            msg = "RecordFile Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        res = self._rest_inbound_socket.api("uuid_record %s stop %s" \
                % (calluuid, recordfile))
        if res.is_success():
            msg = "RecordStop Executed"
            result = True
            return self.send_response(Success=result, Message=msg)

        msg = "RecordStop Failed: %s" % res.get_response()
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def conference_mute(self):
        """ConferenceMute
        Mute a Member in a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to mute all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceMute with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # mute members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "mute %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Mute Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Mute %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Mute done for %s" % str(member))
                members.append(member)
        msg = "Conference Mute Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_unmute(self):
        """ConferenceUnmute
        Unmute a Member in a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to unmute all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceUnmute with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # unmute members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "unmute %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Unmute Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Unmute %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Unmute done for %s" % str(member))
                members.append(member)
        msg = "Conference Unmute Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_kick(self):
        """ConferenceKick
        Kick a Member from a Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to kick all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceKick with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # kick members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "kick %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Kick Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Kick %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Kick done for %s" % str(member))
                members.append(member)
        msg = "Conference Kick Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_hangup(self):
        """ConferenceHangup
        Hangup a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to hangup all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceHangup with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # hangup members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "hup %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Hangup Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Hangup %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Hangup done for %s" % str(member))
                members.append(member)
        msg = "Conference Hangup Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_deaf(self):
        """ConferenceDeaf
        Deaf a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to deaf all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceDeaf with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # deaf members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "deaf %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Deaf Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Deaf %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Deaf done for %s" % str(member))
                members.append(member)
        msg = "Conference Deaf Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_undeaf(self):
        """ConferenceUndeaf
        Undeaf a Member in Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        MemberID: conference member id or list of comma separated member ids to mute
                or 'all' to undeaf all members
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceUndeaf with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        member_id = get_post_param(request, 'MemberID')
        members = []

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        elif not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        # deaf members
        for member in member_id.split(','):
            res = self._rest_inbound_socket.conference_api(room, "undeaf %s" % member, async=False)
            if not res:
                self._rest_inbound_socket.log.warn("Conference Undeaf Failed for %s" % str(member))
            elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
                self._rest_inbound_socket.log.warn("Conference Undeaf %s for %s" % (str(res), str(member)))
            else:
                self._rest_inbound_socket.log.debug("Conference Undeaf done for %s" % str(member))
                members.append(member)
        msg = "Conference Undeaf Executed"
        result = True
        return self.send_response(Success=result, Message=msg, MemberID=members)

    @auth_protect
    def conference_record_start(self):
        """ConferenceRecordStart
        Start Recording Conference

        POST Parameters
        ---------------
        ConferenceName: conference room name
        FileFormat: file format, can be be "mp3" or "wav" (default "mp3")
        FilePath: complete file path to save the file to
        FileName: Default empty, if given this will be used for the recording
        """
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceRecordStart with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        fileformat = get_post_param(request, 'FileFormat')
        filepath = get_post_param(request, 'FilePath')
        filename = get_post_param(request, 'FileName')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not fileformat:
            fileformat = "mp3"
        if not fileformat in ("mp3", "wav"):
            msg = "FileFormat Parameter must be 'mp3' or 'wav'"
            return self.send_response(Success=result, Message=msg)

        if filepath:
            filepath = os.path.normpath(filepath) + os.sep
        if not filename:
            filename = "%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), room)
        recordfile = "%s%s.%s" % (filepath, filename, fileformat)

        res = self._rest_inbound_socket.conference_api(room, "record %s" % recordfile, async=False)
        if not res:
            msg = "Conference RecordStart Failed"
            result = False
            return self.send_response(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference RecordStart %s" % str(res)
            result = False
            return self.send_response(Success=result, Message=msg)
        msg = "Conference RecordStart Executed"
        result = True
        return self.send_response(Success=result, Message=msg, RecordFile=recordfile)

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
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceRecordStop with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        recordfile = get_post_param(request, 'RecordFile')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not recordfile:
            msg = "RecordFile Parameter must be present"
            return self.send_response(Success=result, Message=msg)

        res = self._rest_inbound_socket.conference_api(room,
                                        "norecord %s" % recordfile,
                                        async=False)
        if not res:
            msg = "Conference RecordStop Failed"
            result = False
            return self.send_response(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference RecordStop %s" % str(res)
            result = False
            return self.send_response(Success=result, Message=msg)
        msg = "Conference RecordStop Executed"
        result = True
        return self.send_response(Success=result, Message=msg)

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
        self._rest_inbound_socket.log.debug("RESTAPI ConferencePlay with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        filepath = get_post_param(request, 'FilePath')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not filepath:
            msg = "FilePath Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        filepath = get_resource(self._rest_inbound_socket, filepath)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if member_id == 'all':
            arg = "async"
        else:
            arg = member_id
        res = self._rest_inbound_socket.conference_api(room, "play %s %s" % (filepath, arg), async=False)
        if not res:
            msg = "Conference Play Failed"
            result = False
            return self.send_response(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Play %s" % str(res)
            result = False
            return self.send_response(Success=result, Message=msg)
        msg = "Conference Play Executed"
        result = True
        return self.send_response(Success=result, Message=msg)

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
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceSpeak with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        text = get_post_param(request, 'Text')
        member_id = get_post_param(request, 'MemberID')

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not text:
            msg = "Text Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not member_id:
            msg = "MemberID Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if member_id == 'all':
            res = self._rest_inbound_socket.conference_api(room, "say %s" % text, async=False)
        else:
            res = self._rest_inbound_socket.conference_api(room, "saymember %s %s" % (text, member_id), async=False)
        if not res:
            msg = "Conference Speak Failed"
            result = False
            return self.send_response(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)) or res.startswith('Non-Existant'):
            msg = "Conference Speak %s" % str(res)
            result = False
            return self.send_response(Success=result, Message=msg)
        msg = "Conference Speak Executed"
        result = True
        return self.send_response(Success=result, Message=msg)

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
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceListMembers with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        room = get_post_param(request, 'ConferenceName')
        members = get_post_param(request, 'MemberFilter')
        calluuids = get_post_param(request, 'CallUUIDFilter')
        onlymuted = get_post_param(request, 'MutedFilter') == 'true'
        onlydeaf = get_post_param(request, 'DeafFilter') == 'true'

        if not room:
            msg = "ConferenceName Parameter must be present"
            return self.send_response(Success=result, Message=msg)
        if not members:
            members = None
        res = self._rest_inbound_socket.conference_api(room, "xml_list", async=False)
        if not res:
            msg = "Conference ListMembers Failed"
            result = False
            return self.send_response(Success=result, Message=msg)
        elif res.startswith('Conference %s not found' % str(room)):
            msg = "Conference ListMembers %s" % str(res)
            result = False
            return self.send_response(Success=result, Message=msg)
        try:
            member_list = self._parse_conference_xml_list(res, member_filter=members,
                                uuid_filter=calluuids, mute_filter=onlymuted, deaf_filter=onlydeaf)
            msg = "Conference ListMembers Executed"
            result = True
            return self.send_response(Success=result, Message=msg, List=member_list)
        except Exception, e:
            msg = "Conference ListMembers Failed to parse result"
            result = False
            self._rest_inbound_socket.log.error("Conference ListMembers Failed -- %s" % str(e))
            return self.send_response(Success=result, Message=msg)

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
        self._rest_inbound_socket.log.debug("RESTAPI ConferenceList with %s" \
                                        % str(request.form.items()))
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
                return self.send_response(Success=result, Message=msg, List=confs)
            except Exception, e:
                msg = "Conference List Failed to parse result"
                result = False
                self._rest_inbound_socket.log.error("Conference List Failed -- %s" % str(e))
                return self.send_response(Success=result, Message=msg)
        msg = "Conference List Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def group_call(self):
        """Make Outbound Group Calls in one request
        Allow initiating group outbound calls via the REST API. To make a
        group outbound call, make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        Delimiter: Any special character (with the exception of '/' and ',')
        which will be used as a delimiter for the string of parameters below. E.g. '<'

        From: The phone number to use as the caller id for the call without
        the leading +

        To: The numbers to call without the leading +

        Gateways: Comma separated string of gateways to dial the call out

        GatewayCodecs: Comma separated string of codecs for gateways

        GatewayTimeouts: Comma separated string of timeouts for gateways

        GatewayRetries: Comma separated string of retries for gateways

        AnswerUrl: The URL that should be requested for XML when the call
        connects. Similar to the URL for your inbound calls

        TimeLimit: Define the max time of the calls

        Optional Parameters - You may POST the following parameters:

        [CallerName]: the caller name to use for call

        [HangupUrl]: URL that Plivo will notify to, with POST params when
        calls ends

        [RingUrl]: URL that Plivo will notify to, with POST params when
        calls starts ringing

        [HangupOnRing]: If Set to 0 we will hangup as soon as the number ring,
        if set to value X we will wait X seconds when start ringing and then
        hang up

        [ExtraDialString]: Additional Originate dialstring to be executed
        while making the outbound call

        [RejectCauses]: List of reject causes for each number (comma ',' separated).
        If attempt to call one number failed with a reject cause matching in this parameter,
        there isn't more call attempts for this number.

        [SendDigits]: A string of keys to dial after connecting to the number.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Very useful, if you want to connect to a company phone number,
        and wanted to dial extension 1234 and then the pound key,
        use SendDigits=1234#.
        Remember to URL-encode this string, since the '#' character has
        special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w' or 'W' characters.
        Each 'w' character waits 0.5 seconds instead of sending a digit.
        Each 'W' character waits 1.0 seconds instead of sending a digit.
        You can also add the tone duration in ms by appending @[duration] after string.
        Eg. 1w2w3@1000

        [SendOnPreanswer]: SendDigits on early media instead of answer.

        [ConfirmSound]: Sound to play to called party before bridging call.

        [ConfirmKey]: A one key digits the called party must press to accept the call.
        """
        self._rest_inbound_socket.log.debug("RESTAPI GroupCall with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False
        request_uuid = str(uuid.uuid1())
        default_reject_causes = "NO_ANSWER ORIGINATOR_CANCEL ALLOTTED_TIMEOUT NO_USER_RESPONSE CALL_REJECTED"

        caller_id = get_post_param(request, 'From')
        to_str = get_post_param(request, 'To')
        gw_str = get_post_param(request, 'Gateways')
        answer_url = get_post_param(request, 'AnswerUrl')
        delimiter = get_post_param(request, 'Delimiter')

        if delimiter in (',', '/'):
            msg = "This Delimiter is not allowed"
            return self.send_response(Success=result, Message=msg)
        elif not caller_id or not to_str or not gw_str or not answer_url or not delimiter:
            msg = "Mandatory Parameters Missing"
            return self.send_response(Success=result, Message=msg)
        elif not is_valid_url(answer_url):
            msg = "AnswerUrl is not Valid"
            return self.send_response(Success=result, Message=msg)

        hangup_url = get_post_param(request, 'HangupUrl')
        ring_url = get_post_param(request, 'RingUrl')
        if hangup_url and not is_valid_url(hangup_url):
            msg = "HangupUrl is not Valid"
            return self.send_response(Success=result, Message=msg)
        elif ring_url and not is_valid_url(ring_url):
            msg = "RingUrl is not Valid"
            return self.send_response(Success=result, Message=msg)


        extra_dial_string = get_post_param(request, 'ExtraDialString')
        gw_codecs_str = get_post_param(request, 'GatewayCodecs')
        gw_timeouts_str = get_post_param(request, 'GatewayTimeouts')
        gw_retries_str = get_post_param(request, 'GatewayRetries')
        send_digits_str = get_post_param(request, 'SendDigits')
        send_preanswer_str = get_post_param(request, 'SendOnPreanswer')
        time_limit_str = get_post_param(request, 'TimeLimit')
        hangup_on_ring_str = get_post_param(request, 'HangupOnRing')
        confirm_sound = get_post_param(request, 'ConfirmSound')
        confirm_key = get_post_param(request, 'ConfirmKey')
        reject_causes = get_post_param(request, 'RejectCauses')
        caller_name_str = get_post_param(request, 'CallerName')
        if reject_causes:
            reject_causes = " ".join([ r.strip() for r in reject_causes.split(',') ])

        to_str_list = to_str.split(delimiter)
        gw_str_list = gw_str.split(delimiter)
        gw_codecs_str_list = gw_codecs_str.split(delimiter)
        gw_timeouts_str_list = gw_timeouts_str.split(delimiter)
        gw_retries_str_list = gw_retries_str.split(delimiter)
        send_digits_list = send_digits_str.split(delimiter)
        send_preanswer_list = send_preanswer_str.split(delimiter)
        time_limit_list = time_limit_str.split(delimiter)
        hangup_on_ring_list = hangup_on_ring_str.split(delimiter)
        caller_name_list = caller_name_str.split(delimiter)

        if len(to_str_list) < 2:
            msg = "GroupCall should be used for at least 2 numbers"
            return self.send_response(Success=result, Message=msg)
        elif len(to_str_list) != len(gw_str_list):
            msg = "'To' parameter length does not match 'Gateways' Length"
            return self.send_response(Success=result, Message=msg)


        # set group
        group_list = []
        group_options = []
        # set confirm
        confirm_options = ""
        if confirm_sound:
            if confirm_key:
                confirm_options = "group_confirm_file=%s,group_confirm_key=%s" \
                        % (confirm_sound, confirm_key)
            else:
                confirm_options = "group_confirm_file=playback %s" % confirm_sound
        group_options.append(confirm_options)

        # build calls
        for to in to_str_list:
            try:
                gw = gw_str_list.pop(0)
            except IndexError:
                break
            try:
                gw_codecs = gw_codecs_str_list.pop(0)
            except IndexError:
                gw_codecs = ""
            try:
                gw_timeouts = gw_timeouts_str_list.pop(0)
            except IndexError:
                gw_timeouts = ""
            try:
                gw_retries = gw_retries_str_list.pop(0)
            except IndexError:
                gw_retries = ""
            try:
                send_digits = send_digits_list.pop(0)
            except IndexError:
                send_digits = ""
            try:
                send_preanswer = send_preanswer_list.pop(0) == 'true'
            except IndexError:
                send_preanswer = ""
            try:
                time_limit = time_limit_list.pop(0)
            except IndexError:
                time_limit = ""
            try:
                hangup_on_ring = hangup_on_ring_list.pop(0)
            except IndexError:
                hangup_on_ring = ""
            try:
                caller_name = caller_name_list.pop(0)
            except IndexError:
                caller_name = ""

            call_req = self._prepare_call_request(
                        caller_id, caller_name, to, extra_dial_string,
                        gw, gw_codecs, gw_timeouts, gw_retries,
                        send_digits, send_preanswer, time_limit, hangup_on_ring,
                        answer_url, ring_url, hangup_url)
            group_list.append(call_req)

        # now do the calls !
        if self._rest_inbound_socket.group_originate(request_uuid, group_list, group_options, reject_causes):
            msg = "GroupCall Request Executed"
            result = True
            return self.send_response(Success=result, Message=msg, RequestUUID=request_uuid)

        msg = "GroupCall Request Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def play(self):
        """Play something to a Call or bridged leg or both legs.
        Allow playing a sound to a Call via the REST API. To play sound,
        make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.

        Sounds: Comma separated list of sound files to play.

        Optional Parameters:

        [Length]: number of seconds before terminating sounds.

        [Legs]: 'aleg'|'bleg'|'both'. On which leg(s) to play something.
                'aleg' means only play on the Call.
                'bleg' means only play on the bridged leg of the Call.
                'both' means play on the Call and the bridged leg of the Call.
                Default is 'aleg' .

        [Loop]: 'true'|'false'. Play sound loop indefinitely (default 'false')

        [Mix]: 'true'|'false'. Mix with current audio stream (default 'true')

        """
        self._rest_inbound_socket.log.debug("RESTAPI Play with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        sounds = get_post_param(request, 'Sounds')
        legs = get_post_param(request, 'Legs')
        length = get_post_param(request, 'Length')
        loop = get_post_param(request, 'Loop') == 'true'
        mix = get_post_param(request, 'Mix')
        if mix == 'false':
            mix = False
        else:
            mix = True

        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        if not sounds:
            msg = "Sounds Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        if not legs:
            legs = 'aleg'
        if not length:
            length = 3600
        else:
            try:
                length = int(length)
            except (ValueError, TypeError):
                msg = "Length Parameter must be a positive integer"
                return self.send_response(Success=result, Message=msg)
            if length < 1:
                msg = "Length Parameter must be a positive integer"
                return self.send_response(Success=result, Message=msg)

        sounds_list = sounds.split(',')
        if not sounds_list:
            msg = "Sounds Parameter is Invalid"
            return self.send_response(Success=result, Message=msg)

        # now do the job !
        if self._rest_inbound_socket.play_on_call(calluuid, sounds_list, legs, 
                                        length=length, schedule=0, mix=mix, loop=loop):
            msg = "Play Request Executed"
            result = True
            return self.send_response(Success=result, Message=msg)
        msg = "Play Request Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def schedule_play(self):
        """Schedule playing something to a Call or bridged leg or both legs.
        Allow to schedule playing a sound to a Call via the REST API. To play sound,
        make an HTTP POST request to the resource URI.

        POST Parameters
        ----------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.

        Sounds: Comma separated list of sound files to play.

        Time: When playing sounds in seconds.
        
        Optional Parameters:

        [Length]: number of seconds before terminating sounds.

        [Legs]: 'aleg'|'bleg'|'both'. On which leg(s) to play something.
                'aleg' means only play on the Call.
                'bleg' means only play on the bridged leg of the Call.
                'both' means play on the Call and the bridged leg of the Call.
                Default is 'aleg' .

        [Loop]: 'true'|'false'. Play sound loop indefinitely (default 'false')

        [Mix]: 'true'|'false'. Mix with current audio stream (default 'true')

        Returns a scheduled task with id SchedPlayId that you can use to cancel play.
        """
        self._rest_inbound_socket.log.debug("RESTAPI SchedulePlay with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        sounds = get_post_param(request, 'Sounds')
        legs = get_post_param(request, 'Legs')
        time = get_post_param(request, 'Time')
        length = get_post_param(request, 'Length')
        loop = get_post_param(request, 'Loop') == 'true'
        mix = get_post_param(request, 'Mix')
        if mix == 'false':
            mix = False
        else:
            mix = True

        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        if not sounds:
            msg = "Sounds Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        if not legs:
            legs = 'aleg'
        if not time:
            msg = "Time Parameter Must be Present"
            return self.send_response(Success=result, Message=msg)
        try:
            time = int(time)
        except (ValueError, TypeError):
            msg = "Time Parameter is Invalid"
            return self.send_response(Success=result, Message=msg)
        if time < 1:
            msg = "Time Parameter must be > 0"
            return self.send_response(Success=result, Message=msg)
        if not length:
            length = 3600
        else:
            try:
                length = int(length)
            except (ValueError, TypeError):
                msg = "Length Parameter must be a positive integer"
                return self.send_response(Success=result, Message=msg)
            if length < 1:
                msg = "Length Parameter must be a positive integer"
                return self.send_response(Success=result, Message=msg)

        sounds_list = sounds.split(',')
        if not sounds_list:
            msg = "Sounds Parameter is Invalid"
            return self.send_response(Success=result, Message=msg)

        # now do the job !
        sched_id = self._rest_inbound_socket.play_on_call(calluuid, sounds_list, legs, 
                                    length=length, schedule=time, mix=mix, loop=loop)
        if sched_id:
            msg = "SchedulePlay Request Done with SchedPlayId %s" % sched_id
            result = True
            return self.send_response(Success=result, Message=msg, SchedPlayId=sched_id)
        msg = "SchedulePlay Request Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def cancel_scheduled_play(self):
        """Cancel a Scheduled Call Play
        Unschedule a play on a call.

        To unschedule a play, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------
        SchedPlayId: id of the scheduled play.
        """
        self._rest_inbound_socket.log.debug("RESTAPI CancelScheduledPlay with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        sched_id = get_post_param(request, 'SchedPlayId')
        if not sched_id:
            msg = "SchedPlayId Parameter must be present"
        else:
            res = self._rest_inbound_socket.api("sched_del %s" % sched_id)
            if res.is_success():
                msg = "Scheduled Play Canceled"
                result = True
            else:
                msg = "Scheduled Play Cancelation Failed: %s" % res.get_response()
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def play_stop(self):
        """Call PlayStop
        Stop a play on a call.

        To stop a play, you make an HTTP POST request to a
        resource URI.

        Notes:
            You can not stop a ScheduledPlay with PlayStop.
            PlayStop will stop play for both legs (aleg and bleg, if it exists).

        POST Parameters
        ---------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.

        """
        self._rest_inbound_socket.log.debug("RESTAPI PlayStop with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')

        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)

        self._rest_inbound_socket.play_stop_on_call(calluuid)
        msg = "PlayStop executed"
        result = True
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def sound_touch(self):
        """Add audio effects on a Call

        To add audio effects on a Call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.

        Optional Parameters:

        [AudioDirection]: 'in' or 'out'. Change incoming or outgoing audio stream. (default 'out')

        [PitchSemiTones]: Adjust the pitch in semitones, values should be between -14 and 14, default 0

        [PitchOctaves]: Adjust the pitch in octaves, values should be between -1 and 1, default 0

        [Pitch]: Set the pitch directly, value should be > 0, default 1 (lower = lower tone)

        [Rate]: Set the rate, value should be > 0, default 1 (lower = slower)

        [Tempo]: Set the tempo, value should be > 0, default 1 (lower = slower)

        """
        self._rest_inbound_socket.log.debug("RESTAPI SoundTouch with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        audiodirection = get_post_param(request, 'AudioDirection')

        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        if not audiodirection:
            audiodirection = 'out'
        if not audiodirection in ('in', 'out'):
            msg = "AudioDirection Parameter Must be 'in' or 'out'"
            return self.send_response(Success=result, Message=msg)

        pitch_s = get_post_param(request, 'PitchSemiTones')
        if pitch_s:
            try:
                pitch_s = float(pitch_s)
                if not -14 <= pitch_s <= 14:
                    msg = "PitchSemiTones Parameter must be between -14 and 14"
                    return self.send_response(Success=result, Message=msg)
            except (ValueError, TypeError):
                msg = "PitchSemiTones Parameter must be float"
                return self.send_response(Success=result, Message=msg)

        pitch_o = get_post_param(request, 'PitchOctaves')
        if pitch_o:
            try:
                pitch_o = float(pitch_o)
                if not -1 <= pitch_o <= 1:
                    msg = "PitchOctaves Parameter must be between -1 and 1"
                    return self.send_response(Success=result, Message=msg)
            except (ValueError, TypeError):
                msg = "PitchOctaves Parameter must be float"
                return self.send_response(Success=result, Message=msg)
                
        pitch_p = get_post_param(request, 'Pitch')
        if pitch_p:
            try:
                pitch_p = float(pitch_p)
                if pitch_o <= 0:
                    msg = "Pitch Parameter must be > 0"
                    return self.send_response(Success=result, Message=msg)
            except (ValueError, TypeError):
                msg = "Pitch Parameter must be float"
                return self.send_response(Success=result, Message=msg)
                
        pitch_r = get_post_param(request, 'Rate')
        if pitch_r:
            try:
                pitch_r = float(pitch_r)
                if pitch_r <= 0:
                    msg = "Rate Parameter must be > 0"
                    return self.send_response(Success=result, Message=msg)
            except (ValueError, TypeError):
                msg = "Rate Parameter must be float"
                return self.send_response(Success=result, Message=msg)
                
        pitch_t = get_post_param(request, 'Tempo')
        if pitch_t:
            try:
                pitch_t = float(pitch_t)
                if pitch_t <= 0:
                    msg = "Tempo Parameter must be > 0"
                    return self.send_response(Success=result, Message=msg)
            except (ValueError, TypeError):
                msg = "Tempo Parameter must be float"
                return self.send_response(Success=result, Message=msg)

        if self._rest_inbound_socket.sound_touch(calluuid,
                        direction=audiodirection, s=pitch_s,
                        o=pitch_o, p=pitch_p, r=pitch_r, t=pitch_t):
            msg = "SoundTouch executed"
            result = True
        else:
            msg = "SoundTouch Failed"
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def sound_touch_stop(self):
        """Remove audio effects on a Call

        To remove audio effects on a Call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.
        """
        self._rest_inbound_socket.log.debug("RESTAPI SoundTouchStop with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        cmd = "soundtouch %s stop" % calluuid
        bg_api_response = self._rest_inbound_socket.bgapi(cmd)
        job_uuid = bg_api_response.get_job_uuid()
        if not job_uuid:
            self._rest_inbound_socket.log.error("SoundTouchStop Failed '%s' -- JobUUID not received" % cmd)
            msg = "SoundTouchStop Failed"
            return self.send_response(Success=result, Message=msg)
        msg = "SoundTouchStop executed"
        result = True
        return self.send_response(Success=result, Message=msg)

    @auth_protect
    def send_digits(self):
        """Send DTMFs to a Call.

        To send DTMFs to a Call, you make an HTTP POST request to a
        resource URI.

        POST Parameters
        ---------------

        Required Parameters - You must POST the following parameters:

        CallUUID: Unique Call ID to which the action should occur to.

        Digits: A string of keys to send.
        Valid digits in the string include: any digit (0-9), '#' and '*'.
        Remember to URL-encode this string, since the '#' character has special meaning in a URL.
        To wait before sending DTMF to the extension, you can add leading 'w' or 'W' characters.
        Each 'w' character waits 0.5 seconds instead of sending a digit.
        Each 'W' character waits 1.0 seconds instead of sending a digit.
        You can also add the tone duration in ms by appending @[duration] after string.
        Eg. 1w2W3@1000

        Optional Parameters:

        [Leg]: 'aleg'|'bleg'. On which leg(s) to send DTMFs.
                'aleg' means only send to the Call.
                'bleg' means only send to the bridged leg of the Call.
                Default is 'aleg' .
        """
        self._rest_inbound_socket.log.debug("RESTAPI SendDigits with %s" \
                                        % str(request.form.items()))
        msg = ""
        result = False

        calluuid = get_post_param(request, 'CallUUID')
        if not calluuid:
            msg = "CallUUID Parameter Missing"
            return self.send_response(Success=result, Message=msg)
        digits = get_post_param(request, 'Digits')
        if not digits:
            msg = "Digits Parameter Missing"
            return self.send_response(Success=result, Message=msg)

        leg = get_post_param(request, 'Leg')
        if not leg:
            leg = 'aleg'
        if leg == 'aleg':
            cmd = "uuid_send_dtmf %s %s" % (calluuid, digits)
        elif leg == 'bleg':
            cmd = "uuid_recv_dtmf %s %s" % (calluuid, digits)
        else:
            msg = "Invalid Leg Parameter"
            return self.send_response(Success=result, Message=msg)
            
        res = self._rest_inbound_socket.bgapi(cmd)
        job_uuid = res.get_job_uuid()
        if not job_uuid:
            self._rest_inbound_socket.log.error("SendDigits Failed -- JobUUID not received" % job_uuid)
            msg = "SendDigits Failed"
            return self.send_response(Success=result, Message=msg)
        
        msg = "SendDigits executed"
        result = True
        return self.send_response(Success=result, Message=msg)

