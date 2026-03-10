import socket

SHUTDOWN_PASSWORD = "nick"
SHUTDOWN_PORT = 6000

def send_shutdown_command():
    try:
        with socket.create_connection(('localhost', SHUTDOWN_PORT), timeout=10) as s:
            command = f"shutdown {SHUTDOWN_PASSWORD}"
            s.sendall(command.encode('utf-8'))
            response = s.recv(1024).decode('utf-8')
            print("Response from shutdown listener:", response)
    except Exception as e:
        print("Error sending shutdown command:", e)

if __name__ == "__main__":
    send_shutdown_command()
