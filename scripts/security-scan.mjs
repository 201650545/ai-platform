// scripts/security-scan.mjs — Security scanning of all output files.
// Scans for leaked secrets (FATAL), forbidden files (FATAL), internal Feishu
// identifiers (FATAL), blacklisted names (FATAL), PII (warning), and
// high-entropy strings (warning).
//
// 姓名黑名单：通过环境变量 FDH_NAME_BLACKLIST 注入（逗号/换行分隔），
// 不写死在仓库里。命中即 FATAL，终止部署。

import fs from "node:fs/promises";
import path from "node:path";

import { loadHubConfig } from "../lib/config.mjs";
import {
  SECRET_PATTERNS,
  scanTokenPrefixes,
  scanHighEntropy,
  scanForPII,
  loadNameBlacklist,
  scanForBlacklistedNames,
  isForbiddenFile,
} from "../lib/security.mjs";
import { walkDir } from "../lib/output.mjs";

/**
 * Internal Feishu identifier patterns.
 * - table_id: Feishu table IDs start with "tbl" followed by alphanumeric chars.
 * - app_token: Feishu base/app tokens leaked as JSON key-value pairs.
 */
const FEISHU_TABLE_ID_PATTERN = /\btbl[A-Za-z0-9]{6,}\b/g;
const FEISHU_APP_TOKEN_PATTERN = /"app_token"\s*:\s*"[^"]{15,}"/i;

/**
 * Security scan all files in the public output directory.
 * - Secret patterns, token prefixes, forbidden files, and internal Feishu
 *   identifiers are FATAL errors (exit 1).
 * - PII and high-entropy findings are warnings (printed but don't fail).
 * @param {string} [rootDir] - Root output directory (defaults to hub config output.root_dir).
 * @returns {Promise<object>} - { fatalErrors, warnings, stats }
 */
