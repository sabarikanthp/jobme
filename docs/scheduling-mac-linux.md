# Running JobMe automatically on Mac and Linux

JobMe can switch on automatic searches by itself only on Windows (Settings, Schedule). On Mac and Linux you can get the same result with the tool your system already has. Both options run `jobme run`, the same command the Windows task runs.

## What you need to know first

- The computer must be on, and you must be logged in, when the search starts. Your API keys are kept in your own login's secure store, and a search that runs while you are logged out cannot read them.
- Run `uv run --no-sync jobme run` from the JobMe folder, so it uses the same installation as `uv run jobme start`.
- If a search is already running (for example one you started yourself), the automatic one stops quietly. Nothing is lost.
- If a search cannot start (for example the AI connection is missing), open JobMe afterwards. The Today screen shows the last run and what went wrong.

First check that it works by hand: open a terminal in the JobMe folder and run `uv run --no-sync jobme run`. You should see a line such as "Found 12 jobs: 4 new, 2 matched."

## Mac (launchd)

1. Create the file `~/Library/LaunchAgents/jobme.daily-search.plist` with this content. Replace `/Users/you/JobMeFolder` with the folder where you installed JobMe, and `/Users/you/.local/bin/uv` with the path printed by `which uv`.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>jobme.daily-search</string>
  <key>WorkingDirectory</key>
  <string>/Users/you/JobMeFolder</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/you/.local/bin/uv</string>
    <string>run</string>
    <string>--no-sync</string>
    <string>jobme</string>
    <string>run</string>
  </array>
  <key>StartCalendarInterval</key>
  <array>
    <dict>
      <key>Weekday</key><integer>1</integer>
      <key>Hour</key><integer>7</integer>
      <key>Minute</key><integer>30</integer>
    </dict>
    <dict>
      <key>Weekday</key><integer>3</integer>
      <key>Hour</key><integer>7</integer>
      <key>Minute</key><integer>30</integer>
    </dict>
  </array>
</dict>
</plist>
```

Each `dict` in `StartCalendarInterval` is one day and time. Weekday 1 is Monday and 7 is Sunday. Add one `dict` for each day you want.

2. Load it: `launchctl load ~/Library/LaunchAgents/jobme.daily-search.plist`
3. To turn it off: `launchctl unload ~/Library/LaunchAgents/jobme.daily-search.plist`

If the Mac was asleep at the time, launchd runs the job when it wakes.

## Linux (cron)

1. Run `crontab -e` and add one line for each time. This one runs at 07:30 on Monday, Wednesday and Friday:

```
30 7 * * 1,3,5 cd /home/you/JobMeFolder && DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus uv run --no-sync jobme run
```

Replace `1000` with your user number (the output of `id -u`). Cron has no desktop session of its own, so without that setting JobMe cannot read your saved API key and the search would stop with "no AI connection". If it still cannot read the key, use a systemd user timer instead (below), which runs inside your login.

The five fields are minute, hour, day of month, month and day of week (0 or 7 is Sunday). Use the full path to `uv` if cron cannot find it (`which uv` shows it).

2. To turn it off, remove the line.

Cron does not run a search that was missed while the computer was off. If that matters to you, or the key cannot be read from cron, use a systemd user timer: put a `jobme-run.service` (with `ExecStart=/path/to/uv run --no-sync jobme run` and `WorkingDirectory=` set to the JobMe folder) and a `jobme-run.timer` (with `OnCalendar=Mon,Wed,Fri 07:30` and `Persistent=true`) in `~/.config/systemd/user/`, then run `systemctl --user enable --now jobme-run.timer`. It runs inside your login, so the saved key is available, and `Persistent=true` catches up on a missed run.
