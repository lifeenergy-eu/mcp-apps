<?php
declare(strict_types=1);

const PB_CONTROL_MCP_BACKEND = 'http://127.0.0.1:8793';
const PB_CONTROL_MCP_MAX_REQUEST_BYTES = 2097152;
const PB_CONTROL_MCP_PREFIX = '/pb-control-mcp';

function pb_control_mcp_host(): string {
    $host = strtolower(trim((string)($_SERVER['HTTP_HOST'] ?? '')));
    return preg_replace('/:\\d+$/', '', $host) ?? '';
}

function pb_control_mcp_backend_path(string $path): ?string {
    $direct = ['/mcp','/authorize','/token','/register','/revoke','/oauth/login','/.well-known/oauth-authorization-server'];
    $prefix = PB_CONTROL_MCP_PREFIX;
    if ($path === $prefix || $path === $prefix . '/') return '/';
    if (str_starts_with($path, $prefix . '/')) {
        $inner = substr($path, strlen($prefix));
        if (in_array($inner, $direct, true)) return $inner;
    }
    if ($path === '/.well-known/oauth-authorization-server' . $prefix) return '/.well-known/oauth-authorization-server';
    if ($path === '/.well-known/oauth-protected-resource' . $prefix . '/mcp') {
        return '/.well-known/oauth-protected-resource' . $prefix . '/mcp';
    }
    return null;
}

function pb_control_mcp_fail(int $status, string $code): never {
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode(['status'=>'FAIL_CLOSED','code'=>$code], JSON_UNESCAPED_SLASHES);
    exit;
}

if (pb_control_mcp_host() !== 'ai-runtime.larimarcode.com') pb_control_mcp_fail(421, 'CONTROL_MCP_INGRESS_HOST_DENIED');
$path = parse_url((string)($_SERVER['REQUEST_URI'] ?? '/'), PHP_URL_PATH);
$path = is_string($path) && $path !== '' ? $path : '/';
$backendPath = pb_control_mcp_backend_path($path);
if ($backendPath === null) pb_control_mcp_fail(404, 'CONTROL_MCP_INGRESS_PATH_DENIED');
$method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
if (!in_array($method, ['GET','POST','DELETE','OPTIONS','HEAD'], true)) pb_control_mcp_fail(405, 'CONTROL_MCP_INGRESS_METHOD_DENIED');
$contentLength = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($contentLength < 0 || $contentLength > PB_CONTROL_MCP_MAX_REQUEST_BYTES) pb_control_mcp_fail(413, 'CONTROL_MCP_INGRESS_REQUEST_TOO_LARGE');
$body = file_get_contents('php://input');
if ($body === false || strlen($body) > PB_CONTROL_MCP_MAX_REQUEST_BYTES) pb_control_mcp_fail(413, 'CONTROL_MCP_INGRESS_REQUEST_TOO_LARGE');

$all = function_exists('getallheaders') ? (getallheaders() ?: []) : [];
$normalized = [];
foreach ($all as $name => $value) $normalized[strtolower((string)$name)] = (string)$value;
if (!isset($normalized['authorization']) && isset($_SERVER['HTTP_AUTHORIZATION'])) $normalized['authorization'] = (string)$_SERVER['HTTP_AUTHORIZATION'];
$headers = [];
foreach (['authorization','accept','accept-language','content-type','origin','referer','user-agent','mcp-protocol-version','mcp-session-id','last-event-id'] as $name) {
    if (isset($normalized[$name]) && $normalized[$name] !== '') $headers[] = $name . ': ' . $normalized[$name];
}
$headers[] = 'Host: ai-runtime.larimarcode.com';
$headers[] = 'X-Forwarded-Proto: https';
$headers[] = 'X-Forwarded-Host: ai-runtime.larimarcode.com';
$headers[] = 'X-Forwarded-Prefix: ' . PB_CONTROL_MCP_PREFIX;

$query = (string)($_SERVER['QUERY_STRING'] ?? '');
$url = PB_CONTROL_MCP_BACKEND . $backendPath . ($query !== '' ? '?' . $query : '');
$allowedResponseHeaders = ['content-type','www-authenticate','location','allow','mcp-session-id','access-control-allow-origin','access-control-allow-methods','access-control-allow-headers','access-control-expose-headers'];
$responseHeaders=[]; $responseStatus=502; $headersCommitted=false;
$ch=curl_init($url);
if ($ch===false) pb_control_mcp_fail(502,'CONTROL_MCP_INGRESS_BACKEND_UNAVAILABLE');
curl_setopt_array($ch,[
    CURLOPT_CUSTOMREQUEST=>$method,
    CURLOPT_HTTPHEADER=>$headers,
    CURLOPT_RETURNTRANSFER=>false,
    CURLOPT_FOLLOWLOCATION=>false,
    CURLOPT_CONNECTTIMEOUT=>3,
    CURLOPT_TIMEOUT=>0,
    CURLOPT_LOW_SPEED_LIMIT=>1,
    CURLOPT_LOW_SPEED_TIME=>90,
    CURLOPT_PROXY=>'',
    CURLOPT_HEADERFUNCTION=>static function($curl,string $line) use (&$responseHeaders,&$responseStatus,&$headersCommitted,$allowedResponseHeaders): int {
        $trim=trim($line);
        if (preg_match('#^HTTP/\\S+\\s+(\\d{3})#i',$trim,$m)) { $responseStatus=(int)$m[1]; $responseHeaders=[]; $headersCommitted=false; return strlen($line); }
        if ($trim==='') {
            if (!$headersCommitted && $responseStatus>=100) {
                http_response_code($responseStatus);
                foreach ($responseHeaders as [$name,$value]) if (in_array($name,$allowedResponseHeaders,true)) header($name.': '.$value,false);
                header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
                header('X-PB-Control-MCP-Ingress: cloudways-loopback-v1');
                header('X-Accel-Buffering: no');
                $headersCommitted=true;
            }
            return strlen($line);
        }
        if (str_contains($trim,':')) { [$name,$value]=array_map('trim',explode(':',$trim,2)); $responseHeaders[]=[strtolower($name),$value]; }
        return strlen($line);
    },
    CURLOPT_WRITEFUNCTION=>static function($curl,string $chunk): int { echo $chunk; if(function_exists('ob_flush')) @ob_flush(); flush(); return strlen($chunk); },
]);
if ($method==='HEAD') curl_setopt($ch,CURLOPT_NOBODY,true);
elseif ($body!=='' || in_array($method,['POST','DELETE'],true)) curl_setopt($ch,CURLOPT_POSTFIELDS,$body);
$ok=curl_exec($ch); $errno=curl_errno($ch); $status=(int)curl_getinfo($ch,CURLINFO_RESPONSE_CODE); curl_close($ch);
if ($ok===false || $errno!==0 || $status<100) {
    if (!$headersCommitted) pb_control_mcp_fail(502,'CONTROL_MCP_INGRESS_BACKEND_UNAVAILABLE');
    exit;
}
