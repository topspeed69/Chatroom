import socket
import threading

from db import init_db, save_message, get_recent_messages

# List to keep track of connected clients
clients: list[socket.socket] = []
client_names: dict[socket.socket, str] = {}

def broadcast(message: str, sender_socket: socket.socket) -> None:
    """Broadcast a message to all clients except the sender."""
    for client in list(clients):
        if client != sender_socket:
            try:
                client.send(message.encode('utf-8'))
            except Exception:
                clients.remove(client)
                client_names.pop(client, None)


def send_history(client_socket: socket.socket, limit: int = 50) -> None:
    """Send recent chat history to a newly connected client."""
    history = get_recent_messages(limit)
    if not history:
        return

    try:
        client_socket.send("--- Recent chat history ---\n".encode('utf-8'))
        for message in history:
            formatted = f"[{message.timestamp.isoformat()}] {message.username}: {message.content}\n"
            client_socket.send(formatted.encode('utf-8'))
        client_socket.send("--- End of history ---\n".encode('utf-8'))
    except Exception:
        pass


def handle_client(client_socket: socket.socket) -> None:
    """Handle communication with a single client."""
    try:
        client_socket.send("Please enter your name: ".encode('utf-8'))
        username = client_socket.recv(1024).decode('utf-8').strip()
    except Exception:
        client_socket.close()
        return

    if not username:
        client_socket.send("Invalid name. Disconnecting.\n".encode('utf-8'))
        client_socket.close()
        return

    client_names[client_socket] = username
    send_history(client_socket)
    broadcast(f"{username} has joined the chat.", client_socket)
    print(f"{username} connected.")

    while True:
        try:
            message = client_socket.recv(1024).decode('utf-8')
            if not message:
                break
            print(f"Received from {username}: {message}")
            save_message(username, message)
            formatted = f"{username}: {message}"
            broadcast(formatted, client_socket)
        except Exception:
            break

    if client_socket in clients:
        clients.remove(client_socket)
    client_names.pop(client_socket, None)
    client_socket.close()

def main() -> None:
    init_db()

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.bind(('0.0.0.0', 12345))
    server_socket.listen(5)
    print("Server listening on port 12345")

    while True:
        client_socket, addr = server_socket.accept()
        print(f"Client connected from {addr}")
        clients.append(client_socket)
        # Start a new thread for the client
        threading.Thread(target=handle_client, args=(client_socket,)).start()

if __name__ == "__main__":
    main()