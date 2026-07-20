<?php

header("Access-Control-Allow-Origin: *"); // or specify "http://localhost:8000"
header("Access-Control-Allow-Methods: GET, POST, OPTIONS");
header("Access-Control-Allow-Headers: Content-Type, Authorization");
header("Access-Control-Max-Age: 86400");
set_time_limit(180);

if ($_SERVER["REQUEST_METHOD"] === "OPTIONS") {
    http_response_code(200);
    exit;
}

header("Content-Type: text/event-stream");
header("Cache-Control: no-cache");
header("Connection: keep-alive");
header("X-Accel-Buffering: no");
$logdir = __DIR__ . "/logs/php_logs.log";

session_start();

/*
|--------------------------------------------------------------------------
| Dummy values (Replace these after login / conversation selection)
|--------------------------------------------------------------------------
*/
$_SESSION["user_id"] = 1;
$_SESSION["conv_id"] = 1;

/*
|--------------------------------------------------------------------------
| Disable output buffering
|--------------------------------------------------------------------------
*/
while (ob_get_level() > 0) {
    ob_end_flush();
}

if ($_SERVER["REQUEST_METHOD"] !== "POST") {

    http_response_code(405);

    echo "event: error\n";
    echo "data: " . json_encode([
        "message" => "POST requests only"
    ]) . "\n\n";

    flush();
    exit;
}

$input = json_decode(file_get_contents("php://input"), true);

if (
    !$input ||
    empty(trim($input["query"]))
) {

    http_response_code(400);

    echo "event: error\n";
    echo "data: " . json_encode([
        "message" => "Query is required"
    ]) . "\n\n";

    flush();
    exit;
}

/*
|--------------------------------------------------------------------------
| FastAPI
|--------------------------------------------------------------------------
*/

$url = "http://127.0.0.1:8001/chat";

$payload = [
    "query" => $input["query"],
    "user_id" => $_SESSION["user_id"],
    "conv_id" => $_SESSION["conv_id"]
];

$ch = curl_init($url);

curl_setopt_array($ch, [

    CURLOPT_POST => true,

    CURLOPT_POSTFIELDS => json_encode($payload),

    CURLOPT_HTTPHEADER => [
        "Content-Type: application/json",
        "Accept: text/event-stream"
    ],

    CURLOPT_RETURNTRANSFER => false,

    CURLOPT_TIMEOUT => 0,

    CURLOPT_BUFFERSIZE => 128,

    CURLOPT_WRITEFUNCTION => function ($curl, $chunk) {

        // FastAPI already sends proper SSE.
        // Forward it unchanged.
    
        echo $chunk;

        @ob_flush();
        flush();

        return strlen($chunk);
    }

]);

$result = curl_exec($ch);

if ($result === false) {

    error_log(
        "[CURL ERROR] " .
        curl_error($ch) .
        PHP_EOL,
        3,
        $logdir
    );

    echo "event: error\n";
    echo "data: " . json_encode([
        "message" => "Unable to contact AI server"
    ]) . "\n\n";

    flush();
}

curl_close($ch);

error_log(
    "[SUCCESS] Request completed" . PHP_EOL,
    3,
    $logdir
);