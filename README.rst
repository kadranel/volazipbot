Attention, this will no longer be updated to newer versions of volapi due to time constraints! (Date: 22 June 2019)

=====================
Volazipbot
=====================

This is a volafile.org bot written for Python 3.7. It can zip files, mirror files files to openload and has some basic user authetification. If i were to do this again i'd use javascript, but wanted to share this nevertheless since it works.
The current version is highly dependant on changes to volafile.org and especially to adaptions of changes in volapi_. (Currently the bot is working on volapi 5.14.0)

.. _volapi: https://github.com/volafiled/python-volapi

Installation
------------

0) What do you need?
  a) Python 3.7+?
  b) pip
1) How to install
  a) Download the newest release of the bot at https://github.com/kadranel/volazipbot/archive/2.0.0.zip or git clone this repository.
  b) Unzip and enter the folder with you favourite shell, then type:
::

    pip3 install -r requirements.txt

2) Edit the config.json (Explanation of what you can/should change below):

::

    {
      "main": {                                    MAIN CONFIGURATION
        "admin": "YOURNAMEHERE",                   <- You should change "admin" to your main user account.
        "adminroom": "ROOMNAME",                   <- If you want to use an admin_room for administration
        "adminroom_pass": "",                         specify it here with a password, else set "adminroom": ""
        "keepfiles": 0,                            <- If 0 -> all files will be deleted, If 1 -> zipped
                                                      files will be kept in "archfolder" and "mirrorfolder"
        "headers": {                               <- You should not change "headers", but you can.
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:55.0) Gecko/20100101 Firefox/55.0",
          "DNT": "1",
          "Upgrade-Insecure-Requests": "1"
        },
        "cookies": {                               <- You should not change "cookies"
          "allow-download": "1"
        },
        "mirrorzipmax": 990,                       <- "mirrorzipmax" changes the filesize of split zip files
                                                      for uploading to openload
        "mirrorziptest": 995.0,                    <- "mirrorziptest" maximum size of files that do not get split for
                                                      uploading to openload (Max. filesize of 1 GB)
        "zipbotuser": "zipbotuser",                <- CHANGE NEEDED HERE: user details for your chat/upload volafile
        "zipbotpass": "zipbotpassword",               user
        "dluser": "downloaduser",                  <- CHANGE NEEDED HERE: user details for your download volafile
        "dlpass": "downloadpassword",                 user. It can be the same as zipbot
        "opus": "openload-apiuser",                <- CHANGE NEEDED HERE: Your openload api user and key
        "oppw": "openload-apikey"
      },
      "rooms": {                                   ROOM CONFIGURATION
        "genericroom": {                           <- DO NOT RENAME "genericroom", it is used as a fallback
          "allowedzippers": [                         room, if you send your bot to new rooms.
            "*kad",                                <- Add and/or delete users here to give them permission to
            "+janitor",                                use !zip, !mirror and !count in unknown rooms.
            "+registered"                              The "*" infront of the names refers to registered users
          ],                                           on volafile
          "botadmins": [                           <- Add and/or delete users here to give them permission to
            "*kad"                                    use !sleep/!wake and !kill in unknown rooms.
            "+janitor"                                For more info on user roles refer to this page.
          ],
          "mirrormaxmem": 7500.0,                  <- 7500 MB is the max filesize for mirroring, changeable
          "maxmem": 5000.0,                        <- 5000 Mb is the max filesize for zipping, changeable
          "anonfile": 0                            <- Switch to 1 if you want to use anonfile instead of openload
        },                                            for files >1gb - instable feature though

        "YOURROOM": {                              <- CHANGE NEEDED HERE. Rename this with the room-id of a room
          "allowedzippers": [                         you want to zip in:
            "+all"                                     https://volafile.org/r/[room-id]
          ],                                          Apart from that, the same changes as in "genericroom" can
          "botadmins": [                              be made here. Also you can set different configurations
            "*admiin",                                for multiple rooms by adding multiple of these sections with
            "*kad"                                    different room-ids as names.
          ],
          "mirrormaxmem": 7500.0,
          "maxmem": 5000.0,
          "anonfile": 0
        }
      },
      "os": {                                     <- Two sections here, because i used the same config on a windows
        "nt": {  <- change here for windows          and a linux pc. I did not try it on mac, but it should work.
          "logfolder": "./voladl/log/",              You can change these folder locations to anywhere you like,
          "zipfolder": "./voladl/zip/",              just make sure the folder exists before starting the bot.
          "archfolder": "./voladl/archive/",
          "mirrorfolder": "./voladl/mirror/",
          "mirrorlogs": "./voladl/mirrorlogs/",
          "membuff": 300
        },
        "posix": { <- change here for linux/mac
          "logfolder": "./voladl/log/",
          "zipfolder": "./voladl/zip/",
          "archfolder": "./voladl/archive/",
          "mirrorfolder": "./voladl/mirror/",
          "mirrorlogs": "./voladl/mirrorlogs/",
          "membuff": 300
        }
      }
    }

