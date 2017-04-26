import socket
import os
import time
import sys
import threading
from datetime import datetime

RECV_MAX_LENGTH = 4096
all_output = []
last_output_at = None
last_conn_attempt = None
connection = False
all = None

def getTimeDiff():
    return int(datetime.now().timestamp() - last_output_at.timestamp() )

def display():
    while True:
        _ = os.system('clear')
        if connection is False:
            print("No connection yet. Last connection attempt at {}".format(str(last_conn_attempt)))
            print("---------------------------------------------------")
        elif last_output_at is None:
            print("No output yet")
            print("---------------------------------------------------")
        else:
            print("Output recieved before {} secs".format(str(getTimeDiff())))
            print("---------------------------------------------------")
            print(all)
        time.sleep(1)


display_thread = threading.Thread(target=display, daemon=True)
display_thread.start();

while True:
    all_output = []
    connection = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        last_conn_attempt = datetime.now()
        s.connect(("127.0.0.1", int(sys.argv[1])))
    except:
        time.sleep(1)
        continue
    while True:
        connection = True
        output = s.recv(RECV_MAX_LENGTH)
        all_output.append(output.decode(errors='ignore'))
        if len(output) < RECV_MAX_LENGTH:
            break
    s.close()
    all = "".join(all_output)
    connection = False
    last_output_at = datetime.now()
    with open(sys.argv[2], "w") as text_file:
        text_file.write(all)
