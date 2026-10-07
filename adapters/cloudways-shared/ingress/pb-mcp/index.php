<?php
declare(strict_types=1);

const PB_MCP_BACKEND = 'http://127.0.0.1:8792';
const PB_MCP_MAX_REQUEST_BYTES = 2097152;
const PB_MCP_MAX_RESPONSE_BYTES = 8388608;

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
        return '/.well-known/oauth-protected-resource/mcp';
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
        'referer', 'user-agent', 'mcp-protocol-version', 'mcp-session-id',
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

$responseHeaders = [];
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
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_FOLLOWLOCATION => false,
    CURLOPT_CONNECTTIMEOUT => 3,
    CURLOPT_TIMEOUT => 65,
    CURLOPT_PROXY => '',
    CURLOPT_HEADERFUNCTION => static function ($curl, string $line) use (&$responseHeaders): int {
        $trim = trim($line);
        if ($trim !== '' && str_contains($trim, ':')) {
            [$name, $value] = array_map('trim', explode(':', $trim, 2));
            $responseHeaders[] = [strtolower($name), $value];
        }
        return strlen($line);
    },
]);
if ($method === 'HEAD') {
    curl_setopt($ch, CURLOPT_NOBODY, true);
} elseif ($body !== '' || in_array($method, ['POST', 'DELETE'], true)) {
    curl_setopt($ch, CURLOPT_POSTFIELDS, $body);
}
$responseBody = curl_exec($ch);
$status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
$errno = curl_errno($ch);
curl_close($ch);
if ($errno !== 0 || $responseBody === false || $status < 100) {
    pb_mcp_fail(502, 'MCP_INGRESS_BACKEND_UNAVAILABLE');
}
if (strlen((string)$responseBody) > PB_MCP_MAX_RESPONSE_BYTES) {
    pb_mcp_fail(502, 'MCP_INGRESS_RESPONSE_TOO_LARGE');
}
http_response_code($status);
$allowedResponseHeaders = [
    'content-type', 'www-authenticate', 'location', 'cache-control', 'pragma',
    'expires', 'allow', 'mcp-session-id', 'access-control-allow-origin',
    'access-control-allow-methods', 'access-control-allow-headers',
    'access-control-expose-headers',
];
foreach ($responseHeaders as [$name, $value]) {
    if (in_array($name, $allowedResponseHeaders, true)) {
        header($name . ': ' . $value, false);
    }
}
header('X-PB-MCP-Ingress: cloudways-loopback-v1');
echo $responseBody;
