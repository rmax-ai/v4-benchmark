# Prompt Improvements — Closing the Flash → Pro Gap

Findings from the 2026-07-31 smoke test comparing `deepseek-v4-pro` vs `deepseek-v4-flash` on the `hn-digest` task. Pro scored 9/7/9/9 (depth/actionability/structure) vs Flash's 7/7/8.

**Root cause**: Pro infers domain context that Flash doesn't. Flash follows instructions literally — rank by popularity, summarize generically. Pro trades popularity for personal relevance, connects stories to Max's actual work, and adds reading priority.

## The Core Gap

| What Pro did | What Flash did | Why Flash missed it |
|---|---|---|
| Surfaced Manifest router deprecation (31 pts) — directly adjacent to Max's gateway routing | Dropped it to "Also Worth a Look" buried at the bottom | Prompt says "top 5-8 most interesting stories" — Flash interprets as "by score" |
| Surfaced ORCA-Bench (12 pts) — oncall SRE eval, directly relevant to HITL/eval work | Didn't mention it at all | Same — 12 pts never makes a popularity cutoff |
| Titled output "for Max (platform/governance/infra lens)" | Generic "HN DIGEST — Friday" | No personalization instruction in prompt |
| Explicit "Read #5 first — most operationally relevant" recommendation block | No reading priority at all | No instruction to produce priority |
| Connected every story to a specific work domain | Generic "why it matters" disconnected from Max's context | Prompt doesn't define Max's domains |

## Concrete Prompt Changes

### 1. Add Domain Profile (most impactful)

Insert after the filter categories:

```diff
+## Max's Work Domains
+
+Rank stories by relevance to these areas, not raw HN popularity:
+- **Agent gateways** — governed multi-agent infrastructure, MCP, OAuth/RBAC/ABAC
+- **HITL & evals** — human-in-the-loop approval flows, agent evaluation methodology
+- **Model routing** — cost-performance tradeoffs, inference economics, gateway architecture
+- **Platform engineering** — scalable infrastructure, developer tooling, platform observability
+- **AI governance** — policy enforcement, sandboxing, audit trails, security posture
+
+A story scoring 30 points that directly speaks to one of these domains is more valuable
+than a 600-point story about general AI news. Prioritize surgical relevance over broad appeal.
```

### 2. Change Ranking Semantics

```diff
- Produce a ranked digest of the top 5-8 most interesting stories.
+ Produce a ranked digest of 5-8 stories that are most relevant to Max's work.
+ **Do NOT rank by HN score.** Rank by domain relevance — a low-scoring story about
+ LLM routing, agent evals, or gateway architecture belongs higher than a high-scoring
+ story about general AI capabilities or consumer products.
```

### 3. Add Domain Connection Requirement

```diff
- - Note why it matters
+ - Note why it matters **with explicit connection to Max's work domains when possible**
+   - Bad: "Relevant to AI governance"
+   - Good: "Directly adjacent to Max's agent gateway: scoped identity, policy enforcement,
+     shared skills, and audit — same primitives as Gatehouse"
```

### 4. Add Reading Priority

```diff
  Format as a clear digest with story titles as headings.
+ After the ranked stories, add a "Recommended Reading Order" section (2-3 sentences)
+ with explicit priority and rationale:
+   - "Read #3 first — most operationally relevant to your gateway routing decisions"
+   - "Then #1 as competitor architecture reference"
+   - "Then #5 for eval methodology inspiration"
```

### 5. Add Lens Annotation to Title

```diff
- You are running an AI-focused Hacker News digest for Max.
+ You are running an AI-focused Hacker News digest for Max (platform/governance/infra lens).
+ Title the digest: "HN Digest — YYYY-MM-DD (platform/governance/infra lens)"
```

### 6. Add Anti-Pattern Guidance

After the format instructions, add a "What to avoid" section:

```diff
+## What to Avoid
+
+- **Don't rank by HN score** — the top-scored story is often broadly popular AI news,
+  not surgically relevant to Max's work
+- **Don't drop low-pointer stories** — a 12-point story about agent evals or LLM routing
+  is more valuable than a 700-point story about general AI
+- **Don't summarize generically** — every story should answer "why does Max specifically
+  need to know this?"
+- **Don't skip the reading priority** — Max skims, he needs you to tell him what to read first
```

## Full Improved Prompt

```yaml
name: hn-digest
description: "Hacker News AI-focused story digest"
skills: []
prompt: |
  You are running an AI-focused Hacker News digest for Max (platform/governance/infra lens).

  Fetch the top 30 stories from Hacker News (use the HN API or web extraction).

  ## Max's Work Domains

  Rank stories by relevance to these areas, not raw HN popularity:
  - **Agent gateways** — governed multi-agent infrastructure, MCP, OAuth/RBAC/ABAC
  - **HITL & evals** — human-in-the-loop approval flows, agent evaluation methodology
  - **Model routing** — cost-performance tradeoffs, inference economics, gateway architecture
  - **Platform engineering** — scalable infrastructure, developer tooling, platform observability
  - **AI governance** — policy enforcement, sandboxing, audit trails, security posture

  A story scoring 30 points that directly speaks to one of these domains is more valuable
  than a 600-point story about general AI news. Prioritize surgical relevance over broad appeal.

  ## Filter

  Filter for stories related to:
  - AI, machine learning, LLMs
  - Software engineering and developer tools
  - Startups and technology business
  - Open source projects
  - Infrastructure and DevOps

  ## Digest Format

  For each relevant story:
  - Provide the title, URL, and a 1-2 sentence summary
  - Include the HN points and comment count
  - Note why it matters **with explicit connection to Max's work domains when possible**
    - Bad: "Relevant to AI governance"
    - Good: "Directly adjacent to Max's agent gateway: scoped identity, policy enforcement, shared skills, and audit — same primitives as Gatehouse"

  Title the digest: "HN Digest — YYYY-MM-DD (platform/governance/infra lens)"

  Produce a digest of 5-8 stories ranked by domain relevance, not HN score.

  After the ranked stories, add a "Recommended Reading Order" section (2-3 sentences)
  with explicit priority and rationale.

  ## What to Avoid

  - Don't rank by HN score — the top-scored story is often broadly popular AI news
  - Don't drop low-pointer stories — a 12-point story about agent evals or LLM routing is more valuable than a 700-point story about general AI
  - Don't summarize generically — every story should answer "why does Max specifically need to know this?"
  - Don't skip the reading priority — Max skims, he needs you to tell him what to read first
toolsets:
  - web
  - file
evaluation_focus:
  - correctness
  - depth
  - actionability
```

## Expected Impact

| Dimension | Before (Flash) | Expected After | Pro (reference) |
|---|---|---|---|
| depth | 7 | 8-9 | 9 |
| actionability | 7 | 8-9 | 9 |
| structure | 8 | 9 | 9 |

The domain profile and anti-pattern guidance are the highest-leverage changes — they address the core "popularity sort" default behavior that's the biggest differentiator between Flash and Pro on this task.

## Validation

After updating the task YAML, re-run:

```bash
python runner.py --task hn-digest --compare --runs 3
python evaluate.py --run-dir results/run-<timestamp>
python report.py --eval results/run-<timestamp>/evaluation.json
```

Target: Flash should close the depth/actionability gap by explicitly following the domain profile, without requiring the inference capability that differentiates Pro.
