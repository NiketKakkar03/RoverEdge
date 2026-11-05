# AGENTS.md refactor audit

## Source and contradictions

The user selected the earlier four behavioral sections as the source and authorized replacing the explanatory article found on disk. No direct contradictions were found, so no conflicting versions required a selection.

The original caution about uncertainty and its allowance for judgment on trivial tasks address different cases. The refactor makes that boundary explicit: ask about ambiguity affecting scope, behavior, or acceptance criteria; use judgment for routine choices within the agreed scope.

## Root essentials

- One-sentence project description from the confirmed specification.
- Scope preservation and handling material ambiguity, applicable across tasks.
- Conditional links to planning, implementation, verification, project decisions, and terminology.

No package manager, build command, or typecheck command is established in the current repository. Proposed technologies are not treated as working commands.

## Removed or consolidated instructions

| Source text | Reason | Treatment |
| --- | --- | --- |
| “Behavioral guidelines to reduce common LLM coding mistakes.” | Introductory description, not an action | Removed |
| “Don't assume. Don't hide confusion. Surface tradeoffs.” | Slogan duplicates the concrete planning rules | Replaced by material-assumption and ambiguity guidance |
| “Minimum code that solves the problem. Nothing speculative.” | Duplicates specific scope and abstraction rules | Consolidated into implementation guidance |
| “If you write 200 lines and it could be 50, rewrite it.” | Arbitrary line count is not a reliable simplification criterion | Replaced by the simpler-approach rule |
| “Would a senior engineer say this is overcomplicated?” | Subjective and not directly checkable | Removed; specific abstraction/configuration rules remain |
| “Touch only what you must. Clean up only your own mess.” | Duplicates the concrete diff and orphan rules | Consolidated into implementation guidance |
| “Define success criteria. Loop until verified.” | Duplicates the concrete acceptance and verification steps | Consolidated into verification guidance |
| “Strong success criteria let you loop independently…” | Explains a benefit rather than directing action | Removed |
| “These guidelines are working if…” | Broad retrospective commentary without a per-task action | Removed |
| Current on-disk article defining AGENTS.md, harnesses, sessions, and context windows | Generic explanatory material; several linked pages do not exist here | Removed under the user's source selection |

Concrete preferences such as preserving unrelated code, cleaning up newly orphaned symbols, and reproducing bugs remain. They were not discarded merely because an agent might already follow them.

## File structure

```text
AGENTS.md
GLOSSARY.md
project.md
docs/
├── agent-guidance/
│   ├── planning.md
│   ├── implementation.md
│   ├── verification.md
│   └── refactor-notes.md
├── design-consensus.md
└── adr/
    └── 0001–0004 existing decision records
```

This audit is for human review and is deliberately not part of the root's task-guidance links. Project requirements remain in project.md; agent workflow rules remain in agent-guidance/.
