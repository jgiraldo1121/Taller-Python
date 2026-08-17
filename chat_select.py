import argparse
import pickle
import select
import socket
import struct
import sys
import threading

SERVER_HOST = '127.0.0.1'
CHAT_SERVER_NAME = 'server'

def send(channel, *args):
    buffer = pickle.dumps(args)
    value = socket.htonl(len(buffer))
    size = struct.pack("L", value)
    channel.sendall(size)
    channel.sendall(buffer)

def receive(channel):
    size_len = struct.calcsize("L")
    try:
        size_data = channel.recv(size_len)
        if not size_data or len(size_data) < size_len:
            return ''
        size = socket.ntohl(struct.unpack("L", size_data)[0])
    except (struct.error, OSError):
        return ''
    
    buf = bytearray()
    while len(buf) < size:
        chunk = channel.recv(size - len(buf))
        if not chunk:
            break
        buf.extend(chunk)
    if not buf:
        return ''
    return pickle.loads(buf)[0]

class ChatServer:
    def __init__(self, port, backlog=5):
        self.clients = 0
        self.clientmap = {}
        self.outputs = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((SERVER_HOST, port))
        print(f"Servidor escuchando en puerto: {port} ...")
        self.server.listen(backlog)

    def get_client_name(self, client):
        info = self.clientmap[client]
        host, name = info[0][0], info[1]
        return f"{name}@{host}"

    def run(self):
        inputs = [self.server]
        running = True
        while running:
            try:
                readable, _, _ = select.select(inputs, [], [])
            except OSError:
                break
            for sock in readable:
                if sock == self.server:
                    client, address = self.server.accept()
                    print(f"Chat server: nueva conexión desde {address}")
                    raw_name = receive(client)
                    if not raw_name or 'NAME: ' not in raw_name:
                        client.close()
                        continue
                    cname = raw_name.split('NAME: ')[1]
                    self.clients += 1
                    send(client, f'CLIENT: {address[0]}')
                    inputs.append(client)
                    self.clientmap[client] = (address, cname)
                    msg = f"\n(Conectado: Nuevo cliente ({self.clients}) desde {self.get_client_name(client)})"
                    for output in self.outputs:
                        send(output, msg)
                    self.outputs.append(client)
                else:
                    try:
                        data = receive(sock)
                        if data:
                            msg = f"\n#[{self.get_client_name(sock)}]>>{data}"
                            for output in self.outputs:
                                if output != sock:
                                    send(output, msg)
                        else:
                            print(f"Chat server: cliente desconectado")
                            self.clients -= 1
                            sock.close()
                            if sock in inputs: inputs.remove(sock)
                            if sock in self.outputs: self.outputs.remove(sock)
                            msg = f"\n(Desconectado: Cliente desde {self.get_client_name(sock)})"
                            for output in self.outputs:
                                send(output, msg)
                    except OSError:
                        if sock in inputs: inputs.remove(sock)
                        if sock in self.outputs: self.outputs.remove(sock)

class ChatClient:
    def __init__(self, name, port, host=SERVER_HOST):
        self.name = name
        self.connected = False
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.sock.connect((host, self.port))
            print(f"Conectado al servidor de chat en puerto {self.port}")
            self.connected = True
            send(self.sock, f'NAME: {self.name}')
            data = receive(self.sock)
            addr = data.split('CLIENT: ')[1]
            self.prompt = f'[{self.name}@{addr}]> '
        except OSError as e:
            print(f"Error al conectar al puerto {self.port}: {e}")
            sys.exit(1)

    def _listen_console(self):
        while self.connected:
            try:
                msg = input()
                if msg and self.connected:
                    send(self.sock, msg)
            except (EOFError, KeyboardInterrupt):
                self.connected = False
                break

    def run(self):
        threading.Thread(target=self._listen_console, daemon=True).start()
        while self.connected:
            try:
                readable, _, _ = select.select([self.sock], [], [], 0.5)
                for sock in readable:
                    data = receive(sock)
                    if not data:
                        print("\nServidor desconectado.")
                        self.connected = False
                        break
                    print(f"{data}\n{self.prompt}", end='', flush=True)
            except KeyboardInterrupt:
                print("\nCliente interrumpido.")
                self.sock.close()
                break

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Socket Server con Select (Python 3)')
    parser.add_argument('--name', required=True)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()

    if args.name == CHAT_SERVER_NAME:
        server = ChatServer(args.port)
        server.run()
    else:
        client = ChatClient(name=args.name, port=args.port)
        client.run()