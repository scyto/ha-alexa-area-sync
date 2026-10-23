# Alexa Area Sync

Keep your **Alexa groups** in step with your **Home Assistant areas**. There is one Alexa group per
HA area, holding every Alexa-exposed HA device in that area, so "Alexa, turn off the kitchen
lights" matches how HA is organised. Groups are created, updated when an area's devices change or
the area is renamed, and removed when you skip or delete the area.

> Inspired by [neilellis/ha-alexa-room-sync](https://github.com/neilellis/ha-alexa-room-sync), which
> this started as a fork of. The development history (pull requests #1–#23 and their reviews) is in
> the archived [scyto/ha-alexa-room-sync-history](https://github.com/scyto/ha-alexa-room-sync-history).
> See the [Changelog](#changelog).

Nabu Casa / HA Cloud exposes your devices to Alexa but can't create Alexa groups. This fills that
gap through the **unofficial Alexa API**, using the private endpoints the Alexa app and
[Alexa Media Player](https://github.com/alandtse/alexa_media_player) use.

> ⚠️ **This uses an undocumented Amazon API.** Amazon can change it without notice. Keep dry-run on
> until you've looked at a preview, and test one area first.

## Requirements

- Home Assistant. Tested on 2026.10.
- A signed-in Alexa account in either:
  - **Alexa Devices**, Home Assistant's built-in integration (recommended: its login is a normal
    setup screen with a one-time code), or
  - **Alexa Media Player** (HACS).

  This integration borrows that Amazon session and never asks for your password itself. If both
  are signed in to the same account, it uses Alexa Devices.

  > Alexa Devices in HA 2026.10.2 can't sign in since Amazon changed its sign-in pages: setup
  > spins on "Logging in and scanning" ([aioamazondevices#1188](https://github.com/chemelli74/aioamazondevices/issues/1188),
  > fixed in aioamazondevices 16.9.1). Until your HA ships that, use Alexa Media Player.
- Your HA devices **exposed to Alexa through HA Cloud** (Settings > Voice assistants > Expose) and
  discovered in the Alexa app.

## Install

| Step | With My Home Assistant | By hand |
|---|---|---|
| 1. Get it from HACS | [![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=scyto&repository=ha-alexa-area-sync&category=integration) | HACS > ⋮ > **Custom repositories**, add `https://github.com/scyto/ha-alexa-area-sync` as an **Integration** |
| 2. Download | **Download** in HACS, then restart HA | Same |
| 3. Set it up | [![Add Alexa Area Sync to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=alexa_area_sync) | **Settings > Devices & services > Add integration > Alexa Area Sync** |

Then pick your Alexa account. After installing or updating, reload the browser (F5) if menu or
field labels show up blank.

### Upgrading from Alexa Room Sync

Versions before 0.15.0 were called Alexa Room Sync (domain `alexa_room_sync`). Home Assistant sees
the renamed integration as a new one, so:

1. If the old one has *Sync automatically* on, turn it off (Configure > Settings).
2. Update in HACS and restart, then **Add integration > Alexa Area Sync** with the same Alexa
   account. It copies the old integration's settings and its record of the Alexa groups it manages,
   so your existing groups carry on; nothing is recreated.
3. Remove the old **Alexa Room Sync** entry. That doesn't change Alexa.

Its actions are now `alexa_area_sync.*`, and its button, picker and sensor entity ids change, so
update anything of yours that used the old ones.

## Using it

Syncs are read-only until you turn writes on. The only other action that writes is
*Remove the Alexa groups it manages*, which asks you to confirm.

1. On the integration's device page, press **Whole house – Preview**. The summary appears in
   **Last result**, and the device's **Activity** lists, by name, the devices each Alexa group
   would gain or lose.
2. To allow writes, go to **Configure > Settings**, turn **Dry-run** off and tick **I understand
   'apply' will write to my Alexa account**.
3. Try one area first: pick it in **One area** and press **One area – Sync**.
4. Then press **Whole house – Sync** to do the rest. Groups can take a minute or two to show up in the
   Alexa app; pull to refresh or reopen the app.

So that "turn on the lights" works without saying the area name, each Echo needs to be in its
area's group. Either turn on **Put Echos in their area's Alexa group** (it uses the area each Echo
has in Alexa Devices or Alexa Media Player), or add them by hand in the Alexa app. Echos you add by hand are kept.

### Device page

| Control | What it does |
|---|---|
| **One area** | Picks an HA area. Lists only areas that get an Alexa group (something exposed to Alexa, not skipped). Follows renames. |
| **One area – Preview** | Shows what syncing that area would change. Never writes. |
| **One area – Sync** | Syncs only that area's Alexa group. |
| **Whole house – Preview** | Shows what syncing every area would change. Never writes. |
| **Whole house – Sync** | Syncs every area. |
| **Last result** | One-line summary of the last run. Each run also adds an entry to the device's **Activity** listing what changed in each Alexa group, and the latest run's detail is in the sensor's attributes (`scope`, `mode`, `ran_at`, `groups`). |

Both Sync buttons write only when dry-run is off and writes are confirmed; otherwise they preview.
HA lists the controls by name, which keeps the *One area* controls together, followed by
*Whole house*.

**Wording:** an **area** is Home Assistant's; an **Alexa group** is what this creates for it in Alexa.

### What a sync changes

The integration remembers which Alexa groups it created or adopted, and which devices it put in each, keyed by
HA area. A full sync then:

- **creates** a group for an area that doesn't have one;
- **updates** a managed group when the area's devices change or the area is renamed;
- **deletes** a managed group when its area is skipped, deleted, or has no exposed devices left.
  If the group also holds something you added yourself, such as an Echo, the HA devices are taken
  out, your additions stay, and the group is released instead of deleted.

A single-area sync never touches other groups. Groups the integration didn't create are left alone,
with one exception: an Alexa group with exactly the area's name, in an area nothing manages yet, is
adopted. Only Home Assistant devices are matched, plus Echos if you turn that option on. Nothing else is added.

Deleting a group is the one change you'd notice later (Alexa routines that use it break,
and a recreated group is a new one), so removals are deliberate:

- a group is only deleted, or released, if it was already due for removal on a sync at least
  15 minutes earlier; until then Activity says it's *held*;
- if more than three groups would go in one run, or half of those it manages (once it manages
  six or more), it holds all of them, because that looks like a glitch, not a decision;
- it never takes over one of your groups by name just to delete it.

As safety checks, a sync refuses to run if Alexa returns no devices, or no groups while groups are
managed. Without that, a glitch on Amazon's side could look like "everything is gone".

### Removing it

Removing the integration **doesn't change Alexa**. Your groups keep working, and a reinstall picks
them up again by name. Only the integration's saved record of its groups is deleted. Its settings
go too: after re-adding it, dry-run is back on, so turn it off again before syncing.

To take the groups down too, first use **Configure > Remove the Alexa groups it manages**, which asks
you to confirm. It removes the groups it manages, which are the ones it created **plus any it
adopted** (an existing Alexa group with exactly an area's name). It keeps any device it didn't put
there. So an adopted group you made by hand is deleted too if it only held HA devices. Rename such
a group in Alexa before a sync if you want it left alone.

## Options (Configure > Settings)

- **Dry-run** (on by default): syncs never write to Alexa. (*Remove the Alexa groups it
  manages* is separate and has its own confirmation.)
- **I understand 'apply' will write to my Alexa account**: must be ticked for any write.
- **Alexa group name prefix**: for example `HA `, to tell synced groups apart.
- **Include climate entities** (on by default): thermostats go in their area's group.
- **Include child-lock switches** (off by default).
- **Put Echos in their area's Alexa group** (off by default): each Echo that has an HA area joins
  that area's group, matched by serial number. The areas come from whichever integration the
  session comes from (Alexa Devices or Alexa Media Player). Phone apps and speaker groups are
  skipped. Echos placed this way are managed like HA devices: moved when you change their area, and
  removed by *Remove the Alexa groups it manages*.
- **Also make one Alexa group per Home Assistant floor** (off by default): each HA floor
  gets a group holding the HA devices of its synced areas, so "Alexa, turn off the ground
  floor" works. Floors with nothing synced get no group, Echos stay only in their area's
  group, and a floor named the same as an area's group is skipped. Turning this off
  removes the floor groups on the next whole-house sync.
- **Floor groups: lights and light switches only** (on by default): floor groups hold only
  lights and switches, so "Alexa, turn off the ground floor" doesn't also turn off thermostats,
  purifiers or other devices. Turn it off to give floor groups everything their areas have.
- **Ask HA Cloud to resend exposed devices that Alexa has lost** (on by default): every run lists
  devices that are exposed and have an area in HA but that Alexa doesn't know about ("Not in Alexa
  yet"). If one is still missing 10 minutes later, a sync asks HA Cloud to send it to Alexa again,
  at most once an hour. This is the report HA Cloud's own *Sync entities* button sends; it never
  turns exposure off, which would make Alexa delete the device.
- **Sync automatically** (off by default): runs a whole-house sync a minute after you
  change areas, floors, devices or what's exposed to Alexa, and once an hour to catch
  devices Alexa discovers late. It only writes when dry-run is off and the confirmation is
  ticked, and it only adds to Activity when something changed.
- **Areas to skip**: areas that never get an Alexa group from a whole-house sync and don't appear
  in *One area*. If a skipped area already has an Alexa group from this integration, the next
  whole-house sync removes it. The `sync_area` action can still target a skipped area directly.

## Actions (services)

For scripts and automations. With more than one Alexa account set up, pass `config_entry_id`.

| Action | Writes? | Notes |
|---|---|---|
| `alexa_area_sync.preview` | No | Plan and match details. Optional `area_id`. |
| `alexa_area_sync.sync` | With `apply: true` and the confirmation | Full sync. |
| `alexa_area_sync.sync_area` | With `apply: true` and the confirmation | One area. |
| `alexa_area_sync.list_groups` | No | Lists the groups in your Alexa account and the devices in each. |
| `alexa_area_sync.remove_managed_rooms` | With `confirm: true`, whatever the dry-run setting | Removes the groups it created or adopted (keeps devices you added yourself). |
| `alexa_area_sync.dump_appliances`, `probe_endpoints` | No | Diagnostics. `dump_appliances` redacts Amazon ids and Echo serials but keeps device names. |

## How it works

- **Login:** it reuses an already signed-in session, so no credentials live here: the HTTP
  wrapper of Alexa Devices' `aioamazondevices` API, or Alexa Media Player's `AlexaLogin` and
  alexapy's request helper. Both are private to those integrations, so an update to either can
  break this until it's adapted.
- **Devices:** it lists Alexa's smart-home devices with the Alexa app's GraphQL query
  (`POST /nexus/v1/graphql`), falling back to `GET /api/phoenix`. It matches each exposed HA entity
  by the entity_id that HA Cloud embeds in the Alexa device id (`…_light#kitchen_cans`). Otherwise
  it matches by name, where the first alias is what HA sends Alexa as the name.
- **Groups:** `GET /api/phoenix/group` to list, `POST` to create, `PUT /api/phoenix/group/{id}` to
  update (it sends Amazon's own group document back with the name and members changed), and
  `DELETE` to remove.
- **Memory:** the managed groups and their members are kept in HA storage
  (`.storage/alexa_area_sync.<entry>.rooms`).

## Naming tips

Groups take the HA area's name. If two areas sound alike ("Kitchen" and "Kitchenette"), rename one
or use a prefix, otherwise Alexa will ask "which one?". Device names come from HA too: since HA
2026.8 Alexa gets an entity's **first alias**, so put the area-qualified name ("kitchen cans")
first.

## Caveats

- Switches that drive lights are **switches** to Alexa, so "turn off the lights" in a group may skip
  them. Use HA's *Show as light* if you want them included.
- Devices with no HA area can't be placed. Give them an area first.
- **Alexa Media Player login:** if you use AMP and its login fails with "failed to login", restart HA and
  finish the AMP login in the **first** attempt after the restart. This works around an AMP bug
  where a retry reuses the first attempt's login proxy (see
  [alexa_media_player#3559](https://github.com/alandtse/alexa_media_player/issues/3559)).

## Changelog

- **v0.4.0:** devices are listed via GraphQL, matched by HA's `domain#object_id` ids and by alias.
  The original's `/api/phoenix` lookup returns nothing on current accounts.
- **v0.4.1:** `sync` / `sync_area` actually run. They were registered as lambdas HA never awaited.
- **v0.5.0:** *Rooms to skip* area picker.
- **v0.6.0:** full lifecycle (create, update, delete, adopt, keep Echos), plus Preview and Sync
  buttons (results went to a notification until 0.10.2).
- **v0.7.0:** removing the integration leaves Alexa alone; *Remove managed rooms* in Configure;
  per-call account selection; *Last result* sensor.
- **v0.8.0:** *Sync one area* in Configure (moved to the device page in 0.9.0).
- **v0.9.0:** *Area to sync* picker and per-area buttons on the device page; *Last result* and the
  picked area survive restarts.
- **v0.9.1:** *Area to sync* lists only areas that get an Alexa group.
- **v0.9.2:** `dump_appliances` reports the GraphQL and `/api/phoenix` sources separately.
- **v0.9.3:** removing the integration also removes the `probe_endpoints` action.
- **v0.10.0:** clearer names: *One area* / *Whole house* controls, "area" for HA and "Alexa group" for what's created.
- **v0.10.1:** *Last result* keeps each run's per-group outcome as attributes, viewable in History.
- **v0.10.2:** each run's per-group changes are written to the Activity (logbook); the notification is gone.
- **v0.11.0:** optional *Put Echos in their area's Alexa group*, using Alexa Media Player's areas.
- **v0.11.1:** Echos: only the Echo speaker device is added to a group (a tablet's AlexaBridge endpoint made Amazon reject the update).
- **v0.12.0:** Activity and *Last result* name the devices each run added, removed or deleted, not just counts; `list_groups` lists each group's devices.
- **v0.13.0:** optional floor groups and auto-sync; Add to Home Assistant buttons in the README.
- **v0.14.0:** uses Home Assistant's built-in Alexa Devices integration instead of Alexa Media Player.
- **v0.14.1:** Alexa Media Player works again as a fallback; Alexa Devices is used when it's signed in to the account.
- **v0.14.2:** an Echo that Alexa lists in a group by serial counts as already there, so it no longer shows as added on every sync; such entries show as "<Echo> (by serial)".
- **v0.14.3:** floor groups hold only lights and light switches by default; the "Alexa lists unavailable" message is logged once at info level instead of a warning on every start.
- **v0.15.0:** renamed to **Alexa Area Sync** (domain `alexa_area_sync`, was `alexa_room_sync`) so it can't clash with other integrations of the old name. See [Upgrading from Alexa Room Sync](#upgrading-from-alexa-room-sync).
- **v0.15.1:** no "Unable to remove unknown job listener" error when the integration is reloaded or removed with auto-sync on.
- **v0.16.0:** lists exposed devices Alexa doesn't have, and asks HA Cloud to resend them if they stay missing.
- **v0.17.0:** safer removals (held until confirmed on a later sync, capped per run, never on adoption); a sync stops if HA's exposure settings can't be read; the managed-groups record is saved even after an error; the Alexa lists / to-do feature is removed; diagnostics redact Echo serials; actions register once at startup; the README is exact about what writes.
- **v0.18.0:** setup says what's missing: no Alexa login integration, one that isn't signed in (with its state), a session that can't reach Alexa, or HA Cloud / exposure not set up.

## Credits & licence

MIT. Inspired by and originally forked from
[neilellis/ha-alexa-room-sync](https://github.com/neilellis/ha-alexa-room-sync). Relies on Home
Assistant's [Alexa Devices](https://www.home-assistant.io/integrations/alexa_devices) integration /
[aioamazondevices](https://github.com/chemelli74/aioamazondevices) (Apache-2.0), or
[alexa_media_player](https://github.com/alandtse/alexa_media_player) /
[alexapy](https://gitlab.com/keatontaylor/alexapy) (Apache-2.0), for authentication. Endpoint
shapes come from [alexa-remote](https://github.com/Apollon77/alexa-remote) (MIT) and community
reverse-engineering. Not affiliated with or endorsed by Amazon.
