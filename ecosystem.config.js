// PM2 Ecosystem Configuration for NicheScope
// Usage: pm2 start ecosystem.config.js

const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const projectRoot = __dirname;

function parseEnvValue(rawValue) {
  const value = rawValue.trim();
  if (!value) return "";

  if (value[0] === '"' || value[0] === "'") {
    const quote = value[0];
    let parsed = "";
    let escaped = false;
    for (let index = 1; index < value.length; index += 1) {
      const char = value[index];
      if (escaped) {
        if (char !== quote && char !== "\\") parsed += "\\";
        parsed += char;
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        const trailing = value.slice(index + 1).trim();
        if (!trailing || trailing.startsWith("#")) return parsed;
        return value;
      } else {
        parsed += char;
      }
    }
    return value;
  }

  for (let index = 0; index < value.length; index += 1) {
    if (
      value[index] === "#" &&
      (index === 0 || /\s/.test(value[index - 1]))
    ) {
      return value.slice(0, index).trimEnd();
    }
  }
  return value;
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};

  const values = {};
  for (const rawLine of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;

    const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
    if (!match) continue;

    values[match[1]] = parseEnvValue(match[2]);
  }
  return values;
}

const sharedEnv = loadEnvFile(path.join(projectRoot, ".env"));
let configuredDbPath = sharedEnv.DB_PATH || path.join("data", "nichescope.db");
if (configuredDbPath === "~" || configuredDbPath.startsWith(`~${path.sep}`)) {
  configuredDbPath = path.join(os.homedir(), configuredDbPath.slice(2));
}
sharedEnv.DB_PATH = path.resolve(projectRoot, configuredDbPath);
const logPath = (name) => path.join(projectRoot, "logs", name);

module.exports = {
  apps: [
    {
      name: "nichescope-web",
      cwd: path.join(projectRoot, "frontend"),
      script: "node_modules/.bin/next",
      args: "start -H 127.0.0.1 -p 3000",
      env: {
        ...sharedEnv,
        NODE_ENV: "production",
        PORT: 3000,
      },
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      log_file: logPath("web.log"),
      error_file: logPath("web-error.log"),
      out_file: logPath("web-out.log"),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "512M",
    },
    {
      name: "nichescope-collectors",
      cwd: path.join(projectRoot, "collectors"),
      script: "run_scheduler.sh",
      interpreter: "/bin/bash",
      env: {
        ...sharedEnv,
        PYTHONUNBUFFERED: "1",
      },
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 10000,
      log_file: logPath("collectors.log"),
      error_file: logPath("collectors-error.log"),
      out_file: logPath("collectors-out.log"),
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "256M",
      cron_restart: "50 21 * * *",
    },
  ],
};
