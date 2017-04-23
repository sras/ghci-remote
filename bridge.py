import socket
import subprocess
import io
import sys
import time
import threading
import sys

p = subprocess.Popen(["stack", "ghci"], shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

#print("Starting")
#while True:
#    p.stdin.write(": src/Common.hs\n".encode())

COMMAND_PORT = 1880
ERROR_PORT = 1881
OUTPUT_PORT = 1882
REC_MAX_LENGTH = 4096
DELIMETER = "COMMAND RECIEVED: {}\n"

error_outfile = open("errors.txt", 'w')
output_outfile = open("output.txt", 'w')

def insert_delimeter(command):
    error_outfile.truncate(0)
    error_outfile.seek(0)
    error_outfile.write(DELIMETER.format(command))
    error_outfile.flush()
    output_outfile.truncate(0)
    error_outfile.seek(0)
    output_outfile.write(DELIMETER.format(command))
    output_outfile.flush()

def output_server():
    errsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    errsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    errsocket.bind(('0.0.0.0', OUTPUT_PORT))
    errsocket.listen(5)
    print("Starting output server")
    (clientsocket, address) = errsocket.accept()
    print("Error client connected")
    while True:
        line = p.stdout.readline()
        clientsocket.send(line)

def error_server():
    errsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    errsocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    errsocket.bind(('0.0.0.0', ERROR_PORT))
    errsocket.listen(5)
    print("Starting error server")
    (clientsocket, address) = errsocket.accept()
    print("Error client connected")
    while True:
        line = p.stderr.readline()
        clientsocket.send(line)

def command_server():
    # create an INET, STREAMing socket
    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # bind the socket to a public host, and a well-known port
    serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(('0.0.0.0', COMMAND_PORT))
    # become a server socket
    serversocket.listen(5)
    print("Starting command server")
    while True:
        (clientsocket, address) = serversocket.accept()
        command = clientsocket.recv(REC_MAX_LENGTH)
        insert_delimeter(command)
        p.stdin.write("{}\n".format(command.decode()).encode())
        p.stdin.flush()

def error_client():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # now connect to the web server on port 80 - the normal http port
    s.connect(("127.0.0.1", ERROR_PORT))
    while True:
        while True:
            output = s.recv(REC_MAX_LENGTH)
            output_str = output.decode(encoding='utf-8')
            print(output_str)
            error_outfile.write(output_str)
            if len(output) < REC_MAX_LENGTH:
                error_outfile.flush()
                break

def output_client():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # now connect to the web server on port 80 - the normal http port
    s.connect(("127.0.0.1", OUTPUT_PORT))
    while True:
        while True:
            output = s.recv(REC_MAX_LENGTH)
            output_str = output.decode(encoding='utf-8')
            print(output_str)
            output_outfile.write(output_str)
            if len(output) < REC_MAX_LENGTH:
                output_outfile.flush()
                break

output_server_thread = threading.Thread(target=output_server, daemon=True)
error_server_thread = threading.Thread(target=error_server, daemon=True)
command_server_thread = threading.Thread(target=command_server, daemon=True)

error_client_thread = threading.Thread(target=error_client, daemon=True)
output_client_thread = threading.Thread(target=output_client, daemon=True)

error_server_thread.start();
output_server_thread.start();
command_server_thread.start();

error_client_thread.start();
output_client_thread.start();

try:
    command_server_thread.join();
except KeyboardInterrupt:
    p.stdin.write("{}\n".format(":q\n").encode())
    p.stdin.flush()
    sys.exit()