export async function securityScan(rootDir) {
  const fatalErrors = [];
  const warnings = [];
  const stats = {
    filesScanned: 0,
    secretHits: 0,
    piiHits: 0,
    entropyHits: 0,
    tokenHits: 0,
    forbiddenFiles: 0,
    internalIdHits: 0,
    blacklistHits: 0,
  };

  const hubConfig = await loadHubConfig();
  const outputDir = rootDir || path.resolve(".", hubConfig.output.root_dir);

  // 姓名黑名单来自环境变量 FDH_NAME_BLACKLIST，未配置则规则停用（不阻塞 CI）。
  const nameBlacklist = loadNameBlacklist();
  if (nameBlacklist.length > 0) {
    console.log(`姓名黑名单已启用：${nameBlacklist.length} 个姓名，命中即终止部署`);
  } else {
    console.log("姓名黑名单未配置（FDH_NAME_BLACKLIST 为空），规则停用");
  }

  console.log(`安全扫描目录：${outputDir}`);

  // Walk all files in the output directory
  let files = [];
  try {
    files = await walkDir(outputDir);
  } catch (error) {
    fatalErrors.push(`无法读取输出目录：${error.message}`);
    console.error(`[失败] 无法读取输出目录：${error.message}`);
    return { fatalErrors, warnings, stats };
  }

  if (files.length === 0) {
    console.log("[警告] 输出目录为空，没有文件需要扫描");
    return { fatalErrors, warnings, stats };
  }

  console.log(`发现 ${files.length} 个文件，开始扫描……\n`);

  for (const filePath of files) {
    const relativePath = path.relative(outputDir, filePath);
    const basename = path.basename(filePath);
    stats.filesScanned++;

    // Check for forbidden files (FATAL)
    if (isForbiddenFile(basename)) {
      fatalErrors.push(`禁止文件：${relativePath}`);
      stats.forbiddenFiles++;
      console.error(`[致命] 禁止文件：${relativePath}`);
    }

    // Read file content
    let text;
    try {
      text = await fs.readFile(filePath, "utf8");
    } catch (error) {
      warnings.push(`无法读取文件：${relativePath} (${error.message})`);
      continue;
    }

    // Check for secret patterns (FATAL)
    for (const pattern of SECRET_PATTERNS) {
      if (pattern.test(text)) {
        fatalErrors.push(`敏感信息模式：${relativePath} (匹配: ${pattern.source})`);
        stats.secretHits++;
        console.error(`[致命] 敏感信息模式：${relativePath} (${pattern.source})`);
      }
    }

    // Check for token prefixes (FATAL — tokens are secrets)
    const tokenFindings = scanTokenPrefixes(text);
    if (tokenFindings.length > 0) {
      fatalErrors.push(`Token 前缀：${relativePath} (${tokenFindings.join(", ")})`);
      stats.tokenHits++;
      console.error(`[致命] Token 前缀：${relativePath} (${tokenFindings.join(", ")})`);
    }

    // Check for internal Feishu table_id identifiers (FATAL)
    const tableIdMatches = text.match(FEISHU_TABLE_ID_PATTERN);
    if (tableIdMatches) {
      const unique = [...new Set(tableIdMatches)];
      fatalErrors.push(`内部 table_id：${relativePath} (${unique.join(", ")})`);
      stats.internalIdHits++;
      console.error(`[致命] 内部 table_id：${relativePath} (${unique.join(", ")})`);
    }

    // Check for internal Feishu app_token (FATAL)
    if (FEISHU_APP_TOKEN_PATTERN.test(text)) {
      fatalErrors.push(`内部 app_token：${relativePath}`);
      stats.internalIdHits++;
      console.error(`[致命] 内部 app_token：${relativePath}`);
    }

    // Check for PII patterns (WARNING)
    const piiFindings = scanForPII(text);
    if (piiFindings.length > 0) {
      warnings.push(`PII 疑似：${relativePath} (${piiFindings.length} 处)`);
      stats.piiHits += piiFindings.length;
      console.log(`[警告] PII 疑似：${relativePath} (${piiFindings.length} 处)`);
    }

    // Check for blacklisted names (FATAL — stops deployment)
    const blacklistFindings = scanForBlacklistedNames(text, nameBlacklist);
    if (blacklistFindings.length > 0) {
      fatalErrors.push(`姓名黑名单：${relativePath} (${blacklistFindings.join(", ")})`);
      stats.blacklistHits += blacklistFindings.length;
      console.error(`[致命] 姓名黑名单：${relativePath} (${blacklistFindings.join(", ")})`);
    }

    // Check for high-entropy strings (WARNING)
    const entropyFindings = scanHighEntropy(text);
    if (entropyFindings.length > 0) {
      warnings.push(`高熵字符串：${relativePath} (${entropyFindings.length} 处)`);
      stats.entropyHits += entropyFindings.length;
      console.log(`[警告] 高熵字符串：${relativePath} (${entropyFindings.length} 处)`);
    }
  }

  return { fatalErrors, warnings, stats };
}

/**
 * Main entry point for CLI execution.
 */
async function main() {
  try {
    console.log("=== 安全扫描 ===\n");

    const result = await securityScan();

    console.log("\n=== 扫描摘要 ===");
    console.log(`扫描文件：${result.stats.filesScanned}`);
    console.log(`敏感信息模式：${result.stats.secretHits}`);
    console.log(`Token 前缀：${result.stats.tokenHits}`);
    console.log(`内部标识符：${result.stats.internalIdHits}`);
    console.log(`禁止文件：${result.stats.forbiddenFiles}`);
    console.log(`姓名黑名单：${result.stats.blacklistHits}`);
    console.log(`PII 疑似（警告）：${result.stats.piiHits}`);
    console.log(`高熵字符串（警告）：${result.stats.entropyHits}`);
    console.log(`致命错误：${result.fatalErrors.length}`);
    console.log(`警告数：${result.warnings.length}`);

    if (result.warnings.length > 0) {
      console.log("\n警告列表：");
      for (const w of result.warnings) {
        console.log(`  [警告] ${w}`);
      }
    }

    if (result.fatalErrors.length > 0) {
      console.error("\n安全扫描失败，致命错误列表：");
      for (const err of result.fatalErrors) {
        console.error(`  [致命] ${err}`);
      }
      process.exitCode = 1;
    } else {
      console.log("\n安全扫描通过（无致命错误）。");
    }
  } catch (error) {
    console.error(`安全扫描异常：${error.message}`);
    process.exitCode = 1;
  }
}

// CLI entry point — runs when executed directly via `node scripts/security-scan.mjs`
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve("scripts/security-scan.mjs")) {
  main();
}
