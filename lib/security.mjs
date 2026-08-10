// lib/security.mjs — Security scanning utilities.
// Scans for secrets, tokens, PII, and other sensitive content in output.

import crypto from "node:crypto";

/** SHA-256 hash of a string. */
export function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

/** Patterns that indicate leaked credentials or tokens. */
export const SECRET_PATTERNS = [
  /"app_secret"\s*:\s*"[^"]{10,}"/i,
  /"tenant_access_token"\s*:\s*"[^"]{10,}"/i,
  /"user_access_token"\s*:\s*"[^"]{10,}"/i,
  /"authorization"\s*:\s*"[^"]{10,}"/i,
  /"client_secret"\s*:\s*"[^"]{10,}"/i,
  /"github_token"\s*:\s*"[^"]{10,}"/i,
  /\bbearer\s+[a-z0-9_-]{20,}\b/i,
  /-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----/i,
];

/** Patterns for PII (personally identifiable information). */
export const PII_PATTERNS = [
  // Chinese phone numbers
  /\b1[3-9]\d{9}\b/g,
  // Chinese ID card numbers (18 digits)
  /\b\d{17}[\dXx]\b/g,
  // Email addresses
  /\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b/gi,
  // Bank card numbers (16-19 digits)
  /\b\d{16,19}\b/g,
];

/** Files that must never appear in public output. */
export const FORBIDDEN_FILES = [
  ".env", ".env.local", ".env.production",
  "debug-response.json", "api-cache.json", "raw-response.json",
  ".npmrc", ".netrc",
];

/**
 * Check a serialized string for known secret patterns.
 * Throws on match — this is a hard stop, not a warning.
 * @param {string} serialized - The string to scan.
 * @param {string[]} secretValues - Actual secret values to check for (app_secret, tokens, etc.)
 * @param {string} context - Description of what is being scanned (for error messages).
 */
export function assertNoSecrets(serialized, secretValues = [], context = "输出") {
  // Check for actual credential values
  for (const v of secretValues) {
    if (v && serialized.includes(v)) {
      throw new Error(`检测到实际凭证值即将进入${context}，已中止部署`);
    }
  }
  // Check for patterns
  for (const p of SECRET_PATTERNS) {
    if (p.test(serialized)) {
      throw new Error(`检测到疑似敏感信息模式（${context}）：${p.source}`);
    }
  }
}

/**
 * Scan a string for PII patterns.
 * Returns array of matches found, or empty array if clean.
 */
export function scanForPII(text) {
  const findings = [];
  for (const p of PII_PATTERNS) {
    const matches = text.match(p);
    if (matches) {
      findings.push(...matches);
    }
  }
  return findings;
}

/**
 * Load the PII name blacklist from the environment.
 * Injected via FDH_NAME_BLACKLIST (comma/newline separated), never committed.
 * Empty/unset → rule disabled (no-op), so a missing secret never blocks CI.
 */
export function loadNameBlacklist() {
  const raw = process.env.FDH_NAME_BLACKLIST || "";
  return raw.split(/[,，\s]+/).map((s) => s.trim()).filter(Boolean);
}

/**
 * Scan text for any blacklisted names.
 * @param {string} text - Content to scan.
 * @param {string[]} blacklist - Names to search for (may be empty).
 * @returns {string[]} Matched names (in blacklist order).
 */
export function scanForBlacklistedNames(text, blacklist) {
  if (!blacklist || blacklist.length === 0) return [];
  return blacklist.filter((name) => name && text.includes(name));
}

/**
 * Check if a filename is forbidden in public output.
 */
export function isForbiddenFile(filename) {
  return FORBIDDEN_FILES.includes(filename);
}

/**
 * High-entropy string detection — flags long base64/hex strings
 * that might be encoded secrets.
 */
export function scanHighEntropy(text, minLength = 40) {
  const findings = [];
  // Base64-like sequences
  const b64Pattern = /\b[A-Za-z0-9+/]{minLength,}={0,2}\b/g;
  // Hex sequences
  const hexPattern = /\b[a-f0-9]{minLength,}\b/gi;

  for (const p of [b64Pattern, hexPattern]) {
    const matches = text.match(p);
    if (matches) {
      for (const m of matches) {
        // Calculate Shannon entropy
        const entropy = calculateEntropy(m);
        if (entropy > 4.0) {
          findings.push({ value: m.slice(0, 20) + "...", entropy: entropy.toFixed(2) });
        }
      }
    }
  }
  return findings;
}

/** Shannon entropy of a string. */
function calculateEntropy(str) {
  const freq = {};
  for (const ch of str) freq[ch] = (freq[ch] || 0) + 1;
  let entropy = 0;
  const len = str.length;
  for (const count of Object.values(freq)) {
    const p = count / len;
    entropy -= p * Math.log2(p);
  }
  return entropy;
}

/**
 * Token prefix detection — flags strings starting with known token prefixes.
 * Strict prefixes (cli_, Bearer, ghp_, etc.) are unlikely to appear in natural text.
 * Ambiguous prefixes (t-, u-) require at least 15 chars AND a digit to avoid
 * false positives on English words like "t-generation" or "t-decoration".
 */
export function scanTokenPrefixes(text) {
  const findings = [];
  // Strict prefixes — very specific, safe with {10,}
  const strictPrefixes = ["cli_", "Bearer ", "ghp_", "gho_", "ghs_", "ghr_"];
  // Ambiguous prefixes — need digit constraint to avoid English-word false positives
  const ambiguousPrefixes = ["t-", "u-"];

  for (const prefix of strictPrefixes) {
    const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`${escaped}[a-zA-Z0-9_-]{10,}`, "gi");
    const matches = text.match(pattern);
    if (matches) findings.push(...matches.map(m => m.slice(0, 15) + "..."));
  }

  for (const prefix of ambiguousPrefixes) {
    const escaped = prefix.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const pattern = new RegExp(`${escaped}[a-zA-Z0-9_-]{14,}`, "gi");
    const matches = text.match(pattern);
    if (matches) {
      for (const m of matches) {
        const tokenPart = m.slice(prefix.length);
        // Only flag if token part contains at least one digit
        // (real Feishu tokens are mixed alpha-numeric, English words are pure alpha)
        if (/[0-9]/.test(tokenPart)) {
          findings.push(m.slice(0, 15) + "...");
        }
      }
    }
  }
  return findings;
}

/**
 * Full security scan of a file's content.
 * Returns { passed: boolean, issues: string[] }.
 * For strict mode (fail_on_sensitive_content), any issue is fatal.
 */
export function scanContent(text, { strict = true, context = "" } = {}) {
  const issues = [];

  // Secret patterns
  for (const p of SECRET_PATTERNS) {
    if (p.test(text)) issues.push(`敏感信息模式：${p.source}`);
  }

  // Token prefixes
  const tokenHits = scanTokenPrefixes(text);
  if (tokenHits.length > 0) issues.push(`Token 前缀：${tokenHits.join(", ")}`);

  // High entropy
  const entropyHits = scanHighEntropy(text);
  if (entropyHits.length > 0) issues.push(`高熵字符串：${entropyHits.length} 处`);

  return {
    passed: issues.length === 0,
    issues: issues.map(i => context ? `${context}: ${i}` : i)
  };
}
