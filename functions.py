import string
import random
import requests
from requests_toolbelt.multipart import encoder


def id_generator(size=7, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def msg_formatter(msg):
    prefix = ''
    if msg.purple:
        prefix += "@"
    if msg.owner:
        prefix += "$"
    if msg.janitor:
        prefix += "~"
    if msg.green:
        prefix += "+"
    if msg.system:
        prefix += "%"
    return f"<{prefix}{msg.nick} | {msg}>"


def anonfile_upload(filepath):
    url = 'https://anonfile.com/api/upload'
    spl = filepath.split("/")
    filename = spl[-1]
    with open(filepath, 'rb') as upload_file:
        data = encoder.MultipartEncoder({
            "file": (filename, upload_file, "application/octet-stream"),
        })
        headers = {"Content-Type": data.content_type}
        r = requests.post(url, data=data, headers=headers)
    dat = r.json()
    return dat


def input_replace(text):
    text = str(text).replace(" ", "")
    text = text.replace("#", "")
    text = text.replace("%", "")
    text = text.replace("§", "")
    text = text.replace("&", "")
    text = text.replace("/", "")
    text = text.replace("(", "")
    text = text.replace(")", "")
    text = text.replace("{", "")
    text = text.replace("}", "")
    text = text.replace("[", "")
    text = text.replace("]", "")
    text = text.replace("!", "")
    text = text.replace(".", "")
    text = text.replace("-", "")
    text = text.replace("=", "")
    text = text.replace("´", "")
    text = text.replace("`", "")
    text = text.replace("~", "")
    text = text.replace("*", "")
    return text
