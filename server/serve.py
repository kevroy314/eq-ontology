#!/usr/bin/env python3
"""Static server for the EQ ontology dashboard with caching disabled, so edits
to index.html / data JSON always show up on refresh (no cache-busting needed)."""
import http.server, socketserver, os

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("0.0.0.0", 8787), NoCacheHandler) as httpd:
        print("serving /home/kevin/eq/server on :8787 (no-cache)")
        httpd.serve_forever()
