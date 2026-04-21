import socket
import threading

def receive_messages(sock):
    """Receive messages from the server."""
    while True:
        try:
            message = sock.recv(1024).decode('utf-8')
            if not message:
                break
            print(message)
        except Exception:
            break

def main():
    username = input('Enter your name: ').strip()
    if not username:
        print('Name cannot be empty.')
        return

    # Create client socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect(('127.0.0.1', 12345))
    except Exception:
        print('Failed to connect to server.')
        return

    client_socket.send(username.encode('utf-8'))

    # Start thread to receive messages
    threading.Thread(target=receive_messages, args=(client_socket,), daemon=True).start()

    print('Enter messages to send (type \'exit\' to quit):')
    while True:
        message = input()
        if message == 'exit':
            break
        client_socket.send(message.encode('utf-8'))

    client_socket.close()

if __name__ == '__main__':
    main()
