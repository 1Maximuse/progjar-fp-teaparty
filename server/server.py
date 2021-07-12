import os
import sys

sys.path.append(os.path.abspath('..'))

import pickle
import random
import socket
import string
import time
from urllib.request import urlopen
from queue import Queue
from threading import Lock, Thread

lock_friends = Lock()

from payload import Payload

LISTEN_ADDRESS = ('0.0.0.0', 6666)
LISTEN_CLIENTS = 10
BUFFER_SIZE = 65536
ENCODING = 'utf-8'
DICTIONARY_FILE = urlopen("http://pages.cs.wisc.edu/~o-laughl/csw15.txt")

GAME_ROUNDS = 5
ROUND_SECONDS = 10

global dictionary
dictionary = set()
for line in DICTIONARY_FILE:
    dictionary.add(line.decode(ENCODING).strip())

global sendfiledata
sendfiledata = {}

global rooms
rooms = {}

class Room:
    def __init__(self, room_code, max_participants, partyleader_sock, partyleader_username):
        self.room_code = room_code
        self.participants = [(partyleader_sock, partyleader_username)]
        self.max_participants = max_participants
        self.party_leader = partyleader_username
        self.thread = None
        self.guess_queue = Queue()
        self.running = False
        
    def game_thread(self):
        self.running = True
        game_millis = 0
        game_round = 1
        round_begin = 0
        prompt = self.generate_prompt()
        current_winner = ('', '')
        scores = {}
        for socket, username in self.participants:
            scores[username] = 0
            send(socket, '_newround', (prompt, game_round, GAME_ROUNDS))

        while True:
            if game_round > GAME_ROUNDS:
                max_score = 0
                for username in scores:
                    if scores[username] > max_score:
                        max_score = scores[username]
                
                winners = []
                for username in scores:
                    if scores[username] == max_score:
                        winners.append(username)
                
                for socket, username in self.participants:
                    send(socket, '_gameover', (winners, max_score))
                break
                
            while not self.guess_queue.empty():
                guess = self.guess_queue.get()
                if guess[1].upper() in dictionary and len(guess[1]) > len(current_winner[1]):
                    current_winner = guess
                    for socket, name in self.participants:
                        send(socket, '_winninganswer', current_winner)
                        
            if game_millis == round_begin + ROUND_SECONDS * 1000:
                if current_winner[0] != '':
                    scores[current_winner[0]] += 1
                prompt = self.generate_prompt()
                game_round += 1
                for socket, username in self.participants:
                    if current_winner[0] != '':
                        send(socket, '_roundwinner', (current_winner[0], current_winner[1], scores[current_winner[0]]))
                    else:
                        send(socket, '_roundwinner', (None, None, None))
                    if game_round <= GAME_ROUNDS:
                        send(socket, '_newround', (prompt, game_round, GAME_ROUNDS))
                round_begin = game_millis
                current_winner = ('', '')

            time.sleep(0.01)
            game_millis += 10
        self.running = False
    
    def guess(self, username, word):
        for player_sock, player_username in self.participants:
            send(player_sock, '_playerguessed', (username, word))
        self.guess_queue.put((username, word))

    def generate_prompt(self):
        temp = ''
        while len(temp) < 3:
            temp = random.sample(tuple(dictionary), 1)[0]
            
        index = random.randrange(0, len(temp) - 2)
        return temp[index : index+3]

    def num_players(self):
        return len(self.participants)
    
    def add_player(self, sock, username):
        if self.num_players() < self.max_participants:
            for player in self.participants:
                send(player[0], '_playerjoinedroom', (username, self.room_code, self.num_players() + 1, self.max_participants))
            self.participants.append((sock, username))
            return True
        else:
            return False
    
    def remove_player(self, username):
        sock = None
        for socket, name in self.participants:
            if name == username:
                sock = socket
                break
        self.participants.remove((sock, username))
        send(sock, '_kickedfromroom', (self.room_code,))

    def leave_player(self, username):
        sock = None
        for socket, name in self.participants:
            if name == username:
                sock = socket
                break
        self.participants.remove((sock, username))

    def close(self):
        for player_sock, player_username in self.participants:
            send(player_sock, '_roomclosed', ())

def room_list(sock, username, clients, friends, args):
    listing = []
    for code in rooms:
        listing.append((code, rooms[code].party_leader, len(rooms[code].participants), rooms[code].max_participants, rooms[code].running))
    
    send(sock, '_roomlistdata', (listing,))

