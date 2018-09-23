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

try:
    import psutil
    has_psutil = True
except:
    has_psutil = False

try:
    import tkinter
    from tkinter import messagebox
    has_gui = True
except:
    has_gui = False
    print("TkInter module not available, or there was an error initializing it. Proceeding without gui")

try:
    from neovim import attach
    has_neovim = True
except:
    has_neovim = False

error_re = re.compile(r' (.*):(\d+):(\d+): (warning|error):')
ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
neovim_socket = None

def new_queue():
    return queue.Queue(maxsize=10000000)

def open_file_and_go_to_line_column(file_name, line, col):
    if has_neovim and neovim_socket is not None:
        try:
            nvim = attach('socket', path=neovim_socket)
            try:
                nvim.command('e +{} {}'.format(r'call\ cursor({},{})|execute\ "normal"\ "V"'.format(line, col), file_name))
            except:
                print("Error executing command at neovim")
        except:
            print("Error connecting to neovim")

def send_neovim_command(command):
    if has_neovim and neovim_socket is not None:
        try:
            nvim = attach('socket', path=neovim_socket)
            try:
                nvim.command(command)
            except Exception as err:
                print("Error executing command at neovim: {}", str(err))
        except:
            print("Error connecting to neovim")

def neovim_indicate_activity():
    send_neovim_command("call GHCIBridgeSetActivity()")

def neovim_indicate_error(blocks):
    if blocks is not None:
        if len(blocks["errors"]) > 0:
            send_neovim_command("call GHCIBridgeSetErrors()")
        elif len(blocks["warnings"]) > 0:
            send_neovim_command("call GHCIBridgeSetWarnings()")
        else:
            send_neovim_command("call GHCIBridgeSetSuccess()")

def open_completion(offset, completions):
    if has_neovim and neovim_socket is not None:
        nvim = attach('socket', path=neovim_socket)
        print("call complete(col('.') - {}, {})".format(offset, str(completions)))
        nvim.command("call complete(col('.') - {}, {})".format(offset, str(completions)))

def get_filename_line_col_from_error(content):
    m = error_re.search(content)
    if m is not None:
        return m.group(1,2,3)
    else:
        return None

