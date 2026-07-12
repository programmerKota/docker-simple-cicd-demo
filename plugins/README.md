# Plugins

Plugins are local Python code and therefore have the same authority as the JARVIS process.
They are disabled by default. To enable one:

1. Review every line of the plugin.
2. Place `plugin_name.py` in this directory.
3. Set `JARVIS_ENABLE_PLUGINS=true`.
4. Add its stem to `JARVIS_ENABLED_PLUGINS`, for example `room_presence`.
5. Restart JARVIS and check the audit log.

A plugin exports `register(registry, services)`. See `example_status.py.example`.
Never install an unreviewed plugin on a machine that can control locks, alarms, cameras, or files.
