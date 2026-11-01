# 千牛桌面助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-use Windows desktop rule editor, tested reply engine, optional AI clients, and an honest Windows compatibility diagnostic for Qianniu 9.1907n.

**Architecture:** Separate pure matching, SQLite persistence, reply scheduling, AI transports and platform adapters. The desktop uses those same components; simulated connections are conspicuously labelled. Real sending remains blocked until the Windows adapter's required capabilities are verified on the user's machine.

**Tech Stack:** Python 3.12, PySide6, SQLite, httpx, pywinauto, pytest, PyInstaller.

**Spec:** docs/superpowers/specs/2026-11-01-qianniu-desktop-design.md

## Global Constraints

- Existing isolated checkout /workspace/-, no additional worktree.
- Windows desktop, Qianniu 9.1907n compatibility target; Linux tests do not prove Windows compatibility.
- Self-use: no software billing, activation, quotas, registration or recharge.
- User selected local free Ollama after approving design. AI defaults off; no paid endpoints, keys or cloud services.
- Match precedence: |, &, +, #. Exact matching accepts # candidates only.
- Start paused; one reply per event; advance rotations only after confirmed sends; no automatic retry on ambiguous send.
- Credentials never in exports/logs/database. No silent provider switching.

## Review Focus

1. Malformed expressions and normalization-empty leaves must fail validation (Task 1).
2. Import corruption must not partially overwrite a live rule collection (Task 2).
3. Identical buyer text with different event IDs must receive separate replies (Task 3).
4. Delayed AI results after takeover/disable/new messages must never send (Task 3).
5. Unsupported platform, inaccessible UIA or missing identity must never show connected or enable sending (Task 5).

## Task 1: Rule parsing and domain model

Files: src/qianniu_assistant/{__init__,models,matching}.py, tests/test_matching.py, pyproject.toml, requirements*.txt.
Interfaces: Rule(id,name,expression,replies,match_type,shop,category,priority,enabled,favorite); evaluate(expression: str, message: str, match_type: str='contains')->MatchResult; validate_rule(rule: Rule)->None.
- [ ] Write parametrized tests for all design examples, punctuation, invalid syntax, Unicode, repeated ordered terms and empty input; run pytest tests/test_matching.py and observe missing implementation.
- [ ] Implement immutable expression nodes, parsing and match explanations without eval; cap expression size and normalized-empty keywords.
- [ ] Run pytest tests/test_matching.py; expect every case PASS; commit model/matcher and bootstrap files.

## Task 2: Persistence and import/export

Files: src/qianniu_assistant/store.py, tests/test_store.py.
Interfaces: Store(path), save_rule(rule), rules(shop=None), delete_rule(id), export_rules(path), import_rules(path), settings(), set_settings(dict), history(), clear_history(), cursor(shop,rule_id), record(...), advance(...).
Consumes Rule; settings persisted by allowlist. JSON imports validate whole document before transaction. Rotation and audit rows persist atomically on confirmed send.
- [ ] Write tests for CRUD, stable priority, category/shop scope, Unicode export, invalid/duplicate import atomicity, settings secret rejection, 30-day retention and rotation across reopen; run and observe failure.
- [ ] Implement SQLite with explicit transactions, JSON schema version, bounded data and no auto-seeding real shop data.
- [ ] Run pytest tests/test_store.py; expect PASS; commit.

## Task 3: Reply scheduling and adapters

Files: src/qianniu_assistant/{engine,adapters}.py, tests/test_engine.py.
Interfaces: MessageEvent(shop,conversation,event_id,text,kind='buyer_text'); Adapter.send(event,text)->awaitable bool; Coordinator(store,adapter,ai=None), enable_shop(shop,bool), set_enabled(bool), takeover(shop,conversation), resume(shop,conversation), handle(event), preview(shop,text).
Consumes matcher and Store. Uses per-shop asyncio locks, event identity, conversation generations, current settings recheck and failure-pausing.
- [ ] Write tests for start paused, preview nonmutation, disabled rules, shop isolation, priority/tie-break, distinct identical messages, retries, uncertain send, takeover, outdated AI and per-shop concurrency; observe failure.
- [ ] Implement rule-first routing, optional AI, rotation on acknowledgement only, history controls, simulation adapter clearly separate and unavailable live adapter.
- [ ] Run pytest tests/test_engine.py; expect PASS; commit.

## Task 4: Local AI service

Files: src/qianniu_assistant/ai.py, tests/test_ai.py.
Interfaces: AIClient(model,shop_info,base_url='http://127.0.0.1:11434',transport=None).reply(question)->awaitable str; models()->awaitable list[str].
Ollama uses loopback and no API key. AI remains off by default. Client errors have user-safe text and no raw chat contents.
- [ ] Write transport tests for responses, empty content, timeout, model errors, malformed model/input, loopback restrictions and model detection; observe failure.
- [ ] Implement local-only httpx client with trust_env=False so session proxy settings do not redirect local prompts. Do not issue any paid model requests.
- [ ] Run pytest tests/test_ai.py; expect PASS; commit.

## Task 5: Windows read-only diagnostic and desktop

Files: src/qianniu_assistant/{diagnostics,ui,__main__}.py, tests/{test_diagnostics,test_ui}.py.
Interfaces: diagnose(include_names=False)->dict, save_report(path,report), MainWindow(store), main().
UI tabs: shop control, rules/categories, matching test, AI settings/test, history, diagnostics/help. CRUD dialog validates before save; JSON import/export; simulation is explicit; live sending disabled until real adapter verified. AI work off GUI thread.
- [ ] Write Qt offscreen tests for add/edit/search/delete, invalid-rule feedback, test explanations/rotation, persistence, safe default off and unsupported live state; diagnose on Linux must return unsupported rather than ready; observe failure.
- [ ] Implement desktop and diagnostic; inventory Qianniu UIA structure without chat text by default; identify version evidence without claiming target verified from a filename alone.
- [ ] Run QT_QPA_PLATFORM=offscreen pytest; expect PASS. Start offscreen, exercise real widget actions and capture a screenshot for visual inspection; commit.

## Task 6: Packaging and user instructions

Files: README.md, scripts/{build_windows.ps1,start_windows.bat}, .github/workflows/windows.yml, docs/windows-validation.md.
- [ ] Add pinned install/build commands, Chinese usage, free-vs-paid AI distinction, diagnostic checklist and explicit pending Windows acceptance items. Use the same Python interpreter for dependencies and PyInstaller.
- [ ] Run complete pytest suite, build Python source/wheel locally, inspect archive contents, verify no data/keys included; Windows workflow builds an exe but must run in Windows before claiming exe readiness.
- [ ] Obtain one fresh whole-code review, resolve important findings with regression tests, re-run full suite and commit. Provide source artifact and exact remaining Windows blockers without claiming full live compatibility.
