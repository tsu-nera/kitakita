import sqlite3
from pathlib import Path

import pytest

import write_cues as wc

SR = 48000


def make_db(path: Path) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        create table track_locations (id integer primary key, location text unique);
        create table library (id integer primary key, samplerate integer, location integer);
        create table cues (id integer primary key autoincrement, track_id integer, type integer default 0,
            position integer default -1, length integer default 0, hotcue integer default -1,
            label text default '', color integer default 4294901760);
        insert into track_locations values (1, '/music/a.mp3');
        insert into library values (10, 48000, 1);
        insert into cues (track_id, type, position, hotcue, label) values (10, 1, 111, 0, 'old');
        insert into cues (track_id, type, position, hotcue, label) values (10, 2, 222, -1, 'main');
        """
    )
    con.commit()
    con.close()
    return path


def test_write_replaces_hotcues_only(tmp_path):
    db = make_db(tmp_path / "m.sqlite")
    con = sqlite3.connect(db)
    wc.write(con, Path("/music/a.mp3"), [(1.5, "intro 1"), (10.25, "drop 5")])
    rows = con.execute("select type, position, hotcue, label from cues where type = 1 order by hotcue").fetchall()
    assert rows == [(1, 1.5 * SR * 2, 0, "intro 1"), (1, 10.25 * SR * 2, 1, "drop 5")]
    assert con.execute("select position, label from cues where type = 2").fetchall() == [(222, "main")]


def test_write_intro_outro_markers_replace_existing(tmp_path):
    db = make_db(tmp_path / "m.sqlite")
    con = sqlite3.connect(db)
    con.execute("insert into cues (track_id, type, position, length) values (10, 6, 702, 0)")
    con.execute("insert into cues (track_id, type, position, length) values (10, 7, -1, 999)")
    wc.write(con, Path("/music/a.mp3"), [(1.0, "drop 5")], {"intro": (0.0, 27.0), "outro": (240.0, 270.0)})
    rows = con.execute("select type, position, length, hotcue from cues where type in (6, 7) order by type").fetchall()
    assert rows == [(6, 0.0, 27.0 * SR * 2, -1), (7, 240.0 * SR * 2, 30.0 * SR * 2, -1)]
    assert con.execute("select position, label from cues where type = 2").fetchall() == [(222, "main")]


def test_write_without_markers_keeps_intro_outro(tmp_path):
    db = make_db(tmp_path / "m.sqlite")
    con = sqlite3.connect(db)
    con.execute("insert into cues (track_id, type, position, length) values (10, 6, 702, 0)")
    wc.write(con, Path("/music/a.mp3"), [(1.0, "drop 5")])
    assert con.execute("select position, length from cues where type = 6").fetchall() == [(702, 0)]


def test_write_unknown_track_is_noop(tmp_path):
    con = sqlite3.connect(make_db(tmp_path / "m.sqlite"))
    wc.write(con, Path("/music/zzz.mp3"), [(1.0, "intro 1")])
    assert con.execute("select count(*) from cues").fetchone() == (2,)


def test_open_db_copy_ok_while_mixxx_running(tmp_path, monkeypatch):
    db = make_db(tmp_path / "copy.sqlite")
    monkeypatch.setattr(wc, "mixxx_running", lambda: True)
    con = wc.open_db(db)
    con.close()
    assert len(list(tmp_path.glob("copy.sqlite.bak-*"))) == 1


def test_open_db_default_refused_while_mixxx_running(tmp_path, monkeypatch):
    db = make_db(tmp_path / "fake-default.sqlite")
    monkeypatch.setattr(wc, "DB", db)
    monkeypatch.setattr(wc, "mixxx_running", lambda: True)
    with pytest.raises(SystemExit):
        wc.open_db(db)
    assert list(tmp_path.glob("*.bak-*")) == []


def test_open_db_default_ok_when_mixxx_closed(tmp_path, monkeypatch):
    db = make_db(tmp_path / "fake-default.sqlite")
    monkeypatch.setattr(wc, "DB", db)
    monkeypatch.setattr(wc, "mixxx_running", lambda: False)
    wc.open_db(db).close()
    assert len(list(tmp_path.glob("*.bak-*"))) == 1
