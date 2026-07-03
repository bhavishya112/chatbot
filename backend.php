<?php
declare(strict_types=1);
ini_set("log_errors", 1);
date_default_timezone_set("Asia/Kolkata");
ini_set("error_log", __DIR__ . "logs/agent.log");
/**
 * SSE bridge to the Python agent.
 *
 * This file intentionally contains no model-specific intelligence. It validates
 * the browser request, invokes Agent.py, and forwards newline-delimited Python
 * events as browser-compatible SSE.
 */

function emit_sse(string $event, array $data): void
{
    echo 'event: ' . $event . "\n";
    echo 'data: ' . json_encode($data, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . "\n\n";
    if (ob_get_level() > 0) {
        @ob_flush();
    }
    flush();
}

function fail_request(string $message): never
{
    emit_sse('error', ['error' => $message]);
    exit;
}

while (ob_get_level() > 0) {
    @ob_end_flush();
}
ob_implicit_flush(true);

header('Content-Type: text/event-stream');
header('Cache-Control: no-cache');
header('Connection: keep-alive');
header('X-Accel-Buffering: no');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    fail_request('POST only');
}

$rawBody = file_get_contents('php://input');
if ($rawBody === false || trim($rawBody) === '') {
    fail_request('Request body required');
}

$data = json_decode($rawBody, true);
if (!is_array($data)) {
    fail_request('Malformed JSON request');
}

$query = trim((string) ($data['query'] ?? ''));
if ($query === '') {
    fail_request('Query required');
}

$consoleErrors = $data['console_errors'] ?? [];
if (!is_array($consoleErrors)) {
    $consoleErrors = [];
}
$consoleErrors = array_values(array_filter(array_map(static function ($item): string {
    return substr((string) $item, 0, 2000);
}, $consoleErrors), static fn(string $item): bool => $item !== ''));

$sessionId = preg_replace('/[^a-zA-Z0-9_-]/', '', (string) ($data['session_id'] ?? ''));
if ($sessionId === '') {
    $sessionId = bin2hex(random_bytes(16));
}

$payload = [
    'query' => $query,
    'ui_context' => [
        'visible_html' => substr((string) ($data['visible_html'] ?? ''), 0, 120000),
        'console_errors' => $consoleErrors,
    ],
    'session_id' => $sessionId,
    'stream' => true,
];

$projectDir = __DIR__;
$pythonBin = getenv('PYTHON_BIN') ?: 'python';
$agentPath = $projectDir . DIRECTORY_SEPARATOR . 'Agent.py';
$timeoutSeconds = max(5, (int) (getenv('AGENT_TIMEOUT_SECONDS') ?: 120));

if (!is_file($agentPath)) {
    fail_request('Agent entrypoint is missing');
}

$cmd = escapeshellarg($pythonBin) . ' ' . escapeshellarg($agentPath);
$descriptors = [
    0 => ['pipe', 'r'],
    1 => ['pipe', 'w'],
    2 => ['pipe', 'w'],
];

$process = proc_open($cmd, $descriptors, $pipes, $projectDir);
if (!is_resource($process)) {
    fail_request('Unable to start agent process');
}

fwrite($pipes[0], json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE));
fclose($pipes[0]);
stream_set_blocking($pipes[1], false);
stream_set_blocking($pipes[2], false);

$startedAt = time();
$stdoutBuffer = '';
$stderrBuffer = '';
$doneSent = false;

while (true) {
    $status = proc_get_status($process);
    $stdoutChunk = stream_get_contents($pipes[1]);
    if ($stdoutChunk !== false && $stdoutChunk !== '') {
        $stdoutBuffer .= $stdoutChunk;
        while (($newline = strpos($stdoutBuffer, "\n")) !== false) {
            $line = trim(substr($stdoutBuffer, 0, $newline));
            $stdoutBuffer = substr($stdoutBuffer, $newline + 1);
            if ($line === '') {
                continue;
            }

            $event = json_decode($line, true);
            if (!is_array($event)) {
                emit_sse('error', ['error' => 'Agent emitted an invalid event']);
                error_log("[PHP] ".date("Y-m-d H:i:s"). " event : $event");
                continue;
            }

            $eventName = (string) ($event['event'] ?? 'message');
            unset($event['event']);
            emit_sse($eventName, $event);
            if ($eventName === 'done') {
                $doneSent = true;
            }
        }
    }

    $stderrChunk = stream_get_contents($pipes[2]);
    if ($stderrChunk !== false && $stderrChunk !== '') {
        $stderrBuffer .= $stderrChunk;
        $stderrBuffer = substr($stderrBuffer, -8000);
    }

    if (!$status['running']) {
        break;
    }

    if (time() - $startedAt > $timeoutSeconds) {
        proc_terminate($process);
        emit_sse('error', ['error' => 'Agent timed out']);
        $doneSent = true;
        break;
    }

    usleep(20000);
}

if (trim($stdoutBuffer) !== '') {
    $event = json_decode(trim($stdoutBuffer), true);
    if (is_array($event)) {
        $eventName = (string) ($event['event'] ?? 'message');
        unset($event['event']);
        emit_sse($eventName, $event);
        if ($eventName === 'done') {
            $doneSent = true;
        }
    }
}

fclose($pipes[1]);
fclose($pipes[2]);
$exitCode = proc_close($process);

if ($exitCode !== 0 && !$doneSent) {
    emit_sse('error', ['error' => 'Agent failed to complete the request']);

    error_log("[PHP] " . date("Y-m-d H:i:s") . " exit code : $exitCode");
}

if (!$doneSent) {
    emit_sse('done', ['finished' => true]);
}
