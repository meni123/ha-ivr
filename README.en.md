# IVR — Phone Menu and Voice Assistant for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Tests](https://github.com/meni123/ha-ivr/actions/workflows/validate.yml/badge.svg)](https://github.com/meni123/ha-ivr/actions/workflows/validate.yml)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.11%2B-41BDF5.svg)](https://www.home-assistant.io)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

> **עברית:** [README.md](README.md)

Call your house from any phone. Press a key to turn on a light or
hear the water heater's state — or just **talk** to Home Assistant
in a real conversation. And get voice alerts back: the house calls
you and reads out what happened.

No internet on the phone, no app, no VPN.

---

## What you get, by provider

| | Yemot HaMashiach | Technoline | Direct SIP line | Self-hosted PBX |
|---|:---:|:---:|:---:|:---:|
| **DTMF menu** — a keypress acts and speaks | ✅ | ✅ | ✅ | ✅ |
| **Voice assistant** — free conversation with Assist | ❌ | ✅ | ✅ | ✅ |
| **Voice alerts** — the house dials you | ✅ | ✅ | ✅ | ✅ |

The gap is not missing work — it is what the provider offers. Yemot
has no streaming channel, so there is no way to carry a live
conversation.

**Direct SIP line** is the shortest route: enter the server, username
and password of an ordinary SIP line, and Home Assistant registers to
it itself and answers its calls. No PBX, no external address, and
nothing to configure at the provider. UDP and G.711, no encryption.

**Several providers can run side by side.** Each gets its own card,
with a separate menu tree, token and entities.

---

## What it looks like

**The keypad** is a page in the Home Assistant sidebar that draws a
phone keypad. Each key is what the caller gets when they press it,
and what they hear is shown beside it. The interface is in Hebrew.

<p align="center">
  <img src="docs/panel.png" width="720" alt="The keypad">
</p>

Click an empty key and choose what it does:

<p align="center">
  <img src="docs/panel-add.png" width="720" alt="What happens on a key press">
</p>

**Device** — pick a device and tick what the caller may do with it.
When an action has several values, such as HVAC mode or fan speed, a
second step asks which of them to offer. A key can also set one fixed
value: "AC to 24", "light to 30 percent".

<p align="center">
  <img src="docs/panel-device.png" width="720" alt="Adding a device">
</p>

**Whole room** — one room, several rooms together, a floor or a
label. Choose which kinds of devices, which devices, and what each
kind may do. "Add now" skips the choices and takes everything. Only
actions every device supports are offered, and a device that joins
the room enters the menu by itself.

<p align="center">
  <img src="docs/panel-room-devices.png" width="720" alt="Which devices">
</p>

A key opens on click. Inside it you rename, drag to another key and
remove:

<p align="center">
  <img src="docs/panel-inside.png" width="720" alt="Inside a device key">
</p>

---

## Prerequisites

| Requirement | Detail |
|---|---|
| Home Assistant | 2026.11 or newer |
| External HTTPS address | The provider calls **into** your server. Cloudflare tunnel, Nginx, DuckDNS — any solution. Not needed for a direct SIP line or a self-hosted PBX |
| TLS | Mandatory. The token travels inside the URL |
| A provider account | Yemot HaMashiach or Technoline — or an ordinary SIP line from any provider |
| Voice assistant only | A configured Assist pipeline with speech-to-text and text-to-speech |

---

## Installation — five steps

### Step 1 · Install the integration

**Via HACS (recommended)**

1. In HACS, three-dot menu → `Custom repositories`
2. Paste `https://github.com/meni123/ha-ivr`, category `Integration`, click `Add`
3. Search for `IVR` and install
4. **Restart Home Assistant** — a full restart, not a config reload

**Manually**

Copy the `custom_components/ha_ivr/` directory **in full**, including
`translations/` and `brand/`, into `config/custom_components/`, and
restart.

---

### Step 2 · Configure the reverse proxy

**Needed when the provider calls into your server** — Yemot
HaMashiach and Technoline. Skip it for a direct SIP line or a
self-hosted PBX.