if has_gui:
    class GRText(tkinter.Text):
        def __init__(self, parent, *args, **kw):
            tkinter.Text.__init__(self, parent, *args, **kw)
            self.config(bg="#222222", padx=5, pady=5, state="disabled", highlightthickness=0, bd=0)

        def replace_content(self, content, *args, **kw):
            self.config(state="normal")
            self.delete("1.0", tkinter.END)
            self.insert("0.0", content, *args, **kw)
            self.config(state="disabled")

        def append_content(self, content, *args, **kw):
            self.config(state="normal")
            self.insert(tkinter.END, content, *args, **kw)
            self.config(state="disabled")

    class GRErrorContainer(GRText):
        def __init__(self, parent, *args, **kw):
            GRText.__init__(self, parent, *args, **kw)
            self.link_ix = 0

        def replace_content(self, content, *args, **kw):
            GRText.replace_content(self, content, *args, **kw)
            self.link_ix = 0

        def append_error(self, error, *args, **kw):
            self.config(state="normal")
            tag_name = 'link_tag_{}'.format(self.link_ix)
            self.link_ix = self.link_ix + 1
            self.tag_configure(tag_name)
            file_loc = get_filename_line_col_from_error(error)
            if file_loc is not None:
                (file_name, line, col) = file_loc
                self.tag_bind(tag_name, "<1>", lambda event: open_file_and_go_to_line_column(file_name, line, col))
                self.tag_bind(tag_name, "<Enter>", lambda event: self.configure(cursor="hand1"))
                self.tag_bind(tag_name, "<Leave>", lambda event: self.configure(cursor="arrow"))
                self.insert(tkinter.END, error, tag_name)
            else:
                self.insert(tkinter.END, error)
            self.config(state="disabled")

    class GRWindow(tkinter.PanedWindow):
        def __init__(self, parent, *args, **kw):
            tkinter.PanedWindow.__init__(self, parent, *args, **kw)
            self.config(width=900, bg="#000000", bd=0, sashpad=1, sashwidth=0)
            self.pack(fill=tkinter.BOTH, expand=0)

    class GRLockableEntry(tkinter.Frame):
        def __init__(self, parent, *args, **kw):
            textvar = kw.pop('textvariable', None)
            tkinter.Frame.__init__(self, parent, *args, **kw)
            tv = tkinter.StringVar()
            tv.set("Error file")
            self.lock_status = tkinter.IntVar()
            self.lock_status.set(0)
            label = tkinter.Label(self, textvariable=tv, bg="#222222", fg="white")
            self.widget_lock = tkinter.Checkbutton(self, command=self.set_entry_state, text = "Lock", variable = self.lock_status, onvalue = 1, offvalue = 0, fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
            self.entry_widget = tkinter.Entry(self, width=30, fg="#00ff00", bg="#000000", disabledbackground="#666666", disabledforeground="black", state=tkinter.DISABLED, textvariable=textvar, bd=0, highlightthickness=0, insertbackground="green")
            self.entry_widget.pack(side=tkinter.LEFT, padx=5)
            self.widget_lock.pack(side=tkinter.LEFT)
            self.set_entry_state()

        def set_entry_state(self):
            if self.lock_status.get() == 1:
                self.entry_widget.config(state="disabled")
            else:
                self.entry_widget.config(state="normal")

class Gui:
    def __init__(self, has_gui):
        self.log_length = 0
        self.has_gui = has_gui
        if has_gui:
            self.root = tkinter.Tk()
            self.root.geometry("1360x768")
            self.root.wm_title("RC GHCI")
            self.seconds_since_output = 0
            self.time_string = tkinter.StringVar()
            self.time_string.set("No output yet")
            self.error_file_var = tkinter.StringVar()
            try:
                self.error_file_var.set(os.environ['RCGHCI_ERROR_FILE'])
            except:
                pass
            self.display_errors_var = tkinter.IntVar()
            self.error_file_lock = tkinter.IntVar()
            self.display_warnings_var = tkinter.IntVar()
        self.errors = None
        self.ghci = None
        self.initialize()

    def set_errors(self, errors):
        self.errors = errors
        self.update_errors()

    def start_gui(self):
        try:
            if self.has_gui:
                self.root.mainloop()
                self.ghci_quit()
            else:
                self.ghci.thread.join()
        except KeyboardInterrupt:
            self.ghci_quit()

    def set_ghci(self, ghci):
        self.ghci = ghci
        ghci.set_gui(self)

    def clear_log(self):
        if self.has_gui:
            self.log_widget.replace_content('')
            self.log_widget.see(tkinter.END)

    def set_log(self, content):
        if self.has_gui:
            self.log_widget.replace_content(content)
            self.log_widget.see(tkinter.END)

    def add_log(self, content):
        if self.has_gui:
            self.log_length += len(content)
            if (self.log_length > 10000):
                self.log_widget.replace_content(content)
                self.log_length = len(content)
                self.log_widget.see(tkinter.END)
            else:
                self.log_widget.append_content(content)
                self.log_widget.see(tkinter.END)

    def set_output(self, content):
        self.seconds_since_output = 0
        if self.has_gui:
            self.output_widget.replace_content(content)

    def log_command(self, content):
        if has_gui:
            self.command_widget.append_content(content + '\n')
            self.command_widget.see(tkinter.END)

    def get_error_file(self):
        x = ""
        if has_gui:
            x = self.error_file_var.get()
        else:
            try:
                x = os.environ['RCGHCI_ERROR_FILE']
            except:
                pass
        if len(x) > 0:
            return x
        else:
            return None

    def ghci_start(self):
        if self.ghci.is_running():
            self.log_command("A GHCI instance in still running")
        else:
            self.ghci.start()

    def ghci_quit(self):
        self.ghci.quit()

    def initialize(self):
        if self.has_gui:
            top_pane = GRWindow(self.root)
            top_pane.place(x=0, y=0,relheight=1.0, relwidth=1.0)
            left_pane = GRWindow(top_pane, width=900, orient=tkinter.VERTICAL)
            right_pane = GRWindow(top_pane, width=460, orient=tkinter.VERTICAL)
            top_pane.add(left_pane)
            top_pane.add(right_pane)
            self.time_widget = GRText(left_pane, fg="white")
            self.time_widget.grid(padx=(10, 10), pady=(10, 10))
            left_pane.add(self.time_widget, height=50)
            self.errors_widget = GRErrorContainer(left_pane, fg="yellow")
            left_pane.add(self.errors_widget)
            self.output_widget = GRText(right_pane, fg="#ffffff")
            right_pane.add(self.output_widget, height=150)   
            self.log_widget = GRText(right_pane, fg="#e67e22")
            right_pane.add(self.log_widget, height=350)
            self.command_widget = GRText(right_pane, fg="#ffffff")
            right_pane.add(self.command_widget, height=150)
            bottom_pane = tkinter.Frame(right_pane, height=60, bd=0, bg="#222222")
            button_pane = tkinter.Frame(bottom_pane, height=30, bd=0, bg="#222222")
            right_pane.add(bottom_pane, height=60)
            error_file_widget_wrapper = GRLockableEntry(bottom_pane, bg="#222222", textvariable=self.error_file_var)
            start_button = tkinter.Button(button_pane, text="Start", command=self.ghci_start, bg="#222222", fg="white", highlightthickness=0)
            end_button = tkinter.Button(button_pane, text="Stop", command=self.ghci_quit, bg="#222222", fg="white", highlightthickness=0)
            self.display_errors_checkbox = tkinter.Checkbutton(button_pane, command=self.update_errors, text = "Errors", variable = self.display_errors_var, onvalue = 1, offvalue = 0, height=30,  fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
            self.display_warnings_checkbox = tkinter.Checkbutton(button_pane, command=self.update_errors, text = "Warnings", variable = self.display_warnings_var, onvalue = 1, offvalue = 0, height=30, fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
            self.display_errors_checkbox.select()
            self.display_warnings_checkbox.select()
            error_file_widget_wrapper.pack(side=tkinter.TOP, pady=5, fill=tkinter.X, expand=1)
            button_pane.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=1, pady=5)
            start_button.pack(side=tkinter.LEFT, padx=5)
            end_button.pack(side=tkinter.LEFT, padx=5)
            self.display_errors_checkbox.pack(side=tkinter.LEFT, padx=5)
            self.display_warnings_checkbox.pack(side=tkinter.LEFT, padx=5)
            timer_thread = threading.Thread(target=self.time_updater, daemon=True)
            timer_thread.start()

    def is_errors_enabled(self):
        if has_gui:
            return self.display_errors_var.get()
        else:
            return True

    def is_warnings_enabled(self):
        if has_gui:
            return self.display_warnings_var.get()
        else:
            return True

    def update_errors(self):
        blocks = self.errors;
        stats = print_stats(blocks) + "\n\n"
        neovim_indicate_error(blocks)
        if self.has_gui:
            self.errors_widget.replace_content(stats)
            if self.display_errors_var.get() == 1:
                for (idx, b) in enumerate(blocks["errors"]):
                    self.errors_widget.append_error("{}. {}".format(idx + 1, b.strip()))
                    self.errors_widget.append_content("\n\n")
            if self.display_warnings_var.get() == 1:
                for (idx, b) in enumerate(blocks["warnings"]):
                    self.errors_widget.append_error("{}. {}".format(idx + 1, b.strip()))
                    self.errors_widget.append_content("\n\n")
            if len(blocks['errors']) > 0:
                self.errors_widget.config(bg="#D32F2F", fg="white")
            elif len (blocks['warnings']) > 0:
                self.errors_widget.config(bg="#222222", fg="yellow")
            else:
                self.errors_widget.config(bg="#222222", fg="white")

    def time_updater(self):
        while True:
            process_stat = "Not available"
            if self.ghci:
                s = self.ghci.get_stat()
                if s:
                    process_stat = s
            self.time_widget.replace_content("Time since last output - {} Sec\nGhc processes: {}".format(self.seconds_since_output, process_stat))
            self.seconds_since_output = self.seconds_since_output + 1
            time.sleep(1)

    def show_info(self):
        if self.has_gui:
            tkinter.messagebox.showinfo("Error!", "GHCI is still running")

try:
    COMMAND_PORT = os.environ['RCGHCI_PORT']
except:
    COMMAND_PORT = 1880

REC_MAX_LENGTH = 4096
PROMPT = "GHCIBRIDGEPROMPT>>>"

p = None
gui = None

class GHCIProcess:
    def __init__(self, read_pipe, write_pipe):
        self.read_pipe, self.write_pipe = read_pipe, write_pipe
        self.thread_exit = False
        self.p = None
        self.gui = None
        self.error_blocks = make_error_blocks("");

    def get_stat(self):
        if self.p:
            return get_ghci_process_stat(self.p.pid)
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
        if self.p:
            return self.p.isalive()
        else:
            return False

    def do_startup(self):
        self.p = pexpect.spawn("stack", ["ghci"] + sys.argv[1:], encoding=sys.stdout.encoding)
        self.p.logfile_read = sys.stdout # Set this to 'sys.stdout' to enable logging...
        outlines = []
        self.p.expect_exact([PROMPT], timeout=1000)
        output = self.p.before.replace('\r\n', '\n') + '\n'
        output = ansi_escape.sub('', output)
        self.gui.set_log("Got prompt > ")
        self.error_blocks = make_error_blocks(output)
        self.gui.set_errors(self.error_blocks)
        self.gui.set_output(output)

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
                self.p.sendline(command)
                neovim_indicate_activity()
                outlines = []
                try:
                    self.p.expect_exact([PROMPT], timeout=1000)
                except Exception as err :
                    print("Exception while waiting for the GHCI prompt! This is alright if you stopped the GHCI process.")
                    continue;
                output = self.p.before.replace('\r\n', '\n')
                output = ansi_escape.sub('', output)
                self.error_blocks = merge_blocks(self.error_blocks, make_error_blocks(output))
                self.gui.set_errors(self.error_blocks)
                self.gui.set_output(output)
                self.write_error_file(self.error_blocks)
                if len(self.error_blocks["errors"]) > 0:
                    break

    def write_error_file(self, blocks):
        error_file = self.gui.get_error_file()
        if error_file is not None:
            try:
                with open(error_file, "w") as text_file:
                    if self.gui.is_errors_enabled():
                        for (idx, b) in enumerate(blocks["errors"]):
                            text_file.write(b.strip())
                            text_file.write("\n\n")
                    if self.gui.is_warnings_enabled():
                        for (idx, b) in enumerate(blocks["warnings"]):
                            text_file.write(b.strip())
                            text_file.write("\n\n")
            except:
                tkinter.messagebox.showinfo("Error file write error", "There was an error writing errors to file {}".format(error_file))

    def execute_config_command(self, ghci_command):
       if ghci_command[0:7] == 'socket=':
           global neovim_socket
           try:
               [_, neovim_socket] = ghci_command.split('=')
           except:
               self.gui.log_command("Bad command recieved : {}".format(ghci_command))
               return False
           return True
       if ghci_command == 'stop_ghci':
           self.p.terminate(force=True)
           self.thread_exit = True
           return True
       return False

class CommandServer:
    def __init__(self, socket, command_queue):
        self.socket = socket
        self.command_queue = command_queue
        self.thread = threading.Thread(target=self.server, daemon=True)

    def server(self):
        print("Starting command server")
        self.socket.listen(5)
        while True:
            (clientsocket, address) = self.socket.accept()
            with clientsocket:
                ghci_command = clientsocket.recv(REC_MAX_LENGTH)
                print("Command recieved : {}".format(ghci_command))
                clientsocket.sendall("ok".encode())
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
                    (file_name, line, column, type_, _) = line.split(":")[0:5]
                except Exception as err :
                    continue
                type_ = type_.strip()
                if "error" in type_:
                    errors.append('\n'.join(lines[idx:]))
                elif "warning" in type_:
                    warnings.append('\n'.join(lines[idx:]))
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

def main():
    global command_read_pipe, command_write_pipe
    command_read_pipe, command_write_pipe = os.pipe()
    
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', COMMAND_PORT))
    command_server = CommandServer(serversocket, command_write_pipe)
    command_server.thread.start()

    gui = Gui(has_gui)
    gui.set_ghci(GHCIProcess(command_read_pipe, command_write_pipe))
    gui.ghci_start()
    gui.start_gui()

