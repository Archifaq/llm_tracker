/**
 * Cloudflare Pages Function: POST /api/trigger-run
 *
 * Dispatches the weekly-run.yml GitHub Actions workflow on demand, so the
 * dashboard's "Запустить прогон" button doesn't need any backend of its
 * own. IMPORTANT: this file must live at the repo root (functions/api/...),
 * NOT inside web/ (the Pages "build output directory") -- Cloudflare Pages
 * Functions are only detected in a /functions directory at the project
 * root, never inside the output directory
 * (https://developers.cloudflare.com/pages/functions/get-started/).
 *
 * Requires a Cloudflare Pages environment variable/secret named
 * GITHUB_DISPATCH_TOKEN (a fine-grained GitHub PAT scoped to this repo,
 * "Actions: Read and write" only) -- see README.md "Запуск прогона из
 * интерфейса". Never logged, never echoed back in any response.
 */

const REPO = "Archifaq/llm_tracker";
const WORKFLOW_FILE = "weekly-run.yml";
const REF = "main";

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function handlePost(context) {
  const token = context.env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    return json(
      { ok: false, error: "GITHUB_DISPATCH_TOKEN is not configured on this Pages project" },
      500
    );
  }

  let githubResponse;
  try {
    githubResponse = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          // GitHub's API rejects requests with no User-Agent.
          "User-Agent": "llm_tracker-pages-function",
        },
        body: JSON.stringify({ ref: REF }),
      }
    );
  } catch {
    // Never include the caught error's message here -- it could echo
    // request details. A generic network-failure message is enough.
    return json({ ok: false, error: "could not reach the GitHub API" }, 502);
  }

  if (githubResponse.status === 204) {
    return json({ ok: true }, 200);
  }

  // Deliberately do not read/forward githubResponse's body: GitHub error
  // payloads can restate request context, and this must never end up in a
  // client response or a Cloudflare log line. Categorize by status only.
  let message;
  if (githubResponse.status === 401 || githubResponse.status === 403) {
    message = "GitHub rejected the request -- check GITHUB_DISPATCH_TOKEN's scope and expiry";
  } else if (githubResponse.status === 404) {
    message = "workflow or repository not found -- check REPO/WORKFLOW_FILE in trigger-run.js";
  } else {
    message = `GitHub API returned HTTP ${githubResponse.status}`;
  }
  return json({ ok: false, error: message }, 502);
}

export async function onRequest(context) {
  if (context.request.method !== "POST") {
    return json({ ok: false, error: "method not allowed" }, 405);
  }
  return handlePost(context);
}