Start the bot
------------
::

    python3 bot.py -r ROOMID -z ZIPPER -p PASSWORD[OPTIONAL]

a) ROOMID: https://volafile.org/r/[ROOMID]
b) ZIPPER: True/False -> Determines whether the bot allows the use of the zip/count/mirror functions or whether he just listens to the chat.
c) PASSWORD: The room password if it exists

Example: You want to listen to https://volafile.org/r/n7yc3pgw and zip there:
::

    python3 bot.py -r n7yc3pgw -z True

Bot commands
------------
See https://github.com/kadranel/volazipbot/blob/master/ziphelp.txt

User administration
------------
Possible user groups in the config file include:

a) +all to let all users (whites/greens/etc) use the selected functions. -> not advisable
b) +registered to let all logged in users (greens) use the selected functions
c) +janitor to let all room janitors use the selected functions

Don't want to edit the config.json and restart the bot to add/remove users?
No Problem! The following commands can be used in the current volafile room to do exactly that.
::

    !zip user add USERNAME

Adds the user USERNAME to the allowed zippers in the room -> you can use +USERGROUP_NAME here as well.
Usable by "botadmins" defined in the config.json, the "admin" defined in the config.json and the room owner.
::

    !zip user remove USERNAME

Removes the user USERNAME from the allowed zippers in the room -> you can use +USERGROUP_NAME here as well.
Usable by "botadmins" defined in the config.json, the "admin" defined in the config.json and the room owner.
::

    !zip admin add USERNAME

Adds the user USERNAME to the "botadmins" in the room -> you can use +USERGROUP_NAME here as well.
Usable by the "admin" defined in the config.json and the room owner.
::

    !zip admin remove USERNAME

Removes the user USERNAME from the "botadmins" in the room -> you can use +USERGROUP_NAME here as well.
Usable by the "admin" defined in the config.json and the room owner.

Usage of an admin room
------------
This feature allows you to more easily administrate multiple bot instances at the same time. 90% of the provided features only work on Linux/Mac with the "screen"-tool installed, Therefore it is not advisable to configure this if you want to use the bot on windows.
If you want to use a central admin room for all your room configuration the following things have to be setup and configured:

a) You need to create a volafile room with your admin_user and specify it in config.json (better with a roompassword)
b) Configure the rooms you want to send the bot to in starter_config.json (more explanation below):

::

    {
    "os": {                                     <- Two sections here, because i used the same config on a windows
      "python": "python3",                      <- Specify your python-version here or even better your full path
      "kill": 0,                                <- Used internally
      "folderpath": "/full/path/volazipbot/",   <- Specify the path your application is in
      "rooms": {
        "n7yc3pgw": {                           <- Specify rooms your bot is going to be sent to.
          "password": "",
          "restart": 0,                         <- Used internally
          "join": 1,                            <- Used internally
          "zipper": 1                           <- Do you want to activate functions or only listen.
        },                                         1 = activated, 0 = only listen
        "ADMINROOM": {                          <- You should also send your bot to your specified admin_room
          "password": "",                          if you want to use all features the admin_room provides.
          "restart": 0,                            Therefore change ADMINROOM to the room name of your admin
          "join": 1,                               room.
          "zipper": 1
        },
        "whatever": {
          "password": "whatever",
          "restart": 0,
          "join": 1,
          "zipper": 1
        }
      }
    }

Commands to be used in the admin_room:
You can either call all rooms by using #all or call a specific room with #roomname. 
::
    #all restart
    
Restarts the bot in all rooms. 
::
    #all kill
    
Stops the bot in all rooms.
::
    #all full restart
    
Restarts to the bot in all rooms, but closes all currently running screen-instances instead of restarting in the current running instance
::
    #all full kill
    
Stops the bot in all rooms, but also stops new screen-instances to be started by setting kill to 1 in starter_config.json
::
    #all revive
    
Reverts the full kill command
::
    #all mute
    
Stops all bots from sending chat messages
::
    #all unmute
    
Revert #all mute
::
    #all session

Creates a file of the current log in every bot instance and uploads it to the admin_room
::
    #roomname restart
    #roomname kill
    #roomname mute
    #roomname unmute
    #roomname session

Mirrors the functions from above for a single room
::
    #roomname zipper
    
Switches the bot from listening to zipping and vice-versa
::
    #roomname ping
    
Pings a bot and recieves a message in chat. 
This also allows #roomname user and #roomname admin with the messages defined in User administration.
::
    #adminroom join #newroom#pw
    
Joins a new room and adds it to the starter_config.json

This also enables new ways to start the bot e.g. in a crontab by starting the starter.py all 10 minutes. That will check for bot instances that are stuck or that crashed in the last 10 minutes.

Other
------------
This code was not really prepared to be shared, so if you have any questions/improvements feel free to message me or straight up change code and post a pull request. I'll try to clean up and comment more of the code at a later stage.
