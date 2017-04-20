import socket

PORT = 1881
REC_MAX_LENGTH = 4096
# create an INET, STREAMing socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# now connect to the web server on port 80 - the normal http port
s.connect(("127.0.0.1", PORT))
while True:
    while True:
        errors = s.recv(REC_MAX_LENGTH)
        print(errors.decode(encoding='utf-8'))
        if len(errors) < REC_MAX_LENGTH:
            break
