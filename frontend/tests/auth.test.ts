import assert from "node:assert/strict";
import test from "node:test";

import { decideDashboardAccess } from "../lib/auth";

const configured = {
  NODE_ENV: "production",
  NICHESCOPE_AUTH_USERNAME: "owner",
  NICHESCOPE_AUTH_PASSWORD: "correct horse battery staple",
};

function basic(username: string, password: string): string {
  return `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
}

test("production fails closed when dashboard credentials are missing", () => {
  assert.equal(decideDashboardAccess(null, { NODE_ENV: "production" }), "misconfigured");
});

test("development remains usable without configured credentials", () => {
  assert.equal(decideDashboardAccess(null, { NODE_ENV: "development" }), "allow");
});

test("configured production challenges missing or invalid credentials", () => {
  assert.equal(decideDashboardAccess(null, configured), "challenge");
  assert.equal(decideDashboardAccess(basic("owner", "wrong"), configured), "challenge");
  assert.equal(decideDashboardAccess("Bearer nope", configured), "challenge");
});

test("configured production accepts valid basic auth including a colon in the password", () => {
  const env = { ...configured, NICHESCOPE_AUTH_PASSWORD: "abc:def" };
  assert.equal(decideDashboardAccess(basic("owner", "abc:def"), env), "allow");
});
