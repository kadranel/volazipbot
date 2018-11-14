import string
import random
import requests
from requests_toolbelt.multipart import encoder


def id_generator(size=7, chars=string.ascii_uppercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


def namereplace(name):
    return name.replace('*', '').replace(':', '')


def replaceFName(name):
    return name.replace('#', '').replace('<', '').replace('>', '').replace('$', '').replace('%', '').replace('!', '').replace('&', '').replace('*', '').replace('', '').replace('{', '').replace('}', '').replace('?', '').replace('"', '').replace('/', '').replace(':', '').replace('/', '').replace('@', '').replace(' ', '_')


def zipNameReplace(name):
    return name.replace(' ', '#').replace('<', '#').replace('>', '#').replace('$', '#').replace('%', '#').replace('!', '#').replace('&', '#').replace('*', '#').replace('_', '#').replace('{', '#').replace('}', '#').replace('?', '#').replace('"', '#').replace('/', '#').replace(':', '#').replace('/', '#').replace('@', '#').replace(' ', '#')


def anonfileupload(filepath):
    URL = 'https://anonfile.com/api/upload'
    # files = {'file': open(filepath, 'rb')}
    spl = filepath.split("/")
    filename = spl[-1]
    with open(filepath, 'rb') as upload_file:
        data = encoder.MultipartEncoder({
            "file": (filename, upload_file, "application/octet-stream"),
        })
        headers = {"Content-Type": data.content_type}
        r = requests.post(URL, data=data, headers=headers)
    dat = r.json()
    return dat



