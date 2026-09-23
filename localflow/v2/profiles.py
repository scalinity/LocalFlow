"""Destination styles and explicit writing modes (V2 M10, Spec S15).

Pure, deterministic, model-free domain: the style ``StyleRule`` rows a
user configures, the destination→category derivation, and the frozen
resolution that turns (per-job override, rules, destination) into one
immutable ``WritingProfile``.

Resolution contract (S15 / contracts/profiles.md):

    per-job override → explicit destination rule (workspace > site >
    app) → category default → global default

Modes constrain **what may change**; styles specify how authorized
content is represented. A style rule can never expand the S13 cleanup
contract's permitted edits — ``raw`` (no normalization, no cleanup) is
the only narrowing the mode system performs on the live pipeline; the
remaining S15 modes (polish/concise/prompt_engineer/custom) are
transform-backed and resolve honestly as not-yet-executable with a
fallback to Clean until M11 ships their executors. Nothing here invents
a tone control or an automatic personality switch (S15).
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Optional

SCHEMA_VERSION = 1

# The six S15 writing modes. Only raw/clean have live executors on the
# M10 pipeline; the transform-backed modes resolve with an honest
# fallback rather than silently behaving like something else.
MODES = ("raw", "clean", "polish", "concise", "prompt_engineer",
         "custom")
EXECUTABLE_MODES = ("raw", "clean")

# S15 destination categories (the writing categories, finer than the
# M06 app categories): personal/work messaging share the messaging
# structure hints; ai_prompt covers AI prompt fields.
CATEGORIES = ("personal_messaging", "work_messaging", "messaging",
              "email", "documents", "ai_prompt", "coding", "terminal")

# Number policy per destination ("inherit" = the global config value).
NUMBER_POLICIES = ("inherit", "technical", "standard")

# Rule scopes. Destination-rule precedence within one job mirrors the
# M05 vocabulary discipline: the narrower context wins.
RULE_SCOPES = ("global", "category", "app", "site", "workspace")
SCOPE_PRECEDENCE = {
    "global": 0, "category": 1, "app": 2, "site": 3, "workspace": 4,
}

# Personal vs work messaging split by bundle (the M06 messaging class
# carries both; S15 names them separately).
PERSONAL_MESSAGING_BUNDLES = frozenset({"com.apple.iChat"})
WORK_MESSAGING_BUNDLES = frozenset({"com.tinyspeck.slackmacgap"})

# Browser origins that are AI prompt fields (scheme://netloc exactly as
# the M06 site provider records them — query/fragment already stripped).
AI_PROMPT_ORIGINS = frozenset({
    "https://claude.ai",
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://gemini.google.com",
    "https://copilot.microsoft.com",
    "https://perplexity.ai",
    "https://grok.com",
})


def hint_key(category: Optional[str]) -> Optional[str]:
    """The M07 structure-hints key for a writing category (messaging
    classes share one hint set; every other category maps to itself)."""
    if category in ("personal_messaging", "work_messaging", "messaging"):
        return "messaging"
    return category


def derive_category(target_category: Optional[str],
                    app_bundle: Optional[str],
                    site_origin: Optional[str] = None) -> Optional[str]:
    """Destination → S15 writing category. ``None`` means uncategorized
    (the global default applies); nothing is guessed — a browser field
    that is not a known AI prompt origin is not forced into a category."""
    if target_category == "mail":
        return "email"
    if target_category == "messaging":
        if app_bundle in PERSONAL_MESSAGING_BUNDLES:
            return "personal_messaging"
        if app_bundle in WORK_MESSAGING_BUNDLES:
            return "work_messaging"
        return "messaging"
    if target_category == "editor":
        return "documents"
    if target_category == "ide":
        return "coding"
    if target_category == "terminal":
        return "terminal"
    if target_category == "browser" and site_origin in AI_PROMPT_ORIGINS:
        return "ai_prompt"
    return None


@dataclasses.dataclass(frozen=True)
class StyleRule:
    """One configured style rule (persisted by ``profiles_store``)."""

    rule_id: str
    name: str
    scope_kind: str = "global"        # RULE_SCOPES
    scope_value: Optional[str] = None  # category / bundle / origin /
                                       # workspace the rule targets
    mode: str = "clean"               # MODES
    number_policy: str = "inherit"    # NUMBER_POLICIES
    profile_name: Optional[str] = None  # writing-profile identity for
                                        # profile-scoped vocabulary; None
                                        # = the derived category name
    enabled: bool = True
    revision: int = 1

    def __post_init__(self):
        if self.scope_kind not in RULE_SCOPES:
            raise ValueError(f"unknown rule scope: {self.scope_kind}")
        if self.scope_kind != "global" and not self.scope_value:
            raise ValueError(
                f"scope {self.scope_kind} requires a scope value")
        if self.scope_kind == "category" \
                and self.scope_value not in CATEGORIES:
            raise ValueError(
                f"unknown category: {self.scope_value}")
        if self.mode not in MODES:
            raise ValueError(f"unknown mode: {self.mode}")
        if self.number_policy not in NUMBER_POLICIES:
            raise ValueError(
                f"unknown number policy: {self.number_policy}")
        if not self.name or not self.name.strip():
            raise ValueError("rule name must not be empty")

    def to_json(self) -> dict:
        return {
            "rule_id": self.rule_id, "name": self.name,
            "scope": [self.scope_kind, self.scope_value],
            "mode": self.mode, "number_policy": self.number_policy,
            "profile_name": self.profile_name, "enabled": self.enabled,
            "revision": self.revision,
        }

def rules_revision(rules) -> str:
    """Content hash over a frozen rule set (an edited rule can never
    share a revision id with the old state)."""
    payload = json.dumps(
        {"rules": sorted((r.to_json() for r in rules),
                         key=lambda d: d["rule_id"])},
        sort_keys=True, ensure_ascii=False)
    return f"m10:{hashlib.sha256(payload.encode()).hexdigest()[:12]}"


@dataclasses.dataclass(frozen=True)
class Destination:
    """What the resolution matches against (the M06 snapshot fields)."""

    app_bundle: Optional[str] = None
    site_origin: Optional[str] = None
    workspace: Optional[str] = None
    category: Optional[str] = None   # the DERIVED writing category


@dataclasses.dataclass(frozen=True)
class WritingProfile:
    """The immutable effective profile one job runs under."""

    mode: str                        # the requested S15 mode
    effective_mode: str              # what actually executes (raw/clean)
    source: str                      # job_override | rule:<kind> |
                                     # category_default | global_default
    rule_id: Optional[str] = None
    category: Optional[str] = None
    profile_name: Optional[str] = None
    number_policy: str = "inherit"   # the winning rule's policy
    style_revision: Optional[str] = None
    fallback_reason: Optional[str] = None   # non-executable mode etc.

    @property
    def executable(self) -> bool:
        return self.fallback_reason is None

    def to_json(self) -> dict:
        return {
            "mode": self.mode, "effective_mode": self.effective_mode,
            "source": self.source, "rule_id": self.rule_id,
            "category": self.category,
            "profile_name": self.profile_name,
            "number_policy": self.number_policy,
            "style_revision": self.style_revision,
            "fallback_reason": self.fallback_reason,
        }


def _rule_matches(rule: StyleRule, dest: Destination) -> bool:
    if not rule.enabled:
        return False
    if rule.scope_kind == "global":
        return True
    if rule.scope_kind == "category":
        return dest.category == rule.scope_value
    have = {"app": dest.app_bundle, "site": dest.site_origin,
            "workspace": dest.workspace}[rule.scope_kind]
    return have is not None and have == rule.scope_value


def resolve(job_override: Optional[str], rules, dest: Destination,
            *, default_number_policy: str = "inherit") -> WritingProfile:
    """Resolve the effective writing profile (S15 precedence):

    per-job override → explicit destination rule (workspace > site >
    app) → category default (a category-scoped rule for the derived
    category, else the built-in Clean) → global default (a global
    rule, else Clean).

    Clean is the default everywhere: with no override and no matching
    rule the pipeline behaves exactly as shipped in M03–M09. A
    requested mode without a live executor falls back to Clean with the
    honest ``fallback_reason`` — never a silent behavior change."""
    revision = rules_revision(rules)
    dest_category = dest.category
    override = job_override if job_override in MODES else None
    if override is not None:
        return _finish(override, "job_override", None, dest_category,
                       revision, default_number_policy)
    # Explicit destination rules, narrowest scope first; ties break by
    # rule id so resolution is deterministic. Global/category rules are
    # NOT destination rules — they configure the default steps below.
    explicit = [r for r in rules
                if r.enabled and r.scope_kind in ("app", "site",
                                                  "workspace")]
    matching = sorted(
        (r for r in explicit if _rule_matches(r, dest)),
        key=lambda r: (-SCOPE_PRECEDENCE[r.scope_kind], r.rule_id))
    if matching:
        rule = matching[0]
        return _finish(rule.mode, f"rule:{rule.scope_kind}",
                       rule.rule_id, dest_category, revision,
                       rule.number_policy, rule.profile_name)
    # Category default: a category-scoped rule for this category, else
    # the built-in Clean (S15's table).
    cat_rules = sorted(
        (r for r in rules if r.enabled and r.scope_kind == "category"
         and dest_category is not None
         and r.scope_value == dest_category),
        key=lambda r: r.rule_id)
    if cat_rules:
        rule = cat_rules[0]
        return _finish(rule.mode, "rule:category", rule.rule_id,
                       dest_category, revision, rule.number_policy,
                       rule.profile_name)
    if dest_category is not None:
        return _finish("clean", "category_default", None, dest_category,
                       revision, default_number_policy)
    # Global default: a global rule, else Clean.
    glob = sorted((r for r in rules
                   if r.enabled and r.scope_kind == "global"),
                  key=lambda r: r.rule_id)
    if glob:
        rule = glob[0]
        return _finish(rule.mode, "rule:global", rule.rule_id,
                       dest_category, revision, rule.number_policy,
                       rule.profile_name)
    return _finish("clean", "global_default", None, dest_category,
                   revision, default_number_policy)


def _finish(mode: str, source: str, rule_id, category, revision,
            number_policy: str, profile_name=None) -> WritingProfile:
    effective = mode if mode in EXECUTABLE_MODES else "clean"
    fallback = None if effective == mode else \
        f"mode_not_executable_until_M11:{mode}"
    return WritingProfile(
        mode=mode, effective_mode=effective, source=source,
        rule_id=rule_id, category=category,
        profile_name=profile_name or category, number_policy=number_policy,
        style_revision=revision, fallback_reason=fallback)
