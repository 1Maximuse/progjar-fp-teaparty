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

# 0: outside lobby
# 1: inside lobby
# 2: game started
global state
state = 0

input_message = ([
    '\rAvailable commands:',
    '_roomlist                           List of rooms',
    '_makeroom <number of participants>  Make a room',
    '_joinroom <code>                    Join room with specific code',
    '_bcast <message>                    Broadcast a message',
    '_pm <recipient> <message>           Send a message to recipient',
    '_req <username>                     Send a friend request to username',
    '_acc <username>                     Accept a friend request from username',
    '_friendlist                         See your friend list',
    '_removefriend <username>            Remove a friend from friend list',
    '_sendfile <username> <path>         Send a file at path to username',
    '_quit                               Exit the app',
    '----------',
    '>> '
], [
    '\rAvailable commands:',
    '_kick <username>                    Kick player from room',
    '_leave                              Leave room',
    '_participants                       View room participants',
    '_startgame                          Start the game',
    '----------',
    '>> '
], [
    '\rAvailable commands:',
    '_g <word>                           Guess the word',
    '----------',
    '>> '
])

def incoming_friend_request(sock, message):
    sender, = message
    print_message(f'Received friend request from {sender}, enter _acc {sender} to accept.')


def outgoing_friend_request(sock, message):
    dest, = message
    print_message(f'Friend request to {dest} sent.')


def friend_request_already_exist(sock, message):
    dest, = message
    print_message(f'You have already sent {dest} a friend request.')


def outgoing_friend_request_accepted(sock, message):
    dest, = message
    print_message(f'Your friend request has been accepted by {dest}.')


def incoming_friend_request_accepted(sock, message):
    dest, = message
    print_message(f'You are now friends with {dest}.')


def friend_already_exist(sock, message):
    dest, = message
    print_message(f'You already have {dest} in your friend list.')


def friend_request_does_not_exist(sock, message):
    other, = message
    print_message(f'There is no friend request from {other}.')


def not_friends_yet(sock, message):
    dest, = message
    print_message(f'You are not friends with {dest} yet.')


def friend_list(sock, message):
    friendlist, incoming, outgoing = message
    msg = 'Current friend list:\n'
    i = 1
    for friend in friendlist:
        msg += f'{i}. {friend}\n'
        i = i + 1
    msg += '----------\nIncoming friend request:\n'
    i = 1
    for friend in incoming:
        msg += f'{i}. {friend}\n'
        i = i + 1
    msg += '----------\nSent friend request:\n'
    i = 1
    for friend in outgoing:
        msg += f'{i}. {friend}\n'
        i = i + 1
    print_message(msg)


def friend_remove(sock, message):
    friend, = message
    print_message(f'You have removed {friend} from your friend list.')


def friend_removed(sock, message):
    friend, = message
    print_message(f'Your friendship with {friend} has been revoked.')


def receive_file(sock, message):
    sender, filename, filesize = message
    filedata = b''
    sock.send(pickle.dumps(Payload('_sendfile_ok', ())))
    print_message(f'You received a file from {sender} named {filename} with size of {filesize} bytes.')
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
    print_message(f"{sender}: {body}")

def broadcast_messaging(sock, message):
    sender, body = message
    print_message(f"(Broadcast) {sender}: {body}")

def send_file(sock, message):
    global sendfiledata
    sock.sendall(sendfiledata)

def room_created(sock, message):
    code, maxparticipants = message
    global state
    state = 1
    print_command()
    print_message(f'Successfully created and joined room with code {code} 1/{maxparticipants}')

def room_joined(sock, message):
    code, participantcount, maxparticipant = message
    global state
    state = 1
    print_command()
    print_message(f'Successfully joined room with code {code} {participantcount}/{maxparticipant}')

def room_invalid_code(sock, message):
    code, = message
    print_message(f"Room with code {code} not found")

def room_otherjoined(sock, message):
    joiner_username, room_code, num_players, max_players = message
    print_message(f"{joiner_username} has joined to room {room_code} {num_players}/{max_players}")

def cannot_kick(sock, message):
    print_message(f"You are not authorized to kick")

def cannot_kick_room(sock, message):
    print_message(f'Cannot kick, player is not in the same room.')

def room_kick_success(sock, message):
    kicked, currentplayer, maxparticipants = message
    print_message(f"Successfully kicked {kicked} from room {currentplayer}/{maxparticipants}")

def room_kicked(sock, message):
    code, = message
    global state
    state = 0
    print_command()
    print_message(f"You are kicked from room {code}.")

def room_leave(sock, message):
    global state
    state = 0
    print_command()
    print_message('Successfully left room.')

def room_close(sock, message):
    global state
    state = 0
    print_command()
    print_message('Room has been closed')

def game_start(sock, message):
    global state
    state = 2
    print_command()
    print_message('Game is started')

def room_participant(sock, message):
    participants, = message
    msg = 'Room participants:\n'
    i = 1
    for participant in participants:
        msg += f'{i}. {participant}\n'
        i = i+1
    print_message(msg)

def new_round(sock, message):
    prompt, current_round, max_round = message
    print_message(f'Round {current_round}/{max_round}\nType the longest word containing: {prompt}')