Your server is not directly on the internet but behind a gateway.
Without this, Home Assistant sees the gateway's address instead of
the provider's, **and blocks the provider itself.** The symptom is a
call that drops with no log line at all.

*Settings → System → Network → HTTP server*

Enable **Trust X-Forwarded-For** and add `127.0.0.1` and `::1` to the
proxy list. The two entries are the same local address in two
notations, and both are required. If the gateway runs on another
machine, add its address.

---

### Step 3 · Connect the provider

*Settings → Devices & Services → Add Integration → **IVR***

The first step asks **which provider**. Everything after it shows
only that provider's fields — choosing Yemot will not show
Technoline fields, and will not show a "Voice assistant" screen,
because it has no streaming channel.

| Field | Meaning |
|---|---|
| Provider IP ranges | Who may call in. Defaults to the selected provider's range |
| Allowed phone numbers | Who may call. Optional, **and strongly recommended** |
| Intro sentence | What is heard when entering the menu |
| Credential field | Management token (Yemot) or API key (Technoline) — needed for alerts only |

---

### Step 4 · Configure the extension at the provider

The entry's options screen shows the exact URL to copy. It is the
only place in the UI that displays it:

```
https://<your-address>/api/ha_ivr/<provider>/<token>
```

#### Yemot HaMashiach

An `api` extension, containing:

```ini
type=api
api_link=https://<your-address>/api/ha_ivr/yemot/<token>
api_url_post=yes
api_end_goto=hangup
```

| Field | Why it is needed |
|---|---|
| `api_link` | The URL from the screen. **The token is part of the path** |
| `api_url_post` | Parameters arrive in the request body |
| `api_end_goto` | Covers a response that does not say where to continue. Yemot's default is to go one level back |

#### Technoline

**Two extensions** — one for the menu, one for the voice assistant:

1. **An `api` extension** — paste the URL from the screen. This is the
   menu. Enable **all keys** on it: a restricted list makes the
   exchange swallow any key not on it, and the press never arrives.

2. **A `stream` extension** — for the voice assistant only. Paste the
   `wss` URL from the screen, **and add an `Authorization` header**
   with the value:

   ```
   Bearer <token>
   ```

   The same token as in the URL. **Without this header the connection
   is rejected with 401** and the assistant will not answer.

#### Direct SIP line

**Nothing to configure at the provider.** The server, username and
password the provider gave for the line are entered when adding the
entry, and Home Assistant registers to it itself. Wrong details are
stopped in the form.

Several lines can be added — one entry per account. For an account
that is already registered on a PBX or another phone, create a
separate SIP user: two registrations of one account steal calls from
each other.

---

### Step 5 · Build the menu

