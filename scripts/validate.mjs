import fs from "node:fs/promises";
import path from "node:path";
import crypto from "node:crypto";

const ROOT = path.resolve("site");

async function walk(directory) {
  const output = [];
  const entries = await fs.readdir(directory, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      output.push(...await walk(fullPath));
    } else if (entry.isFile()) {
      output.push(fullPath);
    }
  }
  return output;
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(text) {
  return crypto.createHash("sha256").update(text).digest("hex");
}

async function main() {
  const manifestPath = path.join(ROOT, "data", "manifest.json");
  const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));

  assert(manifest.schema_version === 1, "manifest schema_version 错误");
  assert(Array.isArray(manifest.tables), "manifest.tables 必须为数组");
  assert(manifest.tables.length > 0, "manifest 没有数据表");

  for (const table of manifest.tables) {
    assert(table.name, "表缺少 name");
    assert(table.view, `${table.name} 缺少 view`);
    assert(Array.isArray(table.chunks) && table.chunks.length > 0, `${table.name} 缺少 chunks`);

    let count = 0;
    for (const chunk of table.chunks) {
      const relativePath = chunk.path.replace(/^\.\//, "");
      const localPath = path.join(ROOT, "data", relativePath);
      const text = await fs.readFile(localPath, "utf8");
      const payload = JSON.parse(text);
      assert(Array.isArray(payload.records), `${chunk.path} records 不是数组`);
      assert(Buffer.byteLength(text) === chunk.bytes, `${chunk.path} 字节数不一致`);
      assert(sha256(text) === chunk.sha256, `${chunk.path} SHA-256 不一致`);
      count += payload.records.length;
    }
    assert(count === table.record_count, `${table.name} 记录数不一致`);
  }

  const files = await walk(ROOT);
  const forbiddenPatterns = [
    /"tenant_access_token"\s*:/i,
    /"app_secret"\s*:/i,
    /"authorization"\s*:/i,
    /\bbearer\s+t-[a-z0-9_-]{20,}\b/i
  ];

  for (const file of files) {
    const text = await fs.readFile(file, "utf8");
    for (const pattern of forbiddenPatterns) {
      if (pattern.test(text)) {
        throw new Error(`公开输出疑似包含敏感信息：${path.relative(ROOT, file)}`);
      }
    }
  }

  console.log(`验证通过：${manifest.tables.length} 张表，${files.length} 个文件。`);
}

main().catch((error) => {
  console.error(`验证失败：${error.message}`);
  process.exitCode = 1;
});
