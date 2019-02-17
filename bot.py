import time
from datetime import datetime, timedelta
import os
import json
import shutil
from functools import partial
from volapi import Room, listen_many
import argparse
from unidecode import unidecode
from tqdm import tqdm
import requests
from requests_toolbelt.multipart import encoder
from openload import OpenLoad
import functions as f
import starter as starter

help_file = ""
kill = False


class VolaZipBot(object):
    def __init__(self, args):
        # Creating a session and a refresh_time. The bot starts a new session once the refresh_time is reached
        self.session_id = f.id_generator()
        self.session = f"{datetime.now().strftime('[%Y-%m-%d][%H-%M-%S]')}[{args[0]}][{self.session_id}]"
        self.refresh_time = datetime.now() + timedelta(days=1)

        # Setting status attributes
        self.alive = True
        self.wake = True
        self.zipper = args[1]
        self.logged_in = False
        self.close_status = True
        self.execution_path = os.path.dirname(os.path.abspath(__file__))

        # Setting room information
        self.url = f"https://volafile.org/r/{args[0]}"
        self.room = args[0]
        self.multiplier = 1048576

        # Loading the config.json
        json_file = open(f"{self.execution_path}/config.json", 'r')
        self.cfg = json.load(json_file)
        json_file.close()
        self.cookies = self.cfg['main']['cookies']
        self.headers = self.cfg['main']['headers']
        self.admin_user = self.cfg['main']['admin']
        self.keep_files = self.cfg['main']['keep_files']
        self.admin_room_string = self.cfg['main']['admin_room']
        self.admin_room_password = self.cfg['main']['admin_room_pass']

        # Initialising the room_select and platform -> this is used for navigating in config.json
        if args[0] in self.cfg['rooms'].keys():
            self.room_select = args[0]
        else:
            self.room_select = 'genericroom'
        if os.name in self.cfg['os'].keys():
            self.platform = os.name
        else:
            print(f"OS {os.name} is not supported.")
            self.alive = False

        # room variables
        self.muted = self.cfg["rooms"][self.room_select]['muted']
        self.msg_redirect = self.cfg["rooms"][self.room_select]['msg_redirect']

        # Checking if a room password is set in args
        self.room_password = None
        self.room_key = None
        if len(args) == 3:
            # hacky way to give a room_key instead of a password in case the password is unknown, but the bot should still access
            # if your room_password starts with #key, tough luck ;)
            if args[2][0:4] == '#key':
                self.room_key = args[2][4:]
            else:
                self.room_password = args[2]

        # create session file
        self.create_session_file()

        # Connecting to the room via volapi
        try:
            # Connect to normal room
            self.interact = self.interact_room()
            # self.listen = self.listen_room()
            # Not sure yet if two different sockets are better for consistency
            self.listen = self.interact
            self.printl(f"Session: {self.session}", "__init__")
            # Connect to admin room
            self.admin = None
            if not self.admin_room_string == "":
                self.admin = self.admin_room()
        except OSError:
            # Catching Socket not available on connect
            self.printl("Failed to connect - trying to reconnect in 60 seconds", "__init__")
            time.sleep(60)
            self.alive = False

    def __repr__(self):
        return f"<VolaZipBot(alive={self.alive}, zipper={self.zipper}, listen={str(self.listen)}, interact={str(self.interact)})>"

    def join_room(self):
        """Adds the listener to the room."""

        def onmessage(m):
            """Print the new message and respond to user input"""
            self.printl(f.msg_formatter(m), "onmessage/main")

            # Commands for the bot are evaluated here

            # create a help file for the room: !zip help
            if self.zipper and self.wake and (str(m.lower()[0:9]) == '!zip help' or str(m.lower()[0:5]) == '!help'):
                self.zip_help(m.nick)
            # user administration: !zip user/admin add/remove name
            elif self.zipper and self.wake and (str(m.lower()[0:10]) == '!zip user '):
                # needed linebreak to prevent another check in "!zip"
                if self.admin_check(m.nick, m.logged_in, m.owner, m.janitor, m.purple):
                    self.user_administration(m.nick, "user", str(m))
            elif self.zipper and self.wake and (str(m.lower()[0:11]) == '!zip admin '):
                # needed linebreak to prevent another check in "!zip"
                if self.user_admin_check(m.nick, m.logged_in, m.owner):
                    self.user_administration(m.nick, "admin", str(m))
            # zip files in the room: !zip
            elif self.zipper and self.wake and (str(m.lower()[0:4]) == '!zip') and self.zip_check(m.nick, m.logged_in, m.owner,
                                                                                                  m.janitor, m.purple):
                self.zip_handler(m.nick, m, files=m.files)
            # count file position in room: !count
            elif self.zipper and self.wake and (str(m.lower()[0:6]) == '!count') and self.zip_check(m.nick, m.logged_in, m.owner,
                                                                                                    m.janitor, m.purple):
                self.count_handler(m.nick, m, files=m.files)
            # mirror 1 file in the room : !mirror
            elif self.zipper and self.wake and (str(m.lower()[0:7]) == '!mirror') and self.zip_check(m.nick, m.logged_in, m.owner,
                                                                                                     m.janitor, m.purple):
                self.mirror_handler(m.nick, m)
            # check on bot status: !alive
            elif self.zipper and (str(m.lower()[0:6]) == '!alive'):
                self.printl(f"{m.nick} -> checking for bot: {str(self)}", "alive")
                if self.wake:
                    self.post_chat(f"{m.nick}: chinaman working!")
                else:
                    self.post_chat(f"{m.nick}: chinaman is asleep.")
            # kill the bot in the room: !kill
            elif self.zipper and (str(m.lower()[0:5]) == '!kill') and self.admin_check(m.nick, m.logged_in, m.owner, m.janitor, m.purple):
                self.kill(m.nick)
            # pause/reenable the bot: !sleep/!wake
            elif self.zipper and self.wake and (str(m.lower()[0:6]) == '!sleep') and self.admin_check(m.nick, m.logged_in, m.owner,
                                                                                                      m.janitor, m.purple):
                self.post_chat(f"{m.nick}: chinaman going to sleep!")
                self.wake = False
            elif self.zipper and not self.wake and (str(m.lower()[0:5]) == '!wake') and self.admin_check(m.nick, m.logged_in, m.owner,
                                                                                                         m.janitor, m.purple):
                self.post_chat(f"{m.nick}: chinaman woke up!")
                self.wake = True
            # switch from zipper = False to zipper = True, enables most functions: !zipbot
            elif not self.zipper and (str(m.lower()[0:7]) == '!zipbot') and self.super_admin_check(m.nick, m.logged_in):
                self.post_chat(f"{m.nick}: Whuddup!")
                self.zipper = True
            # reconnect to the room: !restart
            elif str(m.lower()[0:8]) == '!restart' and self.admin_check(m.nick, m.logged_in, m.owner, m.janitor, m.purple):
                self.close()

        def ontime(t):
            """React to time events emitted by volafile socket connection, used for maintenance"""
            if datetime.now() > self.refresh_time:
                # if the refresh_time is now -> close the bot
                self.close()
            # check for connections
            if self.listen and self.interact:
                if not self.listen.connected or not self.interact.connected:
                    self.close()
            return t

        def onadminmsg(m):
            """Print the new message in self.admin and respond to the admin input"""
            room_length = len(self.room) + 2
            if m.lower()[0:room_length] == f'#{self.room} '.lower() and self.super_admin_check(m.nick, m.logged_in):
                self.printl(f.msg_formatter(m), "onadminmsg/admin")
                self.admin_options(m.split(f'#{self.room} ')[1].lower())
            elif m.lower()[0:5] == '#all ' and self.super_admin_check(m.nick, m.logged_in):
                self.printl(f.msg_formatter(m), "onadminmsg/admin")
                self.admin_options(m.split('#all ')[1].lower(), True)

        # connection to the python-volapi
        if self.alive:
            try:
                # add the listeners on the volapi room
                if self.admin:
                    # with an admin_room defined in config ->
                    self.listen.add_listener("chat", partial(onmessage))
                    self.listen.add_listener("time", partial(ontime))
                    self.admin.add_listener("chat", partial(onadminmsg))
                    self.state_session()

                    self.printl(f"Connecting to room: {str(self.listen)}", "join_room")
                    # start listening
                    listen_many(self.listen, self.admin)
                else:
                    # without specific admin room
                    self.listen.add_listener("chat", onmessage)
                    self.listen.add_listener("time", ontime)

                    self.printl(f"Connecting to room: {str(self.listen)}", "join_room")
                    # start listening
                    self.listen.listen()
            except OSError:
                self.printl("Socket disconnected, trying to reconnect... - OSError", "join_room")
                self.close()
            return False

    def admin_options(self, msg, to_all=False):
        """Reacts to messages that get sorted and checked by onadminmsg()"""
        # can only be called with an admin_room defined in the config.json
        if not self.admin:
            return False
        redirect_temp = self.msg_redirect
        if to_all:
            # handles messages broadcasted to all clients specified by #all in the beginning of the message
            if msg[0:7] == 'restart' and not self.is_this_admin_room():
                self.close()
            elif msg[0:4] == 'kill' and not self.is_this_admin_room():
                self.muted = True
                self.kill("ADMIN")
            elif msg[0:4] == 'full' and self.is_this_admin_room():
                if msg[0:9] == 'full kill':
                    json_file = open(f'{self.execution_path}/starter_config.json', 'r')
                    starter_cfg = json.load(json_file)
                    json_file.close()
                    starter_cfg['kill'] = 1
                    for key in starter_cfg['rooms'].keys():
                        starter_cfg['rooms'][key]['restart'] = 1
                    json_file = open(f'{self.execution_path}/starter_config.json', 'w')
                    json.dump(starter_cfg, json_file)
                    json_file.close()
                if msg[0:12] == 'full restart':
                    json_file = open(f'{self.execution_path}/starter_config.json', 'r')
                    starter_cfg = json.load(json_file)
                    json_file.close()
                    for key in starter_cfg['rooms'].keys():
                        starter_cfg['rooms'][key]['restart'] = 1
                    json_file = open(f'{self.execution_path}/starter_config.json', 'w')
                    json.dump(starter_cfg, json_file)
                    json_file.close()
            elif msg[0:4] == 'full' and not self.is_this_admin_room():
                if msg[0:9] == 'full kill':
                    self.muted = True
                    self.kill("ADMIN")
                if msg[0:12] == 'full restart':
                    self.muted = True
                    self.kill("ADMIN")
            elif msg[0:6] == 'revive' and self.is_this_admin_room():
                json_file = open(f'{self.execution_path}/starter_config.json', 'r')
                starter_cfg = json.load(json_file)
                json_file.close()
                starter_cfg['kill'] = 0
                json_file = open(f'{self.execution_path}/starter_config.json', 'w')
                json.dump(starter_cfg, json_file)
                json_file.close()
            elif msg[0:4] == 'mute' and not self.is_this_admin_room():
                self.muted = True
            elif msg[0:6] == 'unmute' and not self.is_this_admin_room():
                self.muted = False
            elif msg[0:7] == 'session' and not self.is_this_admin_room():
                self.upload_vola(f'{self.return_log_folder(self.room)}/{self.session}.txt', self.admin)
        else:
            # handles messages only sent to this room specified by #ROOMNAME in the beginning of the message
            if msg[0:7] == 'restart':
                self.close()
            elif msg[0:4] == 'kill':
                self.muted = True
                json_file = open(f'{self.execution_path}/starter_config.json', 'r')
                starter_cfg = json.load(json_file)
                json_file.close()
                starter_cfg['rooms'][self.room]['join'] = 0
                json_file = open(f'{self.execution_path}/starter_config.json', 'w')
                json.dump(starter_cfg, json_file)
                json_file.close()
                self.kill("ADMIN")
            elif msg[0:4] == 'join' and self.is_this_admin_room():
                # Attention, this has no implementation on windows, the command will still run, but nothing will happen
                # syntax: join #roomname#password if the room has a password, join #roomname if not. Zipper gets automatically set to False
                split_msg = msg.replace(" ", "").split("#")
                if 1 < len(split_msg) < 4:
                    if len(split_msg) == 2:
                        self.post_chat(f"{self.admin_user}: {starter.start_single_room(split_msg[1])}")
                    if len(split_msg) == 3:
                        self.post_chat(f"{self.admin_user}: {starter.start_single_room(split_msg[1], split_msg[2])}")
                else:
                    self.post_chat(f"{self.admin_user}: Message could not be interpreted correctly")
            elif msg[0:6] == 'zipper':
                self.zipper = not self.zipper
                ret = 0
                if self.zipper:
                    ret = 1
                json_file = open(f'{self.execution_path}/starter_config.json', 'r')
                starter_cfg = json.load(json_file)
                json_file.close()
                starter_cfg['rooms'][self.room]['zipper'] = ret
                json_file = open(f'{self.execution_path}/starter_config.json', 'w')
                json.dump(starter_cfg, json_file)
                json_file.close()
                self.post_chat(f"{self.admin_user}: zipper = {str(self.zipper)}", self.admin)
            elif msg[0:4] == 'mute':
                self.muted = True
            elif msg[0:6] == 'unmute':
                self.muted = False
            elif msg[0:4] == 'user':
                self.msg_redirect = True
                self.user_administration(self.admin_user, "user", f"!zip {msg}")
                self.msg_redirect = redirect_temp
            elif msg[0:5] == 'admin':
                self.msg_redirect = True
                self.user_administration(self.admin_user, "admin", f"!zip {msg}")
                self.msg_redirect = redirect_temp
            elif msg[0:7] == 'session':
                self.upload_vola(f'{self.return_log_folder(self.room)}/{self.session}.txt', self.admin)
            elif msg[0:4] == 'ping':
                self.post_chat("pong", self.admin)
            else:
                self.post_chat(f"{self.admin_user}: Message could not be interpreted correctly", self.admin)
        return True

    def state_session(self):
        """creates a file that gets uploaded to the admin room on entry"""
        path = f"{self.return_log_folder(self.room)}/{self.room}-{self.session_id}.txt"
        if os.path.isfile(path):
            os.remove(path)
        fl = open(path, "w+")
        msg = f"room: {self.room} - session: {self.session_id} - zipper: {self.zipper} - muted: {self.muted}"
        fl.write(msg)
        msg = f"\n{str(self.listen)}\n{str(self.interact)}\n{str(self.admin)}"
        fl.write(msg)
        fl.close()
        self.upload_vola(path, self.admin)
        os.remove(path)
        return False

    def is_this_admin_room(self):
        """Checks if this is the defined admin_room"""
        return self.room == self.admin_room_string

    def user_administration(self, name, mode, message):
        """Allows for user administration to add/remove new users in the config.json"""
        json_file = open(f'{self.execution_path}/config.json', 'r')
        new_cfg = json.load(json_file)
        json_file.close()
        # check for the selected mode
        if mode == "user":
            delimiter = "allowedzippers"
        elif mode == "admin":
            delimiter = "botadmins"
        else:
            return False
        # check here if a config for the room already exists, if not create the entry
        if self.room_select == 'genericroom':
            new_cfg = self.create_new_config_entry(new_cfg)
        room_select = self.room
        # handle the command itself
        command_split = message.split(f"!zip {mode} ")
        if len(command_split) > 1:
            # add to the config
            if command_split[1][0:4] == "add ":
                name_split = message.split(f"!zip {mode} add ")
                if len(name_split) > 1:
                    user_name = f.input_replace(name_split[1])
                    if not (user_name == "+all" or user_name == "+registered" or user_name == "+janitor"):
                        user_name = f"*{user_name.replace('+', '')}"
                    if user_name not in new_cfg["rooms"][room_select][delimiter]:
                        if mode == "admin" and (user_name == "+all" or user_name == "+registered"):
                            self.printl(f"{user_name} can't be added as admin: {mode}", "user_administration")
                            self.post_chat(f'{name}: You can not add {user_name} as admin.')
                            return False
                        new_cfg["rooms"][room_select][delimiter].append(user_name)
                        self.printl(f"user_name {user_name} was added to the config: {mode}", "user_administration")
                        self.post_chat(f'{name}: {user_name} was added to the config.')
                    else:
                        self.printl(f"{user_name} already in the config: {mode}", "user_administration")
                        self.post_chat(f'{name}: {user_name} was already in the config.')
                        return False
                else:
                    self.printl("Message could not be interpreted", "user_administration")
                    self.post_chat(f'{name}: Your message could not be interpreted.')
                    return False
            # remove from the config
            elif command_split[1][0:7] == "remove ":
                name_split = message.split(f"!zip {mode} remove ")
                if len(name_split) > 1:
                    user_name = f.input_replace(name_split[1])
                    if not (user_name == "+all" or user_name == "+registered" or user_name == "+janitor"):
                        user_name = f"*{user_name.replace('+', '')}"
                    if user_name in new_cfg["rooms"][room_select][delimiter]:
                        if mode == "admin" and len(new_cfg["rooms"][room_select][delimiter]) == 1:
                            self.printl(f"The last admin can't be removed: {user_name}", "user_administration")
                            self.post_chat(f'{name}: You can not remove the last admin.')
                            return False
                        new_cfg["rooms"][room_select][delimiter].remove(user_name)
                        self.printl(f"user_name {user_name} was removed from the config: {mode}", "user_administration")
                        self.post_chat(f'{name}: {user_name} was removed from the config.')

                    else:
                        self.printl(f"user_name not in the config {mode}", "user_administration")
                        self.post_chat(f'{name}: {user_name} was not in the config.')
                        return False
                else:
                    self.printl("Message could not be interpreted", "user_administration")
                    self.post_chat(f'{name}: Your message could not be interpreted.')
                    return False
            else:
                self.printl("Message could not be interpreted", "user_administration")
                self.post_chat(f'{name}: Your message could not be interpreted.')
                return False
        else:
            self.printl("Message could not be interpreted", "user_administration")
            self.post_chat(f'{name}: Your message could not be interpreted.')
            return False
        # write json back
        json_file = open(f'{self.execution_path}/config.json', 'w')
        json.dump(new_cfg, json_file)
        json_file.close()
        # enable new config
        self.cfg = new_cfg
        self.room_select = room_select
        return True

    def create_new_config_entry(self, cfg):
        """Creates new config entry for current room"""
        self.printl(f"Creating new local config entry for {self.room}:", "create_new_config_entry")
        cfg["rooms"][self.room] = self.cfg["rooms"]["genericroom"].copy()
        return cfg

    def mirror_handler(self, name, message):
        """Grabs files from a room and uplpoads them to openload"""
        self.printl(f"{name} -> requested mirror", "mirror_handler")

        # generate a folder name
        folder_name = f.id_generator()
        message_split = str(message).split('@')
        mirror_msg = ""

        # look if the file is in the room
        file_info, url, file_size, file_checked = self.file_check(name, str(message_split[1]).replace(" ", ""))
        if not file_info:
            self.post_chat(f'{name}: Your Message could not be interpreted correctly. (use !zip help)')
            return False

        # this checks whether the file is lower than the maximum mirror file size allowed in cfg
        if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['mirrormaxmem']:

            self.post_chat(f'{name}: Starting to mirror.')
            time.sleep(1)
            # Downloading the file here while getting the filepath back
            zip_path = self.single_file_download(url, folder_name, True)
            # Checking if file is bigger then 995 mb since openload does not allow files > 1gb
            if file_size / self.multiplier <= self.cfg['main']['mirrorziptest']:
                self.printl(f'Uploading to Openload: {zip_path}', "mirrorhandler")
                # Uploading the file to openload
                upload_infos = self.upload_openload(zip_path)
                self.printl(str(upload_infos), "mirrorhandler")
                mirror_msg = f"{upload_infos['url']}\n"
                upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{upload_infos['name']}_mirror.txt"
                # return message to chat
                self.post_chat(f"{name}: {upload_infos['name']} is uploaded to -> {upload_infos['url']}")
                if os.path.isfile(upload_path):
                    upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{upload_infos['name']}_mirror_{str(f.id_generator())}.txt"
                fl = open(upload_path, "w+")
                fl.write(f'{mirror_msg} \n{file_checked}')
                fl.close()
                self.upload_vola(upload_path)
            else:
                # file is > 1gb -> needs to be converted to zip and split before uploading
                self.printl(f'Checking if zip: {zip_path}', "mirrorhandler")
                path_split = zip_path.split('/')
                file_name_split = str(path_split[-1])
                endsplit = file_name_split.split('.')
                ending = str(endsplit[-1])
                if ending != 'zip':
                    # making a zip
                    zip_name = file_name_split
                    shutil.make_archive(zip_name, 'zip', self.return_zip_folder(folder_name))
                    os.remove(f'{self.return_zip_folder(folder_name)}/{zip_name}')
                    shutil.move(f'{zip_name}.zip', f'{self.return_zip_folder(folder_name)}/{zip_name}.zip')
                    zip_path = f'{self.return_zip_folder(folder_name)}/{zip_name}.zip'

                # splitting the zip with file_split
                self.printl(f'Splitting zip: {zip_path}', "mirrorhandler")
                self.file_split(zip_path, self.cfg['main']['mirrorzipmax'] * self.multiplier)
                shutil.move(zip_path, self.cfg['os'][self.platform]['mirrorfolder'] + file_name_split)

                for fi in os.listdir(self.return_zip_folder(folder_name)):
                    xpath = os.path.join(self.return_zip_folder(folder_name), fi)
                    self.printl(f'Uploading to openload: {xpath}', "mirrorhandler")
                    upload_infos = self.upload_openload(xpath)
                    # putting together the message with file links
                    mirror_msg = f"{mirror_msg}{upload_infos['url']} \n"

                # creating the _mirror.txt here
                upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{file_name_split}_mirror.txt"
                if os.path.isfile(upload_path):
                    upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{file_name_split}_mirror_{str(f.id_generator())}.txt"
                fl = open(upload_path, "w+")
                fl.write(f'{mirror_msg} \n{file_checked}')
                fl.close()
                file_id = self.upload_vola(upload_path)
                retmsg = f'{name}: {file_name_split} is uploaded to -> @{file_id}'
                time.sleep(2)
                self.post_chat(retmsg)

            # cleanup
            path_split = zip_path.split('/')
            file_name_split = str(path_split[-1])
            if os.path.isfile(zip_path) and self.keep_files:
                shutil.move(zip_path, self.cfg['os'][self.platform]['mirrorfolder'] + file_name_split)
            shutil.rmtree(self.return_zip_folder(folder_name))
        else:
            self.post_chat(f"{name}: The file @{str(message_split[1].replace(' ', ''))} is too big to mirror. -> > {str(self.cfg['rooms'][self.room_select]['mirrormaxmem'])} MB")

    def file_check(self, name, file_id):
        """Returns fileinfo for the _mirror.txt"""
        # get file_info from volapi
        file_info = self.interact.fileinfo(file_id)
        if file_info:
            file_uploader = str(file_info['user'])
            file_size = file_info['size']
            requester = str(name)
            file_size_string = "{0:.2f} MB".format(file_size / self.multiplier)
            url = f"https://volafile.org/get/{file_info['id']}/{file_info['name']}"
            file_checked = f"You need to download all of the links for a complete file # Size: {file_size_string} # Uploader: {file_uploader} # Requested by: {requester}"
            # return as tuple
            return file_info, url, file_size, file_checked
        else:
            return False, "", 0, ""

    def count_handler(self, name, message, files):
        """Counts file positions in the current room"""
        self.printl(f"{name} -> requested count", "count_handler")
        # check if request makes sense
        if files and 0 < len(files) < 3:
            message_split = str(message).split('@')
            file_list = self.listen.files
            i = 0
            for file in files:
                i = i + 1
                # check if the mentioned file is in the room
                if self.file_in_room(str(message_split[i]).replace(" ", "")):
                    found = False
                    user_count = 0
                    full_count = 0
                    uploader = file.uploader
                    file_name = str(file.name)
                    fid = file.fid
                    for dat in reversed(file_list):
                        if dat.uploader == uploader:
                            user_count = user_count + 1
                        full_count = full_count + 1
                        # if the file is found -> break here
                        if dat.fid == fid:
                            found = True
                            break
                    if found:
                        self.post_chat(f'{name}: {file_name} - > count in room: {str(full_count)} - count for {uploader}: {str(user_count)}')
                else:
                    self.post_chat(f'{name}: The file @{str(message_split[i].replace(" ", ""))} was not found in the room.')

        else:
            self.post_chat(f'{name}: Your message could not be interpreted correctly. (use !zip help)')
            return False

    def zip_handler(self, name, message, mirror='vola', files=None):
        """Downloads files, zips them, uploads them back to volafile and possibly other mirrorsites"""
        self.printl(f"{name} -> requested zip with: '{message}'", "zip_handler")
        folder_name = f.id_generator()
        full_message_split = message.split('#')
        # initialize variables
        additional_mirror = False
        rename = False
        if len(full_message_split) > 1:
            # if there are any '#command'
            upl = '*'
            file_name = '*'
            file_type = '*'
            number_of_files = -1
            offset = 0
            zip_name = str(f.id_generator())
            for message_split in full_message_split:
                # evaluate the user commands
                splits = str(message_split).split("=")
                if len(splits) == 2:
                    splits[0] = splits[0].replace(" ", "")
                    if str(splits[0]) == 'upl' or str(splits[0]) == 'uploader':
                        upl = str(splits[1])
                    if str(splits[0]) == 'filename' or str(splits[0]) == 'search':
                        file_name = str(splits[1])
                    if str(splits[0]) == 'type' or str(splits[0]) == 'filetype':
                        file_type = str(splits[1]).lower()
                    if str(splits[0]) == 'num' or str(splits[0]) == 'number':
                        number_of_files = int(eval(splits[1]))
                    if str(splits[0]) == 'offset' or str(splits[0]) == 'lownum':
                        offset = int(eval(splits[1]))
                    if str(splits[0]) == 'zipname' or str(splits[0]) == 'zip':
                        zip_name = str(splits[1]).replace(" ", "")
                elif len(splits) == 1:
                    splits[0] = splits[0].replace(" ", "")
                    if str(splits[0]) == 'mirror' or str(splits[0]) == 'openload':
                        additional_mirror = True
                    if str(splits[0]) == 'rename' or str(splits[0]) == 'rnm':
                        rename = True
                else:
                    continue
            if mirror == 'vola':
                self.post_chat(f'{name}: Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
            if mirror == 'openload':
                self.post_chat(f'{name}: Downloading and mirroring initiated. No other requests will be handled until the upload is finished.')
            if rename:
                rename = zip_name
            self.handle_downloads(folder_name, upl, file_name, file_type, number_of_files, offset, rename)

        else:
            # mostly not used: !zip with drag and drop, no further features like mirror or rename
            if not files or len(files) < 2:
                self.post_chat(f'{name}: Your message could not be interpreted correctly. (use !zip help)')
                return False
            else:
                self.post_chat(f'{name}: Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
                file_size = 0
                zip_name = str(f.id_generator())
                self.create_zip_folder(folder_name)
                for file in files:
                    file_size = file_size + file.size
                    url = file.url
                    if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['maxmem']:
                        zip_name = self.single_file_download(url, folder_name)

        if len(os.listdir(self.return_zip_folder(folder_name))) == 0:
            self.printl('No files were downloaded!', "zip_handler")
            self.post_chat(f'{name}: Error creating zip -> No files downloaded. (Use !zip help')
            shutil.rmtree(self.return_zip_folder(folder_name))
            return False
        # zip the file
        self.printl(f'Zipping: {zip_name}.zip', "zip_handler")
        shutil.make_archive(zip_name, 'zip', self.return_zip_folder(folder_name))
        shutil.move(f'{zip_name}.zip', f'{self.return_zip_folder(folder_name)}/{zip_name}.zip')

        # uploading to vola is done here
        if mirror == 'vola':
            upload_path = f'{self.return_zip_folder(folder_name)}/{zip_name}.zip'
            self.printl(f'Uploading to volafile: {zip_name}.zip', "zip_handler")
            self.upload_vola(upload_path)
        # uploading to openload is done here
        if mirror == 'openload' or additional_mirror:
            file_size = 0
            mirror_msg = ''
            for fi in os.listdir(self.return_zip_folder(folder_name)):
                xpath = os.path.join(self.return_zip_folder(folder_name), fi)
                if os.path.isfile(xpath):
                    file_size = file_size + os.path.getsize(xpath)
            if additional_mirror:
                file_size = file_size / 2
            if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['mirrormaxmem']:
                if file_size / self.multiplier <= self.cfg['main']['mirrorziptest']:
                    self.printl(f'Uploading to Openload: {zip_name}.zip', "zip_handler")
                    upload_infos = self.upload_openload(f'{self.return_zip_folder(folder_name)}/{zip_name}.zip')
                    self.printl(str(upload_infos), "zip_handler")
                    mirror_msg = f"{upload_infos['url']}\n"
                    upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{upload_infos['name']}_mirror.txt"
                    if not additional_mirror:
                        self.post_chat(f"{name}: {upload_infos['name']} is uploaded to -> {upload_infos['url']}")
                    if os.path.isfile(upload_path):
                        upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{upload_infos['name']}_mirror_{str(f.id_generator())}.txt"
                    fl = open(upload_path, "w+")
                    fl.write(f"{mirror_msg} \nRequested by {name}")
                    fl.close()
                    # upload the mirror log  to the room
                    self.upload_vola(upload_path)
                else:
                    if self.cfg['rooms'][self.room_select]['anonfile']:
                        # upload to anonfile: !ATTENTION: unstable
                        self.printl(f"Uploading to anonfiles: {zip_name}.zip", "zip_handler")
                        upload_infos = f.anonfile_upload(f'{self.return_zip_folder(folder_name)}/{zip_name}.zip')
                        self.printl(str(upload_infos), "zip_handler")
                        if upload_infos['status'] == 'true':
                            self.post_chat(f"{name}: {upload_infos['data']['file']['metadata']['name']} is uploaded to -> {upload_infos['data']['file']['url']['full']}")
                        else:
                            self.post_chat(f"{name}: Error uploading to anonfiles -> {upload_infos['error']['message']}")
                    else:
                        zip_path = f'{self.return_zip_folder(folder_name)}/{zip_name}.zip'
                        path_split = zip_path.split('/')
                        file_name_split = str(path_split[-1])

                        self.printl(f'Splitting zip: {zip_name}.zip', "zip_handler")
                        newpath = f'{self.return_zip_folder(folder_name)}/mir'
                        try:
                            if not os.path.exists(newpath):
                                os.makedirs(newpath)
                                self.printl(f"Created directory: {newpath}", "zip_handler")
                                newpath = f"{newpath}/"
                        except OSError:
                            self.printl(f"Error: Creating directory {newpath}", "zip_handler")
                        shutil.move(zip_path, newpath + file_name_split)
                        self.file_split(newpath + file_name_split,
                                        self.cfg['main']['mirrorzipmax'] * self.multiplier)
                        shutil.move(newpath + file_name_split, zip_path)
                        retmsg = f"{name}: {file_name_split.replace('%20', '_')} is uploaded to ->"
                        i = 1
                        for fi in os.listdir(newpath):
                            testmsg = retmsg
                            xpath = os.path.join(newpath, fi)
                            upload_infos = self.upload_openload(xpath)
                            testmsg = f"{testmsg} {upload_infos['url']}"
                            mirror_msg = f"{mirror_msg}{upload_infos['url']} \n"
                            if len(testmsg) < (295 * i):
                                retmsg = testmsg
                            else:
                                retmsg = f"{retmsg}\n {upload_infos['url']}"

                                i = i + 1
                        if not additional_mirror:
                            self.post_chat(retmsg)
                        upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{file_name_split.replace('%20', '_')}_mirror.txt"
                        if os.path.isfile(upload_path):
                            upload_path = f"{self.cfg['os'][self.platform]['mirrorlogs']}{file_name_split.replace('%20', '_')}_mirror_{str(f.id_generator())}.txt"
                        fl = open(upload_path, "w+")
                        fl.write(f"{mirror_msg} \nRequested by {name} # You need to download all of the links to have a complete file.")
                        fl.close()
                        self.upload_vola(upload_path)

            else:
                self.post_chat(f"{name}: File too big to mirror. -> > {str(self.cfg['rooms'][self.room_select]['mirrormaxmem'])}")

        if self.keep_files:
            shutil.move(f'{self.return_zip_folder(folder_name)}/{zip_name}.zip',
                        f'{self.return_archive_folder()}/{zip_name}.zip')
        shutil.rmtree(self.return_zip_folder(folder_name))

        return True

    def upload_vola(self, upload_path, room=None):
        """Uploads a file to vola, currently user/passwd are not needed"""
        if not room:
            room = self.interact
        return room.upload_file(upload_path)

    def post_chat(self, message, room=None):
        """Posts a chat message to the connected room"""
        if not room:
            room = self.interact
        if self.msg_redirect:
            room = self.admin
        if not self.muted:
            try:
                room.post_chat(message)
                self.printl(f"Sending message: {message}", "post_chat")
            except OSError:
                self.printl("Message could not be sent - OSError", "post_chat")
        else:
            self.printl(f"Muted: {message}", "post_chat")

    def file_split(self, file, max_size):
        """Splits a zip file"""
        chapters = 1
        ugly_buf = ''
        with open(file, 'rb') as src:
            while True:
                tgt = open(file + '.%03d' % chapters, 'wb')
                written = 0
                while written < max_size:
                    if len(ugly_buf) > 0:
                        tgt.write(ugly_buf)
                    tgt.write(src.read(min(self.cfg['os'][self.platform]['membuff'] * self.multiplier,
                                           self.cfg['main']['mirrorzipmax'] * self.multiplier - written)))
                    written += min(self.cfg['os'][self.platform]['membuff'] * self.multiplier,
                                   self.cfg['main']['mirrorzipmax'] * self.multiplier - written)
                    ugly_buf = src.read(1)
                    if len(ugly_buf) == 0:
                        break
                tgt.close()
                if len(ugly_buf) == 0:
                    break
                chapters += 1

    def single_file_download(self, url, folder_name, mirror=False):
        """Downloads a single file from vola"""
        download_url = url.replace(" ", "")
        if os.path.exists(self.return_zip_folder(folder_name)):
            path = f'{self.return_zip_folder(folder_name)}/'
        else:
            path = self.create_zip_folder(folder_name)
        url_split = download_url.split('/')
        file_split = str(url_split[-1]).split('.')
        file_split_length = len(file_split[-1]) + 1
        download_path = f"{path}{str(url_split[-1][0:-file_split_length])}.{str(file_split[-1])}"
        if os.path.isfile(download_path):
            download_path = f"{path}{str(url_split[-1][0:-file_split_length])}-{f.id_generator()}.{str(file_split[-1])}"
        self.printl(f'[] Downloading: {download_path} - {download_url}', "single_file_download")
        self.download_file(download_url, download_path)
        if mirror:
            return str(download_path)
        else:
            return str(file_split[0])

    def handle_downloads(self, folder_name, uploader_name='*', file_name='*', file_type='*', number_of_files=-1, offset=0, rename=False):
        """Checks the files in the room along the set criteria in a !zip command"""
        if os.path.exists(self.return_zip_folder(folder_name)):
            self.printl('Folder Exists Already', "handle_downloads")
            path = f'{self.return_zip_folder(folder_name)}/'
        else:
            path = self.create_zip_folder(folder_name)
        files = self.listen.files
        i = 1
        j = 1
        file_size = 0
        for file in reversed(files):
            download_url = file.url
            user = file.uploader
            size = file.size
            file_name_full = file.name
            ending = file_name_full.rpartition('.')[-1]
            file_name_short = file_name_full.rpartition('.')[0]
            if uploader_name == '*' or uploader_name == str(user):
                if file_type == '*' or file_type == str(ending).lower():
                    if file_name == '*' or (file_name.lower() in file_name_short.lower()):
                        if i <= number_of_files or number_of_files == -1:
                            if j > offset or offset == 0:
                                file_size = file_size + size
                                if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['maxmem']:
                                    if rename:
                                        file_name_short = f'{str(rename)}-{str(i)}'
                                    download_path = f'{path}{file_name_short}.{ending}'
                                    if os.path.isfile(download_path):
                                        download_path = f'{path}{file_name_short}-{f.id_generator()}.{ending}'
                                    self.printl(f'[{str(i)}] Downloading: {download_path} - {download_url}', "handle_downloads")
                                    self.download_file(download_url, download_path)
                                i = i + 1
                            j = j + 1

    def download_file(self, url, file_name=None):
        """ Downloads a file from volafile and shows a progress bar """
        chunk_size = 1024
        try:
            r = requests.get(url, stream=True, headers=self.headers, cookies=self.cookies)
            r.raise_for_status()
            if not r:
                return False
            total_size = int(r.headers.get("content-length", 0))
            with open(f"{file_name}.part", "wb") as fl:
                for data in tqdm(iterable=r.iter_content(chunk_size=chunk_size), total=total_size / chunk_size, unit="KB", unit_scale=True):
                    fl.write(data)
            # Remove the ".part" from the file name
            os.rename(f"{file_name}.part", file_name)
            return True
        except Exception as ex:
            print(f"[-] Error: {str(ex)}")
            return False

    def zip_help(self, user):
        """Modifies and uploads a ziphelp.txt or links to an existing one"""
        self.printl(f"{user} -> requesting zip_help", "zip_help")
        global help_file
        if help_file == "" or not (self.file_in_room(help_file)):
            tpath = f"{self.return_log_folder(self.room)}/ziphelp-{self.room}.txt"
            if os.path.isfile(tpath):
                os.remove(tpath)
            shutil.copyfile(f"{self.execution_path}/ziphelp.txt", tpath)
            fl = open(tpath, "a")
            msg = "\n# 3 Allowed zippers in this channel #\n"
            for name in self.cfg['rooms'][self.room_select]['allowedzippers']:
                msg = f"{msg}{str(name).replace('*', '')}, "
            msg = msg[:-2]
            msg = f"{msg}\n\n# 4 Bot admins in this channel #\n"
            for name in self.cfg['rooms'][self.room_select]['botadmins']:
                msg = f"{msg}{str(name).replace('*', '')}, "
            msg = msg[:-2]
            fl.write(msg)
            fl.close()
            if self.admin:
                fileid = self.upload_vola(tpath, self.admin)
            else:
                fileid = self.upload_vola(tpath)
            help_file = fileid
            os.remove(tpath)
            time.sleep(2)
        self.post_chat(f"{user}: -> @{str(help_file)}")

    def file_in_room(self, fileid):
        """Checks if a fileid is in the current room"""
        found = False
        file_list = self.listen.files
        for data in reversed(file_list):
            if data.fid == fileid:
                found = True
        return found

    def kill(self, user):
        """Reaction to !kill, kills the whole bot"""
        self.printl(f"{user} -> killing bots in room: {str(self)}", "kill")
        self.alive = False
        try:
            self.post_chat(f"{user}: Thats it, i'm out!")
        except OSError:
            self.printl("Message could not be sent - OSError", "kill")
        time.sleep(2)
        if self.listen:
            self.listen.close()
            self.listen = None
        if self.interact:
            self.interact.close()
            self.interact = None
        if self.admin:
            self.admin.close()
            self.admin = None
        global kill
        kill = True
        return True

    def close(self):
        """only closes the current session, afterwards the bot reconnects"""
        if not self.close_status:
            return False
        self.close_status = False
        self.printl(f"Closing current instance: {str(self)}", "close")
        self.alive = False
        if self.listen:
            self.listen.close()
            self.listen = None
        if self.interact:
            self.interact.close()
            self.interact = None
        if self.admin:
            self.admin.close()
            self.admin = None
        return True

    def printl(self, message, method='NONE'):
        """Log Function"""
        now = datetime.now()
        dt = now.strftime("%Y-%m-%d--%H:%M:%S")
        msg = f'\n[{str(dt)}][{str(method)}] {str(message)}'
        path = f'{self.return_log_folder(self.room)}/{self.session}.txt'
        fl = open(path, "a")
        print(msg)
        fl.write(unidecode(msg))
        fl.close()

    def create_session_file(self):
        """Creates the current log"""
        if not (os.path.exists(self.return_log_folder(self.room))):
            self.create_log_folder(self.room)
        path = f'{self.return_log_folder(self.room)}/{self.session}.txt'

        if not os.path.isfile(path):
            fl = open(path, "w+")
            fl.write(f'Logging for {self.session}:\n')
            fl.close()
            self.printl("Session File Created", "create_session_file")
            return True
        else:
            return False

    def listen_room(self):
        """Creates a Room instance that does only listens to chat."""
        if self.room_password:
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'], password=self.room_password)
        elif self.room_key:
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'], key=self.room_key)
        else:
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'])
        self.printl("Listening room created", "listen_room")

        return r

    def interact_room(self):
        """Creates a Room instance that does not listen to chat, but is used to operate with the room for uploads or messages."""

        if self.room_password:
            r = Room(name=self.room, user=self.cfg['main']['dluser'], password=self.room_password)
        elif self.room_key:
            r = Room(name=self.room, user=self.cfg['main']['dluser'], key=self.room_key)
        else:
            r = Room(name=self.room, user=self.cfg['main']['dluser'])

        time.sleep(1)
        if r.user.login(self.cfg['main']['dlpass']):
            self.printl(f"Logged in as: {self.cfg['main']['dluser']}", "interact_room")
        else:
            self.printl("Login failed!", "interact_room")

        if not self.logged_in:

            time.sleep(1)
            cookie_jar = r.conn.cookies
            cookies_dict = {}
            for cookie in cookie_jar:
                if "volafile" in cookie.domain:
                    cookies_dict[cookie.name] = cookie.value
                    self.logged_in = True
            self.cookies = {**self.cookies, **cookies_dict}
            # self.printl(f"Download session cookie: {str(self.cookies)}", "interact_room")

        if not (self.cfg['main']['dluser'] == self.cfg['main']['zipbotuser']):

            r.user.logout()
            time.sleep(2)
            r.user.change_nick(self.cfg['main']['zipbotuser'])
            time.sleep(1)

            if r.user.login(self.cfg['main']['zipbotpass']):
                self.printl(f"Logged in as: {self.cfg['main']['zipbotuser']}", "interact_room")
            else:
                self.printl("Login failed!", "interact_room")

        return r

    def admin_room(self):
        """Creates a Room instance of the admin room"""
        if not (self.admin_room_password == ""):
            r = Room(name=self.admin_room_string, user=f'{self.room}{self.session_id[0:3]}', password=self.admin_room_password)
        else:
            r = Room(name=self.admin_room_string, user=f'{self.room}{self.session_id[0:3]}')
        self.printl("Admin room created", "admin_room")

        return r

    def super_admin_check(self, user, registered=False):
        """Checks whether the user is the admin account of the bot"""
        return registered and user.replace("*", "") == self.admin_user.replace("*", "")

    def admin_check(self, user, registered=False, owner=False, janitor=False, purple=False):
        """Checks whether the user is a botadmin in the current room"""
        if registered:
            name = f"*{user}"
        else:
            name = user
        if (name in self.cfg['rooms'][self.room_select]['botadmins']) or (
                '+all' in self.cfg['rooms'][self.room_select]['botadmins']) or owner or (
                '+registered' in self.cfg['rooms'][self.room_select]['botadmins'] and registered) or (
                '+janitor' in self.cfg['rooms'][self.room_select]['botadmins'] and janitor) or purple or (
                self.super_admin_check(user, registered)):
            self.printl(f"{user} was accepted!", "admin_check")
            return True
        else:
            self.printl(f"{user} was denied!", "admin_check")
            self.post_chat(f"{user}: Who even are you? (user denied - use !zip help)")
            return False

    def user_admin_check(self, user, registered, owner):
        """Checks whether the user is allowed to modify the admin_config in the current room
        -> allowed for room_owner and self.admin_user"""

        if owner or self.super_admin_check(user, registered):
            self.printl(f"{user} was accepted!", "user_admin_check")
            return True
        else:
            self.printl(f"{user} was denied!", "user_admin_check")
            self.post_chat(f"{user}: Who even are you? (user denied - only allowed for room owner and the bot hoster)")
            return False

    def zip_check(self, user, registered=False, owner=False, janitor=False, purple=False):
        """Checks whether the user is allowed to zip in the current room"""
        if registered:
            name = f"*{user}"
        else:
            name = user
        if (name in self.cfg['rooms'][self.room_select]['allowedzippers']) or (
                '+all' in self.cfg['rooms'][self.room_select]['allowedzippers']) or owner or (
                '+registered' in self.cfg['rooms'][self.room_select]['allowedzippers'] and registered) or (
                '+janitor' in self.cfg['rooms'][self.room_select]['allowedzippers'] and janitor) or purple or (
                self.super_admin_check(user, registered)):
            self.printl(f"{user} was accepted!", "zip_check")
            return True
        else:
            self.printl(f"{user} was denied!", "zip_check")
            self.post_chat(f"{user}: Who even are you? (user denied - use !zip help)")
            return False

    class MyOpenLoad(OpenLoad):
        def upload_large_file(self, file_path, **kwargs):
            """Method that uses Multipartencoder to upload large files without running out of memory"""
            response = self.upload_link(**kwargs)
            upload_url = response['url']

            _, file_name = os.path.split(file_path)

            with open(file_path, 'rb') as upload_file:
                data = encoder.MultipartEncoder({
                    "files": (file_name, upload_file, "application/octet-stream"),
                })

                headers = {"Prefer": "respond-async", "Content-Type": data.content_type}
                response_json = requests.post(upload_url, headers=headers, data=data).json()

            self._check_status(response_json)
            return response_json['result']

    def upload_openload(self, path):
        """Method to upload files to openload"""
        o1 = self.MyOpenLoad(self.cfg['main']['opus'], self.cfg['main']['oppw'])
        info = o1.upload_large_file(path)
        return info

    # FOLDER FUNCTIONS
    def return_log_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['logfolder'] + folder_name
        return path

    def create_log_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['logfolder'] + folder_name

        try:
            if not os.path.exists(path):
                os.makedirs(path)
                self.printl(f'Created directory: {path}', 'create_log_folder')
                return str(f'{path}/')
        except OSError:
            print(f'Error: Creating directory {path}')
            return 'Error'

    def return_zip_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['zipfolder'] + folder_name
        return path

    def create_zip_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['zipfolder'] + folder_name
        try:
            if not os.path.exists(path):
                os.makedirs(path)
                self.printl(f'Created directory: {path}', 'create_zip_folder')
                return str(f'{path}/')
        except OSError:
            print(f'Error: Creating directory {path}')
            return 'Error'

    def return_archive_folder(self):
        path = self.cfg['os'][self.platform]['archfolder']
        return path


def parse_args():
    """Parses user arguments"""
    parser = argparse.ArgumentParser(
        description="Crappy VolaZipBot",
        epilog="Pretty meh"
    )
    parser.add_argument('--room', '-r', dest='room', type=str, required=True,
                        help='Room name, as in https://volafile.org/r/ROOMNAME -> [ROOMNAME]')
    parser.add_argument('--zipper', '-z', dest='zipper', type=str,
                        default="False",
                        help='You want to have functions, or you want to just read chat -> [True/False]')
    parser.add_argument('--passwd', '-p', dest='passwd', type=str,
                        default="",
                        help='Room password to enter the room -> [PASSWD]')

    return parser.parse_args()


def main():
    """Main method"""
    global kill
    args = parse_args()
    if args.zipper == "True" or args.zipper == "1":
        zipper = True
    else:
        zipper = False
    lister = [args.room, zipper, args.passwd]
    while not kill:
        v = VolaZipBot(lister)
        v.join_room()


def main_callable(room, zipper=False, password=''):
    """Callable main method with arguments"""
    global kill
    lister = [room, zipper, password]
    while not kill:
        v = VolaZipBot(lister)
        v.join_room()


if __name__ == "__main__":
    main()