def player_guessed(sock, message):
    guesser, word, = message
    print_message(f'{guesser}: {word}')

def winning_answer(sock, message):
    guesser, word, = message
    length = len(word)
    print_message(f'{guesser} is leading with {word} (word length: {length})')

def game_over(sock, message):
    winner, score, = message
    global state
    state = 1
    print_command()
    msg = f'{winner[0]}'
    if len(winner) > 1:
        for w in winner[1:]:
            msg += f', {w}'
    print_message(f'{msg} won the game with score of {score} >.<')

def round_winner(sock, message):
    winner, word, point, = message
    if winner is not None:
        print_message(f'{winner} won the round with the word: {word}. Total points: {point}')
    else:
        print_message(f'No one guessed right >:(')

def cannot_start(sock, message):
    print_message(f"You are not authorized to start game")

def room_list(sock, message):
    rooms, = message
    msg = 'Code\tLeader\tCapacity\tStatus\n'
    for room in rooms:
        if room[4]:
            msg += f'{room[0]}\t\t{room[1]}\t{room[2]}/{room[3]}\tStarted\n'
        else:
            msg += f'{room[0]}\t\t{room[1]}\t{room[2]}/{room[3]}\tWaiting\n'
    print_message(msg)

def room_already_running(sock, message):
    code, = message
    print_message(f'Cannot join room {code}, game is already started')

def room_full(sock, message):
    code, = message
    print_message(f'Cannot join room {code}, room is full')

def wrong_room_size(sock, message):
    print_message('Room size should be 2-5')

def print_message(message):
    message = message.strip("\n")
    print(f'\r{message}\n----------\n>> ', end='')

COMMANDS = {
    '_request': incoming_friend_request,  # sender username
    '_requestcreated': outgoing_friend_request,
    '_requestexists': friend_request_already_exist,  # destination username
    '_requestaccepted': outgoing_friend_request_accepted,  # other username
    '_requestsentaccept': incoming_friend_request_accepted,  # other username
    '_alreadyfriends': friend_already_exist,  # destination username
    '_requestdoesnotexist': friend_request_does_not_exist,  # other username
    '_notfriends': not_friends_yet,  # other username
    '_friendlisting': friend_list,  # array friend
    '_removefriend': friend_remove,  # username
    '_removedbyfriend': friend_removed,  # username remover
    '_sendfile_ok': send_file,
    '_acceptfile': receive_file,  # sender username, filename, filesize
    '_message': normal_messaging,  # sender username, message
    '_bcastrecv': broadcast_messaging,  # sender username, message
    '_roomcreated': room_created,  # room code
    '_joinedroom': room_joined, # room code, num players, max players
    '_playerjoinedroom': room_otherjoined, # joiner username, room code, num players, max players
    '_invalidroomcode': room_invalid_code, # code
    '_cannotkick_notleader': cannot_kick,
    '_cannotkick_notinroom': cannot_kick_room,
    '_kicksuccess': room_kick_success, # kicked username, num players, max players
    '_kickedfromroom': room_kicked, # code
    '_leavesuccess': room_leave,
    '_roomclosed': room_close,
    '_roomparticipants': room_participant, # list of players
    '_playerguessed': player_guessed, # username, word
    '_winninganswer': winning_answer, # username, word
    '_newround': new_round, # prompt, current round, max round
    '_gamestart': game_start,
    '_gameover': game_over, # usernames, score
    '_roundwinner': round_winner, # username word point
    '_cannotstart_notleader': cannot_start,
    '_roomlistdata': room_list, # code, party leader, participants, max participants, status
    '_roomalreadyrunning': room_already_running, # room code
    '_roomfull': room_full, #room code
    '_wrongroomsize': wrong_room_size,
}

def receive_message(sock_client):
    while True:
        data = sock_client.recv(65535)
        if len(data) == 0:
            break
        payload = pickle.loads(data)
        COMMANDS[payload.command](sock_client, payload.args)

def print_command():
    print('\n'.join(input_message[state]), end='')

def main():
    username = input('Set username: ').strip().lstrip('_')
    print(f'Username set: {username}')

    sock_client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock_client.connect(REMOTE_ADDRESS)

    sock_client.send(username.encode(ENCODING))

    thread_receive = Thread(target=receive_message, args=(sock_client,))
    thread_receive.start()

    print_command()
    while True:
        dest = input()
        available_commands = (
            ('_bcast', '_pm', '_req', '_acc', '_sendfile', '_quit', '_friendlist', '_removefriend', '_makeroom', '_joinroom', '_roomlist'), # not connected to room
            ('_kick', '_leave', '_participants', '_startgame'), # connected to room
            ('_g'), # game playing
        )
        command = dest.split(" ", 1)
        if command[0] not in available_commands[state]:
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
        elif command[0] in ['_friendlist', '_participants', '_leave', '_startgame', '_roomlist']:
            data = pickle.dumps(Payload(command[0], ()))
            sock_client.send(data)
        else:
            data = pickle.dumps(Payload(command[0], (command[1],)))
            sock_client.send(data)
        print_command()

if __name__ == '__main__':
    main()
