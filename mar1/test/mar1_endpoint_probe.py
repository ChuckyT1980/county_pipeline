import socket
import ssl
import time
import json
import requests
from urllib.parse import urlparse
import datetime

def profile_endpoint(url: str, output_file: str):
    parsed = urlparse(url)
    hostname = parsed.hostname
    port = parsed.port if parsed.port else (443 if parsed.scheme == 'https' else 80)
    
    profile = {
        "url": url,
        "dns_resolved": False,
        "tcp_connected": False,
        "tls_established": False,
        "http_status": None,
        "latency_ms": None,
        "response_bytes": 0,
        "redirect_count": 0,
        "capture_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "error_stage": None,
        "error_message": None
    }
    
    start_time = time.time()
    
    try:
        # 1. DNS Resolution
        try:
            ip = socket.gethostbyname(hostname)
            profile["dns_resolved"] = True
        except socket.gaierror as e:
            profile["error_stage"] = "DNS"
            profile["error_message"] = str(e)
            return profile
            
        # 2. TCP Connection
        try:
            sock = socket.create_connection((ip, port), timeout=5.0)
            profile["tcp_connected"] = True
        except (socket.timeout, ConnectionRefusedError, OSError) as e:
            profile["error_stage"] = "TCP"
            profile["error_message"] = str(e)
            return profile
            
        # 3. TLS Handshake
        if parsed.scheme == 'https':
            try:
                context = ssl.create_default_context()
                ssock = context.wrap_socket(sock, server_hostname=hostname)
                profile["tls_established"] = True
                ssock.close()
            except ssl.SSLError as e:
                profile["error_stage"] = "TLS"
                profile["error_message"] = str(e)
                sock.close()
                return profile
            except Exception as e:
                profile["error_stage"] = "TLS_WRAP"
                profile["error_message"] = str(e)
                sock.close()
                return profile
        else:
            profile["tls_established"] = True # N/A for HTTP
            sock.close()
            
        # 4. HTTP Request
        try:
            http_start = time.time()
            resp = requests.get(url, timeout=10.0)
            latency = (time.time() - http_start) * 1000
            
            profile["http_status"] = resp.status_code
            profile["latency_ms"] = int(latency)
            profile["response_bytes"] = len(resp.content)
            profile["redirect_count"] = len(resp.history)
            
        except requests.exceptions.RequestException as e:
            profile["error_stage"] = "HTTP"
            profile["error_message"] = str(e)
            
    finally:
        total_latency = (time.time() - start_time) * 1000
        if profile["latency_ms"] is None:
            profile["latency_ms"] = int(total_latency)
            
        with open(output_file, "w") as f:
            json.dump(profile, f, indent=2)

if __name__ == "__main__":
    print("Running Endpoint Certification Probe...")
    profile_endpoint("https://mptsweb.co.shasta.ca.us/search.asp", "endpoint_profile_shasta.json")
    print("Shasta probe complete. Results saved to endpoint_profile_shasta.json")
    
    profile_endpoint("https://mptsweb.co.tehama.ca.us/taxsearch", "endpoint_profile_tehama.json")
    print("Tehama probe complete. Results saved to endpoint_profile_tehama.json")
