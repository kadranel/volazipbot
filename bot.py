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

        # Setting status booleans
        self.alive = True
        self.wake = True
        self.zipper = args[1]
        self.loggedin = False

        # Setting room information
        self.URL = "https://volafile.org/r/" + args[0]
        self.room = args[0]

        # Loading the config.json
        self.cfg = json.load(open('config.json', 'r'))
        self.cookies = self.cfg['main']['cookies']
        self.headers = self.cfg['main']['headers']

        # Initialising the roomselect and platform -> this is used for navigating in config.json
        if args[0] in self.cfg['rooms'].keys():
            self.roomselect = args[0]
        else:
            self.roomselect = 'genericroom'
        if os.name in self.cfg['os'].keys():
            self.platform = os.name
        else:
            print("OS {} is not supported.".format(os.name))
            self.alive = False

        # Checking if a room password is set in args
        if len(args) == 3:
            self.roompw = args[2]
        elif len(args) == 2:
            self.roompw = '*'

        # create session file
        self.create_session_file()

        # Connecting to the room via volapi
        try:
            self.interact = self.interact_room()
            self.listen = self.listen_room()
            self.printl("Session: {}".format(self.session), "__init__")
        except OSError:
            self.printl("Failed to connect - trying to reconnect in 60 seconds", "__init__")
            time.sleep(60)
            self.alive = False

    def __repr__(self):
        return "<VolaZipBot(alive={}, zipper={}, listen={}, interact={})>".format(self.alive, self.zipper, str(self.listen), str(self.interact))

    def joinroom(self):
        """Adds the listener to the room."""

        def onmessage(m):
            """Print the new message and respond to user input"""
            self.printl(f.msg_formatter(m), "onmessage/main")

            # Commands for the bot are evaluated here
            if self.zipper and self.wake and (str(m.lower()[0:9]) == '!zip help' or str(m.lower()[0:5]) == '!help'):
                self.zip_help(m.nick)
            elif self.zipper and self.wake and (str(m.lower()[0:4]) == '!zip') and self.zipcheck(m.nick, m.green, m.purple or m.janitor):
                self.zip_handler(m.nick, m, files=m.files)
            elif self.zipper and self.wake and (str(m.lower()[0:6]) == '!count') and self.zipcheck(m.nick, m.green, m.purple or m.janitor):
                self.count_handler(m.nick, m, files=m.files)
            elif self.zipper and self.wake and (str(m.lower()[0:7]) == '!mirror') and self.zipcheck(m.nick, m.green, m.purple or m.janitor):
                self.mirror_handler(m.nick, m, files=m.files)
            elif self.zipper and (str(m.lower()[0:6]) == '!alive'):
                self.printl("{} -> checking for bot: {}".format(m.nick, str(self)), "alive")
                if self.wake:
                    self.post_chat("@{}: chinaman working!".format(m.nick))
                else:
                    self.post_chat("@{}: chinaman is asleep.".format(m.nick))
            elif self.zipper and (str(m.lower()[0:5]) == '!kill') and self.admincheck(m.nick, m.green, m.purple):
                self.kill(m.nick)
            elif self.zipper and self.wake and (str(m.lower()[0:6]) == '!sleep') and self.admincheck(m.nick, m.green, m.purple):
                self.post_chat("@{}: chinaman going to sleep!".format(m.nick))
                self.wake = False
            elif self.zipper and not self.wake and (str(m.lower()[0:5]) == '!wake') and self.admincheck(m.nick, m.green, m.purple):
                self.post_chat("@{}: chinaman woke up!".format(m.nick))
                self.wake = True
            elif not self.zipper and (str(m.lower()[0:7]) == '!zipbot') and self.admincheck(m.nick, m.green):
                self.post_chat("@{}: Whuddup!".format(m.nick))
                self.zipper = True
            elif datetime.now() > self.refresh_time:
                # if the refreshtime is now -> close the bot
                self.close()

        if self.alive:
            # add the listener on the volapi room
            try:
                self.listen.add_listener("chat", onmessage)
                self.printl("Connecting to room: {}".format(str(self.listen)), "joinroom")
                self.listen.listen()
            except OSError:
                self.printl("Socket disconnected, trying to reconnect... - OSError", "onmessage")
                self.close()
            return False

    def mirror_handler(self, name, message, files):
        """Grabs files from a room and uplpoads them to openload"""
        self.printl("{} -> requested mirror".format(name), "mirror_handler")

        # generate a folder name
        newfol = f.id_generator()

        if not(files is None) and len(files) == 1:
            mspl = str(message).split('@')
            # look if the file is in the room
            if self.file_in_room(str(mspl[1]).replace(" ", "")):
                # create the message, that gets put at the end of the _mirror.txt
                filechecked = self.filecheck(name, files[0])
                mirr_message = ""
                memadd = files[0].size

                # this checks whether the file is lower than the maximum mirror file size allowed in cfg
                if memadd / self.cfg['main']['multiplier'] <= self.cfg['rooms'][self.roomselect]['mirrormaxmem']:

                    self.post_chat('@{}: Starting to mirror.'.format(name))
                    time.sleep(1)
                    # Downloading the file here while getting the filepath back
                    zippath = self.singleFileDownload(files[0].url, newfol, True)
                    # Checking if file is bigger then 995 mb since openload does not allow files > 1gb
                    if memadd / self.cfg['main']['multiplier'] <= self.cfg['main']['mirrorziptest']:
                        self.printl('Uploading to Openload: {}'.format(zippath), "mirrorhandler")
                        # Uploading the file to openload
                        upinfos = self.upOpenload(zippath)
                        self.printl(str(upinfos), "mirrorhandler")
                        mirr_message = upinfos['url'] + "\n"
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror.txt'
                        # return message to chat
                        self.post_chat('@{}: {} is uploaded to -> {}'.format(name, upinfos['name'], upinfos['url']))
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + filechecked)
                        fl.close()
                        self.volaupload(uppath)
                    else:
                        # file is > 1gb -> needs to be converted to zip and split before uploading
                        self.printl('Checking if zip: {}'.format(zippath), "mirrorhandler")
                        pathsplit = zippath.split('/')
                        filesplit = str(pathsplit[-1])
                        endsplit = filesplit.split('.')
                        ending = str(endsplit[-1])
                        if ending != 'zip':
                            # making a zip
                            zipname = filesplit
                            shutil.make_archive(zipname, 'zip', self.zipfol(newfol))
                            os.remove(self.zipfol(newfol) + '/' + zipname)
                            shutil.move(zipname + '.zip', self.zipfol(newfol) + '/' + zipname + '.zip')
                            zippath = self.zipfol(newfol) + '/' + zipname + '.zip'

                        # splitting the zip with file_split
                        self.printl('Splitting zip: ' + zippath, "mirrorhandler")
                        self.file_split(zippath, self.cfg['main']['mirrorzipmax'] * self.cfg['main']['multiplier'])
                        shutil.move(zippath, self.cfg['os'][self.platform]['mirrorfolder'] + filesplit)
                        retmsg = '@{}: {} is uploaded to ->'.format(name, filesplit)
                        i = 1
                        for fi in os.listdir(self.zipfol(newfol)):
                            testmsg = retmsg
                            xpath = os.path.join(self.zipfol(newfol), fi)
                            self.printl('Uploading to openload: ' + xpath, "mirrorhandler")
                            upinfos = self.upOpenload(xpath)
                            testmsg = testmsg + ' ' + upinfos['url']
                            # putting together the message with file links
                            mirr_message = mirr_message + upinfos['url'] + " \n"
                            if len(testmsg) < (295 * i):
                                # max of 300 characters for one vola chat message
                                retmsg = testmsg
                            else:
                                retmsg = retmsg + '\n' + ' ' + upinfos['url']

                                i = i + 1

                        # self.post_chat(retmsg)

                        # creating the _mirror.txt here
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit + '_mirror.txt'
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + filechecked)
                        fl.close()
                        self.volaupload(uppath)
                    # cleanup
                    pathsplit = zippath.split('/')
                    filesplit = str(pathsplit[-1])
                    if os.path.isfile(zippath):
                        shutil.move(zippath, self.cfg['os'][self.platform]['mirrorfolder'] + filesplit)
                    shutil.rmtree(self.zipfol(newfol))
                else:
                    self.post_chat('@{}: The file @{} is too big to mirror. -> > {} MB'.format(name, str(mspl[1].replace(" ", "")), str(self.cfg['rooms'][self.roomselect]['mirrormaxmem'])))

            else:
                self.post_chat('@{}: The file @{} was not found in the room and can not be mirrored in here.'.format(name, str(mspl[1].replace(" ", ""))))

        else:
            self.post_chat('@{}: Your message could not be interpreted correctly. (use !zip help)'.format(name))

    def filecheck(self, name, file):
        """Returns fileinfo for the _mirror.txt"""
        fileupl = str(file.uploader)
        filesize = file.size/self.cfg['main']['multiplier']
        requester = str(name)
        filesizestring = "{0:.2f}".format(filesize) + " MB"
        return "You need to download all of the links to have a complete file # Size: {} # Uploader: {} # Requested by: {} # ".format(filesizestring, fileupl, requester)

    def count_handler(self, name, message, files):
        """Counts file positions in the current room"""
        self.printl("{} -> requested count".format(name), "count_handler")

        if not(files is None) and len(files)>0 and len(files)<3:
            mspl = str(message).split('@')
            filelist = self.listen.files
            i = 0
            for file in files:
                i = i + 1
                # check if the mentioned file is in the room
                if self.file_in_room(str(mspl[i]).replace(" ", "")):
                    found = False
                    usercount = 0
                    fullcount = 0
                    upl = file.uploader
                    fname = str(file.name)
                    fid = file.fid
                    for dat in reversed(filelist):
                        if dat.uploader == upl:
                            usercount = usercount + 1
                        fullcount = fullcount + 1
                        if dat.fid == fid:
                            found = True
                            break
                    if found:
                        self.post_chat('@{}: {} - > count in room: {} - count for {}: {}'.format(name, fname, str(fullcount), upl, str(usercount)))
                else:
                    self.post_chat('@{}: The file @{} was not found in the room.'.format(name, str(mspl[i].replace(" ", ""))))

        else:
            self.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
            return False

    def zip_handler(self, name, message, mirror='vola', files=None):
        """Downloads files, zips them, uploads them back to volafile and possibly other mirrorsites"""
        self.printl("{} -> requested zip with: '{}'".format(name, message), "zip_handler")
        newfol = f.id_generator()
        mspls = message.split('#')
        additionalmirror = False
        if len(mspls) > 1:
            # if there are any '#command'
            upl = '*'
            fname = '*'
            ftype = '*'
            num = -1
            offset = 0
            zipname = f.zipNameReplace(f.id_generator())
            for mspl in mspls:

                splits = str(mspl).split("=")
                if len(splits) == 2:

                    if str(splits[0]) == 'upl' or str(splits[0]) == 'uploader':
                        upl = str(splits[1])
                    if str(splits[0]) == 'filename' or str(splits[0]) == 'search':
                        fname = str(splits[1])
                    if str(splits[0]) == 'type' or str(splits[0]) == 'filetype':
                        ftype = str(splits[1]).lower()
                    if str(splits[0]) == 'num' or str(splits[0]) == 'number':
                        num = int(eval(splits[1]))
                    if str(splits[0]) == 'offset' or str(splits[0]) == 'lownum':
                        offset = int(eval(splits[1]))
                    if str(splits[0]) == 'zipname' or str(splits[0]) == 'zip':
                        zipname = str(splits[1]).replace(" ", "")
                elif len(splits) == 1:
                    if str(splits[0]) == 'mirror' or str(splits[0]) == 'openload':
                        additionalmirror = True
                else:
                    continue
            if mirror == 'vola':
                self.post_chat('@' + name + ': Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
            if mirror == 'openload':
                self.post_chat('@' + name + ': Downloading and mirroring initiated. No other requests will be handled until the upload is finished.')
            self.handleDownloads(newfol, upl, fname, ftype, num, offset)

        else:
            if files is None or len(files) < 2:
                self.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
                return False
            else:
                self.post_chat('@' + name + ': Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
                memadd = 0
                zipname = f.zipNameReplace(f.id_generator())
                self.crzipfol(newfol)
                for file in files:
                    memadd = memadd + file.size
                    url = file.url
                    if memadd / self.cfg['main']['multiplier'] <= self.cfg['rooms'][self.roomselect]['maxmem']:
                        zipname = self.singleFileDownload(url, newfol)

        if len(os.listdir(self.zipfol(newfol))) == 0:
            self.printl('No files were downloaded!', "zip_handler")
            self.post_chat('@' + name + ': Error creating zip -> No files downloaded. (Use !zip help')
            shutil.rmtree(self.zipfol(newfol))
            return False
        self.printl('Zipping: ' + zipname + '.zip', "zip_handler")
        shutil.make_archive(zipname, 'zip', self.zipfol(newfol))
        shutil.move(zipname + '.zip', self.zipfol(newfol) + '/' + zipname + '.zip')
        if mirror == 'vola':
            uppath = self.zipfol(newfol) + '/' + zipname + '.zip'
            self.printl('Uploading to volafile: ' + zipname + '.zip', "zip_handler")
            self.volaupload(uppath)

        if mirror == 'openload' or additionalmirror:
            memadd = 0
            mirr_message = ''
            for fi in os.listdir(self.zipfol(newfol)):
                xpath = os.path.join(self.zipfol(newfol), fi)
                if os.path.isfile(xpath):
                    memadd = memadd + os.path.getsize(xpath)
            if memadd / self.cfg['main']['multiplier'] <= self.cfg['rooms'][self.roomselect]['mirrormaxmem']:
                if memadd / self.cfg['main']['multiplier'] <= self.cfg['main']['mirrorziptest']:
                    self.printl('Uploading to Openload: ' + zipname + '.zip', "zip_handler")
                    upinfos = self.upOpenload(self.zipfol(newfol) + '/' + zipname + '.zip')
                    self.printl(str(upinfos), "zip_handler")
                    mirr_message = upinfos['url'] + "\n"
                    uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror.txt'
                    if not additionalmirror:
                        self.post_chat('@' + name + ': ' + upinfos['name'] + ' is uploaded to -> ' + upinfos['url'])
                    if os.path.isfile(uppath):
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror_' + str(f.id_generator()) + '.txt'
                    fl = open(uppath, "w+")
                    fl.write(mirr_message + ' \n' + 'Requested by ' + name)
                    fl.close()

                    self.volaupload(uppath)

                else:
                    if self.cfg['rooms'][self.roomselect]['anonfile']:
                        self.printl('Uploading to anonfiles: ' + zipname + '.zip', "zip_handler")
                        upinfos = f.anonfileupload(self.zipfol(newfol) + '/' + zipname + '.zip')
                        self.printl(str(upinfos), "zip_handler")
                        if upinfos['status'] == 'true':
                            self.post_chat('@' + name + ': ' +
                                             upinfos['data']['file']['metadata']['name'] + ' is uploaded to -> ' +
                                             upinfos['data']['file']['url']['full'])
                        else:
                            self.post_chat('@' + name + ': Error uploading to anonfiles -> ' +
                                             upinfos['error']['message'])
                    else:
                        zippath = self.zipfol(newfol) + '/' + zipname + '.zip'
                        pathsplit = zippath.split('/')
                        filesplit = str(pathsplit[-1])

                        self.printl('Splitting zip: ' + zipname + '.zip', "zip_handler")
                        newpath = self.zipfol(newfol) + '/mir'
                        try:
                            if not os.path.exists(newpath):
                                os.makedirs(newpath)
                                self.printl('Created directory: ' + newpath, "zip_handler")
                                newpath = newpath + '/'
                        except OSError:
                            self.printl('Error: Creating directory. ' + newpath, "zip_handler")
                        shutil.move(zippath, newpath + filesplit)
                        self.file_split(newpath + filesplit,
                                        self.cfg['main']['mirrorzipmax'] * self.cfg['main']['multiplier'])
                        shutil.move(newpath + filesplit, zippath)
                        retmsg = '@' + name + ': ' + filesplit.replace('%20', '_') + ' is uploaded to ->'
                        i = 1
                        for fi in os.listdir(newpath):
                            testmsg = retmsg
                            xpath = os.path.join(newpath, fi)
                            upinfos = self.upOpenload(xpath)
                            testmsg = testmsg + ' ' + upinfos['url']
                            mirr_message = mirr_message + upinfos['url'] + " \n"
                            if len(testmsg) < (295 * i):
                                retmsg = testmsg
                            else:
                                retmsg = retmsg + '\n' + ' ' + upinfos['url']

                                i = i + 1
                        if not additionalmirror:
                            self.post_chat(retmsg)
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit.replace('%20', '_') + '_mirror.txt'
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit.replace('%20', '_') + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + 'Requested by ' + name + " # You need to download all of the links to have a complete file.")
                        fl.close()
                        self.volaupload(uppath)

            else:
                self.post_chat('@' + name + ': File too big to mirror. -> > ' + str(self.cfg['rooms'][self.roomselect]['mirrormaxmem']))

        shutil.move(self.zipfol(newfol) + '/' + zipname + '.zip', self.archfol(newfol) + '/' + zipname + '.zip')
        shutil.rmtree(self.zipfol(newfol))

        return True

    def volaupload(self, uppath):
        """Uploads a file to vola, currently user/passwd are not needed"""
        return self.interact.upload_file(uppath)

    def post_chat(self, message):
        """Posts a chat message to the connected room"""

        try:
            self.interact.post_chat(message)
            self.printl("Sending message: {}".format(message), "post_chat")
        except OSError:
            self.printl("Message could not be sent - OSError", "post_chat")
        return False

    def file_split(self, file, max):
        """Splits a zip file"""
        chapters = 1
        uglybuf = ''
        with open(file, 'rb') as src:
            while True:
                tgt = open(file + '.%03d' % chapters, 'wb')
                written = 0
                while written < max:
                    if len(uglybuf) > 0:
                        tgt.write(uglybuf)
                    tgt.write(src.read(min(self.cfg['os'][self.platform]['membuff'] * self.cfg['main']['multiplier'], self.cfg['main']['mirrorzipmax'] * self.cfg['main']['multiplier'] - written)))
                    written += min(self.cfg['os'][self.platform]['membuff'] * self.cfg['main']['multiplier'], self.cfg['main']['mirrorzipmax'] * self.cfg['main']['multiplier'] - written)
                    uglybuf = src.read(1)
                    if len(uglybuf) == 0:
                        break
                tgt.close()
                if len(uglybuf) == 0:
                    break
                chapters += 1

    def singleFileDownload(self, URL, newfol, mirror=False):
        """Downloads a single file from vola"""
        URL = URL.replace(" ", "")
        if os.path.exists(self.zipfol(newfol)):
            path = self.zipfol(newfol)+'/'
        else:
            path = self.crzipfol(newfol)
        urlsplit = URL.split('/')
        filesplit = str(urlsplit[-1]).split('.')
        dpath = path + str(filesplit[0]) + '.' + str(filesplit[1])
        if os.path.isfile(dpath):
            dpath = path + str(filesplit[0]) + "-" + f.id_generator() + '.' + str(filesplit[1])
        self.printl('[] Downloading: ' + dpath + ' - ' + URL, "singleFileDownload")
        self.download_file(URL, dpath)
        if mirror:
            return str(dpath)
        else:
            return str(filesplit[0])

    def handleDownloads(self, newfol, uplname='*', filename='*', filetype='*', numoffiles=-1, offset=0):
        """Checks the files in the room along the set criteria in a !zip command"""
        if os.path.exists(self.zipfol(newfol)):
            self.printl('Folder Exists Already', "handleDownloads")
            path = self.zipfol(newfol) + '/'
        else:
            path = self.crzipfol(newfol)
        files = self.listen.files
        i = 1
        j = 1
        memadd = 0
        for file in reversed(files):
            dlurl = file.url
            user = file.uploader
            size = file.size
            fn_full = file.name
            ending = fn_full.rpartition('.')[-1]
            fn = fn_full.rpartition('.')[0]
            if uplname == '*' or uplname == str(user):
                if filetype == '*' or filetype == str(ending).lower():
                    if filename == '*' or (filename.lower() in fn.lower()):
                        if i <= numoffiles or numoffiles == -1:
                            if j > offset or offset == 0:
                                memadd = memadd + size
                                if memadd / self.cfg['main']['multiplier'] <= self.cfg['rooms'][self.roomselect]['maxmem']:
                                    dpath = path + fn + '.' + ending
                                    if os.path.isfile(dpath):
                                        dpath = path + fn + "-" + f.id_generator() + '.' + ending
                                    self.printl('[' + str(i) + '] Downloading: ' + dpath + ' - ' + dlurl, "handleDownloads")
                                    self.download_file(dlurl, dpath)
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
        if help_file == "" or not(self.file_in_room(help_file)):
            tpath = self.safefol(self.room) + "/ziphelp-" + self.room + ".txt"
            if os.path.isfile(tpath):
                os.remove(tpath)
            shutil.copyfile('ziphelp.txt', tpath)
            fl = open(tpath, "a")
            msg = "\n# 3 Allowed zippers in this channel #\n"
            for name in self.cfg['rooms'][self.roomselect]['allowedzippers']:
                msg = msg + str(name).replace("*", "") + ", "
            msg = msg[:-2]
            msg = msg + "\n\n# 4 Bot admins in this channel #\n"
            for name in self.cfg['rooms'][self.roomselect]['botadmins']:
                msg = msg + str(name).replace("*", "") + ", "
            msg = msg[:-2]
            fl.write(msg)
            fl.close()
            fileid = self.volaupload(tpath)
            help_file = fileid
            time.sleep(2)
        self.post_chat("@{}: -> @{}".format(user, str(help_file)))

    def file_in_room(self, fileid):
        """Checks if a fileid is in the current room"""
        found = False
        filelist = self.listen.files
        for data in reversed(filelist):
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
        del self.listen
        self.interact.close()
        del self.interact
        del self.cfg
        global kill
        kill = True
        return ""

    def close(self):
        """only closes the current session, afterwards the bot reconnects"""
        self.printl("Closing current instance due to runtime: " + str(self), "close")
        self.alive = False
        self.listen.close()
        del self.listen
        self.interact.close()
        del self.interact
        del self.cfg
        return ""

    def printl(self, message, method='NONE'):
        """Log Function"""
        now = datetime.now()
        dt = now.strftime("%Y-%m-%d--%H:%M:%S")
        msg = '\n[' + str(dt) + '][' + str(method) + '] ' + str(message)
        dpath = self.safefol(self.room) + '/' + self.session + '.txt'
        fl = open(dpath, "a")
        print(msg)
        fl.write(unidecode(msg))
        fl.close()

    def create_session_file(self):
        if not(os.path.exists(self.safefol(self.room))):
            self.crfol(self.room)
        dpath = self.safefol(self.room) + '/' + self.session + '.txt'

        if not os.path.isfile(dpath):
            fl = open(dpath, "w+")
            fl.write('Logging for ' + self.session + ':\n')
            fl.close()
            self.printl("Session File Created", "create_session_file")
            return True
        else:
            return False

    def listen_room(self):
        """Creates a Room instance that does only listens to chat."""
        if self.roompw == '*':
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'])
        elif self.roompw[0:4] == '#key':
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'], key=self.roompw[4:])
        else:
            r = Room(name=self.room, user=self.cfg['main']['zipbotuser'], password=self.roompw)
        self.printl("Listening room created", "listen_room")

        return r

    def interact_room(self):
        """Creates a Room instance that does not listen to chat, but is used to operate with the room for uploads or messages."""


        if self.roompw == '*':
            r = Room(name=self.room, user=self.cfg['main']['dluser'])
        elif self.roompw[0:4] == '#key':
            r = Room(name=self.room, user=self.cfg['main']['dluser'], key=self.roompw[4:])
        else:
            r = Room(name=self.room, user=self.cfg['main']['dluser'], password=self.roompw)

        time.sleep(1)
        if r.user.login(self.cfg['main']['dlpass']):
            self.printl("Logged in as: " + self.cfg['main']['dluser'], "interact_room")
        else:
            self.printl("Login failed!", "interact_room")

        if not self.loggedin:

            time.sleep(1)
            cj = r.conn.cookies
            cookies_dict = {}
            for cookie in cj:
                if "volafile" in cookie.domain:
                    cookies_dict[cookie.name] = cookie.value
                    self.loggedin = True
            self.cookies = {**self.cookies, **cookies_dict}
            self.printl("Download session cookie: " + str(self.cookies), "interact_room")

        if not(self.cfg['main']['dluser'] == self.cfg['main']['zipbotuser']):

            r.user.logout()
            time.sleep(2)
            r.user.change_nick(self.cfg['main']['zipbotuser'])
            time.sleep(1)

            if r.user.login(self.cfg['main']['zipbotpass']):
                self.printl("Logged in as: " + self.cfg['main']['zipbotuser'], "interact_room")
            else:
                self.printl("Login failed!", "interact_room")

        return r


    def admincheck(self, user, registered, mod=False):
        """Checks whether the user is a botadmin in the current room"""
        if registered:
            name = "*" + user
        else:
            name = user
        if (name in self.cfg['rooms'][self.roomselect]['botadmins']) or ('all' in self.cfg['rooms'][self.roomselect]['botadmins']) or mod:
            self.printl(user + " was accepted!", "admincheck")
            return True
        else:
            self.printl(user + " was denied!", "admincheck")
            self.post_chat("@{}: Who even are you? (user denied - use !zip help)".format(user))
            return False
            
    def zipcheck(self, user, registered, mod=False):
        """Checks whether the user is allowed to zip in the current room"""
        if registered:
            name = "*" + user
        else:
            name = user
        if (name in self.cfg['rooms'][self.roomselect]['allowedzippers']) or ('all' in self.cfg['rooms'][self.roomselect]['allowedzippers']) or mod:
            return True
        else:
            self.printl(user + " was accepted!", "zipcheck")
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

    def upOpenload(self, path):
        """Method to upload files to openload"""
        o1 = self.MyOpenLoad(self.cfg['main']['opus'], self.cfg['main']['oppw'])
        info = o1.upload_large_file(path)
        return info

    # FOLDER FUNCTIONS
    def safefol(self, newfol):
        newpath = self.cfg['os'][self.platform]['logfolder'] + newfol
        return newpath

    def zipfol(self, newfol):
        newpath = self.cfg['os'][self.platform]['zipfolder'] + newfol
        return newpath

    def archfol(self, newfol):
        newpath = self.cfg['os'][self.platform]['archfolder']
        return newpath

    def crfol(self, newfol):
        newpath = self.cfg['os'][self.platform]['logfolder'] + newfol

        try:
            if not os.path.exists(newpath):
                os.makedirs(newpath)
                self.printl('Created directory: ' + newpath, 'crfol')
                return str(newpath + '/')
        except OSError:
            print('Error: Creating directory. ' + newpath)
            return 'Error'

    def crzipfol(self, newfol):
        newpath = self.cfg['os'][self.platform]['zipfolder'] + newfol
        try:
            if not os.path.exists(newpath):
                os.makedirs(newpath)
                self.printl('Created directory: ' + newpath, 'crzipfol')
                return str(newpath + '/')
        except OSError:
            print('Error: Creating directory. ' + newpath)
            return 'Error'


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
        v.joinroom()


def main_callable(room, zipper=False, passwd='*'):
    """Callable main method with arguments"""
    global kill
    lister = [room, zipper, passwd]
    while not kill:
        v = VolaZipBot(lister)
        v.joinroom()


if __name__ == "__main__":
    main()

