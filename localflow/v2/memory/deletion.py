"""Purge job-derived memory inside Store's existing deletion transaction."""

import json


def purge_job(db, job_id, now):
    # Older schema fixtures and an upgrade rollback have no memory namespace.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_sources'").fetchone():
        return
    sources = db.execute(
        "SELECT id,content_hash FROM memory_sources WHERE id=? OR "
        "json_extract(data,'$.job_id')=?", (job_id, job_id)).fetchall()
    if not sources:
        return
    records = db.execute(
        'SELECT DISTINCT m.id,m.data FROM memory_records m '
        'JOIN memory_evidence e ON e.memory_id=m.id '
        'JOIN memory_sources s ON s.id=e.source_id '
        "WHERE s.id=? OR json_extract(s.data,'$.job_id')=?",
        (job_id, job_id)).fetchall()
    # Corrections have independent current evidence. Remove their old derived
    # history without discarding the separately maintained current memory.
    changed = db.execute(
        'DELETE FROM memory_revisions WHERE EXISTS ('
        "SELECT 1 FROM json_each(memory_revisions.data,'$.evidence_refs') ref "
        "JOIN memory_sources s ON s.id=json_extract(ref.value,'$.source_id') "
        "WHERE s.id=? OR json_extract(s.data,'$.job_id')=?)",
        (job_id, job_id)).rowcount
    for record_id, raw in records:
        record = json.loads(raw)
        record.update(text='', subject='', key='', status='forgotten', evidence_refs=[],
                      revision=record['revision'] + 1, updated_at=now, retrieval_enabled=False)
        db.execute("UPDATE memory_records SET text='',subject='',predicate='',status='forgotten',"
                   'revision=?,updated_at=?,data=? WHERE id=?',
                   (record['revision'], now, json.dumps(record, ensure_ascii=False,
                    sort_keys=True, separators=(',', ':')), record_id))
        for table in ('memory_fts', 'memory_vectors', 'memory_evidence', 'memory_revisions'):
            db.execute('DELETE FROM ' + table + ' WHERE memory_id=?', (record_id,))
        changed += 1
    for source_id, content_hash in sources:
        db.execute('INSERT OR IGNORE INTO memory_suppressed VALUES(?,?)',
                   (source_id, content_hash))
        changed += db.execute(
            "UPDATE memory_sources SET text='',status='deleted',revision=revision+1,data=? "
            "WHERE id=? AND (status<>'deleted' OR text<>'')",
            (json.dumps({'id': source_id, 'job_id': job_id}, sort_keys=True), source_id)).rowcount
        db.execute('DELETE FROM memory_dirty WHERE source_id=?', (source_id,))
    if changed:
        db.execute("UPDATE memory_state SET value=value+1 WHERE key='revocation'")
