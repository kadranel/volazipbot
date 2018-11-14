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

helpfile = ""
kill = False


class VolaZipBot(object):
    def __init__(self, lister):
        self.session = f.id_generator()
        self.refresh_time = datetime.now() + timedelta(days=1)
        self.alive = True
        self.wake = True
        self.cfg = json.load(open('config.json', 'r'))

        if lister[0] in self.cfg['rooms'].keys():
            self.roomselect = lister[0]
        else:
            self.roomselect = 'genericroom'
        if os.name in self.cfg['os'].keys():
            self.platform = os.name
        else:
            self.printl("OS " + os.name + " not supported.", "__init__")
            self.alive = False
        self.cookies = self.cfg['main']['cookies']
        self.headers = self.cfg['main']['headers']
        if len(lister) == 3:
            self.roompw = lister[2]
        elif len(lister) == 2:
            self.roompw = '*'
        self.zipper = lister[1]
        self.URL = "https://volafile.org/r/" + lister[0]
        self.room = lister[0]
        self.loggedin = False
        self.chatbot = self.chatbot()
        if self.roompw == '*':
            self.listen = Room(self.room)
        elif self.roompw[0:4] == '#key':
            self.listen = Room(name=self.room, key=self.roompw[4:])
        else:
            self.listen = Room(name=self.room, password=self.roompw)

    def __repr__(self):
        return "<VolaZipBot(alive={}, zipper={}, listen={}, chatbot={})>".format(self.alive, self.zipper, str(self.listen), str(self.chatbot))

    def joinroom(self):
        """Add the listener to the room."""

        def onmessage(m):
            """Print the new message and respond to user input"""
            self.printl(m, "onmessage/main")

            if self.zipper is True and self.wake is True and (str(m.msg.lower()[0:9]) == '!zip help'):
                self.ziphelp(m.nick)
            elif self.zipper is True and self.wake is True and (str(m.msg.lower()[0:5]) == '!help'):
                self.ziphelp(m.nick)
            elif self.zipper is True and self.wake is True and (str(m.msg.lower()[0:4]) == '!zip') and self.zipcheck(m.nick, m.green, m.purple):
                self.ziphandler(m.nick, m.msg, files=m.files)
            elif self.zipper is True and self.wake is True and (str(m.msg.lower()[0:6]) == '!count') and self.zipcheck(m.nick, m.green, m.purple):
                self.counthandler(m.nick, m.msg, files=m.files)
            elif self.zipper is True and self.wake is True and (str(m.msg.lower()[0:7]) == '!mirror') and self.zipcheck(m.nick, m.green, m.purple):
                self.mirrorhandler(m.nick, m.msg, files=m.files)
            elif self.zipper is True and (str(m.msg.lower()[0:6]) == '!alive'):
                self.printl(m.nick + " -> checking for bot: " + str(self), "alive")
                if self.wake is True:
                    self.chatbot.post_chat("@{}: chinaman working!".format(m.nick))
                else:
                    self.chatbot.post_chat("@{}: chinaman is asleep.".format(m.nick))
            elif self.zipper is True and (str(m.msg.lower()[0:5]) == '!kill') and self.admincheck(m.nick, m.green):
                self.kill(m.nick)
            elif self.zipper is True and self.wake is True and (str(m.msg.lower()[0:6]) == '!sleep') and self.admincheck(m.nick, m.green):
                self.chatbot.post_chat("@{}: chinaman going to sleep!".format(m.nick))
                self.wake = False
            elif self.zipper is True and self.wake is False and (str(m.msg.lower()[0:5]) == '!wake') and self.admincheck(m.nick, m.green):
                self.chatbot.post_chat("@{}: chinaman woke up!".format(m.nick))
                self.wake = True
            elif datetime.now() > self.refresh_time:
                self.close()

        if self.alive:
            self.listen.add_listener("chat", onmessage)
            self.printl("Connecting to room: " + str(self.listen), "joinroom")
            self.listen.listen()

    def mirrorhandler(self, name, message, files):
        """Grabs files from a room and uplpoads them to openload"""
        self.printl(name + " -> requested mirror", "mirrorhandler")
        newfol = f.id_generator()
        inroom = False
        if not(files is None) and len(files) == 1:
            mspl = str(message).split('@')
            filelist = self.listen.files
            for data in reversed(filelist):
                if str(mspl[1]).replace(" ", "") == data.id:
                    inroom = True
            if inroom:
                filechecked = VolaZipBot.filecheck(name, files[0])
                mirr_message = ""
                memadd = files[0].size
                if memadd / 1024 / 1024 <= self.cfg['rooms'][self.roomselect]['mirrormaxmem']:
                    self.chatbot.post_chat('@' + name + ': Starting to mirror.')
                    time.sleep(1)
                    zippath = self.singleFileDownload(files[0].url, newfol, True)
                    if memadd / 1024 / 1024 <= self.cfg['main']['mirrorziptest']:
                        self.printl('Uploading to Openload: ' + zippath, "mirrorhandler")
                        upinfos = self.upOpenload(zippath)
                        self.printl(str(upinfos), "mirrorhandler")
                        mirr_message = upinfos['url'] + "\n"
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror.txt'
                        self.chatbot.post_chat('@' + name + ': ' + upinfos['name'] + ' is uploaded to -> ' + upinfos['url'])
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + filechecked)
                        fl.close()
                        self.volaupload(self.cfg['main']['zipbotuser'], self.cfg['main']['zipbotpass'], uppath)
                    else:
                        self.printl('Checking if zip: ' + zippath, "mirrorhandler")
                        pathsplit = zippath.split('/')
                        filesplit = str(pathsplit[-1])
                        endsplit = filesplit.split('.')
                        ending = str(endsplit[-1])
                        if ending != 'zip':
                            zipname = filesplit
                            shutil.make_archive(zipname, 'zip', self.zipfol(newfol))
                            os.remove(self.zipfol(newfol) + '/' + zipname)
                            shutil.move(zipname + '.zip', self.zipfol(newfol) + '/' + zipname + '.zip')
                            zippath = self.zipfol(newfol) + '/' + zipname + '.zip'
                        self.printl('Splitting zip: ' + zippath, "mirrorhandler")
                        self.file_split(zippath, self.cfg['main']['mirrorzipmax'] * self.cfg['main']['multiplier'])
                        shutil.move(zippath, self.cfg['os'][self.platform]['mirrorfolder'] + filesplit)
                        retmsg = '@' + name + ': ' + filesplit + ' is uploaded to ->'
                        i = 1
                        for fi in os.listdir(self.zipfol(newfol)):
                            testmsg = retmsg
                            xpath = os.path.join(self.zipfol(newfol), fi)
                            upinfos = self.upOpenload(xpath)
                            testmsg = testmsg + ' ' + upinfos['url']
                            mirr_message = mirr_message + upinfos['url'] + " \n"
                            if len(testmsg) < (295 * i):
                                retmsg = testmsg
                            else:
                                retmsg = retmsg + '\n' + ' ' + upinfos['url']

                                i = i + 1
                        self.chatbot.post_chat(retmsg)
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit + '_mirror.txt'
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + filechecked)
                        fl.close()
                        self.volaupload(self.cfg['main']['zipbotuser'], self.cfg['main']['zipbotpass'], uppath)
                    pathsplit = zippath.split('/')
                    filesplit = str(pathsplit[-1])
                    if os.path.isfile(zippath):
                        shutil.move(zippath, self.cfg['os'][self.platform]['mirrorfolder'] + filesplit)
                    shutil.rmtree(self.zipfol(newfol))
                else:
                    self.chatbot.post_chat('@' + name + ': The file @' + str(mspl[1].replace(" ", "")) + ' is too big to mirror. -> > '+ str(self.cfg['rooms'][self.roomselect]['mirrormaxmem']) + ' MB')

            else:
                self.chatbot.post_chat('@' + name + ': The file @' + str(mspl[1].replace(" ", "")) + ' was not found in the room and can not be mirrored in here.')

        else:
            self.chatbot.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
            return False

    @staticmethod
    def filecheck(name, file):
        """Returns fileinfo for the _mirror.txt"""
        fileupl = file.uploader
        filesize = file.size/1024/1024
        requester = name
        filesizestring = "{0:.2f}".format(filesize) + " MB"
        return "You need to download all of the links to have a complete file # Size: " + str(filesizestring) + " # Uploader: " + str(fileupl) + " # Requested by: " + str(requester) + " # "

    def counthandler(self, name, message, files):
        """Counts file positions in the current room"""
        self.printl(name + " -> requested count", "counthandler")

        if not(files is None) and len(files)>0 and len(files)<3:
            mspl = str(message).split('@')
            filelist = self.listen.files
            i = 0

            for file in files:
                i = i + 1
                inroom = False
                for data in reversed(filelist):
                    if str(mspl[i]).replace(" ", "") == data.id:
                        inroom = True
                if inroom:
                    found = False
                    usercount = 0
                    fullcount = 0
                    upl = file.uploader
                    fname = file.name
                    id = file.id
                    for dat in reversed(filelist):
                        if dat.uploader == upl:
                            usercount = usercount + 1
                        fullcount = fullcount + 1
                        if dat.id == id:
                            found = True
                            break
                    if found:
                        self.chatbot.post_chat('@' + name + ': ' + str(fname) + ' - > count in room: ' + str(fullcount) + ' - count for ' + upl + ': ' + str(usercount))
                else:
                    self.chatbot.post_chat('@' + name + ': The file @' + str(mspl[i].replace(" ", "")) + ' was not found in the room.')

        else:
            self.chatbot.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
            return False

    def ziphandler(self, name, message, mirror='vola', files=None):
        """Downloads files, zips them, uploads them back to volafile and possibly other mirrorsites"""
        self.printl(name + " -> requested zip with: '" + message + "'", "ziphandler")
        newfol = f.id_generator()
        mspls = message.split('#')
        additionalmirror = False
        if len(mspls) > 1:
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
                        zipname = str(splits[1]).replace(" ", "")  # + '[' + VolaZipBot.namereplace(name) + ']'
                elif len(splits) == 1:
                    if str(splits[0]) == 'mirror' or str(splits[0]) == 'openload':
                        additionalmirror = True
                else:
                    continue
            if mirror == 'vola':
                self.chatbot.post_chat('@' + name + ': Downloading and zipping initiated. No other requests will be handled until the upload is finished.')
            if mirror == 'openload':
                self.chatbot.post_chat('@' + name + ': Downloading and mirroring initiated. No other requests will be handled until the upload is finished.')
            self.handleDownloads(newfol, upl, fname, ftype, num, offset)

        else:
            if files is None or len(files) < 2:
                self.chatbot.post_chat('@' + name + ': Your message could not be interpreted correctly. (use !zip help)')
                return False
            else:
                self.chatbot.post_chat('@' + name + ': Downloading and zipping initiated. No other reque!sts will be handled until the upload is finished.')
                memadd = 0
                zipname = f.zipNameReplace(f.id_generator())
                self.crzipfol(newfol)
                for file in files:
                    memadd = memadd + file.size
                    url = file.url
                    if memadd / 1024 / 1024 <= self.cfg['rooms'][self.roomselect]['maxmem']:
                        zipname = self.singleFileDownload(url, newfol)

        if len(os.listdir(self.zipfol(newfol))) == 0:
            self.printl('No files were downloaded!', "ziphandler")
            self.chatbot.post_chat('@' + name + ': Error creating zip -> No files downloaded. (Use !zip help')
            shutil.rmtree(self.zipfol(newfol))
            return False
        self.printl('Zipping: ' + zipname + '.zip', "ziphandler")
        shutil.make_archive(zipname, 'zip', self.zipfol(newfol))
        shutil.move(zipname + '.zip', self.zipfol(newfol) + '/' + zipname + '.zip')
        if mirror == 'vola':
            uppath = self.zipfol(newfol) + '/' + zipname + '.zip'
            self.printl('Uploading to volafile: ' + zipname + '.zip', "ziphandler")
            self.volaupload(self.cfg['main']['zipbotuser'], self.cfg['main']['zipbotpass'], uppath)

        if mirror == 'openload' or additionalmirror:
            memadd = 0
            mirr_message = ''
            for fi in os.listdir(self.zipfol(newfol)):
                xpath = os.path.join(self.zipfol(newfol), fi)
                if os.path.isfile(xpath):
                    memadd = memadd + os.path.getsize(xpath)
            if memadd / 1024 / 1024 <= self.cfg['rooms'][self.roomselect]['mirrormaxmem']:
                if memadd / 1024 / 1024 <= self.cfg['main']['mirrorziptest']:
                    self.printl('Uploading to Openload: ' + zipname + '.zip', "ziphandler")
                    upinfos = self.upOpenload(self.zipfol(newfol) + '/' + zipname + '.zip')
                    self.printl(str(upinfos), "ziphandler")
                    mirr_message = upinfos['url'] + "\n"
                    uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror.txt'
                    if not additionalmirror:
                        self.chatbot.post_chat('@' + name + ': ' + upinfos['name'] + ' is uploaded to -> ' + upinfos['url'])
                    if os.path.isfile(uppath):
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + upinfos['name'] + '_mirror_' + str(f.id_generator()) + '.txt'
                    fl = open(uppath, "w+")
                    fl.write(mirr_message + ' \n' + 'Requested by ' + name)
                    fl.close()

                    self.volaupload(self.cfg['main']['zipbotuser'], self.cfg['main']['zipbotpass'], uppath)

                else:
                    if self.cfg['rooms'][self.roomselect]['anonfile']:
                        self.printl('Uploading to anonfiles: ' + zipname + '.zip', "ziphandler")
                        upinfos = f.anonfileupload(self.zipfol(newfol) + '/' + zipname + '.zip')
                        self.printl(str(upinfos), "ziphandler")
                        if upinfos['status'] == 'true':
                            self.chatbot.post_chat('@' + name + ': ' +
                                             upinfos['data']['file']['metadata']['name'] + ' is uploaded to -> ' +
                                             upinfos['data']['file']['url']['full'])
                        else:
                            self.chatbot.post_chat('@' + name + ': Error uploading to anonfiles -> ' +
                                             upinfos['error']['message'])
                    else:
                        zippath = self.zipfol(newfol) + '/' + zipname + '.zip'
                        pathsplit = zippath.split('/')
                        filesplit = str(pathsplit[-1])

                        self.printl('Splitting zip: ' + zipname + '.zip', "ziphandler")
                        newpath = self.zipfol(newfol) + '/mir'
                        try:
                            if not os.path.exists(newpath):
                                os.makedirs(newpath)
                                self.printl('Created directory: ' + newpath, "ziphandler")
                                newpath = newpath + '/'
                        except OSError:
                            self.printl('Error: Creating directory. ' + newpath, "ziphandler")
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
                            self.chatbot.post_chat(retmsg)
                        uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit.replace('%20', '_') + '_mirror.txt'
                        if os.path.isfile(uppath):
                            uppath = self.cfg['os'][self.platform]['mirrorlogs'] + filesplit.replace('%20', '_') + '_mirror_' + str(f.id_generator()) + '.txt'
                        fl = open(uppath, "w+")
                        fl.write(mirr_message + ' \n' + 'Requested by ' + name + " # You need to download all of the links to have a complete file.")
                        fl.close()
                        self.volaupload(self.cfg['main']['zipbotuser'], self.cfg['main']['zipbotpass'], uppath)

            else:
                self.chatbot.post_chat('@' + name + ': File too big to mirror. -> > ' + str(self.cfg['rooms'][self.roomselect]['mirrormaxmem']))

        shutil.move(self.zipfol(newfol) + '/' + zipname + '.zip', self.archfol(newfol) + '/' + zipname + '.zip')
        shutil.rmtree(self.zipfol(newfol))

        return True

    def volaupload(self, user, password, uppath):
        """Uploads a file to vola, currently user/passwd are not needed"""
        self.chatbot.upload_file(uppath)

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
        """Checks if the needed folders for downloading exist"""
        if os.path.exists(self.zipfol(newfol)):
            self.printl('Folder Exists Already', "handleDownloads")
            path = self.zipfol(newfol) + '/'
        else:
            path = self.crzipfol(newfol)
        self.downloadzz(self.listen.files, path, uplname, filename, filetype, numoffiles, offset)

    def downloadzz(self, files, path, uplname, filename, filetype, numoffiles=-1, offset=0):
        """Checks the files in the room along the set criteria in a !zip command"""
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
                                if memadd/1024/1024 <= self.cfg['rooms'][self.roomselect]['maxmem']:
                                    dpath = path + fn + '.' + ending
                                    if os.path.isfile(dpath):
                                        dpath = path + fn + "-" + f.id_generator() + '.' + ending
                                    self.printl('[' + str(i) + '] Downloading: ' + dpath + ' - ' + dlurl, "downloadzz")
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
            with open(file_name + ".part", "wb") as f:
                for data in tqdm(iterable=r.iter_content(chunk_size=chunk_size), total=total_size / chunk_size, unit="KB", unit_scale=True):
                    f.write(data)
            # Remove the ".part" from the file name
            os.rename(file_name + ".part", file_name)
            return True
        except Exception as ex:
            print("[-] Error: " + str(ex))
            return False

    def ziphelp(self, user):
        """Modifies and uploads a ziphelp.txt or links to an existing one"""
        self.printl(user + " -> requesting ziphelp", "ziphelp")
        global helpfile
        if helpfile == "" or not(self.fileinroom(helpfile)):
            tpath = self.safefol(self.room) + "/ziphelp-" + self.room + ".txt"
            if (os.path.isfile(tpath)):
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
            fileid = self.chatbot.upload_file(tpath)
            helpfile = fileid
            time.sleep(2)
        self.chatbot.post_chat("@{}: -> @{}".format(user, str(helpfile)))

    def fileinroom(self, fileid):
        """Checks if a fileid is in the current room"""
        found = False
        filelist = self.listen.files
        for data in reversed(filelist):
            if data.id == fileid:
                found = True
        return found


    def kill(self, user):
        """Reaction to !kill, kills the whole bot"""
        self.printl(user + " -> killing bots in room: " + str(self), "kill")
        self.alive = False
        try:
            self.chatbot.post_chat("@{}: Thats it, i'm out!".format(user))
        except OSError:
            self.printl("message could not be sent - OSError", "kill")
        time.sleep(1)
        self.listen.close()
        self.chatbot.close()
        del self.listen
        del self.chatbot
        del self.cfg
        global kill
        kill = True
        return ""

    def close(self):
        """only closes the current session, afterwards the bot reconnects"""
        self.printl("Closing current instance due to runtime: " + str(self), "close")
        self.alive = False
        self.listen.close()
        self.chatbot.close()
        del self.listen
        del self.chatbot
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

    def chatbot(self):
        """Creates a Room instance that does not listen to chat, but is used to operate with the room for uploads or messages."""
        if not(os.path.exists(self.safefol(self.room))):
            self.crfol(self.room)
        dpath = self.safefol(self.room) + '/' + self.session + '.txt'
        if not (os.path.isfile(dpath)):
            fl = open(dpath, "w+")
            fl.write('Logging for ' + self.session + ':\n')
            fl.close()
        if self.roompw == '*':
            r = Room(self.room)
        elif self.roompw[0:4] == '#key':
            r = Room(name=self.room, key=self.roompw[4:])
        else:
            r = Room(name=self.room, password=self.roompw)
        if not self.loggedin:
            if not(self.cfg['main']['dluser'] == self.cfg['main']['zipbotuser']):
                r.user.change_nick(self.cfg['main']['dluser'])
                time.sleep(1)
                r.user.login(self.cfg['main']['dlpass'])

                time.sleep(1)
                cj = r.conn.cookies
                cookies_dict = {}
                for cookie in cj:
                    if "volafile" in cookie.domain:
                        cookies_dict[cookie.name] = cookie.value
                        self.loggedin = True
                self.cookies = {**self.cookies, **cookies_dict}
                self.printl("Download session cookie: " + str(self.cookies), "chatbot")
                r.user.logout()
                time.sleep(2)
                r.user.change_nick(self.cfg['main']['zipbotuser'])
                time.sleep(1)

                if r.user.login(self.cfg['main']['zipbotpass']):
                    self.printl("Logged in as: " + self.cfg['main']['zipbotuser'], "chatbot")
                else:
                    self.printl("Login failed!", "chatbot")
            else:
                r.user.change_nick(self.cfg['main']['zipbotuser'])
                time.sleep(1)

                if r.user.login(self.cfg['main']['zipbotpass']):
                    self.printl("Logged in as: " + self.cfg['main']['zipbotuser'], "chatbot")
                else:
                    self.printl("Login failed!", "chatbot")
                cj = r.conn.cookies
                cookies_dict = {}
                for cookie in cj:
                    if "volafile" in cookie.domain:
                        cookies_dict[cookie.name] = cookie.value
                        self.loggedin = True
                self.cookies = cookies_dict
                self.printl("Download session cookie: " + str(self.cookies), "chatbot")

        return r

    def admincheck(self, user, registered, mod=False):
        """Checks whether the user is a botadmin in the current room"""
        if registered:
            name = "*" + user
        else:
            name = user
        if (name in self.cfg['rooms'][self.roomselect]['botadmins']) or ('all' in self.cfg['rooms'][self.roomselect]['botadmins']) or mod:
            return True
        else:
            self.printl(user + " was denied!", "admincheck")
            try:
                self.chatbot.post_chat("@{}: Who even are you? (use !zip help)".format(user))
            except OSError:
                self.printl("message could not be sent - OSError", "admincheck")
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
            self.printl(user + " was denied!", "zipcheck")
            try:
                self.chatbot.post_chat("@{}: Who even are you? (use !zip help)".format(user))
            except OSError:
                self.printl("message could not be sent - OSError", "zipcheck")
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
        epilog=("Pretty meh")
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
    while not(kill):
        v = VolaZipBot(lister)
        v.joinroom()


def main_callable(room, zipper=False, passwd='*'):
    """Callable main method with arguments"""
    global kill
    lister = [room, zipper, passwd]
    while not(kill):
        v = VolaZipBot(lister)
        v.joinroom()


if __name__ == "__main__":
    main()

