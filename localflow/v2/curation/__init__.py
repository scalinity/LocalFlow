"""Training-evidence curation (V2 M14, Spec S29.7–S29.13).

The package the milestones document proposed as ``v2/training/`` lives
here under ``curation`` — ``localflow/v2/training.py`` is the M02
collector this package curates and never replaces, and a package cannot
shadow it. Modules: ``classify`` (the S29.7 multi-axis classifier and
correction grafts), ``review`` (edit-observation mining and versioned
labels), ``sampling`` (S29.9 queues), ``splits`` (S29.11 families) and
``export`` (S29.13 portable datasets).
"""
