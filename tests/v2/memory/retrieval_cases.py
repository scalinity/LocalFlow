"""Synthetic calibration set: each query names one relevant scoped record.

No private transcripts or external material. Queries deliberately include
paraphrases with little lexical overlap; every other record is irrelevant.
"""

CASES = [
    ('brevity', 'I prefer concise answers with no unnecessary explanation.', 'Keep the response brief and to the point.'),
    ('audio', 'The voice assistant records microphone samples at 16000 Hz.', 'What sampling rate does speech capture require?'),
    ('writer', 'Database mutations pass through one serialized SQLite writer.', 'How are concurrent persistence changes ordered?'),
    ('keyboard', 'The review consumes the complete Return key press including repeats and release.', 'Prevent a held enter key from leaking into the editor.'),
    ('native', 'The desktop application uses Python and AppKit for native windows.', 'Which technology creates the Mac interface?'),
    ('frontend', 'The settings interface is built using Svelte in a WKWebView.', 'Describe the web user interface framework.'),
    ('docs', 'Project documentation describes the current design without obsolete alternatives.', 'How should architecture notes present superseded approaches?'),
    ('tests', 'Unit tests use Python unittest and synthetic examples.', 'Choose a testing framework and safe fixture data.'),
    ('telemetry', 'The personal tool does not collect analytics or send telemetry.', 'Can usage tracking be transmitted to a remote service?'),
    ('roots', 'Only explicitly approved project folders may supply document excerpts.', 'Limit filesystem context to directories selected for this workspace.'),
    ('offline', 'Local lexical search remains useful without an internet connection.', 'What works when the network is unavailable?'),
    ('semantic', 'Sentence embeddings retrieve memories when the wording changes.', 'Find related meaning even when exact keywords differ.'),
    ('language', 'Preserve the original language unless translation is requested.', 'Should a Spanish prompt be converted to English automatically?'),
    ('numbers', 'Identifiers, paths, and numerical quantities must remain exact.', 'Keep literal values and file locations unchanged.'),
    ('cancel', 'Cancelled generation jobs cannot publish a late result.', 'Stop an abandoned request from replacing the active draft.'),
    ('budget', 'Authoring jobs stop when their configured spending limit is reached.', 'Bound the money consumed by repeated model calls.'),
    ('backup', 'A database backup is created before upgrading its schema.', 'How can stored data be recovered if a migration fails?'),
    ('capture', 'Read only the selected region rather than the entire browser conversation.', 'Avoid collecting surrounding chat messages during acquisition.'),
    ('terminal', 'Terminal editing uses the shell logical input buffer.', 'Where should command line text replacement obtain the actual draft?'),
    ('submit', 'Applying edited text never submits a message or executes a command.', 'Pasting the accepted result must not start the task.'),
    ('theme', 'The interface supports light and dark appearances.', 'Adapt colors for bright and dim display settings.'),
    ('clipboard', 'Clipboard restoration occurs only while ownership still belongs to the application.', 'Avoid overwriting something copied by the person during a paste.'),
    ('conflict', 'Contradictory project facts are shown together and excluded from retrieval.', 'Do not silently choose between disagreeing evidence.'),
    ('fresh', 'Volatile repository state expires sooner than durable writing preferences.', 'Treat current branch information as more perishable than communication style.'),
    ('scope', 'A selected project has a stable identity independent of its directory basename.', 'Two folders with the same name must remain separate workspaces.'),
    ('revisions', 'Every manual edit creates a new canonical prompt revision.', 'Preserve hand changes in version history.'),
    ('authorship', 'Generated text is never accepted as evidence of personal facts.', 'Prevent the assistant from learning its own inventions.'),
    ('secrets', 'Credential files and private keys are excluded from context imports.', 'Keep authentication material out of retrieved notes.'),
    ('forget', 'Forgetting removes a memory from indexes and revokes pending publications.', 'Erase a remembered item even while a response is being generated.'),
    ('learning', 'Automatic memory learning starts disabled and can be paused separately from use.', 'Can existing preferences remain available while observation is turned off?'),
    ('undo', 'Undo restores only the unchanged region that the application previously replaced.', 'Recover an accepted edit without damaging subsequent typing.'),
    ('model', 'Saved model choices are validated against the supported provider registry.', 'Handle an unavailable generation configuration explicitly.'),
    ('source', 'Every factual addition cites a supplied evidence identifier and revision.', 'Trace personalized details back to the exact approved observation.'),
    ('pin', 'A short project brief can be pinned as selected context.', 'Keep the workspace overview available during retrieval.'),
    ('security', 'Secure password fields cannot be read by capture adapters.', 'Do not acquire text from a protected credential input.'),
    ('scopeonly', 'Current explicit instructions override remembered defaults.', 'An immediate request wins over a stored preference.'),
]
