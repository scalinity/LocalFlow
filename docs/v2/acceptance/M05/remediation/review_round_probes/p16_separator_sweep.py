"""Separator sweep between the words of an approved multiword alias.
Contract (AUDIT-01): edge punctuation or ANY Unicode line separator is a
barrier; spaces, tabs and NBSP still match. Every other str.isspace()
character is silently consumed by the rewrite. The information separators
\\x1c-\\x1e are barriers but the UNIT separator \\x1f (same family, also
isspace) is consumed; single-quote/German/CJK quote pairs are not
protected zones (only “”, ", «» are)."""
from _common import *
E = [ent("E-CC", "Claude Code", ["clod code"])]
consumed = []
for cp in range(0x110000):
    ch = chr(cp)
    if ch.isspace() and ch not in " \t\xa0":
        out = run(f"clod{ch}code", E).text
        if out != f"clod{ch}code":
            consumed.append(f"U+{cp:04X}")
print("separators consumed by the alias rewrite:", consumed)
expect("unit separator U+001F behaves like U+001C..U+001E (barrier)", "U+001F" not in consumed, consumed)
for text in ("say ‘ clod code ’ now", "say „ clod code “ now",
             "say 「 clod code 」 now", "say ' clod code ' now",
             'say " clod code " now'):
    out = run(text, E).text
    print(repr(text), "->", repr(out))
done()
