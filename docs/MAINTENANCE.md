# Maintenance

## tvweb updates

The two server patches are reapplied automatically:

- At boot, `51-cecfix` runs `--cecfix-only` before the server finishes
  starting.
- Every 10 minutes the watcher re-checks both markers and heals + restarts
  tvweb if needed.

The reapply is exact-block replacement and refuses (logging
`needs review`) if upstream reshaped the block — check the log after any
tvweb update:

```sh
grep -i -E 'cecfix|launchpoints|needs review' /var/lib/barwatcher/watch.log | tail
```

If it refused, port `launchInputWithCec` / the `/api/launchpoints` endpoint
into the new files by hand (sources of truth: `server-patches/`), update the
`OLD_BLOCK`/`LP_OLD` anchors in `watch.py`, redeploy the watcher.

## Changing the bar

Edit `barapp/index.html`, copy to the TV, reinstall with a bumped version,
relaunch. Tile order/colors/labels come live from `/api/launchpoints` +
`/api/apps/icon`, so most visual changes need no code beyond CSS. Hidden and
order state lives in the app's `localStorage` on the TV (keys `bar.order.v1`,
`bar.hidden.v1`) and is independent of reinstalls; a mangled layout is fixed
through Edit mode itself (unhide everything, drag back into order).

## Key codes

Measured on this remote: HOME 773, GREEN 399, Back 412 (standard Linux
evdev; the 32-bit userspace reads 16-byte `input_event`s). The watcher also
logs proprietary-range codes (≥768) seen around transitions (1198/1199
observed unpressed — treated as system echoes, never as user activity). A
different remote may use different HOME codes: capture with a passive
evdev reader, update `HOME_CODE`/`GREEN_CODE` in `watch.py`, redeploy,
restart the watcher.

## Logs that matter

- `/var/lib/barwatcher/watch.log` — watcher: key presses, bounces, guard
  actions (rotates at 64KB to `.old`).
- `/var/lib/tvweb/tvweb.log` — server; look for `DEEPLINK CEC uniqueId`
  lines (in `/var/log/inputcommon`, actually) after a tile switch: a value
  > 0 means CEC-safe, `-1` means the launch-point table went stale again.
- `/var/log/cecmessages` — raw CEC bus; `SelectDevice` + `Focus l.Addr(4)`
  confirm the handshake for HDMI4.
- `/var/lib/eim/lastinput` — the last-physical-input record the bounce and
  boot-to-input read.

## Known failure modes

- **Tiles lose CEC (OK pops banner):** launch-point table stale again
  (`PhysicalAddress: ''`, value `-1` in `listLaunchPoints`). Reseat the
  HDMI cable or power-cycle the box to force bus re-discovery.
- **Black limbo that never bounces:** check the watcher is alive and the log
  for `bounce armed` / `bounce cancelled` / guard errors; confirm
  `/var/lib/eim/lastinput` names an input.
- **Bar invisible but launches:** page script died before render — static
  markup exists precisely so this shows as an empty strip; read errors via
  the red `#dbg` line (window.onerror) on screen.
- **GREEN does nothing:** watcher dead (restart it), or the bar process is
  wedged (close it via luna `closeByAppId`, or wait out the running-list lag
  the toggle waits handle).
- **Home reappears:** the `48-nohome` hook or marker is gone (update? manual
  delete?). Reinstall hook + `touch /var/lib/barwatcher/no-home` + reboot —
  or follow REVERT if that was intentional. If Home flashes at boot or every
  few seconds while the hook is installed, the preloadmanager has relearned
  Home into `/var/preferences/webos-preload-manager-conf.json` (`SAM
  NL_APP_LAUNCH_BEGIN ... preloadmanager` in `/var/log/messages`): remove
  `com.webos.app.home` from its `allowedApps` and `systemctl restart
  preload-manager` (the `48-nohome` hook now does this automatically).
  (Tried and rejected: blocking Home via the device profile `blockedApps`
  override — the resolved list is derived and the override layer does not
  affect it, verified live via `debug/rescan`.)
- **LG EULA/firmware flows** have never run under no-Home mode; if one ever
  misbehaves, REVERT first, update second.
