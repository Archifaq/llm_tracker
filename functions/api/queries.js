/**
 * Cloudflare Pages Function: GET/PUT /api/queries
 *
 * Reads and writes queries/poland.txt via GitHub's Contents API, so the
 * query pool can be edited from the dashboard without a separate backend.
 * Same repo-root placement rule as trigger-run.js (verified against
 * Cloudflare's docs there) -- Pages Functions are only detected in a
 * /functions directory at the project root, never inside web/ (the build
 * output directory).
 *
 * FILE_PATH is hardcoded below and NEVER accepted from the client -- this
 * endpoint can only ever read/write queries/poland.txt, no matter what a
 * request sends. If another file ever needs editing from the dashboard,
 * that's a new, separate function -- not a parameter added here.
 *
 * Requires the same GITHUB_DISPATCH_TOKEN as trigger-run.js, but that
 * token now also needs "Contents: Read and write" on this repo (in
 * addition to the "Actions: Read and write" trigger-run.js needs) -- see
 * README.md "Редактирование вопросов из интерфейса".
 */

const REPO = "Archifaq/llm_tracker";
const FILE_PATH = "queries/poland.txt";
const BRANCH = "main";
const CONTENTS_URL = `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`;

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function githubHeaders(token, { withContentType = false } = {}) {
  const headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    // GitHub's API rejects requests with no User-Agent.
    "User-Agent": "llm_tracker-pages-function",
  };
  if (withContentType) headers["Content-Type"] = "application/json";
  return headers;
}

// atob/btoa operate on Latin-1 code units, which mangles UTF-8 text (this
// file has Polish diacritics) unless routed through explicit UTF-8 bytes.
function base64EncodeUtf8(text) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  bytes.forEach((b) => {
    binary += String.fromCharCode(b);
  });
  return btoa(binary);
}

function base64DecodeUtf8(base64) {
  const binary = atob(base64.replace(/\n/g, ""));
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

async function handleGet(context) {
  const token = context.env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    return json({ ok: false, error: "GITHUB_DISPATCH_TOKEN is not configured on this Pages project" }, 500);
  }

  let githubResponse;
  try {
    githubResponse = await fetch(`${CONTENTS_URL}?ref=${BRANCH}`, {
      method: "GET",
      headers: githubHeaders(token),
    });
  } catch {
    return json({ ok: false, error: "could not reach the GitHub API" }, 502);
  }

  if (!githubResponse.ok) {
    const message =
      githubResponse.status === 401 || githubResponse.status === 403
        ? "GitHub rejected the request -- check GITHUB_DISPATCH_TOKEN's scope and expiry"
        : `GitHub API returned HTTP ${githubResponse.status}`;
    return json({ ok: false, error: message }, 502);
  }

  let data;
  try {
    data = await githubResponse.json();
  } catch {
    return json({ ok: false, error: "GitHub API returned an unreadable response" }, 502);
  }

  if (!data || typeof data.content !== "string" || typeof data.sha !== "string") {
    return json({ ok: false, error: "unexpected GitHub API response shape" }, 502);
  }

  return json({ content: base64DecodeUtf8(data.content), sha: data.sha }, 200);
}

async function handlePut(context) {
  const token = context.env.GITHUB_DISPATCH_TOKEN;
  if (!token) {
    return json({ ok: false, error: "GITHUB_DISPATCH_TOKEN is not configured on this Pages project" }, 500);
  }

  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return json({ ok: false, error: "request body must be JSON" }, 400);
  }

  const content = payload && payload.content;
  const sha = payload && payload.sha;
  if (typeof content !== "string" || typeof sha !== "string" || !sha) {
    return json({ ok: false, error: "request must include 'content' and 'sha' (from a prior GET)" }, 400);
  }

  let githubResponse;
  try {
    githubResponse = await fetch(CONTENTS_URL, {
      method: "PUT",
      headers: githubHeaders(token, { withContentType: true }),
      body: JSON.stringify({
        message: "chore: update queries via dashboard",
        content: base64EncodeUtf8(content),
        sha,
        branch: BRANCH,
      }),
    });
  } catch {
    return json({ ok: false, error: "could not reach the GitHub API" }, 502);
  }

  if (githubResponse.status === 409) {
    // sha no longer matches the file on GitHub -- someone/something else
    // wrote to it since this client's last GET. Surface this plainly
    // rather than attempting any kind of automatic merge.
    return json({ ok: false, error: "Файл изменился, обновите страницу и попробуйте снова" }, 409);
  }

  if (githubResponse.status === 401 || githubResponse.status === 403) {
    return json(
      { ok: false, error: "GitHub rejected the request -- check GITHUB_DISPATCH_TOKEN's Contents permission" },
      502
    );
  }

  if (githubResponse.status !== 200 && githubResponse.status !== 201) {
    return json({ ok: false, error: `GitHub API returned HTTP ${githubResponse.status}` }, 502);
  }

  let data = null;
  try {
    data = await githubResponse.json();
  } catch {
    // Write still succeeded even if we can't parse the confirmation body.
  }
  const newSha = data && data.content && typeof data.content.sha === "string" ? data.content.sha : null;
  return json({ ok: true, sha: newSha }, 200);
}

export async function onRequest(context) {
  const method = context.request.method;
  if (method === "GET") return handleGet(context);
  if (method === "PUT") return handlePut(context);
  return json({ ok: false, error: "method not allowed" }, 405);
}
