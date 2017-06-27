import socket
import subprocess
import io
import sys
import time
import threading
import sys
import queue
import collections

p = subprocess.Popen(["stack", "ghci"], shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

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
        output_queue.put(line)

def error_collector():
    print("Starting error collector")
    while True:
        line = p.stderr.readline()
        error_queue.put(line.decode())

def dispatch(command):
    command = ":cmd (return \" \\\"\\\"::String \\n \\\"{}\\\"::String\\n{}\\n\\\"{}\\\"::String\")\n".format(OUTPUT_START_DELIMETER, command, OUTPUT_END_DELIMETER)
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
        with clientsocket:
            command = clientsocket.recv(REC_MAX_LENGTH).decode().strip()
            print(command)
            ghci_command = None
            try:
                ghci_command =  {"reload" : ":reload", "build": ":l Main", "buildtags": ":ctags"}[command] 
            except KeyError:
                if command == "collect_types":
                    collect_types()
                else:
                    print("Unknown command {}".format(command))
                continue
            (output, errors) = dispatch(ghci_command)
            try:
                error_dispatch_queue.put_nowait(errors)
            except:
                print("Error queue full: Discarding error")
            try:
                output_dispatch_queue.put_nowait(output)
            except:
                print("Output queue full: Discarding output")
            clientsocket.sendall("ok".encode())

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

try:
    command_server_thread.join();
except KeyboardInterrupt:
    p.stdin.write("{}\n".format(":q\n").encode())
    p.stdin.flush()
    sys.exit()
