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
neovim_socket = None

def open_file_and_go_to_line_column(file_name, line, col):
    if has_neovim and neovim_socket is not None:
        nvim = attach('socket', path=neovim_socket)
        try:
            nvim.command('e +{} {}'.format(r'call\ cursor({},{})|execute\ "normal"\ "V"'.format(line, col), file_name))
        except:
            pass

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
        self.root = tkinter.Tk()
        self.root.geometry("1360x768")
        self.root.wm_title("GHCI Remote")
        self.has_gui = has_gui
        self.seconds_since_output = 0
        self.time_string = tkinter.StringVar()
        self.time_string.set("No output yet")
        self.error_file_var = tkinter.StringVar()
        self.display_errors_var = tkinter.IntVar()
        self.error_file_lock = tkinter.IntVar()
        self.display_warnings_var = tkinter.IntVar()
        self.errors = None
        self.ghci = None
        self.initialize()

    def set_errors(self, errors):
        self.errors = errors
        self.update_errors()

    def set_ghci_process(self, ghci_process):
        self.ghci = ghci_process

    def start(self):
        self.root.mainloop()

    def add_log(self, content):
        self.log_widget.append_content(content)
        self.log_widget.see(tkinter.END)

    def set_output(self, content):
        self.seconds_since_output = 0
        self.output_widget.replace_content(content)

    def log_command(self, content):
        self.command_widget.append_content(content)
        self.command_widget.see(tkinter.END)

    def get_error_file(self):
        x = self.error_file_var.get()
        if len(x) > 0:
            return x
        else:
            return None

    def ghci_start(self):
        self.ghci.start()
    
    def ghci_quit(self):
        self.ghci.quit()
    
    def ghci_restart(self):
        self.ghci.quit_ghci()
        self.ghci.start()
    
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
            restart_button = tkinter.Button(button_pane, text="Restart", command=self.ghci_restart, bg="#222222", fg="white", highlightthickness=0)
            start_button = tkinter.Button(button_pane, text="Start", command=self.ghci_start, bg="#222222", fg="white", highlightthickness=0)
            end_button = tkinter.Button(button_pane, text="Stop", command=self.ghci_quit, bg="#222222", fg="white", highlightthickness=0)
            self.display_errors_checkbox = tkinter.Checkbutton(button_pane, command=self.update_errors, text = "Errors", variable = self.display_errors_var, onvalue = 1, offvalue = 0, height=30,  fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
            self.display_warnings_checkbox = tkinter.Checkbutton(button_pane, command=self.update_errors, text = "Warnings", variable = self.display_warnings_var, onvalue = 1, offvalue = 0, height=30, fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
            self.display_errors_checkbox.select()
            self.display_warnings_checkbox.select()
            error_file_widget_wrapper.pack(side=tkinter.TOP, pady=5, fill=tkinter.X, expand=1)
            button_pane.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=1, pady=5)
            restart_button.pack(side=tkinter.LEFT, padx=5)
            start_button.pack(side=tkinter.LEFT, padx=5)
            end_button.pack(side=tkinter.LEFT, padx=5)
            self.display_errors_checkbox.pack(side=tkinter.LEFT, padx=5)
            self.display_warnings_checkbox.pack(side=tkinter.LEFT, padx=5)
            timer_thread = threading.Thread(target=self.time_updater, daemon=True)
            timer_thread.start()

    def is_errors_enabled(self):
        return self.display_errors_var.get()

    def is_warnings_enabled(self):
        return self.display_warnings_var.get()

    def update_errors(self):
        blocks = make_error_blocks(self.errors)
        stats = print_stats(blocks) + "\n\n"
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
            self.errors_widget.append_content(self.errors)

    def time_updater(self):
        while True:
            if self.ghci is not None:
                process_stat = self.ghci.get_process_stats()
            else:
                process_stat = "Not available"
            self.time_widget.replace_content("Time since last output - {} Sec\nGhc processes: {}".format(self.seconds_since_output, process_stat))
            self.seconds_since_output = self.seconds_since_output + 1
            time.sleep(1)

    def show_info(self):
        if self.has_gui:
            tkinter.messagebox.showinfo("Error!", "GHCI is still running")

COMMAND_PORT = 1880
OUTPUT_PORT = 1881
ERROR_PORT = 1882
LOG_PORT = 1883
REC_MAX_LENGTH = 4096
OUTPUT_START_DELIMETER = "{#--------------------------------- START --------------------------#}"
OUTPUT_END_DELIMETER = "{#--------------------------------- DONE --------------------------#}"

p = None
gui = None

class GHCIProcess:
    def __init__(self):
        self.p = None
        self.error_queue = queue.Queue(maxsize=10000)
        self.output_queue = queue.Queue(maxsize=10000)
        self.output_collector_thread = threading.Thread(target=self.output_collector, daemon=True)
        self.error_collector_thread = threading.Thread(target=self.error_collector, daemon=True)
        self.error_collector_thread.start();
        self.output_collector_thread.start();
        self.log_dispatch_queue = None

    def restart(self):
        quit_ghci()
        start_ghci()

    def set_log_queue(self, log_queue):
        self.log_dispatch_queue = log_queue

    def start(self):
        if self.p is not None and self.p.poll() is None:
            return self.p
        else:
            if len(sys.argv) == 2:
                params = ["stack", "ghci", "--main-is", sys.argv[1], "--ghc-options", "-XNoNondecreasingIndentation", "--ghci-options", "+RTS -M2G -RTS"]
            else:
                params = ["stack", "ghci", "--ghc-options", "-XNoNondecreasingIndentation", "--ghci-options", "+RTS -M2G -RTS"]
            self.p = subprocess.Popen(params, shell=True, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            return None

    def quit(self):
        if self.p is not None and self.p.poll() is None:
            self.p.stdin.write("{}\n".format(":q\n").encode())
            self.p.stdin.flush()

    def get_process_stats(self):
        return get_ghci_process_stat(self.p)

    def output_collector(self):
        print("Starting output collector")
        while True:
            if self.p is None:
                time.sleep(1)
            else:
                rc = self.p.poll()
                if rc is None:
                    line = self.p.stdout.readline().decode()
                    print(line)
                    gui.add_log(line)
                    try:
                        if self.log_dispatch_queue is not None:
                            self.log_dispatch_queue.put_nowait(line)
                        self.output_queue.put_nowait(line)
                    except:
                        pass
                else:
                    print("Thread exited. Code : {}".format(rc))
                    time.sleep(2)

    def error_collector(self):
        print("Starting error collector")
        while True:
            if self.p is None:
                time.sleep(1)
            else:
                if self.p.poll() is None:
                    line = self.p.stderr.readline()
                    try:
                        self.error_queue.put_nowait(line.decode())
                    except:
                        pass
                else:
                    time.sleep(2)

    def dispatch(self, command):
        command = ":cmd (return \" \\\"\\\"::String \\n \\\"{}\\\"::String\\n{}\\n\\\"{}\\\"::String\")\n".format(OUTPUT_START_DELIMETER, command.replace('"', '\\"'), OUTPUT_END_DELIMETER)
        print(command)
        if self.p.poll() is None:
            self.p.stdin.write(command.encode())
            self.p.stdin.flush()
            output = self.read_output()
            errors = self.read_errors()
            return (output, errors)
        else:
            return ("No ghci process running", "No ghci process running")

    def read_errors(self):
        errors = []
        while True:
            try:
                line = self.error_queue.get_nowait()
                errors.append(line)
            except queue.Empty:
                return "".join(errors)
    
    def read_output(self):
        output = []
        started_flag = False
        while True:
            line = self.output_queue.get()
            if line == "\"{}\"\n".format(OUTPUT_START_DELIMETER):
                started_flag = True
                continue
            if started_flag:
                if line == "\"{}\"\n".format(OUTPUT_END_DELIMETER):
                    return "".join(output)
                else:
                    output.append(line)

def make_error_blocks(content):
    errors = []
    warnings = []
    if content is not None and len(content) > 0:
        blocks = content.split("\n\n")
        for b in blocks:
            lines = b.strip().split("\n")
            try:
                (file_name, line, column, type_,_) = lines[0].split(":")
                type_ = type_.strip()
                if type_ == "error":
                    errors.append(b)
                elif type_ == "warning":
                    warnings.append(b)
            except:
                continue
    return {"errors" : errors, "warnings": warnings}

def print_stats(blocks):
    if blocks is None:
        return "Not an error/warning output"
    else:
        return("errors: {}, warnings : {}".format(len(blocks["errors"]), len(blocks["warnings"])))

class CommandServer:
    def __init__(self, ghci_process, gui, command_port):
        self.ghci_process = ghci_process
        self.gui = gui
        self.gui.set_ghci_process(ghci_process)
        self.command_port = command_port
        self.error_dispatch_queue = queue.Queue(maxsize=10000)
        self.output_dispatch_queue = queue.Queue(maxsize=10000)
        self.log_dispatch_queue = queue.Queue(maxsize=10000)
        self.server_thread = threading.Thread(target=self.server, daemon=True)
        self.ghci_process.set_log_queue(self.log_dispatch_queue)
        self.start()
        self.gui.start()
        self.ghci_process.quit()

    def start(self):
        self.server_thread.start()

    def server(self):
        print("Starting command server")
        self.ghci_process.start()
        serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        serversocket.bind(('0.0.0.0', self.command_port))
        serversocket.listen(5)
        self.output_server_thread = threading.Thread(target=queue_server, args=(self.output_dispatch_queue, OUTPUT_PORT), daemon=True)
        self.error_server_thread = threading.Thread(target=queue_server, args=(self.error_dispatch_queue, ERROR_PORT), daemon=True)
        self.log_server_thread = threading.Thread(target=queue_server, args=(self.log_dispatch_queue, LOG_PORT), daemon=True)
        self.output_server_thread.start()
        self.error_server_thread.start()
        self.log_server_thread.start()
        while True:
            print("Listening..")
            (clientsocket, address) = serversocket.accept()
            with clientsocket:
                ghci_command = clientsocket.recv(REC_MAX_LENGTH).decode().strip()
                self.gui.log_command(">{}\n".format(ghci_command))
                if ghci_command[0:7] == 'socket=':
                    global neovim_socket
                    [_, neovim_socket] = ghci_command.split('=')
                    continue
                (output, errors) = self.ghci_process.dispatch(ghci_command)
                if ghci_command[0:9] == ':complete':
                    try:
                        key_len = len(ghci_command.split(' ')[2].strip('"'))
                        print("Len = {}".format(key_len))
                        open_completion(key_len, [x.strip('"') for x in output.split("\n")[1:]])
                    except:
                       pass 
                self.gui.set_output(output)
                self.gui.set_errors(errors)
                if gui.get_error_file() is not None:
                    try:
                        with open(gui.get_error_file(), "w") as text_file:
                            if gui.is_errors_enabled() and gui.is_warnings_enabled():
                                text_file.write(errors)
                            elif gui.is_errors_enabled():
                                blocks = make_error_blocks(errors)
                                for (idx, b) in enumerate(blocks["errors"]):
                                    text_file.write(b.strip())
                                    text_file.write("\n\n")
                            elif gui.is_warnings_enabled():
                                blocks = make_error_blocks(errors)
                                for (idx, b) in enumerate(blocks["warnings"]):
                                    text_file.write(b.strip())
                                    text_file.write("\n\n")
                    except:
                        tkinter.messagebox.showinfo("Error file write error", "There was an error writing errors to file {}".format(error_file))
                try:
                    self.error_dispatch_queue.put_nowait(errors)
                except:
                    print("Error queue full: Discarding error")
                try:
                    self.output_dispatch_queue.put_nowait(output)
                except:
                    print("Output queue full: Discarding output")
                clientsocket.sendall("ok".encode())

count = 0;

def queue_server(queue, port):
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', port))
    serversocket.listen(5)
    while True:
        print("Listening at {}".format(port))
        (clientsocket, address) = serversocket.accept()
        while True:
            try:
                output = queue.get(timeout=1)
                break
            except:
                continue
        try:
            if len(output) == 0:
                output = "No Output"
            clientsocket.sendall(output.encode())
            clientsocket.close()
        except:
            clientsocket.close()

def format_memory_info(mi):
    return "{}".format(convert_size(mi.rss))

def get_ghci_process_stat(p):
    if has_psutil:
        try:
            return " | ".join(["pid={}{}, Mem = {}({}%)".format(x.pid, "*" if x.ppid() == p.pid else "", format_memory_info(x.memory_info()), round(x.memory_percent(), 2)) for x in psutil.process_iter() if x.name() =="ghc"])
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

gui = Gui(has_gui)
command_server = CommandServer(GHCIProcess(), gui, COMMAND_PORT)
