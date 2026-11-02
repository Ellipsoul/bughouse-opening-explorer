"""Routine incremental release checks; no independent full rebuild is required."""
import json
from collections import Counter
from contextlib import closing
from pathlib import Path
import sqlite3

from .incremental import Generation
from .packed import _file_hash
from .publication import validate_artifact
from .snapshot_recovery import audit_snapshot

POLICY = 'incremental-integrity-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reconcile_delta(c, report, directory):
    """Reconcile complete ledgers independently of the change/report counters."""
    parent_count = c.execute("SELECT count(*) FROM old.ledger WHERE outcome!='deleted'").fetchone()[0]
    child_count = c.execute("SELECT count(*) FROM ledger WHERE outcome!='deleted'").fetchone()[0]
    rows = c.execute('''SELECT n.game_key,n.uuid,o.outcome,n.outcome,
        o.replay_fingerprint IS NOT n.replay_fingerprint,o.raw IS NOT n.raw,
        o.source_order IS NOT n.source_order,o.game,n.game
        FROM ledger n LEFT JOIN old.ledger o ON o.uuid=n.uuid
        WHERE (n.outcome!='deleted' AND (o.game_key IS NULL OR o.outcome='deleted' OR n.raw IS NOT o.raw OR n.source_order IS NOT o.source_order))
           OR (n.outcome='deleted' AND o.outcome!='deleted') ORDER BY n.game_key''')
    counts = Counter({k: 0 for k in ('added_uuid','deleted_uuid','existing_changed','existing_topology_changed','existing_outcome_changed','existing_accepted_metadata_changed')})
    counts.update(parent_source_rows=parent_count, target_source_rows=child_count)
    witnessed = 0
    with (directory/'source-changes.jsonl').open() as f:
        for key, uuid, previous, current, replay_changed, raw_changed, order_changed, old_game, new_game in rows:
            line = f.readline()
            require(bool(line), 'missing delta witness')
            witness = json.loads(line)
            category = 'added' if previous is None or previous == 'deleted' else 'deleted' if current == 'deleted' else 'existing'
            topology = (previous == 'accepted' or current == 'accepted') and (previous is None or current == 'deleted' or replay_changed or previous != current)
            require((witness['game_key'],witness['uuid'],witness['category'],witness['old_outcome'],witness['new_outcome'],witness['topology_changed']) == (key,uuid,category,previous,current,bool(topology)), 'delta witness differs from complete ledger comparison')
            if category == 'added':
                counts['added_uuid'] += 1; counts['added_'+current] += 1
            elif category == 'deleted': counts['deleted_uuid'] += 1
            else:
                counts['existing_changed'] += 1
                counts['existing_topology_changed'] += bool(topology)
                counts['existing_outcome_changed'] += previous != current
                if previous == current == 'accepted':
                    before, after = json.loads(old_game), json.loads(new_game)
                    fields = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
                    require(fields == witness['metadata_fields'], 'metadata correction witness mismatch')
                    counts['existing_accepted_metadata_changed'] += bool(fields) and 'move_tokens' not in fields
            witnessed += 1
        require(not f.readline(), 'unexpected extra delta witness')
    require(dict(counts) == report['source_delta'], 'delta counts do not reconcile')
    require(parent_count + counts['added_uuid'] - counts['deleted_uuid'] == child_count, 'source additions/removals do not reconcile')
    require(witnessed == c.execute('SELECT count(*) FROM changes').fetchone()[0], 'change ledger coverage mismatch')
    exclusions = [dict(zip(('uuid','error','unchanged'),r)) for r in c.execute('''SELECT n.uuid,n.error,n.replay_fingerprint=o.replay_fingerprint AND n.error IS o.error FROM ledger n LEFT JOIN old.ledger o ON o.uuid=n.uuid AND o.outcome=n.outcome WHERE n.outcome='position_replay_error' ORDER BY n.uuid''')]
    require(exclusions == report['replay_exclusions'], 'replay exclusions do not reconcile')
    # Verify complete threshold witness coverage against the touched/support tables.
    expected = c.execute('''SELECT t.key,t.old_count,COALESCE(s.count,0),CASE WHEN t.old_count=1 THEN t.old_owner ELSE s.owner_xor END FROM touched t LEFT JOIN support s ON s.key=t.key WHERE (t.old_count=1 AND s.count>=2) OR (t.old_count>=2 AND s.count=1) ORDER BY t.key''')
    threshold = Counter()
    with (directory/'threshold-placements.jsonl').open() as f:
        for key, old, new, owner in expected:
            line=f.readline(); require(bool(line),'missing threshold witness'); w=json.loads(line)
            kind='promotion' if old==1 else 'demotion'
            require((w['position_key'],w['kind'],w['old_count'],w['new_count'],w['singleton_owner']) == (key.hex(),kind,old,new,owner),'threshold witness mismatch')
            threshold[kind+'_placements'] += 1
        require(not f.readline(),'extra threshold witness')
    owners = c.execute("SELECT game_key,reason FROM repairs WHERE reason IN ('promotion','demotion') ORDER BY game_key")
    with (directory/'threshold-games.jsonl').open() as f:
        for key,reason in owners:
            line=f.readline();require(bool(line),'missing owner witness');w=json.loads(line)
            require((w['game_key'],w['reason'])==(key,reason),'owner witness mismatch')
            threshold['repaired_owners'] += 1
            threshold['old_game_frontier_extensions'] += w['extension']
            threshold['newly_reached_true_endings'] += w['new_true_ending']
            threshold['unchanged_frontiers'] += w['old_frontier_and_length']==w['new_frontier_and_length']
        require(not f.readline(),'extra owner witness')
    require(dict(threshold)==report['threshold_delta'],'threshold/owner totals mismatch')
    return {'source_delta':dict(counts),'threshold_delta':dict(threshold),'replay_exclusions':exclusions,'complete_changed_rows':witnessed}


