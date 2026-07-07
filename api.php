<?php
set_time_limit(180);
header("Content-Type: text/event-stream");
header("Cache-Control: no-cache");
header("Connection: keep-alive");
header("X-Accel-Buffering: no");

// Turn off output buffering
while (ob_get_level() > 0) {
    ob_end_clean();
}

$logdir = __DIR__ . "/php_logs.log";
if ($_SERVER["REQUEST_METHOD"] !== "POST") {
    error_log("[ERROR] FrontEnd must use post only" . PHP_EOL, 3, $logdir);
    http_response_code(405);
    echo "data: " . json_encode(["error" => "POST only"]) . "\n\n";
    flush();
    exit;
}
error_log("[SUCCESS] Post Used by Client" . PHP_EOL, 3, $logdir);

$input = json_decode(file_get_contents("php://input"), true);

if (empty($input["query"])) {
    error_log("[ERROR] User Query Empty" . PHP_EOL, 3, $logdir);
    http_response_code(400);
    echo "data: " . json_encode(["error" => "Query required"]) . "\n\n";
    flush();
    exit;
}

error_log("[SUCCESS] User Query NOT Empty" . PHP_EOL, 3, $logdir);


$script = __DIR__ . "/ai_backend.py";

$pythonPath = 'C:\Users\Public\AppData\anaconda3\envs\Agentik\python.exe';
$command = escapeshellarg($pythonPath) . " -u " .
    escapeshellarg($script) . " " .
    escapeshellarg($input["query"]);

$descriptors = [
    0 => ["pipe", "r"],
    1 => ["pipe", "w"],
    2 => ["pipe", "w"],
];

$process = proc_open($command, $descriptors, $pipes);

if (!is_resource($process)) {
    error_log("[ERROR] Couldn't Start Python File" . PHP_EOL, 3, $logdir);
    echo "data: " . json_encode(["error" => "Failed to start Python"]) . "\n\n";
    flush();
    exit;
}

fclose($pipes[0]);

stream_set_blocking($pipes[1], false);
stream_set_blocking($pipes[2], false);

while (true) {

    // Forward anything Python prints
    while (($line = fgets($pipes[1])) !== false) {
        echo $line;
        @ob_flush();
        flush();
    }

    // Log stderr if desired
    while (($err = fgets($pipes[2])) !== false) {
        error_log("[PYTHON ERROR]" . trim($err) . PHP_EOL, 3, $logdir);
    }

    $status = proc_get_status($process);

    if (!$status["running"]) {
        break;
    }

    usleep(10000); // 10 ms
}

fclose($pipes[1]);
fclose($pipes[2]);

proc_close($process);

// echo "data: [DONE]\n\n";
flush();

error_log("[SUCCESS] TRANSACTION COMPLETE" . PHP_EOL, 3, $logdir);
