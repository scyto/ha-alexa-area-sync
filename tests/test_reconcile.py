"""reconcile: what a sync decides to create, update, hold or delete."""

from datetime import datetime, timedelta, timezone

from alexa_area_sync import alexa_client as ac
from alexa_area_sync import sync as s

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)
LIGHT = "SKILL_x_light#{}"


def plan(rooms, groups, **kw):
    ha = {aid for r in rooms for aid in r.matched.values()}
    return s.SyncPlan(rooms=rooms, existing_group_names=[g.name for g in groups],
                      total_exposed=0, total_in_area=0, groups=groups,
                      ha_appliance_ids=ha, **kw)


def room(area, name, *objects):
    return s.PlannedRoom(area, name, matched={f"light.{o}": LIGHT.format(o) for o in objects})


def kinds(actions):
    return {a.room_name: a.kind for a in actions}


def test_creates_missing_group():
    acts = s.reconcile(plan([room("kitchen", "Kitchen", "cans")], []), {}, now=NOW)
    assert kinds(acts) == {"Kitchen": s.CREATE}


def test_never_adopts_a_group_just_to_delete_it():
    yours = ac.AlexaGroup("g1", "Kitchen", [LIGHT.format("cans")])
    acts = s.reconcile(plan([room("kitchen", "Kitchen")], [yours]), {}, now=NOW)
    assert kinds(acts) == {"Kitchen": s.SKIP}


def test_empty_managed_group_is_held_first():
    g = ac.AlexaGroup("g1", "Kitchen", [LIGHT.format("cans")])
    managed = {"kitchen": {"group_id": "g1", "name": "Kitchen", "members": [LIGHT.format("cans")]}}
    acts = s.reconcile(plan([room("kitchen", "Kitchen")], [g]), managed, now=NOW)
    assert acts[0].kind == s.SKIP and acts[0].hold


def test_empty_managed_group_deleted_once_confirmed():
    g = ac.AlexaGroup("g1", "Kitchen", [LIGHT.format("cans")])
    managed = {"kitchen": {"group_id": "g1", "name": "Kitchen",
                           "pending_since": (NOW - timedelta(minutes=20)).isoformat()}}
    acts = s.reconcile(plan([room("kitchen", "Kitchen")], [g]), managed, now=NOW)
    assert acts[0].kind == s.DELETE


def test_not_yet_confirmed_if_too_recent():
    g = ac.AlexaGroup("g1", "Kitchen", [LIGHT.format("cans")])
    managed = {"kitchen": {"group_id": "g1", "name": "Kitchen",
                           "pending_since": (NOW - timedelta(minutes=5)).isoformat()}}
    acts = s.reconcile(plan([room("kitchen", "Kitchen")], [g]), managed, now=NOW)
    assert acts[0].kind == s.SKIP


def test_mass_removal_is_held_even_when_confirmed():
    old = (NOW - timedelta(hours=1)).isoformat()
    groups, managed = [], {}
    for n in range(6):
        groups.append(ac.AlexaGroup(f"g{n}", f"Room {n}", [LIGHT.format(n)]))
        managed[f"a{n}"] = {"group_id": f"g{n}", "name": f"Room {n}", "pending_since": old}
    acts = s.reconcile(plan([], groups), managed, now=NOW)
    assert all(a.kind == s.SKIP and not a.hold for a in acts)


def test_keeps_echo_listed_by_serial():
    echo = "AAA_SonarCloudService_e1"
    by_serial = '{"dsn":"G090ABC","deviceType":"X"}'
    g = ac.AlexaGroup("g1", "Study", [by_serial, LIGHT.format("lamp")])
    r = room("study", "Study", "lamp")
    r.matched["media_player.study_echo"] = echo
    p = plan([r], [g], echo_serials={echo: ("G090ABC",)})
    acts = s.reconcile(p, {"study": {"group_id": "g1", "name": "Study"}}, now=NOW)
    assert kinds(acts) == {"Study": s.UNCHANGED}


def test_device_label_names_serial_entries():
    label = s.device_label('{"dsn":"G090ABC"}', {"dsn:G090ABC": "Study Echo"})
    assert label == "Study Echo (by serial)"
