import socket
import subprocess
import io
import sys
import time
import threading
import sys
import queue
import collections
try:
    import tkinter
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

def output_collector():
    print("Starting output collector")
    while True:
        line = p.stdout.readline().decode()
        print(line)
        if is_gui:
            log_widget.insert(tkinter.END, line)
            log_widget.see("end")
        try:
            output_queue.put_nowait(line)
        except:
            pass

def error_collector():
    print("Starting error collector")
    while True:
        line = p.stderr.readline()
        try:
            error_queue.put_nowait(line.decode())
        except:
            pass

def dispatch(command):
    command = ":cmd (return \" \\\"\\\"::String \\n \\\"{}\\\"::String\\n{}\\n\\\"{}\\\"::String\")\n".format(OUTPUT_START_DELIMETER, command, OUTPUT_END_DELIMETER)
    print(command)
    p.stdin.write(command.encode())
    p.stdin.flush()
    output = read_output()
    errors = read_errors()
    return (output, errors)

def print_stats(content):
    blocks = content.split("\n\n")
    errors = 0
    warnings = 0
    try:
        for b in blocks:
            lines = b.strip().split("\n")
            (file_name, line, column, type_,_) = lines[0].split(":")
            type_ = type_.strip()
            if type_ == "error":
                errors = errors + 1
            elif type_ == "warning":
                warnings = warnings + 1
        return("errors: {}, warnings : {}".format(errors, warnings))
    except:
        return "Not an error/warning output"

def command_server():
    global seconds_since_output
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', COMMAND_PORT))
    serversocket.listen(5)
    print("Starting command server")
    while True:
        (clientsocket, address) = serversocket.accept()
        with clientsocket:
            ghci_command = clientsocket.recv(REC_MAX_LENGTH).decode().strip()
            (output, errors) = dispatch(ghci_command)
            seconds_since_output = 0;
            if is_gui:
                output_widget.delete("1.0", tkinter.END)
                output_widget.insert("0.0", output)
                errors_widget.delete("1.0", tkinter.END)
                errors_widget.insert("0.0", print_stats(errors) + "\n")
                errors_widget.insert(tkinter.END, errors)
                with open(error_file_var.get(), "w") as text_file:
                    text_file.write(errors)
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
    p = subprocess.Popen(["stack", "ghci", "--ghci-options", "-XNoNondecreasingIndentation"], shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

def quit_ghci():
    p.stdin.write("{}\n".format(":q\n").encode())
    p.stdin.flush()

def time_updater():
    global seconds_since_output
    while True:
        time_string.set("Time since last output - {} Sec".format(seconds_since_output))
        seconds_since_output = seconds_since_output + 1
        time.sleep(1)

start_ghci()

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
    top = tkinter.Tk()
    top.geometry('800x600')
    top.wm_title("GHCI Remote")
    time_string = tkinter.StringVar()
    error_file_var = tkinter.StringVar()
    time_string.set("No output yet")
    time_widget = tkinter.Label(top, bg="black", fg="#00ff00", textvariable=time_string, bd=1, highlightthickness=0)
    time_widget.place(relx=0.0, rely=0.0, height=20, relwidth=0.5)
    errors_widget = tkinter.Text(top, bg="black", fg="#00ff00", bd=1, highlightthickness=0)
    errors_widget.place(relx=0.0, y=20, relheight=1.0, relwidth=0.5)
    output_widget = tkinter.Text(top, bg="black", fg="#00ff00", bd=1, highlightthickness=0)
    output_widget.place(relx=0.5, rely=0.0, relheight=0.75, relwidth=0.5)
    frame_widget = tkinter.Text(top, bg="black", fg="#00ff00", bd=1, highlightthickness=0)
    frame_widget.place(relx=0.5, rely=0.75, relheight=0.25, relwidth=0.5)
    log_widget = tkinter.Text(frame_widget, bg="black", fg="#00ff00", bd=1, highlightthickness=0)
    log_widget.place(relx=0.0, rely=0.0, relheight=0.80, relwidth=1.0)
    button_frame_widget = tkinter.Text(frame_widget, bd=1, highlightthickness=0)
    button_frame_widget.place(relx=0.0, rely=0.80, relheight=0.20, relwidth=1.0)
    error_file_widget = tkinter.Entry(button_frame_widget, fg="#000000", bg="#ffffff", textvariable=error_file_var)
    error_file_widget.place(relx=0.0, y=0, relheight=1.0, relwidth=0.5)
    restart_button = tkinter.Button(button_frame_widget, fg="#000000", bg="#ffffff", text="Restart GHCI", command=restart_ghci)
    restart_button.place(relx=0.50, y=0, relheight=1.0, relwidth=0.5)
    timer_thread = threading.Thread(target=time_updater, daemon=True)
    timer_thread.start()
    top.mainloop()
    quit_ghci()
else:
    try:
        command_server_thread.join();
    except KeyboardInterrupt:
        p.stdin.write("{}\n".format(":q\n").encode())
        p.stdin.flush()
        sys.exit()
