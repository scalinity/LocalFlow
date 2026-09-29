# Desktop companion — reference fidelity review

Every supplied image is a design reference from another product. None of
them, `current-home.png` included, shows LocalFlow's own interface. The
"before" state is the AppKit Hub, captured from the running code over a
synthetic world. What follows records, for each reference, what the
companion takes from it, what it leaves out, and how close the result is.

The shots named below are regenerated, in both themes and over synthetic
content only, by:

    .venv/bin/python tests/v2/context/run_isolated.py \
        scripts/v2/companion_screens.py --out DIR \
        --script scripts/v2/companion_review_steps.json

Window: 1150 × 715 pt. Each shot is written as `<name>-light.png` and
`<name>-dark.png`.

What is never copied, anywhere: the other product's name, logo, avatar
and character illustrations, app-icon artwork, plan/upgrade/referral and
team-sharing features, and any control for a feature LocalFlow does not
have. The editorial heroes are LocalFlow's own CSS compositions (warm
gradients, no photographs), and their illustrative examples are
clearly synthetic.

## Shell (all references)

- **Adopted:** window and titlebar proportions (52 pt titlebar band with
  the sidebar toggle), a transparent 216 pt sidebar on the warm shell,
  a large inset canvas with a 20 pt radius and a hairline edge, grouped
  nav with a divider above the secondary items, and the sidebar's
  promo-card slot.
- **Adapted:** the promo slot holds a "Hold fn to dictate" card with live
  engine readiness. There is no plan or word allowance to promote.
- **Dark:** warm ink, not an inversion. Shell, canvas, cards and raised
  surfaces step up in lightness, modals and popovers sit on the raised
  surface with a faint warm ring, and the chart ramps are re-stepped
  (not flipped) for the dark surface.

## current-home.png → Home (collapsed sidebar)

- **Adopted:** the icon-rail sidebar, as the collapsed state of the one
  sidebar (the titlebar toggle; the choice persists).
- **Not copied:** the Transform promotion on Home, with its third-party
  app icons. Home keeps to the layout of `home-history.png`, and the
  Transforms page carries the transform hero.
- **Result:** `home-collapsed`. **Mismatch:** none structural.

## home-history.png → Home

- **Adopted:** the sans "Welcome back" title, date-grouped recent
  dictations in one rounded list with the time in a fixed column, and a
  side card with serif stat numbers over a Your Voice panel.
- **Adapted:** the stats are total words, words per minute and today's
  dictations, all as recorded. There is no streak, because LocalFlow
  does not track one. The illustration slot shows LocalFlow's waveform
  mark.
- **Result:** `home`. **Mismatch:** a row shows its actions (Copy, Paste
  again, Details) inline once selected, not as hover icons.

## dictionary-list.png → Dictionary

- **Adopted:** title with Add new, underline tabs with a right-hand icon
  toolbar (search, sort, reload, more), the dismissible serif hero with
  chip examples and an Add new word action, and outlined entry rows with
  edit, delete and pin actions.
- **Adapted:** the tabs are All, Active and Needs approval (LocalFlow's
  own vocabulary states), rows show scope tags, and unapproved rows
  carry Approve.
- **Not copied:** Personal and Shared with team.
- **Result:** `dictionary`. **Mismatch:** none structural.

## dictionary-add-word.png → Dictionary, Add modal

- **Adopted:** a compact modal with "Correct a misspelling" as a switch,
  the heard → correct field pair joined by an arrow, and Cancel beside a
  dark primary.
