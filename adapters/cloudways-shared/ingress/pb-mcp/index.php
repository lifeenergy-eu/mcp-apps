<?php
declare(strict_types=1);

const PB_MCP_BACKEND = 'http://127.0.0.1:8792';
const PB_MCP_MAX_REQUEST_BYTES = 2097152;

$targets = [
    'ai-runtime.larimarcode.com' => '/pb-mcp',
    'smoothiebarmen.com' => '/pb-mcp',
];

function pb_mcp_host(): string {
    $host = strtolower(trim((string)($_SERVER['HTTP_HOST'] ?? '')));
    $host = preg_replace('/:\\d+$/', '', $host) ?? '';
    return $host;
}

function pb_mcp_backend_path(string $path, string $prefix): ?string {
    $direct = [
        '/mcp', '/authorize', '/token', '/register', '/revoke', '/oauth/login',
        '/.well-known/oauth-authorization-server',
    ];
    if ($path === $prefix || $path === $prefix . '/') {
        return '/';
    }
    if (str_starts_with($path, $prefix . '/')) {
        $inner = substr($path, strlen($prefix));
        if (in_array($inner, $direct, true)) {
            return $inner;
        }
    }
    if ($path === '/.well-known/oauth-authorization-server' ||
        $path === '/.well-known/oauth-authorization-server' . $prefix) {
        return '/.well-known/oauth-authorization-server';
    }
    if ($path === '/.well-known/oauth-protected-resource/mcp' ||
        $path === '/.well-known/oauth-protected-resource' . $prefix . '/mcp') {
        return '/.well-known/oauth-protected-resource' . $prefix . '/mcp';
    }
    return null;
}

function pb_mcp_request_headers(): array {
    $all = function_exists('getallheaders') ? (getallheaders() ?: []) : [];
    $normalized = [];
    foreach ($all as $name => $value) {
        $normalized[strtolower((string)$name)] = (string)$value;
    }
    if (!isset($normalized['authorization']) && isset($_SERVER['HTTP_AUTHORIZATION'])) {
        $normalized['authorization'] = (string)$_SERVER['HTTP_AUTHORIZATION'];
    }
    $forward = [];
    foreach ([
        'authorization', 'accept', 'accept-language', 'content-type', 'origin',
        'referer', 'user-agent', 'mcp-protocol-version', 'mcp-session-id', 'last-event-id',
    ] as $name) {
        if (isset($normalized[$name]) && $normalized[$name] !== '') {
            $forward[] = $name . ': ' . $normalized[$name];
        }
    }
    return $forward;
}

function pb_mcp_fail(int $status, string $code): never {
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode(['status' => 'FAIL_CLOSED', 'code' => $code], JSON_UNESCAPED_SLASHES);
    exit;
}

$host = pb_mcp_host();
if (!isset($targets[$host])) {
    pb_mcp_fail(421, 'MCP_INGRESS_HOST_DENIED');
}
$prefix = $targets[$host];
$path = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH);
$path = is_string($path) && $path !== '' ? $path : '/';
$backendPath = pb_mcp_backend_path($path, $prefix);
if ($backendPath === null) {
    pb_mcp_fail(404, 'MCP_INGRESS_PATH_DENIED');
}
$method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
if (!in_array($method, ['GET', 'POST', 'DELETE', 'OPTIONS', 'HEAD'], true)) {
    pb_mcp_fail(405, 'MCP_INGRESS_METHOD_DENIED');
}
$contentLength = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($contentLength < 0 || $contentLength > PB_MCP_MAX_REQUEST_BYTES) {
    pb_mcp_fail(413, 'MCP_INGRESS_REQUEST_TOO_LARGE');
}
$body = file_get_contents('php://input');
if ($body === false || strlen($body) > PB_MCP_MAX_REQUEST_BYTES) {
    pb_mcp_fail(413, 'MCP_INGRESS_REQUEST_TOO_LARGE');
}
$query = (string)($_SERVER['QUERY_STRING'] ?? '');
$url = PB_MCP_BACKEND . $backendPath . ($query !== '' ? '?' . $query : '');

$allowedResponseHeaders = [
    'content-type', 'www-authenticate', 'location',
    'allow', 'mcp-session-id', 'access-control-allow-origin',
    'access-control-allow-methods', 'access-control-allow-headers',
    'access-control-expose-headers',
];
$responseHeaders = [];
$responseStatus = 502;
$headersCommitted = false;

$ch = curl_init($url);
if ($ch === false) {
    pb_mcp_fail(502, 'MCP_INGRESS_BACKEND_UNAVAILABLE');
}
$forwardHeaders = pb_mcp_request_headers();
$forwardHeaders[] = 'Host: ' . $host;
$forwardHeaders[] = 'X-Forwarded-Proto: https';
$forwardHeaders[] = 'X-Forwarded-Host: ' . $host;
$forwardHeaders[] = 'X-Forwarded-Prefix: ' . $prefix;

curl_setopt_array($ch, [
    CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => $forwardHeaders,
    CURLOPT_RETURNTRANSFER => false,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => 3,
    CURLOPT_TIMEOUT => 0,
    CURLOPT_LOW_SPEED_LIMIT => 1,
    CURLOPT_LOW_SPEED_TIME => 90,
    CURLOPT_PROXY => '',
    CURLOPT_HEADERFUNCTION => static function ($curl, string $line) use (&$responseHeaders, &$responseStatus, &$headersCommitted, $allowedResponseHeaders): int {
        $trim = trim($line);
        if (preg_match('#^HTTP/\\S+\\s+(\\d{3})#i', $trim, $m)) {
            $responseStatus = (int)$m[1];
            $responseHeaders = [];
            $headersCommitted = false;
            return strlen($line);
        }
        if ($trim === '') {
            if (!$headersCommitted && $responseStatus >= 100) {
                http_response_code($responseStatus);
                foreach ($responseHeaders as [$name, $value]) {
                    if (in_array($name, $allowedResponseHeaders, true)) {
                        header($name . ': ' . $value, false);
                    }
                }
                header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
                header('Pragma: no-cache');
                header('Expires: 0');
                header('X-PB-MCP-Ingress: cloudways-loopback-v3');
                header('X-Accel-Buffering: no');
                $headersCommitted = true;
            }
            return strlen($line);
        }
        if (str_contains($trim, ':')) {
            [$name, $value] = array_map('trim', explode(':', $trim, 2));
            $responseHeaders[] = [strtolower($name), $value];
        }
        return strlen($line);
    },
    CURLOPT_WRITEFUNCTION => static function ($curl, string $chunk): int {
        echo $chunk;
        if (function_exists('ob_flush')) @ob_flush();
        flush();
        return strlen($chunk);
    },
]);
if ($method === 'HEAD') {
    curl_setopt($ch, CURLOPT_NOBODY, true);
} elseif ($body !== '' || in_array($method, ['POST', 'DELETE'], true)) {
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
}

$ok = curl_exec($ch);
$errno = curl_errno($ch);
$status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
curl_close($ch);
if ($ok === false || $errno !== 0 || $status < 100) {
    if (!$headersCommitted) {
        pb_mcp_fail(502, 'MCP_INGRESS_BACKEND_UNAVAILABLE');
    }
    exit;
}
