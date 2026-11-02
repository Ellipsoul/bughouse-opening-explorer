"""Reject incomplete or altered delta evidence at the routine release gate."""
from contextlib import closing
from dataclasses import replace
import json
import sqlite3
import pytest
from bughouse_explorer.opening.incremental import Generation, Revision
from bughouse_explorer.opening.incremental_acceptance import reconcile_delta, validate_incremental_release
from bughouse_explorer.opening.packed import _file_hash
from scripts.report_opening_incremental_delta import report
from opening_fixtures import E4,E5,D4,D5,NF3,game

@pytest.fixture
def delta(tmp_path):
    a=game('a',(E4,E5,NF3));b=game('b',(D4,D5,NF3));d=game('d',(E4,E5,D4))
    parent=Generation.create(tmp_path/'parent',source_fingerprint='parent')
    parent.run([Revision.from_game(i,g) for i,g in enumerate([a,b],1)])
    child=Generation.create(tmp_path/'child',source_fingerprint='child',parent=parent)
    child.run([Revision.from_game(i,g) for i,g in enumerate([replace(a,white_username='renamed'),d],1)])
    folder=tmp_path/'delta';data=report(child.directory,folder)
    with closing(sqlite3.connect(f'{child.path.as_uri()}?mode=ro&immutable=1',uri=True)) as c:
        c.execute('ATTACH DATABASE ? AS old',(f'{parent.path.as_uri()}?mode=ro&immutable=1',))
        yield c,data,folder

def test_complete_addition_correction_removal_evidence(delta):
    c,data,folder=delta
    result=reconcile_delta(c,data,folder)
    assert result['source_delta']['added_uuid']==1
    assert result['source_delta']['deleted_uuid']==1
    assert result['source_delta']['existing_changed']==1

@pytest.mark.parametrize('damage',['counter','missing_witness','exclusion'])
def test_rejects_incomplete_or_forged_evidence(delta,damage):
    c,data,folder=delta
    if damage=='counter':data['source_delta']['deleted_uuid']=0
    elif damage=='missing_witness':
        p=folder/'source-changes.jsonl';p.write_text(''.join(p.read_text().splitlines(keepends=True)[1:]))
    else:data['replay_exclusions']=[{'uuid':'invented','error':'bad','unchanged':False}]
    with pytest.raises(ValueError):reconcile_delta(c,data,folder)

def test_cutoff_is_exclusive_and_null_dates_are_rejected(tmp_path):
    source=tmp_path/'source.db'
    with sqlite3.connect(source) as c:
        c.execute('CREATE TABLE games(end_time INTEGER)');c.executemany('INSERT INTO games VALUES (?)',[(1793491200,),(None,)])
    with pytest.raises(ValueError,match='exclusive cutoff'):
        validate_incremental_release(source,_file_hash(source),1793491200,tmp_path/'parent',tmp_path/'child',tmp_path/'artifact',tmp_path/'delta')
