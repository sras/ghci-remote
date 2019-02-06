import sys
import socket
import json
import os
import time
import tempfile
try:
    from pynvim import attach, NvimError
except ImportError:
    print("You need 'neovim' python library to run this adapter. Please install it using pip")

def get_nvim():
    return attach('socket', path=get_nvim_address())

def wait_for_init():
    fn = tempfile.gettempdir() + "/rcghci"
    while True:
        try:
            with open(fn, "r") as f:
                port = f.read()
                break
        except FileNotFoundError:
            print("RCGHCI status file not found. Looking after a bit...")
            time.sleep(3)
        except Exception as e:
            exception(e)
    return int(port)

def main():
    port = wait_for_init()
    nvim = get_nvim()
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.connect(('0.0.0.0', port))
    client_socket.sendall("-- editor neovim".encode('utf-8'))
    msg = bytes()
    while True:
        a = client_socket.recv(1024)
        msg = msg + a
        try:
            v = json.loads(msg.decode())
            msg = bytes()
            process_message(v, nvim)
        except Exception as v:
            if len(a) == 0:
                exception(v)
                break
            else:
                pass

def exception(e):
    print("There was an error : {} - {}".format(e.__class__.__name__, e))

def get_nvim_address():
    return os.environ['NVIM_LISTEN_ADDRESS']

def build_error_list(items):
    ret = []
    for (idx, e) in enumerate(items['errors']):
        for (idx1, ln) in enumerate(e['text'].split('\n')):
            if idx1 == 0:
                ret.append({'filename': e['file_name'], 'lnum': e['line'], 'col': e['column'], 'text': ln, 'nr': idx, 'type': 'E'})
            else:
                ret.append({'text': ln, 'nr': idx, 'type': 'E'})

    for (idx, e) in enumerate(items['warnings']):
        for (idx1, ln) in enumerate(e['text'].split('\n')):
            if idx1 == 0:
                ret.append({'filename': e['file_name'], 'lnum': e['line'], 'col': e['column'], 'text': ln, 'nr': idx, 'type': 'W'})
            else:
                ret.append({'text': ln, 'nr': idx, 'type': 'W'})
    return ret

def call_vim_function(fnc, nvim):
        try:
            nvim.call(fnc)
        except NvimError as e:
            print("Warning: No function {} defined in Neovim.".format(fnc))
            pass

def process_message(msg, nvim):
    if msg == 'indicate_activity':
        call_vim_function('RCGHCIIndicateActivity')
    elif 'status' in msg:
        try:
            elist = build_error_list(msg['status'])
            nvim.call('setqflist', [], 'r', {"items": elist, "title": "RCGHCI Error list"})
            if len(msg['status']['errors']) > 0:
                call_vim_function('RCGHCIIndicateError', nvim)
            elif len(msg['status']['warnings']) > 0:
                call_vim_function('RCGHCIIndicateWarnings', nvim)
            else:
                call_vim_function('RCGHCIIndicateSuccess', nvim)
        except Exception as v:
            exception(v)

main()