def start_game(sock, username, clients, friends, args):
    room_code = get_room(username)

    if username != rooms[room_code].party_leader:
        return error_cannotstart_notleader(sock)

    for player in rooms[room_code].participants:
        send(player[0], '_gamestart', ())
    if rooms[room_code].thread is not None and rooms[room_code].thread.is_alive():
        rooms[room_code].thread.join()
    rooms[room_code].thread = Thread(target=rooms[room_code].game_thread)
    rooms[room_code].thread.start()

def guess_word(sock, username, clients, friends, args):
    word, = args

    room_code = get_room(username)
    rooms[room_code].guess(username, word)

def room_participants(sock, username, clients, friends, args):
    room_code = get_room(username)
    participant = []
    for player_sock, player_username in rooms[room_code].participants:
        participant.append(player_username)
    send(sock, '_roomparticipants', (participant,))

def create_room(sock, username, clients, friends, args):
    max_participants, = args
    if int(max_participants) < 2 or int(max_participants) > 5:
        return error_roomsize(sock)
    code = ''.join(random.choice(string.ascii_uppercase) for i in range(3))
    while code in rooms:
        code = ''.join(random.choice(string.ascii_uppercase) for i in range(3))
    rooms[code] = Room(code, int(max_participants), sock, username)
    send(sock, '_roomcreated', (code, int(max_participants)))

def join_room(sock, username, clients, friends, args):
    room_code, = args

    if room_code not in rooms:
        send(sock, '_invalidroomcode', (room_code,))
        return
    
    if rooms[room_code].running:
        send(sock, '_roomalreadyrunning', (room_code,))
        return
    
    if len(rooms[room_code].participants) >= rooms[room_code].max_participants:
        send(sock, '_roomfull', (room_code,))
        return

    participantcount = rooms[room_code].num_players()
    maxparticipants = rooms[room_code].max_participants
    send(sock, '_joinedroom', (room_code, participantcount + 1, maxparticipants))
    rooms[room_code].add_player(sock, username)

def kick_from_room(sock, username, clients, friends, args):
    kicked_username, = args
    code = get_room(username)
    code2 = get_room(kicked_username)
    if code != code2:
        send(sock, '_cannotkick_notinroom', ())
    elif username == rooms[code].party_leader:
        rooms[code].remove_player(kicked_username)
        send(sock, '_kicksuccess', (kicked_username, rooms[code].num_players(), rooms[code].max_participants))
    else:
        send(sock, '_cannotkick_notleader', ())

def leave_room(sock, username, clients, friends, args):
    code = get_room(username)
    if username == rooms[code].party_leader:
        rooms[code].close()
        rooms.pop(code)
    else:
        rooms[code].leave_player(username)
        send(sock, '_leavesuccess', ())

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

def get_room(username):
    for code in rooms:
        for player_sock, player_username in rooms[code].participants:
            if username == player_username:
                return code

##### ERRORS ###########################################################

def error_alreadyfriends(sock, dest_username):
    send(sock, '_alreadyfriends', (dest_username,))


def error_requestexists(sock, dest_username):
    send(sock, '_requestexists', (dest_username,))


def error_requestdoesnotexist(sock, dest_username):
    send(sock, '_requestdoesnotexist', (dest_username,))


def error_notfriends(sock, dest_username):
    send(sock, '_notfriends', (dest_username,))

def error_roomsize(sock):
    send(sock, '_wrongroomsize', ())

def error_cannotstart_notleader(sock):
    send(sock, '_cannotstart_notleader', ())

########################################################################

def send(sock, command, args):
    sock.send(pickle.dumps(Payload(command, args)))


########################################################################

COMMANDS = {
    '_req': friend_request,  # dest_username
    '_acc': friend_accept,  # dest_username
    '_pm': private_message,  # dest_username, message
    '_bcast': broadcast,  # message
    '_sendfile': sendfile,  # dest_username, filename, filesize
    '_sendfile_ok': sendfile_ok,
    '_friendlist': friend_list,
    '_removefriend': remove_friend,  # dest_username
    '_makeroom': create_room,  # max_participants
    '_joinroom': join_room,  # room_code
    '_kick': kick_from_room, # kicked username
    '_leave': leave_room,
    '_participants': room_participants,
    '_g': guess_word, # word
    '_startgame': start_game,
    '_roomlist': room_list,
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

    print('Server started.')
    while True:
        sock_client, addr_client = sock_server.accept()
        username = sock_client.recv(BUFFER_SIZE).decode(ENCODING)
        print(f'{username} connected from {addr_client}')

        thread = Thread(target=serve_client, args=(sock_client, username, clients, friends))

        clients[username] = (sock_client, addr_client, thread)

        thread.start()


if __name__ == '__main__':
    main()
