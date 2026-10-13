# Architecture

## Big picture

Stock webOS centers on the Home app: HOME opens it, backing out of apps
lands on it, and its tiles launch inputs. This setup removes Home from the
loop:

1. **Home is hidden at boot** (`48-nohome` bind-mounts an empty dir over
   `/usr/palm/applications/com.webos.app.home` plus its six sandboxed views).
   Nothing is deleted; removing the hook and rebooting restores it.
2. **The bar replaces Home's jobs.** `com.lukemulvaney.bar` is a transparent
   overlay (`transparent: true`, `defaultWindowType: overlay`) that draws a
   bottom tile row over live video without disturbing it.
3. **The watcher (`watch.py`) owns the remote buttons and recovery.**
   It passively reads `/dev/input/event*` (evdev gives every open fd its own
   queue, so reading never steals keys) and reacts to HOME/GREEN, tracks the
   foreground app, bounces stranded screens back to video, kills stray Home
   renderers, and guards the server patches.
4. **tvweb does the privileged work.** The bar is an unprivileged web page, so
   input switching goes through the tvweb HTTP API on `127.0.0.1:8080`, which
   runs as root. Two small patches make it CEC-safe (below).

## The CEC problem and the uniqueId fix

Launching an input bare
(`applicationManager/launch {"id":"com.webos.app.hdmi4"}`) shows video but
leaves CEC dead: the input app never learns the CEC device id, so remote keys
stay local (OK just pops the input banner). The stock picker launches with
`params {"id":"uniqueId","value":"<n>"}`, which drives the full handshake
(SelectDevice → RoutingChange → SetStreamPath → Focus, visible in
`/var/log/cecmessages`).

`server-patches/controls.js` (`launchInputWithCec`) reproduces the picker:
resolve the id from the launch-point table first, fall back to eim's live
device list (`getAllInputStatus` subList/lastUniqueId), launch with params.
`server-patches/routes.js` adds `GET /api/launchpoints`, exposing the
launcher's own tile order, titles, card colors, and the removable flag. `boot-input.py` is the
same resolution as a standalone script for boot, when tvweb isn't up yet.

Measured on this TV: Apple TV is HDMI4, physical address 4000, uniqueId 4.
A stale launch-point table (all entries `PhysicalAddress: ''`, value `-1`,
seen after a CEC-discovery reset) breaks CEC for every Home-style launch;
reseating the HDMI cable forces bus re-discovery and rebuilds it.

## The bar app (`barapp/`)

Single-page web app, no build step. Rendered at 4K viewport:

- Tiles come from `/api/launchpoints` in launcher order (self skipped),
  with icons from `/api/apps/icon?id=` — the same files Home displays, so
  custom icons match automatically. Static fallback list if the API is down.
- Card style duplicates the Home shelf: 96px rounded cards in each tile's
  `iconColor`, white glyph centered (input glyphs forced white in CSS;
  app artwork untouched). No labels; focus is a 1.06 scale plus white ring.
- Actions: input tiles POST `/api/control {action,input,value}` (CEC-safe
  via the patch) then close; other tiles POST `launchApp`; APPS tile is a
  CSS grid card opening `com.webos.app.discovery`; Close dismisses.
- Edit mode (pencil tile, last): green rings on editable tiles; OK opens a
  per-tile Move/Hide menu above the card; Back steps out. Order and hidden
  set persist in `localStorage` (`bar.order.v1`, `bar.hidden.v1`).
  Structural tiles (Edit, Close) can't be hidden or moved.
- Long-press OK (~0.65s) on any non-structural tile opens a context menu:
  force Close (via tvweb `closeApp`), Move ◀/▶, Hide/Unhide, and Uninstall
  for removable third-party apps (two taps to confirm, via tvweb
  `/api/apps/uninstall`, which carries its own protected-app denylist).
  Enter is preventDefaulted on keydown with the tap replayed on keyup, so
  hold-vs-tap never races the native click; Back dismisses the menu.
- Back/Escape dismisses (`platformBack` then `window.close`); 10s idle
  auto-close, rearmed on any key/click and on becoming visible.
- Key handling: arrows move (with `preventScroll` focus + horizontal
  `scrollIntoView`), Back exits menu/edit/bar in that order.

Key facts learned the hard way: overlay windows never become the foreground
app (`getForegroundAppInfo` keeps reporting the input — toggle state comes
from the running-app list instead); dynamic-only DOM leaves an invisible
page if the script dies, so tiles exist in static markup; large icons must
not be reclassed by loaders in ways that drop their CSS classes.

## The watcher (`watcher/watch.py`)

Python 3 stdlib only (plus `luna-send` subprocesses, always with
stdin from `/dev/null` — `luna-send` answers nothing when it inherits a
socket as stdin, e.g. after an SSH-started watcher restart). One process, four jobs:

**Keys.** Polls all `/dev/input/event*` non-blocking for HOME (773) and
GREEN (399), 0.5s debounce. Passive: it never grabs the device, so a dead
watcher changes nothing. A grab-and-forward design was attempted and
abandoned after probing proved this kernel's uinput rejects all setup
ioctls — and no input node even advertises the 773 code in its bitmap.

- GREEN: if the bar is in the running-app list, close it; else raise it over
  whatever is showing. State transitions are awaited (up to 4s) because the
  running list lags both registration and teardown by seconds.
- HOME with the no-home marker present: close stock Home (the system still
  launches it on the same keypress — the watcher is passive and can't
  consume keys) and raise the bar over video. Without the marker: stock
  behavior, except closing an open bar.

**Strand recovery (bounce).** Polls the foreground app every 1s. When the
screen strands — Home with no HOME key behind it, or no foreground app at
all (the Home-less back-out leaves `appId: ""`) — after leaving a real app,
it arms a return to the last input from `/var/lib/eim/lastinput` (via tvweb,
CEC-safe). Fires after ~2s idle; any remote keypress in between cancels it;
deliberate HOME presses and a 10s cooldown suppress repeats. Transitions out
of live inputs never arm (those are switches in flight). Idle tracking
ignores codes ≥ 768: the system synthesizes events up there around app
transitions (observed 1198/1199 unpressed), and those phantoms must not veto.

**Home backstop.** With the no-home marker present, any Home renderer that
reaches foreground (early boot, stray launch) is killed so video shows
through again; surface-manager falls back to the previous window. Throttled
to every 10s.

**Patch guard.** Every 10 minutes (and via `--cecfix-only` from `51-cecfix`
at boot) checks both server-patch markers; if a tvweb update wiped one, it
re-applies that file's exact-block edit (refusing loudly in the log if the
upstream block changed shape) and restarts tvweb.

## Boot sequence (hook order is lexical)

1. `20-tvweb-services` — stops disabled daemons (mycar, camera, uploaders…).
2. `48-nohome` — hides Home (7 bind mounts, idempotent so repeats never
   stack), kills Home renderers, touches the no-home marker, evicts Home
   from preloadmanager's `allowedApps` (it otherwise relaunches Home every
   few seconds — that was the boot flash), then a fast detached loop
   (2s cadence, up to ~90s): re-assert the hide, drop Home renderers, and
   switch to the last input via `boot-input.py` until real video is
   foreground.
3. `50-barwatcher`, `50-tvweb` — start watcher and server (both detach).
4. `51-cecfix` — reapply server patches before the server finishes starting.

Net effect well under a minute after power-on: video back on the last input,
Home never rendered. All mounts and markers are transient except files under
`/var/lib` and `/media/developer` (both persist across reboots, wiped only
by factory reset).
