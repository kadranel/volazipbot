import time
from datetime import datetime, timedelta
import os
import json
import shutil
from volapi import Room
import argparse
from unidecode import unidecode
from tqdm import tqdm
import requests
from requests_toolbelt.multipart import encoder
from openload import OpenLoad
import functions as f

help_file = ""
kill = False


class VolaZipBot(object):
    def __init__(self, args):
        # Creating a session and a refresh_time. The bot starts a new session once the refresh_time is reached
        self.session = datetime.now().strftime("[%Y-%m-%d][%H-%M-%S]") + '[' + args[0] + ']' + "[" + f.id_generator() + "]"
        self.refresh_time = datetime.now() + timedelta(days=1)

        # Setting status attributes
        self.alive = True
        self.wake = True
        self.zipper = args[1]
        self.logged_in = False
        self.close_status = True
        self.execution_path = os.path.dirname(os.path.abspath(__file__))

        # Setting room information
        self.url = "https://volafile.org/r/" + args[0]
        self.room = args[0]
        self.multiplier = 1048576

        # Loading the config.json
        json_file = open(self.execution_path + '/config.json', 'r')
        self.cfg = json.load(json_file)
        json_file.close()
        self.cookies = self.cfg['main']['cookies']
        self.headers = self.cfg['main']['headers']
        self.admin = self.cfg['main']['admin']
        self.keep_files = self.cfg['main']['keepfiles']

        # Initialising the room_select and platform -> this is used for navigating in config.json
        if args[0] in self.cfg['rooms'].keys():
            self.room_select = args[0]
        else:
            self.room_select = 'genericroom'
        if os.name in self.cfg['os'].keys():
            self.platform = os.name
        else:
            print("OS {} is not supported.".format(os.name))
            self.alive = False

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
            self.interact = self.interact_room()
            # self.listen = self.listen_room()
            # Not sure yet if two different sockets are better for consistency
            self.listen = self.interact
            self.printl("Session: {}".format(self.session), "__init__")
        except OSError:
            # Catching Socket not available on connect
            self.printl("Failed to connect - trying to reconnect in 60 seconds", "__init__")
            time.sleep(60)
            self.alive = False

    def __repr__(self):
        return "<VolaZipBot(alive={}, zipper={}, listen={}, interact={})>".format(self.alive, self.zipper, str(self.listen),
                                                                                  str(self.interact))

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
                self.printl("{} -> checking for bot: {}".format(m.nick, str(self)), "alive")
                if self.wake:
                    self.post_chat("@{}: chinaman working!".format(m.nick))
                else:
                    self.post_chat("@{}: chinaman is asleep.".format(m.nick))
            # kill the bot in the room: !kill
            elif self.zipper and (str(m.lower()[0:5]) == '!kill') and self.admin_check(m.nick, m.logged_in, m.owner, m.janitor, m.purple):
                self.kill(m.nick)
            # pause/reenable the bot: !sleep/!wake
            elif self.zipper and self.wake and (str(m.lower()[0:6]) == '!sleep') and self.admin_check(m.nick, m.logged_in, m.owner,
                                                                                                      m.janitor, m.purple):
                self.post_chat("@{}: chinaman going to sleep!".format(m.nick))
                self.wake = False
            elif self.zipper and not self.wake and (str(m.lower()[0:5]) == '!wake') and self.admin_check(m.nick, m.logged_in, m.owner,
                                                                                                         m.janitor, m.purple):
                self.post_chat("@{}: chinaman woke up!".format(m.nick))
                self.wake = True
            # switch from zipper = False to zipper = True, enables most functions: !zipbot
            elif not self.zipper and (str(m.lower()[0:7]) == '!zipbot') and self.super_admin_check(m.nick, m.logged_in):
                self.post_chat("@{}: Whuddup!".format(m.nick))
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

        # connection to the python-volapi
        if self.alive:
            try:
                # add the listeners on the volapi room
                self.listen.add_listener("chat", onmessage)
                self.listen.add_listener("time", ontime)
                self.printl("Connecting to room: {}".format(str(self.listen)), "join_room")
                # start listening
                self.listen.listen()
            except OSError:
                self.printl("Socket disconnected, trying to reconnect... - OSError", "join_room")
                self.close()
            return False

    def user_administration(self, name, mode, message):
        """Allows for user administration to add/remove new users into the config.json"""
        json_file = open(self.execution_path + '/config.json', 'r')
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
        command_split = message.split("!zip {} ".format(mode))
        if len(command_split) > 1:
            # add to the config
            if command_split[1][0:4] == "add ":
                name_split = message.split("!zip {} add ".format(mode))
                if len(name_split) > 1:
                    user_name = f.input_replace(name_split[1])
                    if not (user_name == "+all" or user_name == "+registered" or user_name == "+janitor"):
                        user_name = "*" + user_name.replace("+", "")
                    if user_name not in new_cfg["rooms"][room_select][delimiter]:
                        if mode == "admin" and (user_name == "+all" or user_name == "+registered"):
                            self.printl("{} can't be added as admin: {}".format(user_name, mode), "user_administration")
                            self.post_chat('@{}: You can not add {} as admin.'.format(name, user_name))
                            return False
                        new_cfg["rooms"][room_select][delimiter].append(user_name)
                        self.printl("user_name {} was added to the config: {}".format(user_name, mode), "user_administration")
                        self.post_chat('@{}: {} was added to the config.'.format(name, user_name))
                    else:
                        self.printl("user_name already in the config: {}".format(mode), "user_administration")
                        self.post_chat('@{}: {} was already in the config.'.format(name, user_name))
                        return False
                else:
                    self.printl("Message could not be interpreted", "user_administration")
                    self.post_chat('@{}: Your message could not be interpreted.'.format(name))
                    return False
            # remove from the config
            elif command_split[1][0:7] == "remove ":
                name_split = message.split("!zip {} remove ".format(mode))
                if len(name_split) > 1:
                    user_name = f.input_replace(name_split[1])
                    if not (user_name == "+all" or user_name == "+registered" or user_name == "+janitor"):
                        user_name = "*" + user_name.replace("+", "")
                    if user_name in new_cfg["rooms"][room_select][delimiter]:
                        if mode == "admin" and len(new_cfg["rooms"][room_select][delimiter]) == 1:
                            self.printl("The last admin can't be removed: {}".format(mode), "user_administration")
                            self.post_chat('@{}: You can not remove the last admin.'.format(name, user_name))
                            return False
                        new_cfg["rooms"][room_select][delimiter].remove(user_name)
                        self.printl("user_name {} was removed from the config: {}".format(user_name, mode), "user_administration")
                        self.post_chat('@{}: {} was removed from the config.'.format(name, user_name))

                    else:
                        self.printl("user_name not in the config {}".format(mode), "user_administration")
                        self.post_chat('@{}: {} was not in the config.'.format(name, user_name))
                        return False
                else:
                    self.printl("Message could not be interpreted", "user_administration")
                    self.post_chat('@{}: Your message could not be interpreted.'.format(name))
                    return False
            else:
                self.printl("Message could not be interpreted", "user_administration")
                self.post_chat('@{}: Your message could not be interpreted.'.format(name))
                return False
        else:
            self.printl("Message could not be interpreted", "user_administration")
            self.post_chat('@{}: Your message could not be interpreted.'.format(name))
            return False
        # write json back
        json_file = open(self.execution_path + '/config.json', 'w')
        json.dump(new_cfg, json_file)
        json_file.close()
        # enable new config
        self.cfg = new_cfg
        self.room_select = room_select
        return True

    def create_new_config_entry(self, cfg):
        """Creates new config entry for current room"""
        self.printl("Creating new local config entry for {}:".format(self.room), "create_new_config_entry")
        cfg["rooms"][self.room] = self.cfg["rooms"]["genericroom"].copy()
        return cfg

    def mirror_handler(self, name, message):
        """Grabs files from a room and uplpoads them to openload"""
        self.printl("{} -> requested mirror".format(name), "mirror_handler")

        # generate a folder name
        folder_name = f.id_generator()
        message_split = str(message).split('@')
        mirror_msg = ""

        # look if the file is in the room
        file_info, url, file_size, file_checked = self.file_check(name, str(message_split[1]).replace(" ", ""))
        if not file_info:
            self.post_chat('@{}: Your Message could not be interpreted correctly. (use !zip help)'.format(name))
            return False

        # this checks whether the file is lower than the maximum mirror file size allowed in cfg
        if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['mirrormaxmem']:

            self.post_chat('@{}: Starting to mirror.'.format(name))
            time.sleep(1)
            # Downloading the file here while getting the filepath back
            zip_path = self.single_file_download(url, folder_name, True)
            # Checking if file is bigger then 995 mb since openload does not allow files > 1gb
            if file_size / self.multiplier <= self.cfg['main']['mirrorziptest']:
                self.printl('Uploading to Openload: {}'.format(zip_path), "mirrorhandler")
                # Uploading the file to openload
                upload_infos = self.upload_openload(zip_path)
                self.printl(str(upload_infos), "mirrorhandler")
                mirror_msg = upload_infos['url'] + "\n"
                upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + upload_infos['name'] + '_mirror.txt'
                # return message to chat
                self.post_chat('@{}: {} is uploaded to -> {}'.format(name, upload_infos['name'], upload_infos['url']))
                if os.path.isfile(upload_path):
                    upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + upload_infos['name'] + '_mirror_' + str(
                        f.id_generator()) + '.txt'
                fl = open(upload_path, "w+")
                fl.write(mirror_msg + ' \n' + file_checked)
                fl.close()
                self.upload_vola(upload_path)
            else:
                # file is > 1gb -> needs to be converted to zip and split before uploading
                self.printl('Checking if zip: {}'.format(zip_path), "mirrorhandler")
                path_split = zip_path.split('/')
                file_name_split = str(path_split[-1])
                endsplit = file_name_split.split('.')
                ending = str(endsplit[-1])
                if ending != 'zip':
                    # making a zip
                    zip_name = file_name_split
                    shutil.make_archive(zip_name, 'zip', self.return_zip_folder(folder_name))
                    os.remove(self.return_zip_folder(folder_name) + '/' + zip_name)
                    shutil.move(zip_name + '.zip', self.return_zip_folder(folder_name) + '/' + zip_name + '.zip')
                    zip_path = self.return_zip_folder(folder_name) + '/' + zip_name + '.zip'

                # splitting the zip with file_split
                self.printl('Splitting zip: ' + zip_path, "mirrorhandler")
                self.file_split(zip_path, self.cfg['main']['mirrorzipmax'] * self.multiplier)
                shutil.move(zip_path, self.cfg['os'][self.platform]['mirrorfolder'] + file_name_split)

                for fi in os.listdir(self.return_zip_folder(folder_name)):
                    xpath = os.path.join(self.return_zip_folder(folder_name), fi)
                    self.printl('Uploading to openload: ' + xpath, "mirrorhandler")
                    upload_infos = self.upload_openload(xpath)
                    # putting together the message with file links
                    mirror_msg = mirror_msg + upload_infos['url'] + " \n"

                # creating the _mirror.txt here
                upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + file_name_split + '_mirror.txt'
                if os.path.isfile(upload_path):
                    upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + file_name_split + '_mirror_' + str(
                        f.id_generator()) + '.txt'
                fl = open(upload_path, "w+")
                fl.write(mirror_msg + ' \n' + file_checked)
                fl.close()
                file_id = self.upload_vola(upload_path)
                retmsg = '@{}: {} is uploaded to -> @{}'.format(name, file_name_split, file_id)
                time.sleep(2)
                self.post_chat(retmsg)

            # cleanup
            path_split = zip_path.split('/')
            file_name_split = str(path_split[-1])
            if os.path.isfile(zip_path) and self.keep_files:
                shutil.move(zip_path, self.cfg['os'][self.platform]['mirrorfolder'] + file_name_split)
            shutil.rmtree(self.return_zip_folder(folder_name))
        else:
            self.post_chat('@{}: The file @{} is too big to mirror. -> > {} MB'.format(name, str(message_split[1].replace(" ", "")), str(
                self.cfg['rooms'][self.room_select]['mirrormaxmem'])))

    def file_check(self, name, file_id):
        """Returns fileinfo for the _mirror.txt"""
        # get file_info from volapi
        file_info = self.interact.fileinfo(file_id)
        if file_info:
            file_uploader = str(file_info['user'])
            file_size = file_info['size']
            requester = str(name)
            file_size_string = "{0:.2f}".format(file_size / self.multiplier) + " MB"
            url = 'https://volafile.org/get/{}/{}'.format(file_info['id'], file_info['name'])
            file_checked = "You need to download all of the links for a complete file # Size: {} # Uploader: {} # Requested by: {}".format(
                file_size_string, file_uploader, requester)
            # return as tuple
            return file_info, url, file_size, file_checked
        else:
            return False, "", 0, ""

    def count_handler(self, name, message, files):
        """Counts file positions in the current room"""
        self.printl("{} -> requested count".format(name), "count_handler")
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
                        self.post_chat(
                            '@{}: {} - > count in room: {} - count for {}: {}'.format(name, file_name, str(full_count), uploader,
                                                                                      str(user_count)))
                else:
                    self.post_chat('@{}: The file @{} was not found in the room.'.format(name, str(message_split[i].replace(" ", ""))))

        else:
            self.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
            return False

    def zip_handler(self, name, message, mirror='vola', files=None):
        """Downloads files, zips them, uploads them back to volafile and possibly other mirrorsites"""
        self.printl("{} -> requested zip with: '{}'".format(name, message), "zip_handler")
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
                self.post_chat(
                    '@' + name + ': Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
            if mirror == 'openload':
                self.post_chat(
                    '@' + name + ': Downloading and mirroring initiated. No other requests will be handled until the upload is finished.')
            if rename:
                rename = zip_name
            self.handle_downloads(folder_name, upl, file_name, file_type, number_of_files, offset, rename)

        else:
            # mostly not used: !zip with drag and drop, no further features like mirror or rename
            if not files or len(files) < 2:
                self.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
                return False
            else:
                self.post_chat(
                    '@' + name + ': Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
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
            self.post_chat('@' + name + ': Error creating zip -> No files downloaded. (Use !zip help')
            shutil.rmtree(self.return_zip_folder(folder_name))
            return False
        # zip the file
        self.printl('Zipping: ' + zip_name + '.zip', "zip_handler")
        shutil.make_archive(zip_name, 'zip', self.return_zip_folder(folder_name))
        shutil.move(zip_name + '.zip', self.return_zip_folder(folder_name) + '/' + zip_name + '.zip')

        # uploading to vola is done here
        if mirror == 'vola':
            upload_path = self.return_zip_folder(folder_name) + '/' + zip_name + '.zip'
            self.printl('Uploading to volafile: ' + zip_name + '.zip', "zip_handler")
            self.upload_vola(upload_path)
        # uploading to openload is done here
        if mirror == 'openload' or additional_mirror:
            file_size = 0
            mirror_msg = ''
            for fi in os.listdir(self.return_zip_folder(folder_name)):
                xpath = os.path.join(self.return_zip_folder(folder_name), fi)
                if os.path.isfile(xpath):
                    file_size = file_size + os.path.getsize(xpath)
            if file_size / self.multiplier <= self.cfg['rooms'][self.room_select]['mirrormaxmem']:
                if file_size / self.multiplier <= self.cfg['main']['mirrorziptest']:
                    self.printl('Uploading to Openload: ' + zip_name + '.zip', "zip_handler")
                    upload_infos = self.upload_openload(self.return_zip_folder(folder_name) + '/' + zip_name + '.zip')
                    self.printl(str(upload_infos), "zip_handler")
                    mirror_msg = upload_infos['url'] + "\n"
                    upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + upload_infos['name'] + '_mirror.txt'
                    if not additional_mirror:
                        self.post_chat('@' + name + ': ' + upload_infos['name'] + ' is uploaded to -> ' + upload_infos['url'])
                    if os.path.isfile(upload_path):
                        upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + upload_infos['name'] + '_mirror_' + str(
                            f.id_generator()) + '.txt'
                    fl = open(upload_path, "w+")
                    fl.write(mirror_msg + ' \n' + 'Requested by ' + name)
                    fl.close()
                    # upload the mirror log  to the room
                    self.upload_vola(upload_path)
                else:
                    if self.cfg['rooms'][self.room_select]['anonfile']:
                        # upload to anonfile: !ATTENTION: unstable
                        self.printl('Uploading to anonfiles: ' + zip_name + '.zip', "zip_handler")
                        upload_infos = f.anonfile_upload(self.return_zip_folder(folder_name) + '/' + zip_name + '.zip')
                        self.printl(str(upload_infos), "zip_handler")
                        if upload_infos['status'] == 'true':
                            self.post_chat('@' + name + ': ' +
                                           upload_infos['data']['file']['metadata']['name'] + ' is uploaded to -> ' +
                                           upload_infos['data']['file']['url']['full'])
                        else:
                            self.post_chat('@' + name + ': Error uploading to anonfiles -> ' +
                                           upload_infos['error']['message'])
                    else:
                        zip_path = self.return_zip_folder(folder_name) + '/' + zip_name + '.zip'
                        path_split = zip_path.split('/')
                        file_name_split = str(path_split[-1])

                        self.printl('Splitting zip: ' + zip_name + '.zip', "zip_handler")
                        newpath = self.return_zip_folder(folder_name) + '/mir'
                        try:
                            if not os.path.exists(newpath):
                                os.makedirs(newpath)
                                self.printl('Created directory: ' + newpath, "zip_handler")
                                newpath = newpath + '/'
                        except OSError:
                            self.printl('Error: Creating directory. ' + newpath, "zip_handler")
                        shutil.move(zip_path, newpath + file_name_split)
                        self.file_split(newpath + file_name_split,
                                        self.cfg['main']['mirrorzipmax'] * self.multiplier)
                        shutil.move(newpath + file_name_split, zip_path)
                        retmsg = '@' + name + ': ' + file_name_split.replace('%20', '_') + ' is uploaded to ->'
                        i = 1
                        for fi in os.listdir(newpath):
                            testmsg = retmsg
                            xpath = os.path.join(newpath, fi)
                            upload_infos = self.upload_openload(xpath)
                            testmsg = testmsg + ' ' + upload_infos['url']
                            mirror_msg = mirror_msg + upload_infos['url'] + " \n"
                            if len(testmsg) < (295 * i):
                                retmsg = testmsg
                            else:
                                retmsg = retmsg + '\n' + ' ' + upload_infos['url']

                                i = i + 1
                        if not additional_mirror:
                            self.post_chat(retmsg)
                        upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + file_name_split.replace('%20', '_') + '_mirror.txt'
                        if os.path.isfile(upload_path):
                            upload_path = self.cfg['os'][self.platform]['mirrorlogs'] + file_name_split.replace('%20',
                                                                                                                '_') + '_mirror_' + str(
                                f.id_generator()) + '.txt'
                        fl = open(upload_path, "w+")
                        fl.write(
                            mirror_msg + ' \nRequested by {} # You need to download all of the links to have a complete file.'.format(name))
                        fl.close()
                        self.upload_vola(upload_path)

            else:
                self.post_chat('@' + name + ': File too big to mirror. -> > ' + str(self.cfg['rooms'][self.room_select]['mirrormaxmem']))

        if self.keep_files:
            shutil.move(self.return_zip_folder(folder_name) + '/' + zip_name + '.zip',
                        self.return_archive_folder() + '/' + zip_name + '.zip')
        shutil.rmtree(self.return_zip_folder(folder_name))

        return True

    def upload_vola(self, upload_path, room=False):
        """Uploads a file to vola, currently user/passwd are not needed"""
        if not room:
            room = self.interact
        return room.upload_file(upload_path)

    def post_chat(self, message, room=False):
        """Posts a chat message to the connected room"""
        if not room:
            room = self.interact
        try:
            room.post_chat(message)
            self.printl("Sending message: {}".format(message), "post_chat")
        except OSError:
            self.printl("Message could not be sent - OSError", "post_chat")

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
            path = self.return_zip_folder(folder_name) + '/'
        else:
            path = self.create_zip_folder(folder_name)
        url_split = download_url.split('/')
        file_split = str(url_split[-1]).split('.')
        download_path = path + str(file_split[0]) + '.' + str(file_split[-1])
        if os.path.isfile(download_path):
            download_path = path + str(file_split[0]) + "-" + f.id_generator() + '.' + str(file_split[-1])
        self.printl('[] Downloading: ' + download_path + ' - ' + download_url, "single_file_download")
        self.download_file(download_url, download_path)
        if mirror:
            return str(download_path)
        else:
            return str(file_split[0])

    def handle_downloads(self, folder_name, uploader_name='*', file_name='*', file_type='*', number_of_files=-1, offset=0, rename=False):
        """Checks the files in the room along the set criteria in a !zip command"""
        if os.path.exists(self.return_zip_folder(folder_name)):
            self.printl('Folder Exists Already', "handle_downloads")
            path = self.return_zip_folder(folder_name) + '/'
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
                                        file_name_short = str(rename) + '-' + str(i)
                                    download_path = path + file_name_short + '.' + ending
                                    if os.path.isfile(download_path):
                                        download_path = path + file_name_short + "-" + f.id_generator() + '.' + ending
                                    self.printl('[' + str(i) + '] Downloading: ' + download_path + ' - ' + download_url, "handle_downloads")
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
            with open(file_name + ".part", "wb") as fl:
                for data in tqdm(iterable=r.iter_content(chunk_size=chunk_size), total=total_size / chunk_size, unit="KB", unit_scale=True):
                    fl.write(data)
            # Remove the ".part" from the file name
            os.rename(file_name + ".part", file_name)
            return True
        except Exception as ex:
            print("[-] Error: " + str(ex))
            return False

    def zip_help(self, user):
        """Modifies and uploads a ziphelp.txt or links to an existing one"""
        self.printl(user + " -> requesting zip_help", "zip_help")
        global help_file
        if help_file == "" or not (self.file_in_room(help_file)):
            tpath = self.return_log_folder(self.room) + "/ziphelp-" + self.room + ".txt"
            if os.path.isfile(tpath):
                os.remove(tpath)
            shutil.copyfile(self.execution_path + '/ziphelp.txt', tpath)
            fl = open(tpath, "a")
            msg = "\n# 3 Allowed zippers in this channel #\n"
            for name in self.cfg['rooms'][self.room_select]['allowedzippers']:
                msg = msg + str(name).replace("*", "") + ", "
            msg = msg[:-2]
            msg = msg + "\n\n# 4 Bot admins in this channel #\n"
            for name in self.cfg['rooms'][self.room_select]['botadmins']:
                msg = msg + str(name).replace("*", "") + ", "
            msg = msg[:-2]
            fl.write(msg)
            fl.close()
            fileid = self.upload_vola(tpath)
            help_file = fileid
            os.remove(tpath)
            time.sleep(2)
        self.post_chat("@{}: -> @{}".format(user, str(help_file)))

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
        self.printl(user + " -> killing bots in room: " + str(self), "kill")
        self.alive = False
        try:
            self.interact.post_chat("@{}: Thats it, i'm out!".format(user))
        except OSError:
            self.printl("message could not be sent - OSError", "kill")
        time.sleep(1)
        self.listen.close()
        self.listen = None
        self.interact.close()
        self.interact = None
        del self.cfg
        global kill
        kill = True
        return True

    def close(self):
        """only closes the current session, afterwards the bot reconnects"""
        if not self.close_status:
            return False
        self.close_status = False
        self.printl("Closing current instance: " + str(self), "close")
        self.alive = False
        self.listen.close()
        self.listen = None
        self.interact.close()
        self.interact = None
        del self.cfg
        return True

    def printl(self, message, method='NONE'):
        """Log Function"""
        now = datetime.now()
        dt = now.strftime("%Y-%m-%d--%H:%M:%S")
        msg = '\n[' + str(dt) + '][' + str(method) + '] ' + str(message)
        path = self.return_log_folder(self.room) + '/' + self.session + '.txt'
        fl = open(path, "a")
        print(msg)
        fl.write(unidecode(msg))
        fl.close()

    def create_session_file(self):
        if not (os.path.exists(self.return_log_folder(self.room))):
            self.create_log_folder(self.room)
        path = self.return_log_folder(self.room) + '/' + self.session + '.txt'

        if not os.path.isfile(path):
            fl = open(path, "w+")
            fl.write('Logging for ' + self.session + ':\n')
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
            self.printl("Logged in as: " + self.cfg['main']['dluser'], "interact_room")
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
            self.printl("Download session cookie: " + str(self.cookies), "interact_room")

        if not (self.cfg['main']['dluser'] == self.cfg['main']['zipbotuser']):

            r.user.logout()
            time.sleep(2)
            r.user.change_nick(self.cfg['main']['zipbotuser'])
            time.sleep(1)

            if r.user.login(self.cfg['main']['zipbotpass']):
                self.printl("Logged in as: " + self.cfg['main']['zipbotuser'], "interact_room")
            else:
                self.printl("Login failed!", "interact_room")

        return r

    def super_admin_check(self, user, registered=False):
        """Checks whether the user is the admin account of the bot"""
        return registered and user.replace("*", "") == self.admin.replace("*", "")

    def admin_check(self, user, registered=False, owner=False, janitor=False, purple=False):
        """Checks whether the user is a botadmin in the current room"""
        if registered:
            name = "*" + user
        else:
            name = user
        if (name in self.cfg['rooms'][self.room_select]['botadmins']) or (
                '+all' in self.cfg['rooms'][self.room_select]['botadmins']) or owner or (
                '+registered' in self.cfg['rooms'][self.room_select]['botadmins'] and registered) or (
                '+janitor' in self.cfg['rooms'][self.room_select]['botadmins'] and janitor) or purple or (
                self.super_admin_check(user, registered)):
            self.printl(user + " was accepted!", "admin_check")
            return True
        else:
            self.printl(user + " was denied!", "admin_check")
            self.post_chat("@{}: Who even are you? (user denied - use !zip help)".format(user))
            return False

    def user_admin_check(self, user, registered, owner):
        """Checks whether the user is allowed to modify the admin_config in the current room
        -> allowed for room_owner and self.admin"""

        if owner or self.super_admin_check(user, registered):
            self.printl(user + " was accepted!", "user_admin_check")
            return True
        else:
            self.printl(user + " was denied!", "user_admin_check")
            self.post_chat("@{}: Who even are you? (user denied - only allowed for room owner and the bot hoster)".format(user))
            return False

    def zip_check(self, user, registered=False, owner=False, janitor=False, purple=False):
        """Checks whether the user is allowed to zip in the current room"""
        if registered:
            name = "*" + user
        else:
            name = user
        if (name in self.cfg['rooms'][self.room_select]['allowedzippers']) or (
                '+all' in self.cfg['rooms'][self.room_select]['allowedzippers']) or owner or (
                '+registered' in self.cfg['rooms'][self.room_select]['allowedzippers'] and registered) or (
                '+janitor' in self.cfg['rooms'][self.room_select]['allowedzippers'] and janitor) or purple or (
                self.super_admin_check(user, registered)):
            self.printl(user + " was accepted!", "zip_check")
            return True
        else:
            self.printl(user + " was denied!", "zip_check")
            self.post_chat("@{}: Who even are you? (user denied - use !zip help)".format(user))
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
                self.printl('Created directory: ' + path, 'create_log_folder')
                return str(path + '/')
        except OSError:
            print('Error: Creating directory. ' + path)
            return 'Error'

    def return_zip_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['zipfolder'] + folder_name
        return path

    def create_zip_folder(self, folder_name):
        path = self.cfg['os'][self.platform]['zipfolder'] + folder_name
        try:
            if not os.path.exists(path):
                os.makedirs(path)
                self.printl('Created directory: ' + path, 'create_zip_folder')
                return str(path + '/')
        except OSError:
            print('Error: Creating directory. ' + path)
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
                        default="*",
                        help='Room password to enter the room -> [PASSWD]')

    return parser.parse_args()


def main():
    """Main method"""
    global kill
    args = parse_args()
    if args.zipper == "True":
        zipper = True
    else:
        zipper = False
    lister = [args.room, zipper, args.passwd]
    while not kill:
        v = VolaZipBot(lister)
        v.join_room()


def main_callable(room, zipper=False, password='*'):
    """Callable main method with arguments"""
    global kill
    lister = [room, zipper, password]
    while not kill:
        v = VolaZipBot(lister)
        v.join_room()


if __name__ == "__main__":
    main()
