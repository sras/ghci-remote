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
    is_gui = True
except:
    is_gui = False
    print("TkInter module not available, proceeding without gui")

seconds_since_output = 0
COMMAND_PORT = 1880
OUTPUT_PORT = 1881
ERROR_PORT = 1882
REC_MAX_LENGTH = 4096
OUTPUT_START_DELIMETER = "{#--------------------------------- START --------------------------#}"
OUTPUT_END_DELIMETER = "{#--------------------------------- DONE --------------------------#}"
error_queue = queue.Queue(maxsize=10000)
output_queue = queue.Queue(maxsize=10000)
error_dispatch_queue = queue.Queue(maxsize=10000)
output_dispatch_queue = queue.Queue(maxsize=10000)
last_error = None

p = None

def output_collector():
    print("Starting output collector")
    while True:
        if p is None:
            time.sleep(1)
        else:
            if p.poll() is None:
                line = p.stdout.readline().decode()
                print(line)
                if is_gui:
                    log_widget.config(state="normal")
                    log_widget.insert(tkinter.END, line)
                    log_widget.see("end")
                    log_widget.config(state="disabled")
                try:
                    output_queue.put_nowait(line)
                except:
                    pass

def error_collector():
    print("Starting error collector")
    while True:
        if p is None:
            time.sleep(1)
        else:
            if p.poll() is None:
                line = p.stderr.readline()
                try:
                    error_queue.put_nowait(line.decode())
                except:
                    pass

def dispatch(command):
    command = ":cmd (return \" \\\"\\\"::String \\n \\\"{}\\\"::String\\n{}\\n\\\"{}\\\"::String\")\n".format(OUTPUT_START_DELIMETER, command, OUTPUT_END_DELIMETER)
    print(command)
    if p.poll() is None:
        p.stdin.write(command.encode())
        p.stdin.flush()
        output = read_output()
        errors = read_errors()
        return (output, errors)
    else:
        return ("No ghci process running", "No ghci process running")

def make_error_blocks(content):
    errors = []
    warnings = []
    if content is not None and len(content) > 0:
        blocks = content.split("\n\n")
        try:
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
        except:
            return None
    return {"errors" : errors, "warnings": warnings}

def print_stats(blocks):
    if blocks is None:
        return "Not an error/warning output"
    else:
        return("errors: {}, warnings : {}".format(len(blocks["errors"]), len(blocks["warnings"])))

def update_errors():
    errors_widget.config(state="normal")
    errors_widget.delete("1.0", tkinter.END)
    blocks = make_error_blocks(last_error)
    errors_widget.insert("0.0", print_stats(blocks) + "\n\n")
    if blocks is not None:
        if display_errors_var.get() == 1 and display_warnings_var.get() == 1:
            errors_widget.insert(tkinter.END, last_error)
        elif display_errors_var.get() == 1:
            errors_widget.insert(tkinter.END, "\n\n".join(blocks["errors"]))
        elif display_warnings_var.get() == 1:
            errors_widget.insert(tkinter.END, "\n\n".join(blocks["warnings"]))
    else:
        errors_widget.insert(tkinter.END, last_error)
    errors_widget.config(state="disabled")

def command_server():
    global seconds_since_output, last_error
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', COMMAND_PORT))
    serversocket.listen(5)
    print("Starting command server")
    while True:
        (clientsocket, address) = serversocket.accept()
        with clientsocket:
            ghci_command = clientsocket.recv(REC_MAX_LENGTH).decode().strip()
            if is_gui:
                command_widget.config(state="normal")
                command_widget.insert(tkinter.END, ">{}\n".format(ghci_command))
                command_widget.see("end")
                command_widget.config(state="disabled")
            (output, errors) = dispatch(ghci_command)
            seconds_since_output = 0;
            if is_gui:
                output_widget.config(state="normal")
                output_widget.delete("1.0", tkinter.END)
                output_widget.insert("0.0", output)
                output_widget.config(state="disabled")
                last_error = errors
                update_errors()
                error_file = error_file_var.get()
                if len(error_file) > 0:
                    try:
                        with open(error_file, "w") as text_file:
                            text_file.write(errors)
                    except:
                        tkinter.messagebox.showinfo("Error file write error", "There was an error writing errors to file {}".format(error_file))
            try:
                error_dispatch_queue.put_nowait(errors)
            except:
                print("Error queue full: Discarding error")
            try:
                output_dispatch_queue.put_nowait(output)
            except:
                print("Output queue full: Discarding output")
            clientsocket.sendall("ok".encode())

