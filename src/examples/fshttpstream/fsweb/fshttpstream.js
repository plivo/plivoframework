function FSHttpStream(host, port, onMessage, onOpen, onClose, filters) {
    if ((!port) || (port == null) || (port == "")) { 
        this.address = host;
    } else {
        this.address = host + ":"+port;
    }

    this.mode = 0;
    this.url = "";
    this.sock = null;

    this.onMessage = onMessage;
    this.onOpen = onOpen;
    this.onClose = onClose;

    if ((!filters) || (filters == null)) {
        this.filters = Array();
    } else {
        this.filters = filters;
    }

    if (!window.WebSocket) {
        this.mode = -1;
        alert("Websocket not supported !");
        return false;
    } else {
        this.mode = 1;
    }

    this.ws_state = 0;
    this.url = "ws://" + this.address + "/websock"; 
    this.sock = new WebSocket(this.url);
    this.sock.onmessage = this.Bind(function(e) {
        this.onMessage(this, e.data);
    });
    this.sock.onopen = this.Bind(function(e) {
        this.ws_state = 1;
        for(i=0; i<this.filters.length; i++) {
            this.sock.send(this.filters[i]);
        }
        this.sock.send("EOF");
        this.onOpen(this);
    });
    this.sock.onclose = this.Bind(function(e) {
        this.ws_state = 0;
        this.onClose(this);
    });
}

FSHttpStream.prototype.Bind = function(func) {
    var obj = this;
    return function() {
        return func.apply(obj, arguments);
    }
}

function has_websocket() {
    if (!window.WebSocket) { return false; }
        return true;
}

FSHttpStream.prototype.getMode = function() {
    return this.mode;
};
  
FSHttpStream.prototype.getStringMode = function() {
    if (this.mode == 1) {
        return "WebSocket";
    }
    return "NotSupported";
};

FSHttpStream.prototype.getFilters = function() {
    return this.filters;
};

FSHttpStream.prototype.getUrl = function() {
    return this.url;
};

FSHttpStream.prototype.getAddress = function() {
    return this.address;
};



