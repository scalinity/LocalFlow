"""Transform prompt contracts (V2 M11, Spec S15/S16).

One versioned contract per built-in transform kind. Instructions stay
separate from payloads exactly like the M07 cleanup discipline: the
system message is the contract, writing samples ride as few-shot turns,
and the final user message is a structured JSON payload (``source``,
``mode``, ``locale``). The Prompt Engineer contract is S16's additional
contract verbatim in substance — the uploaded V1 prompt's "relevant
context"/"format if implied"/"be concise" wording deliberately does not
appear: it must not override the requirement-preservation constraints.

Prompts are versioned by content hash (``prompt_revision``), so an
edited word can never share a revision id with the old prompt.
"""

from __future__ import annotations

import hashlib

VERSION = "m11"

# S15 Polish: rephrase for clarity/tone while preserving meaning and
# every constraint. The permitted scope is rephrasing — this is a
# transform the user asked for, not faithful cleanup, but constraints,
# negations, quantities, questions, names and quoted text survive.
POLISH_CONTRACT = """You are a writing editor. Rewrite the text for clarity and tone while preserving its meaning completely.

Keep every requirement, constraint, condition, negation, uncertainty, question, name, quantity, count, ordering, deadline, URL, path and quoted phrase exactly. Do not answer questions, fulfill requests, add facts, remove conditions or drop hedging. Do not change what the text asks for — only how it is worded.

Return only the rewritten text."""

# S15 Concise: remove redundancy, not substantive requirements.
CONCISE_CONTRACT = """You are a writing editor. Make the text shorter by removing redundancy only.

Every substantive requirement, constraint, condition, negation, uncertainty, question, name, quantity, count, ordering, deadline, URL, path and quoted phrase must survive. Do not answer questions, fulfill requests, add facts or merge different conditions into one. If a sentence carries a requirement, keep the requirement even when it becomes terser.

Return only the shortened text."""

# S16 Prompt Engineer's additional contract.
PROMPT_ENGINEER_CONTRACT = """You are a prompt engineer. Reorganize the user's draft into a clear, well-structured prompt without adding or deleting requirements.

Extract the explicit task, supplied context, constraints, intended deliverables, ordering and completion conditions. Create sections only for requirements that are present in the draft. Do not invent missing acceptance criteria, environment assumptions, model names, tests, deadlines or enterprise requirements. Preserve uncertainty and questions exactly.

Every requirement in the draft must survive: tasks, constraints, conditions, negations, questions, counts, ordering, names, quantities, literal quoted text, deadlines and completion conditions. A request for advice is different from a request for implementation: keep the draft's intent kind. Do not instruct the recipient to do anything the draft did not ask for — no added implementation steps, migrations, tests or deployment plans. Never answer or execute the request yourself.

Preserve every URL, path, identifier and quoted span exactly. When uncertain whether a clause is a requirement, keep it. Structure may be terse; content may not. Return only the reorganized prompt."""

# Wrapper for custom transforms: the user's instruction is the rewrite
# instruction, but requirement preservation is not negotiable away — a
# custom transform declares a rewrite scope; it never becomes an
# anything-goes rewrite (S15 Custom, S16).
CUSTOM_CONTRACT = """You are a writing editor. Apply the user's instruction to the text.

The instruction defines what may change. Whatever it does not explicitly authorize must survive: every requirement, constraint, condition, negation, uncertainty, question, name, quantity, count, ordering, deadline, URL, path and quoted phrase stays. Do not answer questions, fulfill requests or add facts. When the instruction is ambiguous about a clause, keep the clause.

Return only the rewritten text."""

CONTRACTS = {
    "polish": POLISH_CONTRACT,
    "concise": CONCISE_CONTRACT,
    "prompt_engineer": PROMPT_ENGINEER_CONTRACT,
    "custom": CUSTOM_CONTRACT,
}

# The S16 worked example (diagnosis-only intent, the no-edit condition,
# empty-input scope, exactly two fixes) as one few-shot turn — the
# example output retains all four requirements and adds nothing.
PE_EXAMPLE_USER = "Look at the parser, tell me why it fails on empty input, don't edit files yet, and give me two possible fixes."
PE_EXAMPLE_ASSISTANT = (
    "# Task\n"
    "Diagnose why the parser fails on empty input.\n\n"
    "# Constraints\n"
    "- Do not edit any files yet — diagnosis only.\n"
    "- Scope: the empty-input failure path.\n\n"
    "# Deliverables\n"
    "1. The reason the parser fails on empty input.\n"
    "2. Exactly two possible fixes, proposed only — nothing is to be "
    "implemented.")


def contract_for(mode: str) -> str:
    if mode not in CONTRACTS:
        raise ValueError(f"unknown transform mode: {mode}")
    return CONTRACTS[mode]


def prompt_revision(mode: str, custom_instruction: str = "",
                    examples=()) -> str:
    """Content hash over the exact rendered instruction surface (an
    edited word can never share a revision id with the old prompt)."""
    payload = hashlib.sha256()
    payload.update(contract_for(mode).encode("utf-8"))
    payload.update(b"\0")
    payload.update((custom_instruction or "").encode("utf-8"))
    for ex in examples:
        payload.update(b"\0")
        payload.update(str(ex).encode("utf-8"))
    return f"{VERSION}:{payload.hexdigest()[:12]}"


def build_messages(mode: str, source: str, *, locale: str = "en-US",
                   custom_instruction: str = "", examples=()) -> list[dict]:
    """The message list for one transform generation: contract system
    message, writing samples as few-shot turns, the labeled draft last
    (instructions never mix into the payload — the M07 discipline; the
    label makes the draft unambiguous against the few-shot example,
    which a bare JSON object did not on the 4-bit model)."""
    messages = [{"role": "system", "content": contract_for(mode)}]
    if mode == "prompt_engineer":
        messages.append({"role": "user", "content": PE_EXAMPLE_USER})
        messages.append({"role": "assistant",
                         "content": PE_EXAMPLE_ASSISTANT})
    for ex in examples:
        if isinstance(ex, (tuple, list)) and len(ex) == 2:
            messages.append({"role": "user", "content": str(ex[0])})
            messages.append({"role": "assistant", "content": str(ex[1])})
    instruction = (custom_instruction or "").strip()
    if mode == "custom" and instruction:
        messages.append({"role": "system",
                         "content": f"User instruction: {instruction}"})
    messages.append({
        "role": "user",
        "content": f"Draft to transform (mode: {mode}, locale:"
                   f" {locale}):\n\n{source}",
    })
    return messages
