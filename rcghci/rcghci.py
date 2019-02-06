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

def log(msg):
    print("RCGHCI: {}".format(msg))

error_re = re.compile(r' (.*):(\d+):(\d+): (warning|error):')
ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
neovim_socket = None

EDITOR_ID = '-- editor'.encode('utf-8')

def new_queue():
    return queue.Queue(maxsize=10000000)

try:
    COMMAND_PORT = int(os.environ['RCGHCI_PORT'])
except:
    COMMAND_PORT = 1880

with open(tempfile.gettempdir() + "/rcghci", "w") as f:
    f.write(str(COMMAND_PORT))

GUI_PORT = COMMAND_PORT + 2

REC_MAX_LENGTH = 4096

try:
    PROMPT = os.environ['RCGHCI_PROMPT']
    if len(PROMPT) < 5:
        log("ERROR ! Empty or short prompt found. Please use a prompt with more than five characters. You can configure the GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
        sys.exit(0)
except KeyError:
        log("ERROR ! The environment variable `RCGHCI_PROMPT` which is supposed to hold the custom ghci prompt was not found. You can set a custom GHCI prompt by adding the line ':set prompt <prompt>' to ~/.ghci file. Then configure rcghci to use that prompt by setting the RCGHCI_PROMPT env variable using 'export RCGHCI_PROMPT=<prompt>' command from termial, before starting RCGHCI. This is so that RCGHCI script can detect when a command has finished execution.")
        sys.exit(0)

log("Using prompt : {}".format(PROMPT))

def remove_init_file():
    os.remove(tempfile.gettempdir() + "/rcghci")

class Editor:
    def __init__(self):
        self.editor_connections = []

    def add_editor(self, socket, idf):
        self.editor_connections.append((socket, idf))

    def send_msg(self, msg):
        new = []
        log("Sending message")
        for (c, idf) in self.editor_connections:
             try:
                 s = c.sendall(json.dumps(msg).encode())
                 new.append((c, idf))
             except Exception as e:
                 log("Error in Sending : {} to {}".format(str(e), idf))
                 pass
        self.editor_connections = new

    def indicate_activity(self):
        self.send_msg("indicate_activity")

    def set_status(self, output, errors):
        self.send_msg({"status": errors, "output": output})

class Gui:
    def set_log(self, content):
        pass

    def set_status(self, output, errors):
        self.set_output(output)
        self.set_errors(errors)

    def set_errors(self, errors):
        pass

    def set_output(self, output):
        try:
            ofile = os.environ['RCGHCI_OUTPUT_FILE']
            try:
                with open(ofile, "w") as text_file:
                    text_file.write(output)
            except:
                log("Output file write error", "There was an error writing output to file {}".format(ofile))
        except:
            pass

    def clear_log(self):
        pass

    def add_log(self, log):
        pass
    
    def log_command(self, log):
        pass

    def is_errors_enabled(self):
        return True

    def is_warnings_enabled(self):
        return True

    def set_ghci(self, ghci):
        pass

class GHCIProcess:
    def __init__(self, read_pipe, write_pipe):
        self.read_pipe, self.write_pipe = read_pipe, write_pipe
        self.thread_exit = False
        self.process = None
        self.gui = None
        self.error_blocks = make_error_blocks("");

    def set_editor(self, editor):
        self.editor = editor

    def get_stat(self):
        if self.process:
            return get_ghci_process_stat(self.process.pid)
        else:
            return None

    def set_gui(self, gui):
        self.gui = gui

    def quit(self):
        self.thread_exit = True
        os.write(self.write_pipe, ":quit".encode())

    def start(self):
        self.thread = threading.Thread(target=self.thread_callback, daemon=True)
        self.thread.start()
        return self.thread

    def is_running(self):
        if self.process:
            return self.process.isalive()
        else:
            return False

    def do_startup(self):
        self.process = pexpect.spawn("stack", ["ghci"] + sys.argv[1:], encoding=sys.stdout.encoding)
        self.process.logfile_read = sys.stdout # Set this to 'sys.stdout' to enable logging...
        outlines = []
        self.process.expect_exact([PROMPT], timeout=1000)
        output = self.process.before.replace('\r\n', '\n') + '\n'
        # output = ansi_escape.sub('', output)
        self.gui.set_log("Got prompt > ")
        self.error_blocks = make_error_blocks(output)
        self.gui.set_status(output, self.error_blocks)
        self.editor.set_status(output, self.error_blocks)

    def thread_callback(self):
        self.do_startup()
        while True: # command execution loop
            if self.thread_exit:
                self.thread_exit = False
                return
            self.gui.clear_log()
            self.error_blocks = make_error_blocks("");
            self.gui.add_log("Waiting for command...")
            try:
                ch = os.read(self.read_pipe, 1000).decode().strip()
            except Exception as err :
                print("An exception was caught: {}".format(err))
                continue;
            for c in ch.split(','):
                self.gui.log_command(c)
                if self.execute_config_command(c):
                    continue
                self.gui.set_log("Executing `{}`...".format(c))
                command = c
                self.process.sendline(command)
                self.editor.indicate_activity()
                outlines = []
                try:
                    self.process.expect_exact([PROMPT], timeout=1000)
                except Exception as err :
                    print("Exception while waiting for the GHCI prompt! This is alright if you stopped the GHCI process.")
                    continue;
                output = self.process.before.replace('\r\n', '\n')
                output = ansi_escape.sub('', output)
                self.error_blocks = merge_blocks(self.error_blocks, make_error_blocks(output))
                self.gui.set_status(output, self.error_blocks)
                self.editor.set_status(output, self.error_blocks)
                if len(self.error_blocks["errors"]) > 0:
                    break

    def execute_config_command(self, ghci_command):
       if ghci_command == 'stop_ghci':
           self.process.terminate(force=True)
           self.thread_exit = True
           return True
       return False

class CommandServer:
    def __init__(self, socket, command_queue):
        self.socket = socket
        self.command_queue = command_queue
        self.thread = threading.Thread(target=self.server, daemon=True)

    def set_editor(self, editor):
        self.editor = editor

    def server(self):
        log("Starting command server")
        self.socket.listen(5)
        while True:
            (clientsocket, address) = self.socket.accept()
            ghci_command = clientsocket.recv(REC_MAX_LENGTH)
            if ghci_command.startswith(EDITOR_ID):
                self.editor.add_editor(clientsocket, ghci_command[len(EDITOR_ID):])
                log("Editor adapter connected")
            else:
                log("Command recieved : {}".format(ghci_command))
                clientsocket.sendall("ok".encode())
                clientsocket.close()
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

def print_stats(blocks):
    if blocks is None:
        return "Not an error/warning output"
    else:
        return("errors: {}, warnings : {}".format(len(blocks["errors"]), len(blocks["warnings"])))

def format_memory_info(mi):
    return "{}".format(convert_size(mi.rss))

def get_ghci_process_stat(pid):
    if has_psutil:
        try:
            return " | ".join(["pid={}{}, Mem = {}({}%)".format(x.pid, "*" if x.ppid() == pid else "", format_memory_info(x.memory_info()), round(x.memory_percent(), 2)) for x in psutil.process_iter() if x.name() =="ghc"])
        except:
            return "Not available"
    else:
        return "Not available"

def convert_size(size_bytes):
  if size_bytes == 0:
      return "0B"
  size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
  i = int(math.floor(math.log(size_bytes, 1024)))
  p = math.pow(1024, i)
  s = round(size_bytes / p, 2)
  return "%s %s" % (s, size_name[i])

def _main():
        global command_read_pipe, command_write_pipe
        command_read_pipe, command_write_pipe = os.pipe()
        
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(('0.0.0.0', COMMAND_PORT))
        editor = Editor()

        ghci = GHCIProcess(command_read_pipe, command_write_pipe)
        ghci.set_editor(editor)
        ghci.start()

        command_server = CommandServer(serversocket, command_write_pipe)
        command_server.set_editor(editor)
        command_server.thread.start()

        gui = Gui()
        ghci.set_gui(gui)
        gui.set_ghci(ghci)

        ghci.thread.join()

def main():
    try:
        _main()
    except KeyboardInterrupt:
        remove_init_file()
