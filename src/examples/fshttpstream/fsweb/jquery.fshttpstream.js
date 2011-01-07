$.fn.fshttpstream = function(options) {
    var settings = $.extend({}, $.fn.fshttpstream.defaults, options);
   
    return this.each(function() {
        window.WEB_SOCKET_SWF_LOCATION = settings.WebSocketMain_swf_path;
        $.ajax({
        url: settings.swfobject_js_path,
            dataType: 'script',
            async: false
        });
        $.ajax({
        url: settings.FABridge_js_path,
            dataType: 'script',
            async: false,
        });
        $.ajax({
        url: settings.web_socket_js_path,
            dataType: 'script',
            async: false
        });
        $.ajax({
        url: settings.fshttpstream_js_path,
            dataType: 'script',
            async: false,
            success: function(data) {
                        $.fn.fshttpstream.fs = new FSHttpStream(settings.host, settings.port, settings.on_message, settings.on_open, settings.on_close, settings.filters);
            }
        });
    });
   
};

$.fn.fshttpstream.fs = null;

$.fn.fshttpstream.parse_event = function(options) {
    var defaults = {"data": null};
    var settings = $.extend({}, defaults, options);

    return this.each(function() {
        try {
	    ev = $.parseJSON(settings.data)
            return ev;
        } catch(e) {
            return;
        }
    });
};

// default settings
$.fn.fshttpstream.defaults = {
    host : '127.0.0.1',
    port : null,
    on_message : function(){},
    on_open : function(){},
    on_close : function(){},
    filters : [],
    fshttpstream_js_path : "fshttpstream.js",
    swfobject_js_path : "swfobject.js",
    FABridge_js_path : "FABridge.js",
    web_socket_js_path : "web_socket.js",
    WebSocketMain_swf_path : "WebSocketMain.swf"
};