- **Adapted:** "Where it applies" (the entry's scope) replaces sharing,
  and the primary stays disabled until both fields are filled.
- **Result:** `dictionary-add`. **Mismatch:** the modal is about 10%
  wider than the reference, to fit the scope row.

## insights-usage.png → Insights, Your Usage

- **Adopted:** Your Usage and Your Voice tabs; three stat cards with a
  large number, a tracked caps label, a rule and detail lines; a
  per-app bar card and a daily-activity calendar card below.
- **Adapted:** filters for app, mode and range (7, 30 or 90 days, or all)
  sit on the tab row. The measures are LocalFlow's own: words per
  minute, arrival time after release, dictionary fixes, snippets,
  cleanup fallbacks and words dictated. A measure with no data reads as
  not measured, never zero.
- **Not copied:** the share badge, the gauge percentile (no population to
  rank against), mobile download and streaks.
- **Result:** `insights`. **Mismatch:** the calendar draws only the
  selected range, so 30 days is five columns and leaves the card's
  right side empty. The reference shows about 14 weeks. Drawing weeks
  outside the loaded range would show unloaded days as quiet ones.

## insights-your-voice.png and insights-your-voice-details.png → Insights, Your Voice

- **Adopted:** the progress track with a meta line, a large serif profile
  hero with a caps "Voice profile" label and an illustration slot, then
  two columns of serif phrase and time cards with caps labels.
- **Adapted:** every card is the local ProfileService's deterministic
  measure with its evidence. "Measure again" runs it off the main
  thread. There is no model-written personality text.
- **Not copied:** the character illustration, the share badge and the
  blurred catchphrase cards.
- **Result:** `insights-voice`. **Mismatch:** none structural.

## snippets.png → Snippets

- **Adopted:** title with Add new, underline tabs with a toolbar, and the
  serif hero "The stuff *you* shouldn't have to re-type." with trigger →
  text example pairs and an Add new snippet action.
- **Adapted:** the tabs are All, On and Off, and each row has its own
  enable switch and kind tag.
- **Result:** `snippets`, `snippets-add`. **Mismatch:** none structural.

## transforms-overview.png → Transforms

- **Adopted:** a hero with a serif headline, body, a light primary and a
  "How it works" link, floating circular glyphs on the right, a serif
  "My Transforms" section title with Create new, and three-column cards
  (menu key, title, description) ending with "Create your own".
- **Adapted:** the glyphs are generic line icons, not app logos. The
  header states where transforms live (menu bar → LocalFlow →
  Transforms), because LocalFlow has no global transform hotkey. Cards
  carry origin and "While dictating" tags, with an enable switch at the
  top right.
- **Not copied:** Beta badge, Opt-in switch, the "⌥ O to view changes"
  hint, Reset to defaults.
- **Result:** `transforms-page`. **Mismatch:** the synthetic transforms
  have no menu keys, so cards read "No menu key" where the reference
  shows keycaps.

## transform-onboarding-overview.png, -hotkey.png, -enable.png → Transforms onboarding

- **Adopted:** a large sheet with step pills; step one's serif headline
  with an accent word, and three cards (Original, a tracked-changes
  Polish, and a structured Prompt Engineer).
- **Adapted:** step two shows the real flow (select text, then choose
  from the LocalFlow menu) with a mock editor and the menu. Step three
  shows the review panel and states that Accept replaces the selection
  and the original stays in History. There is no hotkey step and no
  "Turn on Transforms" step, because neither exists in LocalFlow.
- **Result:** `transform-onboarding-1`, `-2`, `-3`. **Mismatch:** none
  structural.

## transform-changes-popover.png → transform review panel (native)

- **Adopted:** a warm-ink panel, a change count at the top left, a
  "Configure …" link at the top right, and the output with each change
  marked inline (struck original, highlighted replacement).
- **Adapted:** it stays the native panel with LocalFlow's own actions
  (Accept, Copy, Retry Original, Apply Another…, Transform Output…, Save
  to Scratchpad). Its behavior, non-activating window and text content
  are unchanged.
- **Result:** rendered from the real panel class over a synthetic
  result. **Mismatch:** the reference uses icon actions; LocalFlow's six
  actions stay labeled buttons.

## scratchpad-account-menu.png → Scratchpad

- **Adopted:** the serif hero "For quick thoughts you want to keep." with
  Start new note, and a Recents list with a search, add and reload
  toolbar.
- **Not copied:** the account menu, since LocalFlow has no accounts.
- **Adapted:** Recents rows show word count and last saved time, and the
  writing view has open-note tabs, a transform picker, versions and
  note actions.
- **Result:** `scratchpad`, `scratchpad-editor`,
  `scratchpad-editor-focused`. **Mismatch:** none structural.

## settings-general.png, settings-system.png, settings-vibe-coding.png → Settings

- **Adopted:** a two-pane modal with a small caps group label, icon nav
  items, a serif section heading, grouped rows in rounded cards, and a
  version footer.
- **Adapted:** the sections are General, Dictation, Appearance (Auto,
  Light, Dark), Data and privacy (training evidence On/Paused/Off, and
  keep-for periods) and Usage analytics. Values set in `config.json`
  are shown with a note that they apply at launch; they get no "Change"
  button, because the page cannot change them.
- **Not copied:** System's launch-at-login, dock and sound switches, all
  of Vibe coding, Account, and Plans and Billing. None of them is a
  LocalFlow setting.
- **Result:** `settings-general`, `settings-privacy`. **Mismatch:** none
  structural.

## Surfaces without a reference

History, Styles, Models (Engines, and Training Data with Evidence,
Review, Splits and Export) and Diagnostics follow the same system:
page title and toolbar, underline tabs or segmented control, outlined
lists, cards with hairlines, and the same modals.
