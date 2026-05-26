<?php
/**
 * SSE Streaming API - Forwards Python chunks to browser in real-time
 */

// CRITICAL: Disable all output buffering
ob_implicit_flush(true);
ob_end_flush();
if (ob_get_level()) {
    while (ob_get_level()) ob_end_flush();
}

header('Content-Type: text/event-stream');
header('Cache-Control: no-cache');
header('Connection: keep-alive');
header('X-Accel-Buffering: no');  // Disable nginx buffering

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    echo "event: error\ndata: " . json_encode(['error' => 'POST only']) . "\n\n";
    exit;
}

// Read POST body (SSE usually sends data via POST)
$json = file_get_contents('php://input');
$data = json_decode($json, true);

if (empty($data['query'])) {
    echo "event: error\ndata: " . json_encode(['error' => 'Query required']) . "\n\n";
    exit;
}

$host = '127.0.0.1';
$port = 9999;
$timeout = 120;

$socket = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if (!$socket) {
    echo "event: error\ndata: " . json_encode(['error' => 'Socket failed']) . "\n\n";
    exit;
}

socket_set_option($socket, SOL_SOCKET, SO_RCVTIMEO, ['sec' => $timeout, 'usec' => 0]);
socket_set_option($socket, SOL_SOCKET, SO_SNDTIMEO, ['sec' => 5, 'usec' => 0]);

// Disable Nagle algorithm for low latency
socket_set_option($socket, SOL_TCP, TCP_NODELAY, 1);

if (!socket_connect($socket, $host, $port)) {
    echo "event: error\ndata: " . json_encode(['error' => 'Cannot connect to AI server']) . "\n\n";
    socket_close($socket);
    exit;
}

// Send query to Python
$payload = json_encode(['query' => $data['query']]) . "\n";
socket_write($socket, $payload, strlen($payload));

// Stream Python's chunks directly to browser
$buffer = '';
while (true) {
    $chunk = socket_read($socket, 4096);
    if ($chunk === false || $chunk === '') {
        break;
    }
    
    $buffer .= $chunk;
    
    // Process complete lines (newline-delimited JSON)
    while (($pos = strpos($buffer, "\n")) !== false) {
        $line = substr($buffer, 0, $pos);
        $buffer = substr($buffer, $pos + 1);
        
        if (empty($line)) continue;
        
        $token_data = json_decode($line, true);
        if (!$token_data) continue;
        
        // Send SSE event
        echo "event: message\n";
        echo "data: " . json_encode($token_data) . "\n\n";
        
        // Flush to browser immediately
        if (ob_get_level()) {
            ob_flush();
        }
        flush();
        
        // Check if done
        if (!empty($token_data['done'])) {
            break 2;
        }
    }
}

socket_close($socket);

// Send final done event
echo "event: done\ndata: " . json_encode(['finished' => true]) . "\n\n";
flush();
?>