import os
import pickle
import socket
import sys
from threading import Thread

sys.path.append(os.path.abspath('..'))

from payload import Payload

REMOTE_ADDRESS = ('127.0.0.1', 6666)
ENCODING = 'utf-8'

global sendfiledata
sendfiledata = None

def incoming_friend_request(sock, message):
    sender, = message
    print(f'\rReceived friend request from {sender}, enter _acc {sender} to accept.\n----------\n>> ', end='')

def outgoing_friend_request(sock, message):
    dest, = message
    print(f'\rFriend request to {dest} sent.\n----------\n>> ', end='')

def friend_request_already_exist(sock, message):
    dest, = message
    print(f'\rYou have already sent {dest} a friend request.\n----------\n>> ', end='')

def outgoing_friend_request_accepted(sock, message):
    dest, = message
    print(f'\rYour friend request has been accepted by {dest}.\n----------\n>> ', end='')

def incoming_friend_request_accepted(sock, message):
    dest, = message
    print(f'\rYou are now friends with {dest}.\n----------\n>> ', end='')

def friend_already_exist(sock, message):
    dest, = message
    print(f'\rYou already have {dest} in your friend list.\n----------\n>> ', end='')

def friend_request_does_not_exist(sock, message):
    other, = message
    print(f'\rThere is no friend request from {other}.\n----------\n>> ', end='')

def not_friends_yet(sock, message):
    dest, = message
    print(f'\rYou are not friends with {dest} yet.\n----------\n>> ', end='')

def friend_list(sock, message):
    friendlist, incoming, outgoing = message
    print('\rCurrent friend list:\n')
    i=1
    for friend in friendlist:
        print(f'\r{i}. {friend}\n')
        i = i+1
    print('----------\n')
    print('\rIncoming friend request:\n')
    i=1
    for friend in incoming:
        print(f'\r{i}. {friend}\n')
        i = i+1
    print('----------\n')
    print('\rSent friend request:\n')
    i=1
    for friend in outgoing:
        print(f'\r{i}. {friend}\n')
        i = i+1
    print('----------\n>> ', end='')

def friend_remove(sock, message):
    friend, = message
    print(f'\rYou have removed {friend} from your friend list.\n----------\n>> ', end='')

def friend_removed(sock, message):
    friend, = message
    print(f'\rYour friendship with {friend} has been revoked.\n----------\n>> ', end='')

def receive_file(sock, message):
    sender, filename, filesize = message
    filedata = b''
    sock.send(pickle.dumps(Payload('_sendfile_ok', ())))
    print(f'\rYou received a file from {sender} named {filename} with size of {filesize} bytes.\n----------\n>> ', end='')
    while len(filedata) < filesize:
        if filesize - len(filedata) > 65536:
            filedata += sock.recv(65536)
        else:
            filedata += sock.recv(filesize - len(filedata))
            break

    if not os.path.exists('files'):
        os.mkdir('files')
    with open(f'files/{filename}', 'wb') as f:
        f.write(filedata)

def normal_messaging(sock, message):
    sender, body = message
    print(f"\r{sender}: {body}\n----------\n>> ", end='')

def broadcast_messaging(sock, message):
    sender, body = message
    print(f"\r(Broadcast) {sender}: {body}\n----------\n>> ", end='')
    
def send_file(sock, message):
    global sendfiledata
    sock.sendall(sendfiledata)

COMMANDS = {
    '_request': incoming_friend_request, # sender username
    '_requestcreated': outgoing_friend_request,
    '_requestexists': friend_request_already_exist, # destination username
    '_requestaccepted': outgoing_friend_request_accepted, # other username
    '_requestsentaccept': incoming_friend_request_accepted, # other username
    '_alreadyfriends': friend_already_exist, # destination username
    '_requestdoesnotexist': friend_request_does_not_exist, # other username
    '_notfriends': not_friends_yet, # other username
    '_friendlisting': friend_list, # array friend
    '_removefriend': friend_remove, # username
    '_removedbyfriend': friend_removed, # username remover
    '_sendfile_ok': send_file, # no params
    '_acceptfile': receive_file, # sender username, filename, filesize 
    '_message': normal_messaging, # sender username, message
    '_bcastrecv': broadcast_messaging # sender username, message
}

def receive_message(sock_client):
    while True:
        data = sock_client.recv(65535)
        if len(data) == 0:
            break
        payload = pickle.loads(data)
        COMMANDS[payload.command](sock_client, payload.args)

def main():
    username = input('Set username: ').strip().lstrip('_')
    print(f'Username set: {username}')

    sock_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_client.connect(REMOTE_ADDRESS)

    sock_client.send(username.encode(ENCODING))

    thread_receive = Thread(target=receive_message, args=(sock_client,))
    thread_receive.start()

    while True:
        dest = input(\
'''----------
Available commands:
_bcast <message>\tBroadcast a message
_pm <recipient> <message>\tSend a message to recipient
_req <username>\tSend a friend request to username
_acc <username>\tAccept a friend request from username
_friendlist\tSee your friend list
_removefriend <username>\tRemove a friend from friend list
_sendfile <username> <path>\tSend a file at path to username
_quit\tExit the app
----------
>> ''')
        available_commands = ('_bcast', '_pm', '_req', '_acc', '_sendfile', '_quit', '_friendlist', '_removefriend')
        command = dest.split(" ", 1)
        if command[0] not in available_commands:
            print(f'\rCommand {command[0]} not found.\n----------\n>> ', end='')
        elif command[0] == '_quit':
            sock_client.close()
            break
        elif command[0] == '_sendfile':
            username, path = dest.split(" ", 2)[1:]
            size = os.path.getsize(path)
            filename = path.split("/")[-1]
            filedata = b''
            with open(path, 'rb') as f:
                filedata += f.read()

            global sendfiledata
            sendfiledata = filedata

            data = pickle.dumps(Payload(command[0], (username, filename, size)))
            sock_client.send(data)
        elif command[0] == '_pm':
            args = command[1].split(' ')
            data = pickle.dumps(Payload(command[0], (args[0], args[1])))
            sock_client.send(data)
        elif command[0] == '_friendlist':
            data = pickle.dumps(Payload(command[0], ()))
            sock_client.send(data)
        else:
            data = pickle.dumps(Payload(command[0], (command[1],)))
            sock_client.send(data)

if __name__ == '__main__':
    main()
