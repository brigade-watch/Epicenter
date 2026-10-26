// Epicenter front end: plain JS, no build step. Reads the JSON in data/.
(() => {
  "use strict";

  const repo = document.body.dataset.repo;
  const main = document.getElementById("main");
  document.getElementById("repo-link").href = repo;
  document.getElementById("dispute-link").href = `${repo}/issues/new?template=dispute.yml`;

  const SIGNALS = {
    duplicate_text: "Near-identical wording to other accounts",
    spike_source: "Posted the source of a pile-on",
    early_amplifier: "Among the first to arrive in a spike",
    arrived_via_source: "Arrived from a source post",
    new_account: "Account was under 30 days old",
  };

  // ---- helpers -------------------------------------------------------------
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https:\/\//.test(u || "") ? esc(u) : "#");
  const fmtDate = (iso) => iso ? new Date(iso).toLocaleString(undefined,
    { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit" }) : "";
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const listedNote = (shown, total) => total > shown
    ? `${total - shown} ${shown ? "other " : ""}account${total - shown === 1 ? " isn't" : "s aren't"} named because ${total - shown === 1 ? "it hasn't" : "they haven't"} reached the listing threshold.`
    : "";

  const cache = {};
  async function load(path) {
    if (!cache[path]) {
      cache[path] = fetch(path, { cache: "no-cache" }).then((r) => {
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      });
    }
    return cache[path];
  }

  async function accountsByRef() {
    try {
      const data = await load("data/accounts.json");
      return Object.fromEntries(data.accounts.map((a) => [a.ref, a]));
    } catch { return {}; }
  }

  function setNav(name) {
    document.querySelectorAll("[data-nav]").forEach((a) => {
      if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
  }

  // ---- charts --------------------------------------------------------------
  function sparkSvg(values) {
    if (!values || values.length < 2) return "";
    const w = 260, h = 56, max = Math.max(...values, 1);
    const pts = values.map((v, i) => `${(i / (values.length - 1)) * w},${h - 4 - (v / max) * (h - 10)}`);
    return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true">
      <polyline points="${pts.join(" ")}" fill="none" stroke="var(--trace)" stroke-width="1.5" vector-effect="non-scaling-stroke"/></svg>`;
  }

  function traceSvg(inc) {
    const tl = inc.timeline;
    if (!tl.length) return "<p class='muted'>No activity recorded yet.</p>";
    const W = Math.round(Math.min(900, Math.max(300, main.clientWidth - 72))), H = W < 520 ? 200 : 220, padL = 34, padB = 22, padT = 26;
    const t0 = Date.parse(tl[0].t), t1 = Date.parse(tl[tl.length - 1].t) || t0 + 1;
    const span = Math.max(1, t1 - t0);
    const max = Math.max(...tl.map((b) => b.count), 1);
    const x = (t) => padL + ((t - t0) / span) * (W - padL - 8);
    const y = (v) => H - padB - (v / max) * (H - padB - padT);

    const spikes = inc.spikes.map((s) => {
      const a = x(Date.parse(s.start)), b = Math.max(a + 3, x(Date.parse(s.end)));
      return `<rect x="${a}" y="${padT - 8}" width="${b - a}" height="${H - padB - padT + 8}" fill="var(--spike-wash)"/>`;
    }).join("");

    const sources = inc.sources.slice(0, 3).map((s) => {
      const sx = x(Date.parse(s.time));
      if (sx < padL || sx > W) return "";
      return `<line x1="${sx}" x2="${sx}" y1="${padT - 14}" y2="${H - padB}" stroke="var(--source)" stroke-width="2" stroke-dasharray="4 3"/>
        <text class="src-label" x="${Math.max(padL, Math.min(sx + 5, W - 200))}" y="${padT - 16}">Source: @${esc(s.handle)}</text>`;
    }).join("");

    const d = tl.map((b, i) => `${i ? "L" : "M"}${x(Date.parse(b.t)).toFixed(1)},${y(b.count).toFixed(1)}`).join("");
    const ticks = (W < 520 ? [0, 1] : [0, 0.5, 1]).map((f) => {
      const t = t0 + f * span;
      const label = new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric" });
      return `<text x="${x(t)}" y="${H - 4}" text-anchor="${f === 0 ? "start" : f === 1 ? "end" : "middle"}">${esc(label)}</text>`;
    }).join("");

    return `<svg class="trace" viewBox="0 0 ${W} ${H}" role="img"
        aria-label="Activity over time: ${plural(inc.summary.spikes, "spike")}, peak of ${max} posts in ten minutes">
      ${spikes}
      <line x1="${padL}" x2="${W}" y1="${H - padB}" y2="${H - padB}" stroke="var(--rule)"/>
      <text x="0" y="${y(max) + 4}">${max}</text><text x="0" y="${H - padB}">0</text>
      ${sources}
      <path class="line" d="${d}" fill="none" stroke="var(--trace)" stroke-width="2" stroke-linejoin="round"/>
      ${ticks}
    </svg>`;
  }

  // ---- views ---------------------------------------------------------------
  async function viewIncidents() {
    setNav("incidents");
    const index = await load("data/index.json");
    if (!index.incidents.length) {
      main.innerHTML = `<h1>Incidents</h1><div class="empty"><p>Nothing is being tracked yet.</p>
        <p>To suggest a post to watch, <a href="${esc(repo)}/issues/new?template=watch-request.yml">open a watch request</a>.</p></div>`;
      return;
    }
    main.innerHTML = `<h1>Incidents</h1>
      <p class="lede">Posts being watched for pile-ons. Each line is the activity around one post; the sharp peaks are what we look into.
        Seeing one happen? <a href="${esc(repo)}/issues/new?template=watch-request.yml">Suggest a post to watch</a>.</p>
      <ul class="incidents">${index.incidents.map((i) => {
        const hot = i.summary.assessment === "coordination signals present";
        return `<li><a class="strip" href="#/incident/${esc(i.id)}">
          <div><h3>${esc(i.target.note || i.target.url)}</h3>
            <div class="when">${i.first_spike ? `First spike ${esc(fmtDate(i.first_spike))}` : `Checked ${esc(fmtDate(i.analyzed_at))}`},
              ${plural(i.summary.participants, "account")} involved</div>
            <span class="verdict ${hot ? "hot" : "calm"}">${esc(i.summary.assessment[0].toUpperCase() + i.summary.assessment.slice(1))}</span></div>
          ${sparkSvg(i.spark)}</a></li>`;
      }).join("")}</ul>`;
  }

  async function viewIncident(id) {
    setNav("incidents");
    const [inc, refs] = await Promise.all([load(`data/incidents/${encodeURIComponent(id)}.json`), accountsByRef()]);
    const t = inc.target;
    const listed = inc.listed.filter((r) => refs[r]);
    const who = (ref) => `<a href="#/account/${esc(ref)}">@${esc(refs[ref].handle)}</a>`;

    main.innerHTML = `
      <p class="small"><a href="#/">All incidents</a></p>
      <h1>${esc(t.note || "Watched post")}</h1>
      <div class="target">
        ${t.text ? `<blockquote>${esc(t.text)}</blockquote>` : ""}
        <div class="small muted">${t.author_handle ? `Posted by @${esc(t.author_handle)}, ` : ""}
          <a href="${safeUrl(t.url)}" rel="noopener">view the original</a></div>
      </div>
      ${inc.notes.length ? `<p class="small muted">${inc.notes.map(esc).join(" ")}</p>` : ""}

      <div class="trace-box">${traceSvg(inc)}
        <div class="legend"><span><i style="background:var(--trace)"></i>Posts per 10 minutes</span>
          <span><i style="background:var(--spike-wash);border:1px solid var(--spike)"></i>Spike</span>
          <span><i style="background:var(--source)"></i>Source post</span></div></div>

      <dl class="facts">
        <div><dt>Posts</dt><dd>${inc.summary.events}</dd></div>
        <div><dt>Accounts</dt><dd>${inc.summary.participants}</dd></div>
        <div><dt>Spikes</dt><dd>${inc.summary.spikes}</dd></div>
        <div><dt>Copy-paste groups</dt><dd>${inc.summary.duplicate_clusters}</dd></div>
      </dl>

      <h2>Where it came from</h2>
      ${inc.sources.length ? `<p class="lede">Posts whose audience showed up here afterward. "Arrived" means the account liked or replied to the source first, then posted on the watched post.</p>` +
        inc.sources.map((s) => `<div class="source">
          <h3>${s.kind === "quote" ? "Quote post" : "Shared link"} by @${esc(s.handle)}</h3>
          <blockquote>${esc(s.text)}</blockquote>
          <div class="share-bar"><span style="width:${Math.min(100, s.arrival_share * 100)}%"></span></div>
          <div class="small">${s.arrivals} of the accounts here arrived from this post (${Math.round(s.arrival_share * 100)}%).
            Posted ${esc(fmtDate(s.time))}. <a href="${safeUrl(s.url)}" rel="noopener">Open the source</a></div>
        </div>`).join("")
        : `<p class="muted">No single post clearly sent people here.</p>`}

      <h2>Copy-paste groups</h2>
      ${inc.duplicate_clusters.length ? `<p class="lede">Different accounts posting near-identical text within an hour of each other.</p>` +
        inc.duplicate_clusters.map((c) => `<div class="cluster">
          <h3>${plural(c.accounts, "account")} within ${c.span_minutes} minutes</h3>
          <blockquote>${esc(c.sample_text)}</blockquote>
          ${c.listed.filter((r) => refs[r]).length ? `<ul class="chips">${c.listed.filter((r) => refs[r]).map((r) => `<li>${who(r)}</li>`).join("")}</ul>` : ""}
          <div class="small muted">${listedNote(c.listed.filter((r) => refs[r]).length, c.accounts)}</div></div>`).join("")
        : `<p class="muted">No repeated wording found.</p>`}

      <h2>Repeat accounts</h2>
      <p class="lede">${listed.length
        ? `${plural(listed.length, "account")} here also showed this behavior in at least two other incidents:`
        : "No one involved here has shown up in enough incidents to be listed."}</p>
      ${listed.length ? `<ul class="chips">${listed.map((r) => `<li>${who(r)}</li>`).join("")}</ul>` : ""}
      ${inc.unlisted_flagged ? `<p class="small muted">${plural(inc.unlisted_flagged, "other account")} showed a pattern here but ${inc.unlisted_flagged === 1 ? "isn't" : "aren't"} listed. Accounts are named only after three separate incidents.</p>` : ""}
      <p class="small muted">Analyzed ${esc(fmtDate(inc.analyzed_at))}.</p>`;

    const line = main.querySelector(".trace .line");
    if (line) line.style.setProperty("--len", line.getTotalLength());
  }

  async function viewAccounts(focus) {
    setNav("accounts");
    const data = await load("data/accounts.json");
    main.innerHTML = `<h1>Accounts</h1>
      <p class="lede">Accounts that showed coordination patterns in at least three separate incidents in the last six months.
        The gauge measures how often and how strongly, with older incidents counting less. It says nothing about what anyone believes.</p>
      ${data.accounts.length ? `<ul class="accounts">${data.accounts.map((a) => `
        <li class="account" id="acct-${esc(a.ref)}">
          <div class="account-head">
            <div><h3>@${esc(a.handle)}</h3>
              <div class="small muted">${esc(a.label)}, ${plural(a.incidents, "incident")}</div></div>
            <div><div class="gauge" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${a.gauge}"
                aria-label="Coordination gauge"><span style="left:${a.gauge}%"></span></div>
              <div class="gauge-caption"><span>Occasional</span><span>${a.gauge}</span><span>Constant</span></div></div>
          </div>
          <ul class="chips">${Object.entries(a.signal_counts).map(([k, n]) =>
            `<li>${esc(SIGNALS[k] || k)}: ${n}</li>`).join("")}</ul>
          <details${focus === a.ref ? " open" : ""}><summary>Evidence</summary>
            <ul class="history">${a.history.map((h) => `<li>
              <a href="#/incident/${esc(h.incident)}">Incident on ${esc(fmtDate(h.time))}</a>
              <div class="small muted">${h.signals.map((s) => esc(SIGNALS[s] || s)).join("; ")}</div>
              ${h.evidence.length ? `<div class="small">${h.evidence.map((u, i) =>
                `<a href="${safeUrl(u)}" rel="noopener">post ${i + 1}</a>`).join(", ")}</div>` : ""}
            </li>`).join("")}</ul>
          </details>
        </li>`).join("")}</ul>`
      : `<div class="empty"><p>No accounts meet the listing threshold yet.</p></div>`}`;
    if (focus) {
      const el = document.getElementById(`acct-${focus}`);
      if (el) { el.scrollIntoView({ block: "center" }); el.tabIndex = -1; el.focus({ preventScroll: true }); }
    }
  }

  function viewAbout() {
    setNav("about");
    main.innerHTML = `<div class="prose"><h1>How it works</h1>
      <p>Epicenter looks at public activity around posts people ask it to watch. It looks for three things:</p>
      <ul>
        <li><strong>Spikes.</strong> A sudden burst of replies far above the post's normal pace.</li>
        <li><strong>Sources.</strong> Another post whose audience liked or replied to it first, then showed up on the watched post.</li>
        <li><strong>Copy-paste.</strong> Different accounts posting nearly the same words within an hour.</li>
      </ul>
      <p>It scores behavior only. It never labels anyone a bot or a troll, never guesses who runs an account, and never connects accounts across platforms unless the person linked them publicly.</p>
      <h2>Who gets listed</h2>
      <ul>
        <li>An account is listed only after showing these patterns in three separate incidents within six months. Joining one pile-on never gets anyone listed.</li>
        <li>Older incidents count less, and anything older than six months drops off.</li>
        <li>Every score links to the posts behind it.</li>
        <li>Everyone else appears in incident pages as "unlisted account". Their history is encrypted and not published.</li>
      </ul>
      <h2>Suggesting a post</h2>
      <p>Anyone can <a href="${esc(repo)}/issues/new?template=watch-request.yml">suggest a post to watch</a>. A maintainer reviews each suggestion before anything is tracked, so the tool can't be pointed at people automatically.</p>
      <h2>Think we got it wrong?</h2>
      <p><a href="${esc(repo)}/issues/new?template=dispute.yml">Open a dispute</a>. Listings removed after review stay removed.</p>
      <p>The full method, thresholds, and code are in the <a href="${esc(repo)}">public repository</a>.</p></div>`;
  }

  // ---- router --------------------------------------------------------------
  async function route() {
    const [, page, arg] = (location.hash || "#/").split("/");
    try {
      if (page === "incident" && arg) await viewIncident(arg);
      else if (page === "accounts") await viewAccounts();
      else if (page === "account" && arg) await viewAccounts(arg);
      else if (page === "about") viewAbout();
      else await viewIncidents();
    } catch (err) {
      main.innerHTML = `<h1>That page didn't load</h1><p>${esc(err.message)}. Go back to <a href="#/">all incidents</a>.</p>`;
    }
    if (page !== "account") window.scrollTo(0, 0);
  }

  load("data/index.json").then((i) => {
    const demo = i.incidents.some((x) => (x.target.note || "").startsWith("Demo target"));
    document.getElementById("demo-banner").hidden = !demo;
  }).catch(() => {});
  window.addEventListener("hashchange", route);
  route();
})();
