import assert from "node:assert/strict";
import { afterEach, test } from "node:test";
import { loadCheckout } from "./checkout.js";

afterEach(() => {
  delete globalThis.window;
  delete globalThis.document;
});

function mockDocument() {
  const scripts = [];
  globalThis.document = {
    querySelector: () => scripts.find((script) => !script.removed) || null,
    createElement: () => ({ dataset: {}, remove() { this.removed = true; } }),
    body: { appendChild: (script) => { scripts.push(script); } }
  };
  return scripts;
}

test("a failed checkout load can be retried", async () => {
  globalThis.window = {};
  const scripts = mockDocument();

  const first = loadCheckout();
  scripts[0].onerror();
  await assert.rejects(first, /could not be loaded/);
  assert.equal(scripts[0].removed, true);

  const retry = loadCheckout();
  assert.equal(scripts.length, 2);
  assert.equal(scripts[1].src, "https://checkout.razorpay.com/v1/checkout.js");
  window.Razorpay = function Razorpay() {};
  scripts[1].onload();
  await retry;
});

test("a stale checkout script does not block a retry", async () => {
  globalThis.window = {};
  const scripts = mockDocument();
  const stale = document.createElement("script");
  scripts.push(stale);

  const retry = loadCheckout();
  assert.equal(stale.removed, true);
  assert.equal(scripts.length, 2);
  window.Razorpay = function Razorpay() {};
  scripts[1].onload();
  await retry;
});

test("a script load without Razorpay reports an error and clears the script", async () => {
  globalThis.window = {};
  const scripts = mockDocument();
  const attempt = loadCheckout();
  scripts[0].onload();
  await assert.rejects(attempt, /could not be loaded/);
  assert.equal(scripts[0].removed, true);
});

