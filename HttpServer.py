# python3

from abc import abstractmethod, ABCMeta
from email.message import Message
import typing
from threading import Thread, Lock, current_thread
from socket import socket, AF_INET, SOCK_STREAM
from email.parser import Parser
from functools import lru_cache
from urllib.parse import parse_qs, urlparse
from typing import BinaryIO

MAX_LINE = 64 * 1024
MAX_HEADERS = 100


class Request:
    def __init__(self, method: str, target: str, version: str, headers: Message, rfile: BinaryIO):
        self.method = method
        self.target = target
        self.version = version
        self.headers = headers
        self.rfile = rfile

    @property
    def path(self) -> str:
        return self.url.path

    @property
    @lru_cache(maxsize=None)
    def query(self):
        return parse_qs(self.url.query)

    @property
    @lru_cache(maxsize=None)
    def url(self):
        return urlparse(self.target)

    def body(self) -> bytes:
        size = self.headers.get('Content-Length')
        if not size:
            return None
        return self.rfile.read(int(size))


class Response:
    def __init__(self, status: int, reason: str, headers=None, body=None):
        self.status = status
        self.reason = reason
        self.headers = headers
        self.body = body


class HTTPError(Exception):
    def __init__(self, status: int, reason: str, body: str = None):
        super()
        self.status = status
        self.reason = reason
        self.body = body


class HTTPServer(metaclass=ABCMeta):
    def __init__(self, host: str, port: int):
        self._host = host
        self._port = port
        self._threads = set()
        self._lock = Lock()
        self._serv_sock = socket(AF_INET, SOCK_STREAM, proto=0)

    def __del__(self):
        self._serv_sock.close()

    def serve_forever(self):
        try:
            self._serv_sock.bind((self._host, self._port))
            self._serv_sock.listen()

            while True:
                conn, _ = self._serv_sock.accept()
                try:
                    th = Thread(target=self.serve_client, args=(conn,))
                    th.start()
                    self._threads.add(th)
                    # self.serve_client(conn)
                except Exception as e:
                    print('Client serving failed', e)
        finally:
            self._serv_sock.close()
            for th in self._threads:
                th.join()

    def serve_client(self, conn: socket):
        req = None
        try:
            req = self.parse_request(conn)
            resp = self.handle_request(req)
            self.send_response(conn, resp)
        except ConnectionResetError:
            conn = None
        except Exception as e:
            self.send_error(conn, e)

        if conn:
            conn.close()
        if req:
            req.rfile.close()

        self._lock.acquire()
        self._threads.remove(current_thread())
        self._lock.release()

    def parse_request(self, conn: socket) -> Request:
        rfile = conn.makefile('rb')
        method, target, ver = self.parse_request_line(rfile)
        headers = self.parse_headers(rfile)
        host = headers.get('Host')
        if not host:
            raise HTTPError(400, 'Bad request', 'Host header is missing')

        return Request(method, target, ver, headers, rfile)

    def parse_request_line(self, rfile: BinaryIO) -> tuple[str, str, str]:
        raw = rfile.readline(MAX_LINE + 1)
        if len(raw) > MAX_LINE:
            raise HTTPError(400, 'Bad request', 'Request line is too long')

        req_line = str(raw, 'iso-8859-1')
        words = req_line.split()
        if len(words) != 3:
            raise HTTPError(400, 'Bad request', 'Malformed request line')

        method, target, ver = words
        if ver != 'HTTP/1.1':
            raise HTTPError(505, 'HTTP Version Not Supported')
        return method, target, ver

    def parse_headers(self, rfile: BinaryIO) -> Message:
        headers = []
        while True:
            line = rfile.readline(MAX_LINE + 1)
            if len(line) > MAX_LINE:
                raise HTTPError(494, 'Request header too large')

            if line in (b'\r\n', b'\n', b''):
                break

            headers.append(line)
            if len(headers) > MAX_HEADERS:
                raise HTTPError(494, 'Too many headers')

        sheaders = b''.join(headers).decode('iso-8859-1')
        return Parser().parsestr(sheaders)

    @abstractmethod
    def handle_request(self, req: Request) -> Response:
        pass

    def send_response(self, conn: socket, resp: Response):
        wfile = conn.makefile('wb')
        status_line = f'HTTP/1.1 {resp.status} {resp.reason}\r\n'
        wfile.write(status_line.encode('iso-8859-1'))

        if resp.headers:
            for (key, value) in resp.headers:
                header_line = f'{key}: {value}\r\n'
                wfile.write(header_line.encode('iso-8859-1'))

        wfile.write(b'\r\n')

        if resp.body:
            wfile.write(resp.body)

        wfile.flush()
        print(f"send {resp.status} {resp.reason}")  # logging
        wfile.close()

    def send_error(self, conn: socket, err: HTTPError):
        try:
            status = err.status
            reason = err.reason
            body = (err.body or err.reason).encode('utf-8')
        except:
            status = 500
            reason = 'Internal Server Error'
            body = err.__str__().encode("utf-8")
        resp = Response(status, reason, [('Content-Length', len(body))], body)
        self.send_response(conn, resp)
