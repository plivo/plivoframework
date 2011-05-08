# -*- coding: utf-8 -*-
# Copyright (c) 2011 Plivo Team. See LICENSE for details

import re
import uuid

from flask import request

from plivo.rest.freeswitch.helpers import is_valid_url, get_conf_value


class PlivoRestApi(object):
    _config = None
    _rest_inbound_socket = None

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
                        ring_url):

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
        args_str = ','.join(args_list)
        originate_str = ''.join(["originate {", args_str])
        if extra_dial_string:
            originate_str = "%s,%s" % (originate_str, extra_dial_string)

        gw_try_number = 0
        request_params = [originate_str, to, gw_try_number, gw_list,
                          gw_codec_list, gw_timeout_list, gw_retry_list,
                          answer_url, hangup_url, ring_url]
        self._rest_inbound_socket.call_request[request_uuid] = request_params
        keystring = "%s-%s" % (to, caller_id)
        self._rest_inbound_socket.ring_map[keystring] = request_uuid

        return request_uuid

    def calls(self):
        msg = None
        caller_id = request.form['From']
        to = request.form['To']
        gw = request.form['Gateways']
        answer_url = request.form['AnswerUrl']

        if not caller_id or not to or not gw or not answer_url:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "Answer URL is not Valid"
        else:
            hangup_url = request.form['HangUpUrl']
            ring_url = request.form['RingUrl']
            if hangup_url and not is_valid_url(hangup_url):
                msg = "Hangup URL is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "Ring URL is not Valid"
            else:
                extra_dial_string = request.form['OriginateDialString']
                gw_codecs = request.form['GatewayCodecs']
                gw_timeouts = request.form['GatewayTimeouts']
                gw_retries = request.form['GatewayRetries']

                request_uuid = self.prepare_request(caller_id, to,
                            extra_dial_string, gw, gw_codecs, gw_timeouts,
                            gw_retries, answer_url, hangup_url, ring_url)

                self._rest_inbound_socket.spawn_originate(request_uuid)
                msg = "Request Executed %s" % request_uuid

        return msg

    def bulk_calls(self):
        msg = None
        caller_id = request.form['From']
        to_str = request.form['To']
        gw_str = request.form['Gateways']
        answer_url = request.form['AnswerUrl']

        if not caller_id or not to_str or not gw_str or not answer_url:
            msg = "Mandatory Parameters Missing"
        elif not is_valid_url(answer_url):
            msg = "Answer URL is not Valid"
        else:
            hangup_url = request.form['HangUpUrl']
            ring_url = request.form['RingUrl']
            if hangup_url and not is_valid_url(hangup_url):
                msg = "Hangup URL is not Valid"
            elif ring_url and not is_valid_url(ring_url):
                msg = "Ring URL is not Valid"
            else:
                extra_dial_string = request.form['OriginateDialString']
                delimeter = request.form['Delimeter']
                # Is a string of strings
                gw_codecs_str = request.form['GatewayCodecs']
                gw_timeouts_str = request.form['GatewayTimeouts']
                gw_retries_str = request.form['GatewayRetries']
                request_uuid_list = []
                i = 0

                to_str_list = to_str.split(delimeter)
                gw_str_list = gw_str.split(delimeter)
                gw_codecs_str_list = gw_codecs_str.split(delimeter)
                gw_timeouts_str_list = gw_timeouts_str.split(delimeter)
                gw_retries_str_list = gw_retries_str.split(delimeter)

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

                        request_uuid = self.prepare_request(caller_id, to,
                                    extra_dial_string, gw_str_list[i],
                                    gw_codecs, gw_timeouts, gw_retries,
                                    answer_url, hangup_url, ring_url)

                        i += 1
                        request_uuid_list.append(request_uuid)

                self._rest_inbound_socket.bulk_originate(request_uuid_list)
                msg = "Requests Executed"

        return msg
