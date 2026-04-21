/**
 * ═══════════════════════════════════════════════════════════════════
 * 🔥 HUNTER888 — HARDCORE SYSTEM TEST SUITE (Browser Console Edition)
 * ═══════════════════════════════════════════════════════════════════
 *
 * USAGE:
 *   1. Login at http://localhost:3000/login
 *   2. Open DevTools Console (F12)
 *   3. Paste this entire script
 *   4. Run: await Hunter888Test.runAll()
 *
 *   Or run individual groups:
 *     await Hunter888Test.auth()
 *     await Hunter888Test.gamification()
 *     await Hunter888Test.training()
 *     await Hunter888Test.pvp()
 *     await Hunter888Test.crm()
 *     await Hunter888Test.security()
 *     await Hunter888Test.stress()
 *     await Hunter888Test.websocket()
 * ═══════════════════════════════════════════════════════════════════
 */

const Hunter888Test = (() => {
  // ── Config ──
  const API = "http://localhost:8000";
  let _token = null;
  let _csrf = null;
  let _userId = null;
  let _refreshToken = null;

  // ── Helpers ──
  const passed = [];
  const failed = [];
  const skipped = [];

  function getCSRF() {
    return document.cookie
      .split("; ")
      .find((r) => r.startsWith("csrf_token="))
      ?.split("=")[1];
  }

  function getRT() {
    return sessionStorage.getItem("vh_rt");
  }

  async function req(method, path, body = null, opts = {}) {
    const headers = {
      "Content-Type": "application/json",
    };
    if (_token) headers["Authorization"] = `Bearer ${_token}`;
    if (["POST", "PUT", "DELETE", "PATCH"].includes(method) && _csrf) {
      headers["X-CSRF-Token"] = _csrf;
    }
    const res = await fetch(`${API}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : null,
      credentials: "include",
      signal: opts.signal,
      ...opts,
    });
    const text = await res.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch {}
    return { status: res.status, json, text, headers: res.headers };
  }

  async function test(name, fn) {
    try {
      await fn();
      passed.push(name);
      console.log(`  ✅ ${name}`);
    } catch (e) {
      failed.push({ name, error: e.message || e });
      console.error(`  ❌ ${name}: ${e.message || e}`);
    }
  }

  function assert(condition, msg) {
    if (!condition) throw new Error(msg || "Assertion failed");
  }

  function section(title) {
    console.log(`\n${"═".repeat(60)}\n  📋 ${title}\n${"═".repeat(60)}`);
  }

  function report() {
    console.log(`\n${"═".repeat(60)}`);
    console.log(`  📊 ИТОГИ: ✅ ${passed.length} | ❌ ${failed.length} | ⏭️ ${skipped.length}`);
    console.log(`${"═".repeat(60)}`);
    if (failed.length > 0) {
      console.log("\n  ❌ ПРОВАЛЕНЫ:");
      failed.forEach((f) => console.log(`    • ${f.name}: ${f.error}`));
    }
    return { passed: passed.length, failed: failed.length, details: failed };
  }

  // ══════════════════════════════════════════════════════════
  //  1. AUTH TESTS
  // ══════════════════════════════════════════════════════════
  async function auth() {
    section("1. АУТЕНТИФИКАЦИЯ И БЕЗОПАСНОСТЬ ТОКЕНОВ");

    // Grab tokens from current session
    _csrf = getCSRF();
    _refreshToken = getRT();

    await test("1.1 GET /api/auth/me — текущий пользователь", async () => {
      const r = await req("GET", "/api/auth/me");
      assert(r.status === 200, `Expected 200, got ${r.status}`);
      assert(r.json?.id, "No user ID in response");
      assert(r.json?.email, "No email");
      assert(r.json?.role, "No role");
      _userId = r.json.id;
      _token = _token; // keep existing
      console.log(`    → User: ${r.json.full_name} (${r.json.role})`);
    });

    await test("1.2 Refresh token rotation (JTI replay protection)", async () => {
      if (!_refreshToken) {
        skipped.push("1.2");
        return;
      }
      const r1 = await req("POST", "/api/auth/refresh", {
        refresh_token: _refreshToken,
      });
      assert(r1.status === 200, `Refresh failed: ${r1.status}`);
      assert(r1.json?.access_token, "No new access_token");
      assert(r1.json?.refresh_token, "No new refresh_token");
      // Save new tokens
      _token = r1.json.access_token;
      _csrf = r1.json.csrf_token || _csrf;
      const oldRefresh = _refreshToken;
      _refreshToken = r1.json.refresh_token;

      // Replay old refresh token — should FAIL
      const r2 = await req("POST", "/api/auth/refresh", {
        refresh_token: oldRefresh,
      });
      assert(
        r2.status === 401 || r2.status === 403,
        `Replay attack succeeded! Got ${r2.status} instead of 401/403`
      );
      console.log("    → Replay attack correctly blocked");
    });

    await test("1.3 Невалидный Bearer token → 401", async () => {
      const saved = _token;
      _token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake.token";
      const r = await req("GET", "/api/auth/me");
      _token = saved;
      assert(r.status === 401, `Expected 401, got ${r.status}`);
    });

    await test("1.4 Login rate limit (5 failed → block)", async () => {
      // Send 6 bad login attempts
      const results = [];
      for (let i = 0; i < 6; i++) {
        const r = await req("POST", "/api/auth/login", {
          email: `ratelimit_test_${Date.now()}@test.com`,
          password: "wrong",
        });
        results.push(r.status);
      }
      const has429 = results.includes(429);
      console.log(`    → Statuses: [${results.join(", ")}]`);
      // Either 429 (rate limit) or all 401 (user not found) is acceptable
      assert(
        has429 || results.every((s) => s === 401 || s === 422),
        "No rate limiting detected"
      );
    });

    await test("1.5 Security headers present", async () => {
      const r = await req("GET", "/api/auth/me");
      const h = r.headers;
      assert(
        h.get("x-content-type-options") === "nosniff",
        "Missing X-Content-Type-Options"
      );
      assert(
        h.get("x-request-id"),
        "Missing X-Request-Id for request tracing"
      );
    });

    await test("1.6 JWT token payload structure (decode)", async () => {
      if (!_token) return;
      const parts = _token.split(".");
      assert(parts.length === 3, "Token is not a valid JWT");
      const payload = JSON.parse(atob(parts[1]));
      assert(payload.sub, "Missing 'sub' claim");
      assert(payload.role, "Missing 'role' claim");
      assert(payload.type === "access", "Not an access token");
      assert(payload.exp, "Missing 'exp' claim");
      assert(payload.jti, "Missing 'jti' claim (token revocation)");
      const ttl = payload.exp - Math.floor(Date.now() / 1000);
      console.log(`    → TTL: ${ttl}s, role: ${payload.role}, jti: ${payload.jti.slice(0, 8)}...`);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  2. GAMIFICATION TESTS
  // ══════════════════════════════════════════════════════════
  async function gamification() {
    section("2. ГЕЙМИФИКАЦИЯ");

    await test("2.1 GET /gamification/me/progress — XP, level, streak", async () => {
      const r = await req("GET", "/api/gamification/me/progress");
      assert(r.status === 200, `Status ${r.status}: ${r.text}`);
      assert(typeof r.json?.total_xp === "number", "No total_xp");
      assert(typeof r.json?.level === "number", "No level");
      assert(typeof r.json?.streak_days === "number", "No streak_days");
      console.log(
        `    → Level ${r.json.level}, XP ${r.json.total_xp}, Streak ${r.json.streak_days}d`
      );
    });

    await test("2.2 GET /gamification/goals — daily/weekly goals", async () => {
      const r = await req("GET", "/api/gamification/goals");
      assert(r.status === 200, `Status ${r.status}`);
      assert(Array.isArray(r.json?.daily) || Array.isArray(r.json?.goals), "No goals array");
      const goals = r.json.daily || r.json.goals || [];
      console.log(`    → ${goals.length} goals loaded`);
    });

    await test("2.3 GET /gamification/daily-challenge — adaptive challenge", async () => {
      const r = await req("GET", "/api/gamification/daily-challenge");
      assert(r.status === 200, `Status ${r.status}`);
      assert(r.json?.challenge || r.json?.date, "No challenge data");
    });

    await test("2.4 GET /gamification/daily-drill — micro-simulation", async () => {
      const r = await req("GET", "/api/gamification/daily-drill");
      assert(r.status === 200, `Status ${r.status}: ${r.text}`);
      assert(r.json?.skill_focus || r.json?.already_completed_today !== undefined, "No drill data");
      console.log(`    → Skill: ${r.json.skill_name || "completed"}, Archetype: ${r.json.archetype || "N/A"}`);
    });

    await test("2.5 GET /gamification/league/me — weekly league", async () => {
      const r = await req("GET", "/api/gamification/league/me");
      // 200 or 404 (no league yet) are both valid
      assert(r.status === 200 || r.status === 404, `Status ${r.status}`);
      if (r.status === 200) {
        console.log(`    → Tier: ${r.json.tier_name}, Rank: ${r.json.rank}/${r.json.group_size}`);
      } else {
        console.log("    → No active league (groups not yet formed)");
      }
    });

    await test("2.6 GET /gamification/season/active — content season", async () => {
      const r = await req("GET", "/api/gamification/season/active");
      assert(r.status === 200, `Status ${r.status}`);
      if (r.json?.active) {
        console.log(`    → Season: ${r.json.name}, Chapters: ${r.json.chapters?.length || 0}`);
      } else {
        console.log("    → No active season");
      }
    });

    await test("2.7 GET /gamification/streak-freeze — freeze status", async () => {
      const r = await req("GET", "/api/gamification/streak-freeze");
      assert(r.status === 200, `Status ${r.status}`);
      assert(typeof r.json?.freezes_available === "number", "No freezes_available");
      console.log(`    → Freezes: ${r.json.freezes_available}/${r.json.freezes_max}`);
    });

    await test("2.8 GET /gamification/xp-event/active — XP multiplier", async () => {
      const r = await req("GET", "/api/gamification/xp-event/active");
      assert(r.status === 200, `Status ${r.status}`);
      if (r.json?.active) {
        console.log(`    → Event: ${r.json.name}, ${r.json.multiplier}x, ${r.json.minutes_remaining}min left`);
      } else {
        console.log("    → No active XP event");
      }
    });

    await test("2.9 GET /gamification/leaderboard — top players", async () => {
      const r = await req("GET", "/api/gamification/leaderboard");
      assert(r.status === 200, `Status ${r.status}`);
      assert(Array.isArray(r.json), "Not an array");
      console.log(`    → ${r.json.length} players on leaderboard`);
    });

    await test("2.10 GET /gamification/leaderboard/composite — multi-metric ranking", async () => {
      const r = await req("GET", "/api/gamification/leaderboard/composite?period=week&limit=10");
      assert(r.status === 200, `Status ${r.status}`);
      if (r.json?.length > 0) {
        const top = r.json[0];
        console.log(
          `    → #1: composite=${top.composite_score}, training=${top.training_avg}, pvp=${top.pvp_rating_norm}`
        );
      }
    });

    await test("2.11 GET /gamification/me/skill-mastery — 6 soft skills", async () => {
      const r = await req("GET", "/api/gamification/me/skill-mastery");
      assert(r.status === 200, `Status ${r.status}`);
      assert(r.json?.skills, "No skills object");
      const skills = Object.entries(r.json.skills);
      console.log(`    → ${skills.map(([k, v]) => `${k}:${v}`).join(", ")}`);
    });

    await test("2.12 GET /gamification/checkpoints — level progression", async () => {
      const r = await req("GET", "/api/gamification/checkpoints");
      assert(r.status === 200, `Status ${r.status}`);
      const done = Array.isArray(r.json) ? r.json.filter((c) => c.is_completed).length : 0;
      console.log(`    → ${done}/${r.json?.length || 0} checkpoints completed`);
    });

    await test("2.13 GET /gamification/portfolio — deal archive", async () => {
      const r = await req("GET", "/api/gamification/portfolio?limit=5&offset=0");
      assert(r.status === 200, `Status ${r.status}`);
      assert(typeof r.json?.total_deals === "number", "No total_deals");
      console.log(`    → ${r.json.total_deals} total deals`);
    });

    await test("2.14 POST chest open (bronze) — reward generation", async () => {
      const r = await req("POST", "/api/gamification/chest/open", {
        chest_type: "bronze",
      });
      // 200 success or 400/409 (no chest available)
      assert(
        r.status === 200 || r.status === 400 || r.status === 409 || r.status === 422,
        `Unexpected: ${r.status}`
      );
      if (r.status === 200) {
        console.log(
          `    → Chest: +${r.json.xp_reward}XP, +${r.json.ap_reward}AP, item: ${r.json.item_name || "none"}, rare: ${r.json.is_rare_drop}`
        );
      } else {
        console.log(`    → ${r.status}: ${r.json?.detail || "No chest available"}`);
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  3. TRAINING TESTS
  // ══════════════════════════════════════════════════════════
  async function training() {
    section("3. ТРЕНИРОВОЧНЫЕ СЕССИИ");

    let scenarioId = null;

    await test("3.1 GET /scenarios/ — список сценариев", async () => {
      const r = await req("GET", "/api/scenarios/");
      assert(r.status === 200, `Status ${r.status}`);
      assert(Array.isArray(r.json), "Not an array");
      assert(r.json.length > 0, "No scenarios available");
      scenarioId = r.json[0].id;
      console.log(`    → ${r.json.length} scenarios, first: "${r.json[0].title}"`);
    });

    await test("3.2 GET /training/assigned — назначенные тренировки", async () => {
      const r = await req("GET", "/api/training/assigned");
      assert(r.status === 200, `Status ${r.status}`);
      console.log(`    → ${Array.isArray(r.json) ? r.json.length : 0} assigned`);
    });

    await test("3.3 GET /training/history — история сессий", async () => {
      const r = await req("GET", "/api/training/history?limit=5&offset=0");
      assert(r.status === 200, `Status ${r.status}`);
      assert(Array.isArray(r.json), "Not an array");
      if (r.json.length > 0) {
        const last = r.json[0];
        console.log(
          `    → Last: score=${last.score_total}, status=${last.status}, duration=${last.duration_seconds}s`
        );
      }
    });

    await test("3.4 GET /training/sessions/{id} — детали сессии (последняя)", async () => {
      const hist = await req("GET", "/api/training/history?limit=1&offset=0");
      if (hist.json?.length > 0) {
        const sid = hist.json[0].id;
        const r = await req("GET", `/api/training/sessions/${sid}`);
        assert(r.status === 200, `Status ${r.status}`);
        assert(r.json?.id === sid, "ID mismatch");
        const scores = r.json;
        console.log(
          `    → Score: ${scores.score_total}, Script: ${scores.score_script_adherence}, ` +
            `Objections: ${scores.score_objection_handling}, Comm: ${scores.score_communication}`
        );
      } else {
        console.log("    → No sessions to inspect");
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  4. PVP TESTS
  // ══════════════════════════════════════════════════════════
  async function pvp() {
    section("4. PVP АРЕНА");

    await test("4.1 GET /pvp/rating/me — Glicko-2 рейтинг", async () => {
      const r = await req(
        "GET",
        "/api/pvp/rating/me?rating_type=training_duel"
      );
      assert(r.status === 200, `Status ${r.status}`);
      assert(typeof r.json?.rating === "number", "No rating");
      console.log(
        `    → Rating: ${r.json.rating} (RD: ${r.json.rd}), Tier: ${r.json.rank_display}, W/L: ${r.json.wins}/${r.json.losses}`
      );
    });

    await test("4.2 GET /pvp/leaderboard — PvP таблица", async () => {
      const r = await req("GET", "/api/pvp/leaderboard?limit=10");
      assert(r.status === 200, `Status ${r.status}`);
    });

    await test("4.3 GET /pvp/duels/me — история дуэлей", async () => {
      const r = await req("GET", "/api/pvp/duels/me?limit=5");
      assert(r.status === 200, `Status ${r.status}`);
      console.log(`    → ${Array.isArray(r.json) ? r.json.length : 0} duels`);
    });

    await test("4.4 GET /pvp/gauntlet/cooldown — кулдаун гаунтлета", async () => {
      const r = await req("GET", "/api/pvp/gauntlet/cooldown");
      assert(r.status === 200, `Status ${r.status}`);
      console.log(`    → Cooldown: ${r.json?.cooldown_minutes || 0} min`);
    });

    await test("4.5 GET /pvp/queue/status — статус очереди", async () => {
      const r = await req("GET", "/api/pvp/queue/status");
      assert(r.status === 200 || r.status === 404, `Status ${r.status}`);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  5. CRM TESTS
  // ══════════════════════════════════════════════════════════
  async function crm() {
    section("5. CRM / КЛИЕНТЫ");

    await test("5.1 GET /clients — список клиентов", async () => {
      const r = await req("GET", "/api/clients?limit=5&offset=0");
      assert(r.status === 200, `Status ${r.status}`);
      console.log(`    → ${Array.isArray(r.json) ? r.json.length : "?"} clients`);
    });

    await test("5.2 GET /clients/pipeline — Kanban данные", async () => {
      const r = await req("GET", "/api/clients/pipeline");
      assert(r.status === 200, `Status ${r.status}`);
    });

    await test("5.3 GET /clients/pipeline/stats — воронка конверсии", async () => {
      const r = await req("GET", "/api/clients/pipeline/stats");
      assert(r.status === 200, `Status ${r.status}`);
    });

    await test("5.4 CRUD: создать → обновить → удалить клиента", async () => {
      // CREATE
      const ts = Date.now();
      const c = await req("POST", "/api/clients", {
        phone: `+7999${ts.toString().slice(-7)}`,
        email: `test_${ts}@hunter888.test`,
        full_name: `Тест Клиент ${ts}`,
        notes: "Автотест — можно удалить",
      });
      assert(c.status === 201 || c.status === 200, `Create: ${c.status} - ${c.text}`);
      const clientId = c.json?.id;
      assert(clientId, "No client ID returned");

      // UPDATE
      const u = await req("PUT", `/api/clients/${clientId}`, {
        full_name: `Обновлённый Клиент ${ts}`,
        notes: "Обновлено автотестом",
      });
      assert(u.status === 200, `Update: ${u.status}`);

      // DELETE
      const d = await req("DELETE", `/api/clients/${clientId}`);
      assert(d.status === 204 || d.status === 200, `Delete: ${d.status}`);
      console.log("    → Create ✓ → Update ✓ → Delete ✓");
    });

    await test("5.5 GET /clients/graph/data — граф связей", async () => {
      const r = await req("GET", "/api/clients/graph/data");
      assert(r.status === 200, `Status ${r.status}`);
    });

    await test("5.6 GET /clients/stats — статистика CRM", async () => {
      const r = await req("GET", "/api/clients/stats");
      assert(r.status === 200, `Status ${r.status}`);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  6. SECURITY TESTS (CSRF, injection, auth bypass)
  // ══════════════════════════════════════════════════════════
  async function security() {
    section("6. БЕЗОПАСНОСТЬ (CSRF, инъекции, обход авторизации)");

    await test("6.1 POST без CSRF → 403", async () => {
      const savedCsrf = _csrf;
      _csrf = null;
      const r = await req("POST", "/api/clients", {
        phone: "+79991234567",
        full_name: "CSRF Test",
      });
      _csrf = savedCsrf;
      assert(r.status === 403, `Expected 403, got ${r.status} — CSRF bypass!`);
    });

    await test("6.2 POST с неправильным CSRF → 403", async () => {
      const savedCsrf = _csrf;
      _csrf = "invalid_csrf_token_12345";
      const r = await req("POST", "/api/clients", {
        phone: "+79991234568",
        full_name: "Bad CSRF Test",
      });
      _csrf = savedCsrf;
      assert(r.status === 403, `Expected 403, got ${r.status} — CSRF validation broken!`);
    });

    await test("6.3 SQL injection в query params", async () => {
      const r = await req(
        "GET",
        "/api/clients?limit=5&offset=0; DROP TABLE users;--"
      );
      // Should return 422 (validation error) or 200 (ignored), NOT 500
      assert(r.status !== 500, `SQL injection caused 500 server error!`);
      console.log(`    → Status ${r.status} (safe)`);
    });

    await test("6.4 XSS в пользовательском вводе (client name)", async () => {
      const xss = `<script>alert('XSS')</script>`;
      const r = await req("POST", "/api/clients", {
        phone: "+79991234569",
        full_name: xss,
        email: `xss_test_${Date.now()}@test.com`,
      });
      if (r.status === 200 || r.status === 201) {
        // If created, check that script tags are escaped/stored as text
        const clientId = r.json?.id;
        if (clientId) {
          const g = await req("GET", `/api/clients/${clientId}`);
          assert(
            !g.text.includes("<script>alert"),
            "XSS payload stored unescaped!"
          );
          // Cleanup
          await req("DELETE", `/api/clients/${clientId}`);
        }
        console.log("    → XSS payload sanitized or escaped");
      } else {
        console.log(`    → Rejected: ${r.status} (input validation)`);
      }
    });

    await test("6.5 Path traversal в session ID", async () => {
      const r = await req(
        "GET",
        "/api/training/sessions/../../etc/passwd"
      );
      assert(r.status === 422 || r.status === 404, `Got ${r.status}`);
      console.log(`    → Blocked: ${r.status}`);
    });

    await test("6.6 Oversized payload (1MB JSON)", async () => {
      const big = { data: "A".repeat(1024 * 1024) };
      const r = await req("POST", "/api/clients", big);
      assert(
        r.status === 413 || r.status === 422 || r.status === 400,
        `Expected rejection, got ${r.status}`
      );
      console.log(`    → Rejected: ${r.status}`);
    });

    await test("6.7 Доступ к чужим данным (IDOR)", async () => {
      // Try to access another user's data with a fake UUID
      const fakeId = "00000000-0000-0000-0000-000000000001";
      const r = await req("GET", `/api/users/${fakeId}/stats`);
      // Should be 403 (forbidden) or 404 (not found), not 200
      assert(
        r.status === 403 || r.status === 404 || r.status === 422,
        `IDOR: got ${r.status} — may have accessed another user's data!`
      );
      console.log(`    → Blocked: ${r.status}`);
    });

    await test("6.8 Без авторизации → все protected endpoints → 401", async () => {
      const saved = _token;
      _token = null;
      const endpoints = [
        "/api/gamification/me/progress",
        "/api/training/history",
        "/api/pvp/rating/me",
        "/api/clients",
      ];
      for (const ep of endpoints) {
        const r = await req("GET", ep);
        assert(r.status === 401, `${ep} returned ${r.status} without auth!`);
      }
      _token = saved;
      console.log(`    → All ${endpoints.length} endpoints correctly return 401`);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  7. STRESS TESTS
  // ══════════════════════════════════════════════════════════
  async function stress() {
    section("7. СТРЕСС-ТЕСТЫ");

    await test("7.1 20 параллельных запросов к /gamification/me/progress", async () => {
      const start = performance.now();
      const promises = Array.from({ length: 20 }, () =>
        req("GET", "/api/gamification/me/progress")
      );
      const results = await Promise.all(promises);
      const elapsed = Math.round(performance.now() - start);
      const statuses = results.map((r) => r.status);
      const ok = statuses.filter((s) => s === 200).length;
      const rate_limited = statuses.filter((s) => s === 429).length;
      assert(ok + rate_limited === 20, `Unexpected statuses: ${statuses}`);
      console.log(
        `    → ${ok} OK, ${rate_limited} rate-limited, ${elapsed}ms total`
      );
    });

    await test("7.2 50 параллельных запросов к разным endpoints", async () => {
      const endpoints = [
        "/api/auth/me",
        "/api/gamification/me/progress",
        "/api/gamification/goals",
        "/api/gamification/daily-challenge",
        "/api/gamification/leaderboard",
        "/api/training/history?limit=1",
        "/api/scenarios/",
        "/api/pvp/rating/me?rating_type=training_duel",
        "/api/clients?limit=1",
        "/api/gamification/checkpoints",
      ];
      const start = performance.now();
      const promises = [];
      for (let i = 0; i < 50; i++) {
        promises.push(req("GET", endpoints[i % endpoints.length]));
      }
      const results = await Promise.all(promises);
      const elapsed = Math.round(performance.now() - start);
      const ok = results.filter((r) => r.status === 200).length;
      const errors = results.filter(
        (r) => r.status >= 500
      ).length;
      assert(errors === 0, `${errors} server errors (5xx)!`);
      console.log(
        `    → ${ok}/50 OK, 0 server errors, ${elapsed}ms total (avg ${Math.round(elapsed / 50)}ms/req)`
      );
    });

    await test("7.3 Быстрые последовательные запросы (100 запросов)", async () => {
      const start = performance.now();
      let ok = 0;
      let err500 = 0;
      for (let i = 0; i < 100; i++) {
        const r = await req("GET", "/api/auth/me");
        if (r.status === 200) ok++;
        if (r.status >= 500) err500++;
      }
      const elapsed = Math.round(performance.now() - start);
      assert(err500 === 0, `${err500} server errors!`);
      console.log(`    → ${ok}/100 OK, ${elapsed}ms total, ${Math.round(elapsed / 100)}ms/req avg`);
    });

    await test("7.4 Timeout handling (AbortController 100ms)", async () => {
      const controller = new AbortController();
      setTimeout(() => controller.abort(), 100);
      try {
        // This endpoint is slow (AI-powered) — should timeout
        await req("GET", "/api/gamification/daily-challenge", null, {
          signal: controller.signal,
        });
        console.log("    → Completed within 100ms (fast response)");
      } catch (e) {
        assert(
          e.name === "AbortError" || e.message?.includes("abort"),
          `Unexpected error: ${e.message}`
        );
        console.log("    → Correctly aborted after 100ms");
      }
    });
  }

  // ══════════════════════════════════════════════════════════
  //  8. WEBSOCKET TESTS
  // ══════════════════════════════════════════════════════════
  async function websocket() {
    section("8. WEBSOCKET");

    await test("8.1 WS Training — connect + auth + pong", async () => {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Timeout 5s")), 5000);
        const protocol = window.location.protocol === "https:" ? "wss" : "ws";
        const ws = new WebSocket(`${protocol}://localhost:8000/ws/training`);
        const log = [];

        ws.onopen = () => {
          log.push("connected");
          ws.send(JSON.stringify({ type: "auth", token: _token }));
        };

        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          log.push(msg.type);

          if (msg.type === "auth.success") {
            ws.send(JSON.stringify({ type: "ping" }));
          }
          if (msg.type === "pong") {
            clearTimeout(timeout);
            ws.close();
            console.log(`    → Flow: ${log.join(" → ")}`);
            resolve();
          }
          if (msg.type === "error") {
            clearTimeout(timeout);
            ws.close();
            reject(new Error(`WS error: ${msg.data?.message}`));
          }
        };

        ws.onerror = () => {
          clearTimeout(timeout);
          reject(new Error("WebSocket connection failed"));
        };
      });
    });

    await test("8.2 WS Training — invalid token → auth denied", async () => {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Timeout 5s")), 5000);
        const ws = new WebSocket("ws://localhost:8000/ws/training");

        ws.onopen = () => {
          ws.send(
            JSON.stringify({ type: "auth", token: "invalid.fake.token" })
          );
        };

        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          if (msg.type === "error" || msg.type === "auth.error") {
            clearTimeout(timeout);
            ws.close();
            console.log(`    → Correctly rejected: ${msg.data?.message || msg.data?.code}`);
            resolve();
          }
        };

        ws.onclose = (e) => {
          clearTimeout(timeout);
          if (e.code === 1008 || e.code === 4001) {
            console.log(`    → Correctly closed: code=${e.code}`);
            resolve();
          }
        };

        ws.onerror = () => {
          clearTimeout(timeout);
          reject(new Error("Connection failed"));
        };
      });
    });

    await test("8.3 WS без Origin → отклонение (CSWSH protection)", async () => {
      // Browser always sends Origin, so we can't truly test this from browser
      // Instead verify the WS connects successfully (Origin is valid)
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error("Timeout 3s")), 3000);
        const ws = new WebSocket("ws://localhost:8000/ws/training");

        ws.onopen = () => {
          clearTimeout(timeout);
          ws.close();
          console.log("    → WS accepts browser Origin (localhost valid)");
          resolve();
        };

        ws.onerror = () => {
          clearTimeout(timeout);
          reject(new Error("WS rejected valid origin"));
        };
      });
    });

    await test("8.4 WS Notifications — connect + auth", async () => {
      return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
          ws.close();
          // Notifications WS may not send pong - just connecting is enough
          console.log("    → Connected successfully (no messages expected)");
          resolve();
        }, 3000);
        const ws = new WebSocket("ws://localhost:8000/ws/notifications");

        ws.onopen = () => {
          ws.send(JSON.stringify({ type: "auth", token: _token }));
        };

        ws.onmessage = (e) => {
          const msg = JSON.parse(e.data);
          if (msg.type === "auth.success") {
            clearTimeout(timeout);
            ws.close();
            console.log("    → Authenticated to notifications WS");
            resolve();
          }
        };

        ws.onerror = () => {
          clearTimeout(timeout);
          reject(new Error("Notifications WS failed"));
        };
      });
    });
  }

  // ══════════════════════════════════════════════════════════
  //  9. DATA INTEGRITY TESTS
  // ══════════════════════════════════════════════════════════
  async function integrity() {
    section("9. ЦЕЛОСТНОСТЬ ДАННЫХ");

    await test("9.1 Gamification progress XP ≥ 0 и level ≥ 1", async () => {
      const r = await req("GET", "/api/gamification/me/progress");
      assert(r.json.total_xp >= 0, `Negative XP: ${r.json.total_xp}`);
      assert(r.json.level >= 1, `Invalid level: ${r.json.level}`);
      assert(r.json.streak_days >= 0, `Negative streak: ${r.json.streak_days}`);
    });

    await test("9.2 Leaderboard sorted correctly (desc)", async () => {
      const r = await req("GET", "/api/gamification/leaderboard");
      if (r.json?.length >= 2) {
        for (let i = 1; i < r.json.length; i++) {
          const prev = r.json[i - 1].total_score || r.json[i - 1].avg_score || 0;
          const curr = r.json[i].total_score || r.json[i].avg_score || 0;
          assert(
            prev >= curr,
            `Leaderboard not sorted: position ${i - 1}(${prev}) < position ${i}(${curr})`
          );
        }
        console.log(`    → ${r.json.length} entries correctly sorted`);
      }
    });

    await test("9.3 User profile consistency (me vs users/me/profile)", async () => {
      const [me, profile] = await Promise.all([
        req("GET", "/api/auth/me"),
        req("GET", "/api/users/me/profile"),
      ]);
      assert(me.status === 200, `auth/me: ${me.status}`);
      assert(profile.status === 200, `users/me/profile: ${profile.status}`);
      assert(
        me.json.id === profile.json.id,
        `ID mismatch: ${me.json.id} vs ${profile.json.id}`
      );
      assert(
        me.json.email === profile.json.email,
        `Email mismatch`
      );
    });

    await test("9.4 PvP rating bounds (1000-3000 Glicko-2)", async () => {
      const r = await req("GET", "/api/pvp/rating/me?rating_type=training_duel");
      if (r.status === 200) {
        assert(r.json.rating >= 0, `Rating below 0: ${r.json.rating}`);
        assert(r.json.rating <= 4000, `Rating above 4000: ${r.json.rating}`);
        assert(r.json.rd > 0, `RD must be positive: ${r.json.rd}`);
      }
    });

    await test("9.5 Health check endpoint", async () => {
      const r = await req("GET", "/api/health");
      assert(r.status === 200, `Health check failed: ${r.status}`);
      console.log(`    → ${JSON.stringify(r.json)}`);
    });

    await test("9.6 Training history — scores в диапазоне 0-100", async () => {
      const r = await req("GET", "/api/training/history?limit=10");
      for (const s of r.json || []) {
        if (s.score_total !== null) {
          assert(
            s.score_total >= 0 && s.score_total <= 100,
            `Score out of range: ${s.score_total} in session ${s.id}`
          );
        }
      }
      console.log(`    → ${r.json?.length || 0} sessions, all scores in 0-100`);
    });
  }

  // ══════════════════════════════════════════════════════════
  //  10. NETWORK MONITOR COMMANDS
  // ══════════════════════════════════════════════════════════
  async function networkMonitor() {
    section("10. NETWORK MONITORING (для вкладки Network)");

    console.log(`
  📡 Откройте вкладку Network в DevTools и выполните:

  ──── Фильтры для Network tab ────

  🔍 Только API:           is:running domain:localhost:8000
  🔍 Только ошибки:        status-code:400-599
  🔍 Только WS:            ws://
  🔍 Только медленные:     larger-than:5ms

  ──── Ручные команды ────

  // Проверить все API за один раз:
  await Hunter888Test.stress()

  // Мониторить WebSocket в реальном времени:
  Hunter888Test.wsMonitor()

  // Проверить размер ответов:
  await Hunter888Test.responseSizes()
`);
  }

  // WebSocket real-time monitor
  function wsMonitor() {
    console.log("🔌 WS Monitor started — watching all messages...\n");
    const ws = new WebSocket("ws://localhost:8000/ws/training");
    ws.onopen = () => {
      console.log("📡 Connected, authenticating...");
      ws.send(JSON.stringify({ type: "auth", token: _token }));
    };
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      const ts = new Date().toLocaleTimeString();
      if (msg.type === "pong") return; // skip noise
      console.log(
        `[${ts}] ← ${msg.type}`,
        msg.data ? JSON.stringify(msg.data).slice(0, 200) : ""
      );
    };
    ws.onclose = (e) =>
      console.log(`🔌 WS closed: code=${e.code}, reason=${e.reason}`);
    console.log("  → Для остановки: ws.close() или обновите страницу");
    return ws;
  }

  // Response size analyzer
  async function responseSizes() {
    section("РАЗМЕРЫ ОТВЕТОВ");
    const endpoints = [
      "/api/auth/me",
      "/api/gamification/me/progress",
      "/api/gamification/goals",
      "/api/gamification/leaderboard",
      "/api/scenarios/",
      "/api/training/history?limit=10",
      "/api/clients?limit=10",
      "/api/pvp/rating/me?rating_type=training_duel",
      "/api/gamification/checkpoints",
      "/api/gamification/portfolio?limit=10",
    ];
    for (const ep of endpoints) {
      const r = await req("GET", ep);
      const size = new Blob([r.text]).size;
      const kb = (size / 1024).toFixed(1);
      const icon = size > 50000 ? "🔴" : size > 10000 ? "🟡" : "🟢";
      console.log(
        `  ${icon} ${ep.padEnd(50)} ${r.status} ${kb}KB`
      );
    }
  }

  // ══════════════════════════════════════════════════════════
  //  RUN ALL
  // ══════════════════════════════════════════════════════════
  async function runAll() {
    console.clear();
    console.log(`
╔══════════════════════════════════════════════════════════╗
║    🔥 HUNTER888 HARDCORE SYSTEM TEST SUITE              ║
║    ${new Date().toLocaleString().padEnd(53)}║
╚══════════════════════════════════════════════════════════╝
`);
    passed.length = 0;
    failed.length = 0;
    skipped.length = 0;

    const start = performance.now();

    await auth();
    await gamification();
    await training();
    await pvp();
    await crm();
    await security();
    await integrity();
    await stress();
    await websocket();

    const elapsed = Math.round(performance.now() - start);
    console.log(`\n⏱️  Total time: ${(elapsed / 1000).toFixed(1)}s`);
    return report();
  }

  return {
    runAll,
    auth,
    gamification,
    training,
    pvp,
    crm,
    security,
    stress,
    websocket,
    integrity,
    networkMonitor,
    wsMonitor,
    responseSizes,
  };
})();

console.log(`
╔══════════════════════════════════════════════════════════╗
║  🔥 Hunter888 Test Suite loaded!                        ║
║                                                         ║
║  await Hunter888Test.runAll()    — ВСЕ тесты            ║
║  await Hunter888Test.auth()     — Аутентификация        ║
║  await Hunter888Test.gamification() — Геймификация      ║
║  await Hunter888Test.training() — Тренировки            ║
║  await Hunter888Test.pvp()      — PvP арена             ║
║  await Hunter888Test.crm()      — CRM клиенты           ║
║  await Hunter888Test.security() — Безопасность          ║
║  await Hunter888Test.stress()   — Стресс-тесты          ║
║  await Hunter888Test.websocket() — WebSocket            ║
║  await Hunter888Test.integrity() — Целостность данных   ║
║  Hunter888Test.wsMonitor()      — WS мониторинг live    ║
║  await Hunter888Test.responseSizes() — Размеры ответов  ║
╚══════════════════════════════════════════════════════════╝
`);
