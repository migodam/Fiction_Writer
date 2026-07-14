import { lookup } from "node:dns/promises";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { isIP } from "node:net";

const CONNECTION_TIMEOUT_MS = 8_000;
const MAX_RESPONSE_BYTES = 1_000_000;

const failure = (code, message, extras = {}) => ({
  ok: false,
  code,
  message,
  ...extras,
});

function isLoopbackHostname(hostname) {
  const normalized = hostname.toLowerCase().replace(/^\[|\]$/g, "");
  return (
    normalized === "localhost" ||
    normalized.endsWith(".localhost") ||
    normalized === "::1" ||
    normalized.startsWith("127.") ||
    normalized === "0:0:0:0:0:0:0:1"
  );
}

function modelsUrl(endpoint) {
  if (typeof endpoint !== "string" || !endpoint.trim()) {
    throw new ProviderConnectionError(
      "missing_endpoint",
      "Enter a provider endpoint before testing.",
    );
  }

  let url;
  try {
    url = new URL(endpoint.trim());
  } catch {
    throw new ProviderConnectionError(
      "invalid_endpoint",
      "Enter a valid HTTPS or loopback endpoint.",
    );
  }

  if (
    url.username ||
    url.password ||
    !url.hostname ||
    (url.protocol !== "https:" &&
      !(url.protocol === "http:" && isLoopbackHostname(url.hostname)))
  ) {
    throw new ProviderConnectionError(
      "invalid_endpoint",
      "Use an HTTPS endpoint, or an HTTP endpoint on localhost only.",
    );
  }

  url.search = "";
  url.hash = "";
  const pathname = url.pathname.replace(/\/+$/, "");
  url.pathname = pathname.endsWith("/models") ? pathname : `${pathname}/models`;
  return url;
}

class ProviderConnectionError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

function countModels(body) {
  if (Array.isArray(body?.data)) return body.data.length;
  if (Array.isArray(body?.models)) return body.models.length;
  return null;
}

function isPrivateAddress(address) {
  const mappedIpv4 = address.toLowerCase().match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/)?.[1];
  if (mappedIpv4) return isPrivateAddress(mappedIpv4);
  if (isIP(address) === 4) {
    const [a, b] = address.split(".").map(Number);
    return (
      a === 0 || a === 10 || a === 127 ||
      (a === 169 && b === 254) ||
      (a === 172 && b >= 16 && b <= 31) ||
      (a === 192 && b === 168) || a >= 224
    );
  }
  if (isIP(address) === 6) {
    const normalized = address.toLowerCase();
    return normalized === "::" || normalized === "::1" ||
      normalized.startsWith("fc") || normalized.startsWith("fd") ||
      /^fe[89ab]/.test(normalized) || normalized.startsWith("ff");
  }
  return true;
}

async function resolveTarget(url) {
  const hostname = url.hostname.replace(/^\[|\]$/g, "");
  const directFamily = isIP(hostname);
  const addresses = directFamily
    ? [{ address: hostname, family: directFamily }]
    : await lookup(hostname, { all: true, verbatim: true });
  if (!addresses.length) {
    throw new ProviderConnectionError(
      "network_error",
      "The provider hostname did not resolve to an address.",
    );
  }
  if (
    !isLoopbackHostname(url.hostname) &&
    addresses.some(({ address }) => isPrivateAddress(address))
  ) {
    throw new ProviderConnectionError(
      "unsafe_endpoint",
      "Provider endpoints must resolve to public addresses or localhost.",
    );
  }
  return addresses.sort((left, right) => left.family - right.family);
}

function requestModels(url, apiKey, addresses, signal) {
  return new Promise((resolve, reject) => {
    const request = (url.protocol === "https:" ? httpsRequest : httpRequest)(
      url,
      {
        method: "GET",
        headers: { Authorization: `Bearer ${apiKey}` },
        signal,
        lookup: (_hostname, options, callback) => {
          if (options?.all) callback(null, addresses);
          else callback(null, addresses[0].address, addresses[0].family);
        },
      },
      (response) => {
        const chunks = [];
        let size = 0;
        response.on("data", (chunk) => {
          size += chunk.length;
          if (size > MAX_RESPONSE_BYTES) {
            request.destroy(
              new ProviderConnectionError(
                "invalid_response",
                "The provider models response exceeded the size limit.",
              ),
            );
            return;
          }
          chunks.push(chunk);
        });
        response.on("end", () =>
          resolve({
            status: response.statusCode ?? 0,
            body: Buffer.concat(chunks).toString("utf8"),
          }),
        );
      },
    );
    request.on("error", reject);
    request.end();
  });
}

