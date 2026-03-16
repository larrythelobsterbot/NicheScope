// PM2 Ecosystem Configuration for NicheScope
// Usage: pm2 start ecosystem.config.js

module.exports = {
  apps: [
    {
      name: "nichescope-web",
      cwd: "/opt/nichescope/frontend",
      script: "node_modules/.bin/next",
      args: "start -p 3000",
      env: {
        NODE_ENV: "production",
        PORT: 3000,
      },
      instances: 1,
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      log_file: "/opt/nichescope/logs/web.log",
      error_file: "/opt/nichescope/logs/web-error.log",
      out_file: "/opt/nichescope/logs/web-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "512M",
    },
    {
      name: "nichescope-collectors",
      cwd: "/opt/nichescope/collectors",
      script: "run_scheduler.sh",
      interpreter: "/bin/bash",
      env: {
        PYTHONUNBUFFERED: "1",
      },
      exec_mode: "fork",
      autorestart: true,
      max_restarts: 10,
      restart_delay: 10000,
      log_file: "/opt/nichescope/logs/collectors.log",
      error_file: "/opt/nichescope/logs/collectors-error.log",
      out_file: "/opt/nichescope/logs/collectors-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      max_memory_restart: "256M",
      cron_restart: "50 21 * * *",
    },
  ],
};
