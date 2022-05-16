#!/usr/bin/python3

import json
import shutil
import time
from HttpServer import HTTPError, HTTPServer, Request, Response
from pathlib import Path
import os
from os.path import basename


def get_file_if_exists(path_str: str):
    path = Path(path_str)
    if path.is_file():
        return path.name
    else:
        return None

def path_to_dict(path):
    d = {'name': basename(path)}
    if os.path.isdir(path):
        d['type'] = "directory"
        d['children'] = [path_to_dict(os.path.join(path,x)) for x in os.listdir(path) if not basename(x).startswith('.')]
    else:
        d['type'] = "file"
    return d

class MyServer(HTTPServer):
    def __init__(self, host: str, port: int):
        super().__init__(host, port)


    def handle_request(self, req: Request):
        file_path = f".{req.path}"

        if(file_path == "./favicon.ico"):
            response = Response(404, "Not Found")
        elif(req.method == "PUT"):
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(req.body())
            response = Response(200, "OK")
        elif(req.method == "GET"):
            path = Path(file_path)

            if(path.is_file()):
                with open(file_path, "rb") as f:
                    file = f.read()
                headers = [
                    ('Content-Type', 'application/octet-stream'),
                    ('Content-Disposition', f"attachment; filename=\"{os.path.basename(file_path)}\""),
                    ('Content-Length', len(file))
                ]
                response = Response(200, "OK", headers, file)
            elif(path.exists()):
                folder = path_to_dict(file_path)
                folder = json.dumps(folder, indent = 4).encode("utf-8")
                headers = [
                    ('Content-Type', 'application/json; charset=utf-8'),
                    ('Content-Length', len(folder))
                ]
                response = Response(200, "OK", headers, folder)
            else:
                response = Response(404, "No such file", body=b"No such file")
        elif(req.method == "HEAD"):
            path = Path(file_path)

            if(path.is_file()):
                headers = [
                    ('Content-Length', os.path.getsize(file_path)),
                    ('Last-Modified', time.ctime(os.path.getmtime(file_path))),
                    ('Created', time.ctime(os.path.getctime(file_path))),
                    ('File-Name', basename(file_path))
                ]
                response = Response(200, "OK", headers)
            else:
                response = Response(400, "Not a file")
        elif(req.method == "DELETE"):
            path = Path(file_path)
            if(path.is_file()):
                os.remove(file_path) 
                response = Response(200, "Ok")
            elif(path.exists()):
                shutil.rmtree(file_path)
                response = Response(200, "Ok")
            else:
                response = Response(404, "No such file/folder", body=b"No such file/folder")
        elif(req.method == "COPY"):
            source = '.'+req.headers["X-Copy-From"]
            shutil.copyfile(source, file_path)
            response = Response(200, "Ok")
        else:
            raise HTTPError(404, "Not found")
        return response


if __name__ == '__main__':
    host = "localhost"
    port = 8003

    serv = MyServer(host, port)
    try:
        serv.serve_forever()
    except KeyboardInterrupt:
        pass
