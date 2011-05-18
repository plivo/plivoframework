
EXAMPLE OVERVIEW
~~~~~~~~~~~~~~~~

This directory contains the scripts that will launch the different components
for the Plivo Server to be operational


FILES
~~~~~

    * plivo :
        Script to start, stop, restart and get status of the plivo server
    
    * plivo-outbound :
        
        Python script to launch the Plivo Outbound Server
        This server is by default listening on 8084
        
        This server is used when you want to connect directly from Freeswitch
        to plivo
        
    * plivo-postinstall :
    
        Python Script that need to be run after install.
        Active some settings in configuration file and script
    
    * plivo-rest :
    
        Script to start, stop, restart and get status of the plivo Rest server
        This server is by default listening on 8088
