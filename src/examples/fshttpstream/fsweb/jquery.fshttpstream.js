$.fn.fshttpstream = function(options) {
    var settings = $.extend({}, $.fn.fshttpstream.defaults, options);
   
    return this.each(function() {
        window.WEB_SOCKET_SWF_LOCATION = "WebSocketMain.swf";
        $.ajax({
	    url: "swfobject.js",
            dataType: 'script',
            async: false
        });
        $.ajax({
	    url: "FABridge.js",
            dataType: 'script',
            async: false
        });
        $.ajax({
	    url: "web_socket.js",
            dataType: 'script',
            async: false
        });
        $.ajax({
	    url: "fshttpstream.js",
            dataType: 'script',
            async: false
        });
        fsconfig = new FSConfig();
        fsconfig.setFilter(settings.refilter);
        $.fn.fshttpstream.fs = new FSHttpStream(settings.host, settings.port, settings.on_message, settings.on_open, settings.on_close, fsconfig);
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
    refilter : null
};

