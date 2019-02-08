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

VERSION = "2.1.2"

def log(msg):
    print("RCREPL: {}".format(msg))

EDITOR_ID = '-- editor'.encode('utf-8')

def new_queue():
    return queue.Queue(maxsize=10000000)

REC_MAX_LENGTH = 4096

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
    def __init__(self, prompt, read_pipe, write_pipe):
        self.read_pipe, self.write_pipe = read_pipe, write_pipe
        self.thread_exit = False
        self.process = None
        self.prompt = prompt

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
        self.process.expect_exact([self.prompt], timeout=1000)

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

class ReplServer:
    def __init__(self, prompt, cmd, args, listenon, output_processor):
        self.output_processor = output_processor
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(listenon)
        self.socket = serversocket

        editor = Editor()
        self.editor = editor
        command_read_pipe, command_write_pipe = os.pipe()

        repl = ReplProcess(prompt, command_read_pipe, command_write_pipe)
        repl.start(cmd, args, self.output_callback)

        self.command_queue = command_write_pipe
        self.thread = threading.Thread(target=self.server, daemon=True)

    def start(self):
        self.thread.start()
        self.thread.join()

    def output_callback(self, output):
        self.editor.set_status(output, self.output_processor(output))

    def server(self):
        log(VERSION)
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

class WatchServer:
    def __init__(self, cmd_with_args, listenon, output_processor):
        self.cmd_with_args = cmd_with_args
        self.output_processor = output_processor
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(listenon)
        self.socket = serversocket
        editor = Editor()
        self.editor = editor
        self.thread = threading.Thread(target=self.server, daemon=True)

    def start(self):
        self.thread.start()
        self.thread.join()

    def output_callback(self, output):
        self.editor.set_status(output, self.output_processor(output))

    def server(self):
        log(VERSION)
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
                result = subprocess.run(self.cmd_with_args, stdout=subprocess.PIPE)
                self.output_callback(result.stdout.decode())
