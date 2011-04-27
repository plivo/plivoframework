# Copyright (c) 2011 Plivo Team. See LICENSE for details.

from gevent import monkey; monkey.patch_all()
from flask import Flask, request

import re
import uuid

import settings
from helpers import is_valid_url

rest_server = Flask("RestServer")
rest_server.secret_key = settings.SECRET_KEY
rest_server.debug = settings.DEBUG

inbound_listener = None
log = None

def set_instances(inbound_listener_obj, log_obj):
    global inbound_listener
    global log
    log = log_obj
    inbound_listener = inbound_listener_obj


@rest_server.errorhandler(404)
def page_not_found(error):
    return 'This URL does not exist', 404


@rest_server.route('/')
def root_directory():
    message = """
    Welcome to REST Layer for FreeSWITCH Event Socket using Telephonie<br>
    <br>
    REST Telephonie layer is an open source asynchronous Framework that provide a Rest API <br>
    Layer on top of Event Socket. It is focused to processed real-time communication with <br>
    Freeswitch.<br>
    <br>
    Version 0.1 available to /v0.1/<br>
    <br>
    """
    #TODO: Convert markup to HTML ;)
    return message


@rest_server.route('/v0.1/')
def version_0_1():
    message = """
    This document describes REST Layer 0.1<br>
    <br>
    REST Telephonie layer is an open source asynchronous Framework that provide a Rest API <br>
    Layer on top of Event Socket. It is focused to processed real-time communication with <br>
    Freeswitch.<br>
    <br>
    Overview<br>
    ========<br>
    <br>
    Methods<br>
    =======<br>
    <br>
    Originate Calls<br>
    ~~~~~~~~~~~~~~~<br>
    <br>
    * /v0.1/Calls/ - POST Method<br>
    <br>
    """
    #TODO: Convert markup to HTML ;)
    return message


@rest_server.route('/v0.1/Calls/', methods=['POST'])
def calls():
    msg = None
    caller_id =  request.form['From']
    to =  request.form['To']
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

            request_uuid = prepare_request(caller_id, to, extra_dial_string, gw, gw_codecs, \
                        gw_timeouts, gw_retries, answer_url, hangup_url, ring_url)

            inbound_listener.spawn_originate(request_uuid)
            msg = "Request Executed %s" % request_uuid

    return msg


@rest_server.route('/v0.1/BulkCalls/', methods=['POST'])
def bulkcalls():
    msg = None
    caller_id =  request.form['From']
    to_str =  request.form['To']
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
                msg = "Gateway length does not match number of users to call"
            else:
                for to in to_str_list:
                    try:
                        gw_codecs = gw_codecs_str_list[i]
                    except Exception:
                        gw_codecs = ""
                    try:
                        gw_timeouts = gw_timeouts_str_list[i]
                    except Exception:
                        gw_timeouts = ""
                    try:
                        gw_retries = gw_retries_str_list[i]
                    except Exception:
                        gw_retries = ""

                    request_uuid = prepare_request(caller_id, to, extra_dial_string, gw_str_list[i], \
                                        gw_codecs, gw_timeouts, gw_retries, answer_url, hangup_url, ring_url)

                    i += 1
                    request_uuid_list.append(request_uuid)

            inbound_listener.bulk_originate(request_uuid_list)
            msg = "Requests Executed"

    return msg


def prepare_request(caller_id, to, extra_dial_string, gw, gw_codecs, \
                    gw_timeouts, gw_retries, answer_url, hangup_url, ring_url):
    gw_retry_list = []
    gw_codec_list = []
    gw_timeout_list = []

    gw_list = gw.split(',')
    # split gw codecs by , but only outside the ''
    if gw_codecs:
        gw_codec_list = re.split(''',(?=(?:[^'"]|'[^']*'|"[^"]*")*$)''', gw_codecs)
    if gw_timeouts:
        gw_timeout_list = gw_timeouts.split(',')
    if gw_retries:
        gw_retry_list = gw_retries.split(',')

    request_uuid = str(uuid.uuid1())
    originate_str = "originate {request_uuid=%s,answer_url=%s,origination_caller_id_number=%s" % (request_uuid, answer_url, caller_id)
    if extra_dial_string:
        originate_str = "%s,%s" % (originate_str, extra_dial_string)

    gw_try_number = 0
    request_params = [originate_str, to, gw_try_number, gw_list, gw_codec_list, \
                        gw_timeout_list, gw_retry_list, answer_url, hangup_url, ring_url]
    inbound_listener.call_request[request_uuid] = request_params
    keystring = "%s-%s" %(to, caller_id)
    inbound_listener.ring_map[keystring] = request_uuid

    return request_uuid
