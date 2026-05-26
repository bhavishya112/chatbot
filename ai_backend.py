#!/usr/bin/env python3
"""
AI Streaming Server - Sends tokens as they're generated
Start: python3 ai_stream_server.py &
"""

import socket
import json
import signal
import sys
import warnings
from transformers import pipeline, TextIteratorStreamer
from threading import Thread

HOST = '127.0.0.1'
PORT = 9999

pipe = None

def load_model():
    global pipe
    warnings.filterwarnings('ignore')
    print("[SERVER] Loading model...", flush=True)
    
    pipe = pipeline(
        "text-generation",
        model="meta-llama/Llama-3.2-1B-Instruct",
        torch_dtype="auto",
        device_map="auto"
    )
    print("[SERVER] Ready on port 9999", flush=True)

def stream_response(query, conn):
    """Generate and stream tokens immediately"""
    try:
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": query}
        ]
        
        # Use streamer for token-by-token output
        streamer = TextIteratorStreamer(pipe.tokenizer, skip_prompt=True, skip_special_tokens=True)
        
        # Generation args
        generation_kwargs = dict(
            text_inputs=messages,
            max_new_tokens=256,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            streamer=streamer,
        )
        
        # Run generation in background thread
        thread = Thread(target=pipe, kwargs=generation_kwargs)
        thread.start()
        
        # Stream each token as it's generated
        generated_text = ""
        for new_text in streamer:
            generated_text += new_text
            
            # Send chunk immediately to PHP
            chunk = json.dumps({
                'token': new_text,
                'done': False
            }) + "\n"  # newline delimiter
            
            conn.sendall(chunk.encode('utf-8'))
            conn.settimeout(0.1)  # small timeout to flush buffer
        
        # Send completion signal
        done_msg = json.dumps({
            'token': '',
            'done': True,
            'full_response': generated_text
        }) + "\n"
        conn.sendall(done_msg.encode('utf-8'))
        
        thread.join()
        
    except Exception as e:
        error_msg = json.dumps({
            'token': '',
            'done': True,
            'error': str(e)
        }) + "\n"
        conn.sendall(error_msg.encode('utf-8'))

def main():
    signal.signal(signal.SIGINT, lambda s,f: sys.exit(0))
    load_model()
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    print("[SERVER] Waiting for connections...", flush=True)
    
    while True:
        conn, addr = server.accept()
        print(f"[SERVER] Connection from {addr}", flush=True)
        
        with conn:
            # Read query
            data = b''
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b'\n' in chunk or len(chunk) < 4096:
                    break
            
            try:
                request = json.loads(data.decode('utf-8'))
                query = request.get('query', '')
                
                if query:
                    stream_response(query, conn)
                    
            except Exception as e:
                print(f"[SERVER] Error: {e}", flush=True)
        
        print(f"[SERVER] Connection closed", flush=True)

if __name__ == "__main__":
    main()