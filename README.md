# ShinBot Plugins

Official ShinBot plugin marketplace index.

This repository stores marketplace metadata only. Plugin source code lives in
standalone repositories, and `plugins.json` points ShinBot WebUI to those
repositories for install and update operations.

## Index

ShinBot reads `plugins.json` from the repository root. Each top-level key is a
plugin id, and each entry includes the plugin metadata plus its GitHub
repository URL.

Current plugin repositories:

- `shinbot_plugin_astroassist`: https://github.com/NekyuuYa/shinbot_plugin_astroassist
- `shinbot_plugin_minesweeper`: https://github.com/NekyuuYa/shinbot_plugin_minesweeper
- `shinbot_plugin_renderkit`: https://github.com/NekyuuYa/shinbot_plugin_renderkit
- `shinbot_converter_astrbot`: https://github.com/NekyuuYa/shinbot_converter_astrbot