**On the keypad** — "תפריט טלפוני" in the sidebar. Click an empty key
and choose what it does, as shown in
[What it looks like](#what-it-looks-like).

**Or on the integration card**, with Home Assistant's own forms.
Alert recipients are added there too:

<p align="center">
  <img src="docs/integration.png" width="720" alt="The integration card">
</p>

| Type | What it does |
|---|---|
| **Device** | One device: its own menu with everything it can do, or one action on the key press |
| **Device group** | Several devices in a place you choose, with exclusions: one item for one kind, a submenu for several kinds |
| **Submenu** | A key that opens another level. Nests up to four levels; moving it moves what is under it |
| **Voice assistant** | A key that connects the caller to the voice assistant |
| **Transfer to extension** | Hands the call to another extension at the provider |
| **Alerts extension** | Reads the caller the alerts that were sent to them |
| **Alert recipient** | A phone number that becomes a `notify` entity. Not part of the menu |

**Its own menu** is built from what the device reports: on, off,
state, a submenu per supported mode, and number entry for values such
as temperature. **One action** is for a key that does one thing, or
for a value of your own ("add milk to the shopping list"). A device
group offers only what every member supports, and membership is
resolved on each call.

The path is the key sequence: `1` is key 1 at the root, `1/2` is key
2 inside key 1's submenu. `*` goes one level back.

**The tree is rebuilt on every call**, so a change in the form
affects the next call — with no restart.

---

## The voice assistant

<p align="center">
  <img src="docs/assistant.png" width="440" alt="Voice assistant settings">
</p>

A WebSocket channel streams two-way audio into the Assist pipeline.
A free conversation over the phone, including device control,
barge-in mid-sentence, and an exit phrase that returns to the menu.

It runs as an `assist_satellite` entity — the same platform Home
Assistant's own VoIP integration uses.

**The pipeline and VAD sensitivity are `select` entities on the
device, not form fields.** This is not a style choice: Home
Assistant reads both from the entity registry, and a value set
anywhere else simply never reaches the pipeline.

**Two lines per entry.** A second concurrent call lands on the
second line; a third is rejected with a tone, rather than a socket
that closes in silence.

---

## Voice alerts

Every recipient is a separate `notify` entity, so an automation
picks people exactly the way it picks any other entity:

```yaml
automation:
  - alias: front_door_alert
    triggers:
      - trigger: state
        entity_id: binary_sensor.front_door
        to: "on"
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.dad
        data:
          message: The front door was opened
```

For a number computed at runtime — from a template, from `person`,
or from anywhere else — `ha_ivr.send_call` takes an explicit list.

Every incoming call also fires the `ha_ivr_call_received` event,
carrying the path, the entity and the caller. An automation can run
on the call itself.

**On Technoline the speech is generated in Home Assistant**, not at
the provider: the outbound call only dials and connects the
recipient to the streaming channel. That is also what works around
their speech engine, which fails on some accounts.

### Alert channels on Yemot — cheaper alerts

An outbound voice call costs a **full unit** on Yemot. Each recipient
card can therefore choose a cheaper channel:

| Channel | Cost | What the recipient gets |
|---|---|---|
| **Voice call** | 1 unit | A call that reads the alert |
| **SMS** | **0.1 unit** | A text message with the alert |
| **Tzintuk** | **0.1 unit** | A short ring, no content |

**SMS is ten times cheaper** and carries the same information — for a
typical home alert that is two agorot instead of twenty. The figures
were measured against Yemot's price list.

### Tzintuk as a full alert system

A tzintuk is ten times cheaper but carries no content. Combined with a
**"recent alerts"** extension it becomes a full system that costs a
tenth of a unit per alert:

1. A sensor fires → a **tzintuk** goes to the recipient (0.1 unit)
2. The recipient sees a missed call and dials **into** the system
3. On entering the menu they hear *"you have a new alert"*
4. They press the "recent alerts" extension and hear what happened

The content is delivered on an **inbound** call, so the outbound charge
is avoided. **Each caller hears only the alerts sent to them** — by
their number, so two people's alerts never mix.

The "recent alerts" extension is added from the `+` button on the
integration card, just like a menu item. Every alert sent — on any
channel — is logged and read back there.

---

## Security

**This integration opens an internet-facing endpoint that can
physically control your home, including blinds and locks.** Read
this section before enabling it.

### What is built in

- Filtering by the real connection address, resistant to header spoofing
- A strong random token, compared in constant time against timing attacks
- `Bearer` authentication required on the streaming channel —
  configured on the extension for Technoline
- The token identifies the **entry** — a request for one provider is never resolved against another's token
- An action allow-list, checked before any other stage
- Caller-number filtering — the strongest layer available
- A line cap and a call-length cap, as a ceiling against abuse
- Secrets redacted in the log, the history buffer and the diagnostics file

### The token is a password

It is embedded in the URL configured at the provider. **Never publish
it** — not in forums, support groups, screenshots or bug reports. On
any suspicion of a leak, replace the token in the options screen and
update it at the provider.

### Risks worth knowing

| Risk | Recommendation |
|---|---|
| Control of locks and gates | Fill in the allowed phone numbers field |
| **Telephony costs** | Every inbound and outbound call costs money at the provider |
| **Voice assistant costs** | Every call consumes speech-to-text, a language model and text-to-speech — usually billed per use |
| A leaked token | Whoever holds it can open calls and burn budget, without touching the house |
| Disabling address filtering | For diagnosis only, and briefly |
| Running without TLS | The token travels in clear text |
| An over-broad proxy list | List only the gateways you run yourself |

### Enabling automatic banning

A built-in Home Assistant mechanism, off by default:

```yaml
http:
  ip_ban_enabled: true
  login_attempts_threshold: 10
```

Note that repeatedly mistyping your own password may lock you out.
Recovery requires editing the ban file and restarting.

---

## Troubleshooting

**A request that arrived always produces a log line, even when it is
rejected.** So a completely empty log means the request **never
arrived** — the problem is at the provider or in the URL, not here.

| Symptom | Likely cause |
|---|---|
| Call drops immediately, **zero log lines** | The URL at the provider is wrong or from an older version |
| `Blocked a request from…` in the log | The reverse proxy setup (step 2) is missing, or the range is wrong |
| `Bad token` / `401` in the log | The token in the provider's URL does not match. Copy it again |
| `503 Not configured` in the log | No entry is configured for that provider |
| An undefined key gives total silence | The exchange restricts which keys are forwarded. Allow all of them |
| The UI shows English | The `translations` directory was not copied, or a full restart is needed |
| The voice assistant does not answer | On Technoline: the `stream` extension is missing, or its `Authorization` header is not set |
| Alerts fail | Check your unit balance at the provider — that is the common cause |

For detailed diagnosis:

```yaml
logger:
  logs:
    custom_components.ha_ivr: debug
```

The integration card also offers **Download diagnostics** — a single
file with the configuration (without secrets), the menu tree as it
is actually built, and the last exchanges with the provider. That is
what to attach to a bug report.

---

## Known limitations

This project was built against measurement on real calls, not
against documentation. Anything unverified is marked as such, here
and in `CHANGELOG.md`:

- **Fields 7–10 of Yemot's `read`** — the mapping is unconfirmed, and
  the code deliberately does not guess it
- **VAD sometimes misses the start of speech** — investigated, not solved

---

## Disclaimer

**This software is provided as is, without warranty of any kind. Use
of it is entirely and solely at the user's own risk.**

The developer bears no liability whatsoever, direct or indirect, for
any damage, loss, breach, unauthorised access, malfunction, incorrect
operation of devices, monetary charge, or any other consequence
arising from installing this software, using it, or being unable to
use it.

In particular, and without limiting the above:

- This software opens an internet-facing endpoint that controls
  physical devices. **Assessing that risk and deciding to install is
  the user's responsibility alone**
- The security measures are intended to reduce risk, and do not
  guarantee absolute protection against unauthorised access
- Integration with locks, gates or alarm systems is done at the
  user's own risk alone
- **All costs are the user's responsibility** — inbound and outbound
  calls at the telephony provider, as well as speech-to-text, language
  model and text-to-speech usage in the voice assistant, which are
  typically billed per use
- The user is responsible for securing their server, keeping the
  token secret, and configuring their gateway
- **This is not an official Home Assistant product**, is not
  developed, supported or endorsed by the Open Home Foundation or
  Nabu Casa, and the developer is not affiliated with them. It is a
  third-party custom integration
- **This is not an official product of Yemot HaMashiach or
  Technoline**, is not supported or endorsed by them, and the
  developer is not affiliated with either of them
- The user is responsible for complying with their chosen provider's
  terms of service

**Installing and using this software constitutes full agreement to
these terms.**

---

## Development

```bash
python3 tests/run_live.py     # 350 checks, without Home Assistant
python3 tests/check_names.py  # a name used before it is defined
python3 tests/check_flow.py   # use before assignment
python3 tests/check_gate.py   # every exit path reopens the input gate
```

The tests import the real modules against a fake Home Assistant, so a
changed signature or a missing import fails here rather than on a
call. Some of them enforce architectural rules: the core may not name
a provider, every user-facing error carries a translation key, and no
real phone number or personal path enters the tree.

**Adding a provider** is a new module under `providers/` and one line
in `PROVIDERS`. A test fails if anything more than that is needed.

---

## Predecessor

This project succeeds [`ha-yemot`](https://github.com/meni123/ha-yemot),
which supported Yemot alone. Both can be installed side by side —
just not on the same extension.

## License

[MIT](LICENSE), including its standard warranty disclaimer.
