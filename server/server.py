import os
import sys

sys.path.append(os.path.abspath('..'))

import pickle
import socket
from threading import Lock, Thread

lock_friends = Lock()

from payload import Payload

LISTEN_ADDRESS = ('0.0.0.0', 6666)
LISTEN_CLIENTS = 10
BUFFER_SIZE = 65536
ENCODING = 'utf-8'

global sendfiledata
sendfiledata = {}

def remove_friend(sock, username, clients, friends, args):
    dest_username, = args

    if not check_friends(friends, username, dest_username):
        return error_notfriends(sock, dest_username)
    
    with lock_friends:
        friends.remove((username, dest_username))
        friends.remove((dest_username, username))
    
    send(sock, '_removefriend', (dest_username,))
    dest_sock = clients[dest_username][0]
    send(dest_sock, '_removedbyfriend', (username,))

def friend_list(sock, username, clients, friends, args):
    incoming = set()
    outgoing = set()
    with lock_friends:
        for a, b in friends:
            if a == username:
                outgoing.add(b)
            elif b == username:
                incoming.add(a)
    
    friended = incoming.intersection(outgoing)
    incoming = incoming.difference(friended)
    outgoing = outgoing.difference(friended)

    send(sock, '_friendlisting', (friended, incoming, outgoing))

def sendfile_ok(sock, username, clients, friends, args):
    if username in sendfiledata:
        sock.sendall(sendfiledata[username])

def friend_accept(sock, username, clients, friends, args):
    dest_username, = args

    if check_friends(friends, username, dest_username):
        return error_alreadyfriends(sock, dest_username)
        
    with lock_friends:
        if (dest_username, username) not in friends:
            return error_requestdoesnotexist(sock, dest_username)
    
        friends.add((username, dest_username))

    send(sock, '_requestsentaccept', (dest_username,))
    dest_sock = clients[dest_username][0]
    send(dest_sock, '_requestaccepted', (username,))

def friend_request(sock, username, clients, friends, args):
    dest_username, = args

    if check_friends(friends, username, dest_username):
        return error_alreadyfriends(sock, dest_username)
        
    with lock_friends:
        if (username, dest_username) in friends:
            return error_requestexists(sock, dest_username)

        friends.add((username, dest_username))

    dest_sock = clients[dest_username][0]
    send(dest_sock, '_request', (username,))

def broadcast(sock, username, clients, friends, args):
    message, = args

    for dest_username in clients:
        dest = clients[dest_username]
        dest_sock = dest[0]
        if check_friends(friends, username, dest_username):
            send(dest_sock, '_bcastrecv', (username, message))

def private_message(sock, username, clients, friends, args):
    dest_username, message = args

    if not check_friends(friends, username, dest_username):
        return error_notfriends(sock, dest_username)

    dest_sock = clients[dest_username][0]
    send(dest_sock, '_message', (username, message))

def sendfile(sock, username, clients, friends, args):
    dest_username, filename, filesize = args

    if not check_friends(friends, username, dest_username):
        return error_notfriends(sock, dest_username)

    send(sock, '_sendfile_ok', ())

    cursor = 0
    filedata = b''
    while (cursor < filesize):
        data = sock.recv(BUFFER_SIZE)
        if len(data) == 0:
            return
        filedata += data
        cursor += len(data)
    
    global sendfiledata
    sendfiledata[dest_username] = filedata
    
    dest_sock = clients[dest_username][0]
    send(dest_sock, '_acceptfile', (username, filename, filesize))

def check_friends(friends, a, b):
    with lock_friends:
        return (a, b) in friends and (b, a) in friends

##### ERRORS ###########################################################

def error_alreadyfriends(sock, dest_username):
    send(sock, '_alreadyfriends', (dest_username,))

def error_requestexists(sock, dest_username):
    send(sock, '_requestexists', (dest_username,))

def error_requestdoesnotexist(sock, dest_username):
    send(sock, '_requestdoesnotexist', (dest_username,))

def error_notfriends(sock, dest_username):
    send(sock, '_notfriends', (dest_username,))

########################################################################

def send(sock, command, args):
    sock.send(pickle.dumps(Payload(command, args)))

########################################################################

COMMANDS = {
    '_req': friend_request, # dest_username
    '_acc': friend_accept, # dest_username
    '_pm': private_message, # dest_username, message
    '_bcast': broadcast, # message
    '_sendfile': sendfile, # dest_username, filename, filesize
    '_sendfile_ok': sendfile_ok,
    '_friendlist': friend_list,
    '_removefriend': remove_friend, #dest_username
}

def serve_client(sock, username, clients, friends):
    while True:
        data = sock.recv(BUFFER_SIZE)
        if len(data) == 0:
            break
        
        payload = pickle.loads(data)
        print(f'{payload.command} {payload.args}')
        try:
            COMMANDS[payload.command](sock, username, clients, friends, payload.args)
        except KeyError:
            pass

def main():
    sock_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_server.bind(LISTEN_ADDRESS)
    sock_server.listen(LISTEN_CLIENTS)

    clients = {}
    friends = set()

    while True:
        sock_client, addr_client = sock_server.accept()
        username = sock_client.recv(BUFFER_SIZE).decode(ENCODING)
        print(f'{username} connected from {addr_client}')

        thread = Thread(target=serve_client, args=(sock_client, username, clients, friends))

        clients[username] = (sock_client, addr_client, thread)

        thread.start()

if __name__ == '__main__':
    main()
