<?php
/**
 * SSE Streaming API - Streams directly from Google Gemini API
 * 
 * Setup: Get a free API key from https://aistudio.google.com/app/apikey
 *        Set it below or via environment variable: GEMINI_API_KEY
 */

// ─── CONFIG ─────────────────────────────────────────────────────────
$GEMINI_API_KEY = getenv('GEMINI_API_KEY') ?: 'AQ.Ab8RN6KK16GDAdckP_qJqjRmr2o86FsqvG9nmDCrE_l6Ub-oSw';
$GEMINI_MODEL   = getenv('GEMINI_MODEL')   ?: 'gemini-2.5-flash';
$GEMINI_BASE_URL = 'https://generativelanguage.googleapis.com/v1beta/models';

// ─── DISABLE ALL BUFFERING ──────────────────────────────────────────
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

// ─── READ CLIENT REQUEST ────────────────────────────────────────────
$json = file_get_contents('php://input');
$data = json_decode($json, true);

if (empty($data['query'])) {
    echo "event: error\ndata: " . json_encode(['error' => 'Query required']) . "\n\n";
    exit;
}

// ─── BUILD GEMINI REQUEST ───────────────────────────────────────────
$geminiUrl = sprintf(
    '%s/%s:streamGenerateContent?alt=sse&key=%s',
    $GEMINI_BASE_URL,
    $GEMINI_MODEL,
    urlencode($GEMINI_API_KEY)
);

$geminiPayload = json_encode([
    'contents' => [
        [
            'role'  => 'user',
            'parts' => [
                ['text' => $data['query']]
            ]
        ]
    ],
    'generationConfig' => [
        'maxOutputTokens' => 1024,
        'temperature'     => 0.7,
        'topP'            => 0.9,
    ],
    'safetySettings' => [
        ['category' => 'HARM_CATEGORY_HARASSMENT',       'threshold' => 'BLOCK_MEDIUM_AND_ABOVE'],
        ['category' => 'HARM_CATEGORY_HATE_SPEECH',      'threshold' => 'BLOCK_MEDIUM_AND_ABOVE'],
        ['category' => 'HARM_CATEGORY_SEXUALLY_EXPLICIT','threshold' => 'BLOCK_MEDIUM_AND_ABOVE'],
        ['category' => 'HARM_CATEGORY_DANGEROUS_CONTENT','threshold' => 'BLOCK_MEDIUM_AND_ABOVE'],
    ]
]);

// ─── STREAM FROM GEMINI TO CLIENT ───────────────────────────────────
$ch = curl_init($geminiUrl);

curl_setopt_array($ch, [
    CURLOPT_POST           => true,
    CURLOPT_POSTFIELDS     => $geminiPayload,
    CURLOPT_HTTPHEADER     => [
        'Content-Type: application/json',
        'Accept: text/event-stream'
    ],
    CURLOPT_RETURNTRANSFER => false,  // We want to stream directly
    CURLOPT_WRITEFUNCTION  => function ($ch, $chunk) {
        // Gemini returns SSE format: data: {...}\n\n
        // We parse each SSE line and re-emit in our own SSE format
        // so the frontend contract stays identical to the old Python backend
        
        static $buffer = '';
        $buffer .= $chunk;
        
        while (($pos = strpos($buffer, "\n")) !== false) {
            $line = substr($buffer, 0, $pos);
            $buffer = substr($buffer, $pos + 1);
            
            $line = trim($line);
            if (empty($line) || !str_starts_with($line, 'data: ')) {
                continue;
            }
            
            $jsonStr = substr($line, 6); // Remove "data: " prefix
            
            // Gemini sends "[DONE]" as final marker in some proxies
            if ($jsonStr === '[DONE]') {
                echo "event: done\ndata: " . json_encode(['finished' => true]) . "\n\n";
                flush();
                continue;
            }
            
            $geminiChunk = json_decode($jsonStr, true);
            if (!$geminiChunk || empty($geminiChunk['candidates'])) {
                continue;
            }
            
            // Extract token text from Gemini's nested structure
            $candidate = $geminiChunk['candidates'][0] ?? null;
            $parts     = $candidate['content']['parts'] ?? [];
            $tokenText = '';
            
            foreach ($parts as $part) {
                $tokenText .= $part['text'] ?? '';
            }
            
            $isDone = !empty($candidate['finishReason']);
            
            // Re-emit in the SAME format as the old Python backend
            // { token: "...", done: false }
            echo "event: message\n";
            echo "data: " . json_encode([
                'token' => $tokenText,
                'done'  => $isDone
            ]) . "\n\n";
            
            if (ob_get_level()) ob_flush();
            flush();
            
            if ($isDone) {
                // Send final done event too
                echo "event: done\ndata: " . json_encode(['finished' => true]) . "\n\n";
                flush();
            }
        }
        
        return strlen($chunk); // Required by cURL
    },
    CURLOPT_TIMEOUT        => 120,
    CURLOPT_FOLLOWLOCATION => true,
    CURLOPT_SSL_VERIFYPEER => true,
]);

// Execute — this blocks and streams via the write callback
$result = curl_exec($ch);

if ($result === false) {
    $error = curl_error($ch);
    echo "event: error\ndata: " . json_encode(['error' => 'Gemini API error: ' . $error]) . "\n\n";
    flush();
}

unset($ch);

// Final safety flush
echo "event: done\ndata: " . json_encode(['finished' => true]) . "\n\n";
flush();
?>