def validate_incremental_release(source, source_sha256, cutoff, parent, child, artifact, delta):
    source, artifact, delta = map(lambda p: Path(p).resolve(), (source, artifact, delta))
    require(_file_hash(source)==source_sha256,'source checksum mismatch')
    with closing(sqlite3.connect(f'{source.as_uri()}?mode=ro&immutable=1',uri=True)) as c:
        require(c.execute('SELECT count(*) FROM games WHERE end_time IS NULL OR end_time>=?',(cutoff,)).fetchone()[0]==0,'source violates exclusive cutoff')
        run=c.execute('SELECT id FROM crawl_runs ORDER BY started_at DESC,id DESC LIMIT 1').fetchone()[0]
    source_audit=audit_snapshot(source,run)
    parent,child=Generation(parent),Generation(child)
    pc,cc=parent.verify_complete(),child.verify_complete()
    require(pc['policy']==cc['policy'],'parent/child policy mismatch; explicit migration required')
    require(cc['source'].startswith(f'sha256:{source_sha256};rowid-mod-1-0;'),'child source identity mismatch')
    report=json.loads((delta/'report.json').read_text())
    require(report['parent']==pc and report['target']==cc,'delta generation identity mismatch')
    with closing(sqlite3.connect(f'{child.path.as_uri()}?mode=ro&immutable=1',uri=True)) as c:
        require(Path(Generation.get(c,'parent')).resolve()==parent.directory,'unexpected parent')
        require(Generation.get(c,'stage')=='complete','checkpoint is incomplete')
        require('verify' in cc['metrics']['timings'],'support/owner verification was not completed')
        c.execute('ATTACH DATABASE ? AS old',(f'{parent.path.as_uri()}?mode=ro&immutable=1',))
        c.execute('ATTACH DATABASE ? AS source',(f'{source.as_uri()}?mode=ro&immutable=1',))
        require(c.execute("SELECT count(*) FROM ledger WHERE outcome!='deleted'").fetchone()[0]==source_audit['games'],'source/ledger count mismatch')
        require(not c.execute("SELECT 1 FROM ledger l LEFT JOIN source.games g ON g.uuid=l.uuid WHERE l.outcome!='deleted' AND (g.uuid IS NULL OR l.source_order IS NOT g.rowid OR json_extract(l.raw,'$.end_time') IS NOT g.end_time) LIMIT 1").fetchone(),'source/ledger identity or date mismatch')
        reconciliation=reconcile_delta(c,report,delta)
        outcomes=dict(c.execute('SELECT outcome,count(*) FROM ledger GROUP BY outcome'))
    validated=validate_artifact(artifact)
    manifest=json.loads((artifact/'manifest.json').read_text())
    require(manifest['source_fingerprint']==cc['source'],'artifact source identity mismatch')
    require(manifest['games']==outcomes.get('accepted',0)==cc['metrics']['accepted'],'exported accepted count mismatch')
    require(manifest['format_version']=='packed-position-graph-v2','candidate must be serving v2')
    return {'policy':POLICY,'source':str(source),'source_sha256':source_sha256,'exclusive_cutoff':cutoff,'source_audit':source_audit,'parent_sha256':pc['sha256'],'child_sha256':cc['sha256'],'durable_completion':True,'support_owner_consistency':'verified by completed generation _verify; checksum and pinned policy revalidated','delta':reconciliation,'outcomes':outcomes,'candidate':str(artifact),'dataset_version':manifest['dataset_version'],'artifact_build_id':validated.build_id,'components':manifest['files'],'assurance_limit':'No independent full rebuild or full-versus-incremental byte comparison. Common-mode incremental/adapter/exporter defects remain possible; regression/recovery and local behavior checks are separate required gates.'}
