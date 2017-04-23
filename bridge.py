import socket
import subprocess
import io
import sys
import time
import threading
import sys
import queue

p = subprocess.Popen(["stack", "ghci"], shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

COMMAND_PORT = 1880
REC_MAX_LENGTH = 4096
OUTPUT_START_DELIMETER = "{#--------------------------------- START --------------------------#}"
OUTPUT_END_DELIMETER = "{#--------------------------------- DONE --------------------------#}"


error_queue = queue.Queue()
output_queue = queue.Queue()

def output_collector():
    print("Starting output collector")
    while True:
        line = p.stdout.readline()
        output_queue.put(line.decode())

def error_collector():
    print("Starting error collector")
    while True:
        line = p.stderr.readline()
        error_queue.put(line.decode())

def dispatch(command):
    command = ":cmd (return \" \\\"\\\" \\n \\\"{}\\\"\\n{}\\n\\\"{}\\\"\")\n".format(OUTPUT_START_DELIMETER, command, OUTPUT_END_DELIMETER)
    print(command)
    p.stdin.write(command.encode())
    p.stdin.flush()
    output = read_output()
    errors = read_errors()
    return (output, errors)

def command_server():
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', COMMAND_PORT))
    serversocket.listen(5)
    print("Starting command server")
    while True:
        (clientsocket, address) = serversocket.accept()
        command = clientsocket.recv(REC_MAX_LENGTH).decode().strip()
        print(command)
        ghci_command = None
        try:
            ghci_command =  {"reload" : ":reload", "build": ":l Main", "buildtags": ":ctags"}[command] 
        except KeyError:
            if command == "collect_types":
                collect_types()
            continue
        (output, errors) = dispatch(ghci_command)
        output_outfile = open("output.txt", 'w')
        error_outfile = open("errors.txt", 'w')
        output_outfile.write(output)
        error_outfile.write(errors)
        output_outfile.close()
        error_outfile.close()
        clientsocket.send("ok".encode())

def collect_types():
    ghci_command = ":set +c\\n:r\\n:all-types\\n:unset +c"
    print(ghci_command)
    (output, errors) = dispatch(ghci_command)
    store_types(output)

def store_types(output):
    pass

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

output_collector_thread = threading.Thread(target=output_collector, daemon=True)
error_collector_thread = threading.Thread(target=error_collector, daemon=True)
command_server_thread = threading.Thread(target=command_server, daemon=True)

error_collector_thread.start();
output_collector_thread.start();
command_server_thread.start();

try:
    command_server_thread.join();
except KeyboardInterrupt:
    p.stdin.write("{}\n".format(":q\n").encode())
    p.stdin.flush()
    sys.exit()