export async function testProviderConnection(payload = {}) {
  if (typeof payload?.provider !== "string" || !payload.provider.trim()) {
    return failure(
      "missing_provider",
      "Choose or name a provider before testing.",
    );
  }
  if (typeof payload?.apiKey !== "string" || !payload.apiKey.trim()) {
    return failure(
      "missing_api_key",
      "Enter an API key before testing this provider.",
    );
  }

  let url;
  let addresses;
  try {
    url = modelsUrl(payload.endpoint);
    addresses = await resolveTarget(url);
  } catch (error) {
    if (error instanceof ProviderConnectionError)
      return failure(error.code, error.message);
    return failure(
      "network_error",
      "The provider hostname could not be resolved. Check the endpoint and network.",
    );
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), CONNECTION_TIMEOUT_MS);
  const startedAt = performance.now();
  try {
    const response = await requestModels(
      url,
      payload.apiKey.trim(),
      addresses,
      controller.signal,
    );
    const latencyMs = Math.round(performance.now() - startedAt);

    if (response.status < 200 || response.status >= 300) {
      if (response.status === 401 || response.status === 403) {
        return failure(
          "authentication_failed",
          "The provider rejected the API key. Check the key and try again.",
          { httpStatus: response.status, latencyMs },
        );
      }
      if (response.status === 429) {
        return failure(
          "rate_limited",
          "The provider rate-limited the connection test. Wait briefly and try again.",
          { httpStatus: response.status, latencyMs, retryable: true },
        );
      }
      if (response.status >= 500) {
        return failure(
          "server_error",
          `The provider is unavailable (HTTP ${response.status}). Try again later.`,
          { httpStatus: response.status, latencyMs, retryable: true },
        );
      }
      return failure(
        "http_error",
        `The provider returned HTTP ${response.status}. Check the endpoint and provider status.`,
        { httpStatus: response.status, latencyMs },
      );
    }

    let body;
    try {
      body = JSON.parse(response.body);
    } catch {
      return failure(
        "invalid_response",
        "The provider returned an unreadable models response.",
        { httpStatus: response.status, latencyMs },
      );
    }
    const modelCount = countModels(body);
    if (modelCount === null) {
      return failure(
        "invalid_response",
        "The provider returned a models response in an unsupported format.",
        { httpStatus: response.status, latencyMs },
      );
    }
    return {
      ok: true,
      code: "connected",
      message: "Connection verified.",
      httpStatus: response.status,
      latencyMs,
      modelCount,
    };
  } catch (error) {
    if (error?.name === "AbortError") {
      return failure(
        "timeout",
        "The connection test timed out after 8 seconds. Check the endpoint and network.",
        { latencyMs: CONNECTION_TIMEOUT_MS },
      );
    }
    if (error instanceof ProviderConnectionError) {
      return failure(error.code, error.message);
    }
    const tlsErrorCodes = new Set([
      "CERT_HAS_EXPIRED",
      "DEPTH_ZERO_SELF_SIGNED_CERT",
      "ERR_TLS_CERT_ALTNAME_INVALID",
      "SELF_SIGNED_CERT_IN_CHAIN",
      "UNABLE_TO_VERIFY_LEAF_SIGNATURE",
    ]);
    const errorCode = error?.cause?.code || error?.code;
    if (tlsErrorCodes.has(errorCode)) {
      return failure(
        "tls_error",
        "The provider certificate could not be verified. Check the endpoint and TLS configuration.",
      );
    }
    return failure(
      "network_error",
      "Could not reach the provider. Check the endpoint and network connection.",
    );
  } finally {
    clearTimeout(timer);
  }
}
