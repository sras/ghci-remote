import sys
import socket
import json
import os
import time
import tempfile

def wait_for_init():
    fn = tempfile.gettempdir() + "/rcghci"
    while True:
        try:
            with open(fn, "r") as f:
                port = f.read()
                break
        except FileNotFoundError:
            print("RCGHCI status file not found. Looking after a bit...")
            time.sleep(1)
        except Exception as e:
            exception(e)
    return (int(port), "")

def main():
    (port, nvim_addr) = wait_for_init()
    print(port)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    client_socket.connect(('0.0.0.0', port + 1))
    msg = bytes()
    while True:
        a = client_socket.recv(1024)
        msg = msg + a
        try:
            v = json.loads(msg.decode())
            msg = bytes()
            process_message(v)
        except Exception as v:
            print(v)
            pass

def exception(e):
    print("There was an error : {}".format(e))

def get_error_file():
    try:
        return os.environ['RCGHCI_ERROR_FILE']
    except:
        return None

def write_error_file(blocks):
    error_file = get_error_file()
    if error_file is not None:
        try:
            with open(error_file, "w") as text_file:
                for (idx, b) in enumerate(blocks["errors"]):
                    text_file.write(b.strip())
                    text_file.write("\n\n")
                for (idx, b) in enumerate(blocks["warnings"]):
                    text_file.write(b.strip())
                    text_file.write("\n\n")
        except:
            log("Error file write error", "There was an error writing errors to file {}".format(error_file))
    else:
        print("Error file not set")

def process_message(msg):
    if msg == 'indicate_activity':
        pass
    elif 'status' in msg:
        try:
            write_error_file(msg['status'])
        except Exception as v:
            exception(v)

main()
