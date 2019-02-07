import socket
import subprocess
import io
import sys
import time
import threading
import sys
import queue
import collections
import math
import re
import pipes
import os
import select
import pexpect
import pexpect.exceptions
import json
import tempfile

VERSION = "2.1.2"

def log(msg):
    print("RCGHCI: {}".format(msg))

EDITOR_ID = '-- editor'.encode('utf-8')

def new_queue():
    return queue.Queue(maxsize=10000000)

REC_MAX_LENGTH = 4096

def remove_init_file():
    os.remove(tempfile.gettempdir() + "/rcghci")

class Editor:
    def __init__(self):
        self.editor_connections = []

    def add_editor(self, socket, idf):
        self.editor_connections.append((socket, idf))

    def send_msg(self, msg):
        new = []
        for (c, idf) in self.editor_connections:
             try:
                 s = c.sendall(json.dumps(msg).encode())
                 new.append((c, idf))
             except Exception as e:
                 log("Error in Sending : {} to {}".format(str(e), idf))
                 pass
        self.editor_connections = new

    def indicate_activity(self):
        self.send_msg({"op": 'indicate_activity'})

    def set_status(self, output, errors):
        self.send_msg({"op": "status_update", "data": {"status": errors, "output": output}})

class ReplProcess:
    def __init__(self, read_pipe, write_pipe):
        self.read_pipe, self.write_pipe = read_pipe, write_pipe
        self.thread_exit = False
        self.process = None
        self.error_blocks = make_error_blocks("");

    def quit(self):
        os.write(self.write_pipe, ":quit".encode())

    def start(self, cmd, args, output_callback):
        self.thread = threading.Thread(target=self.thread_callback, args=(cmd, args, output_callback), daemon=True)
        self.thread.start()
        return self.thread

    def is_running(self):
        if self.process:
            return self.process.isalive()
        else:
            return False

    def do_startup(self, cmd, args, output_callback):
        self.output_callback = output_callback
        self.process = pexpect.spawn(cmd, args, encoding=sys.stdout.encoding)
        self.process.logfile_read = sys.stdout # Set this to 'sys.stdout' to enable logging...
        outlines = []
        self.expect()
        output = self.process.before.replace('\r\n', '\n') + '\n'
        self.output_callback(output)

    def expect(self):
        self.process.expect_exact([PROMPT], timeout=1000)

    def thread_callback(self, cmd, args, output_callback):
        self.do_startup(cmd, args, output_callback)
        while True: # command execution loop
            try:
                command = os.read(self.read_pipe, 1000).decode().strip()
            except Exception as err :
                print("An exception was caught: {}".format(err))
                continue;
            self.process.sendline(command)
            try:
                self.expect()
            except Exception as err :
                print("Exception while waiting for the prompt! This is alright if you stopped the REPL process.")
                continue;
            output = self.process.before.replace('\r\n', '\n')
            self.output_callback(output)

class MainServer:
    def __init__(self, cmd, args, listenon):
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(listenon)
        self.socket = serversocket

        editor = Editor()
        self.editor = editor
        command_read_pipe, command_write_pipe = os.pipe()

        repl = ReplProcess(command_read_pipe, command_write_pipe)
        repl.start(cmd, args, self.output_callback)

        self.command_queue = command_write_pipe
        self.thread = threading.Thread(target=self.server, daemon=True)

    def start(self):
        self.thread.start()
        self.thread.join()

    def output_callback(self, output):
        print(output)
        self.editor.set_status(output, make_error_blocks(output))

    def server(self):
        log("Starting command server")
        self.socket.listen(5)
        while True:
            (clientsocket, address) = self.socket.accept()
            ghci_command = clientsocket.recv(REC_MAX_LENGTH)
            if ghci_command.startswith(EDITOR_ID):
                editor_id = ghci_command[len(EDITOR_ID):].decode().strip()
                self.editor.add_editor(clientsocket, editor_id )
                log("Editor adapter {} connected...".format(editor_id))
            else:
                log("Command recieved : {}".format(ghci_command))
                clientsocket.sendall("ok".encode())
                clientsocket.close()
                self.editor.indicate_activity()
                os.write(self.command_queue, ghci_command)

def make_error_blocks(content):
    errors = []
    warnings = []
    if content is not None and len(content) > 0:
        if "\n\n" in content:
            blocks = content.split("\n\n")
        else:
            blocks = content.split("\r\n")
        for b in blocks:
            lines = b.strip().split("\n")
            for idx, line in enumerate(lines):
                try:
                    (file_name, line, column, type_, msg) = line.split(":")[0:5]
                except Exception as err :
                    continue
                type_ = type_.strip()
                err_msg = "\n".join(lines[idx:])
                full_item =  {'file_name': file_name, 'line': line, 'column' : column, 'text': err_msg }
                if "error" in type_:
                    errors.append(full_item)
                elif "warning" in type_:
                    warnings.append(full_item)
    return {"errors" : errors, "warnings": warnings}

def merge_blocks(errors1, errors2):
    return {"errors": errors1['errors'] + errors2['errors'], "warnings": errors1['warnings'] + errors2['warnings']}

def _main():
    global PROMPT
    print("RCGHCI Version {}".format(VERSION))
    try:
        COMMAND_PORT = int(os.environ['RCGHCI_PORT'])
    except:
        COMMAND_PORT = 1880

    with open(tempfile.gettempdir() + "/rcghci", "w") as f:
        f.write(str(COMMAND_PORT))

    try:
        PROMPT = os.environ['RCGHCI_PROMPT']
        if len(PROMPT) < 5:
            log("ERROR ! Empty or short prompt found. Please use a prompt with more than five characters. You can configure the GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
            sys.exit(0)
    except KeyError:
            log("ERROR ! The environment variable `RCGHCI_PROMPT` which is supposed to hold the custom ghci prompt was not found. You can set a custom GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
            sys.exit(0)
    log("Using prompt : {}".format(PROMPT))
    master_server = MainServer("stack", ["ghci"] + sys.argv[1:], ('0.0.0.0', COMMAND_PORT))
    master_server.start()

def main():
    try:
        _main()
    except KeyboardInterrupt:
        remove_init_file()
