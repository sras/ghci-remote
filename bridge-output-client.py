import socket

PORT = 1882
REC_MAX_LENGTH = 4096
# create an INET, STREAMing socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# now connect to the web server on port 80 - the normal http port
s.connect(("127.0.0.1", PORT))
while True:
    while True:
        output = s.recv(REC_MAX_LENGTH)
        print(output.decode(encoding='utf-8'))
        if len(output) < REC_MAX_LENGTH:
            break
