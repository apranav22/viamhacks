"""Laptop redirect + UDP relay for the station dashboard. No camera or robot connection.

python -I dashboard/relay.py --station 172.16.0.182
HTTP stays loopback-only; run telemetry received on UDP 8766 forwards unchanged to station UDP 8776.
"""
import argparse
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--station', required=True)
    ap.add_argument('--station-port', type=int, default=8775)
    ap.add_argument('--station-udp-port', type=int, default=8776)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--udp-port', type=int, default=8766)
    args = ap.parse_args()
    address = socket.gethostbyname(args.station)
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.bind(('0.0.0.0', args.udp_port))

    class Redirect(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header('Location', f'http://{address}:{args.station_port}/')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def log_message(self, *args):
            pass

    def forward():
        while True:
            data, _ = udp.recvfrom(65535)
            udp.sendto(data, (address, args.station_udp_port))

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Redirect)
    threading.Thread(target=forward, daemon=True).start()
    print(f'localhost:{args.port} -> {address}:{args.station_port}; UDP relay active', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
