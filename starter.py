from subprocess import check_output
import os
import time
from datetime import datetime, timedelta
import json


# This has no implementation for windows since I found it pretty useless to automate this on windows.

def screen_present(name):
    """checks if a screen exists"""
    if os.name == "nt":
        print("Windows is currently not implemented here.")
        return False
    if os.name == "posix":
        var = check_output(["screen -ls; true"], shell=True)

        if "." + name + "\\t(" in str(var):
            print(f"{name} is running")
            return True
        else:
            print(f"{name} is not running")
            return False


def closer(cfg):
    """closes rooms if they stopped working or if they were """
    if os.name == "nt":
        print("Windows is currently not implemented here.")
        return False
    if os.name == "posix":
        execution_path = os.path.dirname(os.path.abspath(__file__))

        json_file = open(f'{execution_path}/starter_config.json', 'r')
        starter_cfg = json.load(json_file)
        json_file.close()
        save_cfg = False

        for key in cfg['rooms'].keys():
            if screen_present(str(key)):
                print(f"Checking on screen session {str(key)}:")
                cmd = f"screen -S {str(key)} -p0 -X hardcopy {cfg['folderpath']}{str(key)}.log"
                print(cmd)
                os.system(cmd)
                time.sleep(5)
                f = open(f"{cfg['folderpath']}{str(key)}.log", 'r', errors='replace')
                lines = f.readlines()
                j = 0
                for line in reversed(lines):
                    if 'create_session_file' in str(line) or '[Errno' in str(line) or cfg['rooms'][key]['restart']:
                        splitted = str(line).split('create_session_file')
                        formatted = splitted[0].replace('[', '').replace(']', '')
                        try:
                            datetime_object = datetime.strptime(formatted, "%Y-%m-%d--%H:%M:%S")
                            refresh_time = datetime.now() - timedelta(minutes=2)
                            if datetime_object < refresh_time or cfg['rooms'][key]['restart']:
                                print("Need to kill old session")
                                cmd = f"screen -S {str(key)} -p0 -X stuff $'\003'"
                                print(cmd)
                                os.system(cmd)
                                time.sleep(1)
                        except ValueError:
                            print("Need to kill old session")
                            cmd = f"screen -S {str(key)} -p0 -X stuff $'\003'"
                            print(cmd)
                            os.system(cmd)
                            time.sleep(1)

                    if str(line[0:1]) == '[':
                        break
                    j = j + 1

                os.remove(f"{cfg['folderpath']}{str(key)}.log")
            if cfg['rooms'][key]['restart'] == 1:
                starter_cfg['rooms'][key]['restart'] = 0
                save_cfg = True

        if save_cfg:
            json_file = open(f'{execution_path}/starter_config.json', 'w')
            json.dump(starter_cfg, json_file)
            json_file.close()
        return True


def starter(cfg):
    """Starts all rooms defined in starter_config.json"""
    if os.name == "nt":
        print("Windows is currently not implemented here.")
        return False
    if os.name == "posix":
        for key in cfg['rooms'].keys():
            if not screen_present(str(key)) and cfg['rooms'][key]['join'] == 1:
                print("Starting new screen session.")
                if cfg['rooms'][key]['password'] == '':
                    cmd = f"screen -dmS {str(key)} {cfg['python']} {cfg['folderpath']}bot.py -r {str(key)} -z {str(cfg['rooms'][key]['zipper'])}"
                else:
                    cmd = f"screen -dmS {str(key)} {cfg['python']} {cfg['folderpath']}bot.py -r {str(key)} -z {str(cfg['rooms'][key]['zipper'])} -p '{str(cfg['rooms'][key]['password'])}'"
                print(cmd)
                os.system(cmd)
                time.sleep(60)
            else:
                print("Room could not be joined - (join == 0)")

        return True


def start_single_room(roomname, password="", zipper=0):
    """Starts a single bot instead of all"""
    if os.name == "nt":
        print("Windows is currently not implemented here.")
        return "Windows is currently not implemented here."
    if os.name == "posix":
        execution_path = os.path.dirname(os.path.abspath(__file__))
        json_file = open(f'{execution_path}/starter_config.json', 'r')
        cfg = json.load(json_file)
        json_file.close()
        if zipper != 1:
            zipper = 0
        if not cfg['kill']:
            if not screen_present(roomname):
                if password == "":
                    cmd = f"screen -dmS {roomname} {cfg['python']} {cfg['folderpath']}bot.py -r {roomname} -z {zipper}"
                else:
                    cmd = f"screen -dmS {roomname} {cfg['python']} {cfg['folderpath']}bot.py -r {roomname} -z {zipper} -p '{password}'"

                os.system(cmd)
                time.sleep(2)
                if screen_present(roomname):
                    if roomname in cfg['rooms'].keys():
                        cfg['rooms'][roomname]['join'] = 1
                        cfg['rooms'][roomname]['restart'] = 0
                    else:
                        cfg['rooms'][roomname] = {}
                        cfg['rooms'][roomname]['zipper'] = zipper
                        cfg['rooms'][roomname]['password'] = password
                        cfg['rooms'][roomname]['restart'] = 0
                        cfg['rooms'][roomname]['join'] = 1

                    json_file = open(f'{execution_path}/starter_config.json', 'w')
                    json.dump(cfg, json_file)
                    json_file.close()
                    return f"#{roomname} was joined."

                else:
                    return f"#{roomname} could not be joined - unknown error."

            else:
                return f"#{roomname} is already running or in the starter_config.json."
        else:
            return f"#{roomname} could not be joined, bot is killed right now."


def main():
    """Gets called when starter.py gets executed"""
    if os.name == "nt":
        print("Windows is currently not implemented here.")
        return False
    if os.name == "posix":
        execution_path = os.path.dirname(os.path.abspath(__file__))
        json_file = open(f'{execution_path}/starter_config.json', 'r')
        cfg = json.load(json_file)
        json_file.close()
        if not cfg['kill']:
            closer(cfg)
            starter(cfg)
        return True


if __name__ == "__main__":
    main()