def read_errors():
    errors = []
    while True:
        try:
            line = error_queue.get_nowait()
            errors.append(line)
        except queue.Empty:
            return "".join(errors)

def read_output():
    output = []
    started_flag = False
    while True:
        line = output_queue.get()
        if line == "\"{}\"\n".format(OUTPUT_START_DELIMETER):
            started_flag = True
            continue
        if started_flag:
            if line == "\"{}\"\n".format(OUTPUT_END_DELIMETER):
                return "".join(output)
            else:
                output.append(line)

def queue_server(queue, port):
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', port))
    serversocket.listen(5)
    while True:
        print("Listening at {}".format(port))
        (clientsocket, address) = serversocket.accept()
        print("Client connected")
        output = queue.get()
        print("Sending output")
        try:
            if len(output) == 0:
                output = "No Output"
            clientsocket.sendall(output.encode())
            clientsocket.close()
        except:
            print("Exception while sending to client")

def restart_ghci():
    global p
    quit_ghci()
    start_ghci()

def start_ghci():
    global p
    if p is not None and p.poll() is None:
        tkinter.messagebox.showinfo("Error!", "GHCI is still running")
    else:
        p = subprocess.Popen(["stack", "ghci", "--ghci-options", "-XNoNondecreasingIndentation"], shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

def quit_ghci():
    if p is not None and p.poll() is None:
        p.stdin.write("{}\n".format(":q\n").encode())
        p.stdin.flush()

def time_updater():
    global seconds_since_output
    while True:
        process_stat = get_ghci_process_stat()
        time_widget.config(state="normal")
        time_widget.delete("1.0", tkinter.END)
        time_widget.insert("0.0", "Time since last output - {} Sec\nGhc processes: {}".format(seconds_since_output, process_stat))
        time_widget.config(state="disabled")
        seconds_since_output = seconds_since_output + 1
        time.sleep(1)

def format_memory_info(mi):
    return "{}".format(convert_size(mi.rss))

def get_ghci_process_stat():
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

def toggle_error_file_widget():
    if error_file_lock.get() == 1:
        error_file_widget.config(state=tkinter.DISABLED)
    else:
        error_file_widget.config(state=tkinter.NORMAL)

# start_ghci()

output_collector_thread = threading.Thread(target=output_collector, daemon=True)
error_collector_thread = threading.Thread(target=error_collector, daemon=True)
command_server_thread = threading.Thread(target=command_server, daemon=True)
output_server_thread = threading.Thread(target=queue_server, args=(output_dispatch_queue, OUTPUT_PORT), daemon=True)
error_server_thread = threading.Thread(target=queue_server, args=(error_dispatch_queue, ERROR_PORT), daemon=True)

output_server_thread.start();
error_server_thread.start();

error_collector_thread.start();
output_collector_thread.start();
command_server_thread.start();

if is_gui:
    root = tkinter.Tk()
    root.geometry('1360x768')
    root.wm_title("GHCI Remote")
    top_pane = tkinter.PanedWindow(root, bd=0, sashpad=1, sashwidth=0, bg="#000000")
    top_pane.place(x=0, y=0,relheight=1.0, relwidth=1.0)
    left_pane = tkinter.PanedWindow(top_pane, width=900, bg="#000000", bd=0, sashpad=1, sashwidth=0, orient=tkinter.VERTICAL)
    right_pane = tkinter.PanedWindow(top_pane, width=460, bg="#000000", bd=0, sashpad=1, sashwidth=0, orient=tkinter.VERTICAL)
    right_pane.pack(fill=tkinter.BOTH, expand=0)
    top_pane.add(left_pane)
    top_pane.add(right_pane)
    time_string = tkinter.StringVar()
    error_file_var = tkinter.StringVar()
    display_errors_var = tkinter.IntVar()
    error_file_lock = tkinter.IntVar()
    display_warnings_var = tkinter.IntVar()
    time_string.set("No output yet")
    time_widget = tkinter.Text(left_pane, bg="#222222", fg="#ffffff", padx=5, pady=5, state="disabled", highlightthickness=0, bd=0)
    time_widget.grid(padx=(10, 10), pady=(10,10))
    left_pane.add(time_widget, height=50)
    # time_widget.place(relx=0.0, rely=0.0, height=50, relwidth=1.0)
    errors_widget = tkinter.Text(left_pane, bg="#222222", padx=5, pady=5, bd=0, state="disabled", fg="yellow",highlightthickness=0)
    left_pane.add(errors_widget)
    #errors_widget.place(relx=0.0, y=50, relheight=1.0, relwidth=1.0)
    output_widget = tkinter.Text(right_pane, bd=0, padx=5, pady=5, bg="#222222", fg="#ffffff", state="disabled", highlightthickness=0)
    right_pane.add(output_widget, height=150)   
    # output_widget.place(relx=0.0, rely=0.0, relheight=0.75, relwidth=1.0)
    # frame_widget.place(relx=1.0, rely=0.75, relheight=0.25, relwidth=1.0)
    log_widget = tkinter.Text(right_pane, bd=0, padx=5, pady=5, bg="#222222", fg="#e67e22", state="disabled", highlightthickness=0)
    right_pane.add(log_widget, height=350)
    command_widget = tkinter.Text(right_pane, padx=5, pady=5, bd=0, bg="#222222", fg="#ffffff", state="disabled", highlightthickness=0)
    right_pane.add(command_widget, height=150)
    # log_widget.place(relx=0.0, rely=0.0, relheight=0.80, relwidth=1.0)
    bottom_pane = tkinter.Frame(right_pane, height=60, bd=0, bg="#222222")
    button_pane = tkinter.Frame(bottom_pane, height=30, bd=0, bg="#222222")
    right_pane.add(bottom_pane, height=60)
    # button_frame_widget.place(relx=0.0, rely=0.80, relheight=0.20, relwidth=1.0)
    error_file_widget_wrapper = tkinter.Frame(bottom_pane, bg="#222222")
    tv = tkinter.StringVar()
    tv.set("Error file")
    label = tkinter.Label(error_file_widget_wrapper, textvariable=tv, bg="#222222", fg="white")
    c3 = tkinter.Checkbutton(error_file_widget_wrapper, command=toggle_error_file_widget, text = "Lock", variable = error_file_lock, onvalue = 1, offvalue = 0, fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
    error_file_widget = tkinter.Entry(error_file_widget_wrapper, width=30, fg="#00ff00", bg="#000000", disabledbackground="#666666", disabledforeground="black", state=tkinter.DISABLED, textvariable=error_file_var, bd=0, highlightthickness=0, insertbackground="green")
    label.pack(side=tkinter.LEFT)
    error_file_widget.pack(side=tkinter.LEFT, padx=5)
    c3.pack(side=tkinter.LEFT)
    restart_button = tkinter.Button(button_pane, text="Restart", command=restart_ghci, bg="#222222", fg="white", highlightthickness=0)
    start_button = tkinter.Button(button_pane, text="Start", command=start_ghci, bg="#222222", fg="white", highlightthickness=0)
    end_button = tkinter.Button(button_pane, text="Stop", command=quit_ghci, bg="#222222", fg="white", highlightthickness=0)
    c1 = tkinter.Checkbutton(button_pane, command=update_errors, text = "Errors", variable = display_errors_var, onvalue = 1, offvalue = 0, height=30,  fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
    c2 = tkinter.Checkbutton(button_pane, command=update_errors, text = "Warnings", variable = display_warnings_var, onvalue = 1, offvalue = 0, height=30, fg="white", selectcolor="black", padx=0, highlightthickness=0, bd=0, bg="#222222")
    #button_pane.add(restart_button)
    c1.select()
    c2.select()
    c3.select()
    error_file_widget_wrapper.pack(side=tkinter.TOP, pady=5, fill=tkinter.X, expand=1)
    button_pane.pack(side=tkinter.TOP, fill=tkinter.BOTH, expand=1, pady=5)
    restart_button.pack(side=tkinter.LEFT, padx=5)
    start_button.pack(side=tkinter.LEFT, padx=5)
    end_button.pack(side=tkinter.LEFT, padx=5)
    c1.pack(side=tkinter.LEFT, padx=5)
    c2.pack(side=tkinter.LEFT, padx=5)
    timer_thread = threading.Thread(target=time_updater, daemon=True)
    timer_thread.start()
    root.mainloop()
    quit_ghci()
else:
    try:
        command_server_thread.join();
    except KeyboardInterrupt:
        p.stdin.write("{}\n".format(":q\n").encode())
        p.stdin.flush()
        sys.exit()
