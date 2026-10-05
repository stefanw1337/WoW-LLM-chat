# WoW LLM Chat

Talk to a local language model from the **AI** channel in World of Warcraft 3.3.5a (and one for Forever version). A Windows companion connects the addon to LM Studio and displays replies as **Qwen3 (MoE)**. Shared mode posts replies through your character so other players can participate.

```text
[7. AI] [YourCharacter]: How do I bake a chocolate cake?
[7. AI] [Qwen3 (MoE)]: To bake a chocolate cake...
```

The addon joins AI automatically. WoW assigns the channel number, so it may not be 7. Qwen is not an actual player account. In shared mode, other players see replies from your character, prefixed with `[Qwen3 (MoE) -> PlayerName]:`. Your screen keeps the local light-blue Qwen name without duplicating the network echo. In private mode, replies appear only on your screen.

**Status: experimental.** Basic Qwen replies have been observed in game. Automated tests and a real LM Studio request have passed. Shared-channel delivery, queueing, and live settings still need an in-game multiplayer check.

## Features

- Ask questions about any topic, including cooking, history, programming, and WoW.
- Automatic local replies, without pasting text or reloading the UI for each reply.
- Supports LM Studio's OpenAI-compatible API; no Claude API key or subscription required.
- Short conversation history per character and model.
- Your waiting questions always take priority over guests; the response already being generated finishes first.
- Guests can ask one question every five minutes by default. Cooldown and queue settings can be changed in the companion window.
- Optional keyword rules for routing questions to additional models.
- No simulated keystrokes, game-memory access, or automatic UI reloads.

## Requirements

- Windows and an original WoW 3.3.5a-compatible client (Interface 30300).
- WoW running in windowed or borderless mode.
- Python 3.10 or newer, including Tkinter, and Pillow.
- LM Studio with a text-generation model loaded and its API server running.

The project was designed around Qwen3 30B A3B 2507. API integration has also been tested with `qwen/qwen3-next-80b`. The in-game display name is currently fixed to `Qwen3 (MoE)`.

## Installation

1. Fully close WoW.
2. Double-click **Setup.cmd** and enter your WoW client folder. Setup copies the addon, creates 2,048 small load-on-demand reply addons, and installs the Python dependency. It does not change other addons.
3. Load your model in LM Studio and start its server. The example configuration uses `http://127.0.0.1:1234/v1`.
4. Review **bridge/config.json**, created by the installer. For a server on another computer, change `base_url` to its reachable address, including `/v1`.
5. Double-click **Start-Bridge.vbs** to open the companion without a console window. **Start-Bridge.cmd** also starts the windowless Python launcher, but a console may briefly flash.
6. Launch WoW and enable **WoW LLM Chat** and its reply addons on the character selection screen. Disable other addons that draw a transport strip in the upper-left corner if they overlap this addon's strip.
7. Log in, wait a few seconds for the AI channel to connect, and type into that channel. Keep WoW in the foreground while sending questions and receiving replies.

For manual installation, run these commands from the project folder:

```powershell
./Install.ps1 -WowDirectory 'C:/Games/World of Warcraft 3.3.5a'
python -m pip install -r bridge/requirements.txt
```

If LM Studio requires authentication, set the `LM_STUDIO_API_KEY` environment variable before starting the bridge. Do not put API keys in files you intend to share.

## Configuration

The companion window follows Windows display scaling at startup and starts with a larger, resizable layout. Use **A-** / **A+** or **Ctrl+-** / **Ctrl++** to adjust text size. This preference is saved locally in `bridge/ui_settings.json`, which is excluded from the shared package. Restart the companion after changing Windows display scaling.

Your local settings are stored in `bridge/config.json`, which is excluded from version control. The public template is `bridge/config.example.json`. Reinstalling preserves existing settings and updates the WoW folder.

| Setting | Purpose |
| --- | --- |
| `wow_directory` | Your WoW client folder, containing `Interface`. |
| `base_url` | LM Studio's API address, including `/v1`. |
| `model` | `auto` selects the only available non-embedding model; otherwise specify its exact model ID. |
| `window_titles` | Window-title fragments used to recognize the active game window. |
| `max_tokens` | Maximum generated tokens per response; defaults to 160 for short replies. |
| `timeout_seconds` | HTTP request timeout, including model loading time. |
| `history_turns` | Number of previous question/answer pairs retained per character and model. |
| `system_prompt` | Assistant instructions. The default requests short, concise answers without code. |
| `routes` | Optional keyword-to-model rules, evaluated in order before the default model. |

List models and check the connection:

```powershell
python bridge/bridge.py --check
```

If more than one text model is listed, set `model` to the desired model's exact ID. Model replies follow the language of your question; the addon, companion, and documentation use English.

The channel is fixed to `AI` in this version. The `channel` field in the example configuration does not rename the addon's channel.

With one model, all questions go to that model. MoE expert selection happens inside the model, not in the addon. Optional `routes` are simple keyword rules, not an automatic assessment of which model is smartest.

## Shared-channel controls

The companion window provides **Post replies to AI**, **Answer other players**, **Guest cooldown (minutes)**, and **Maximum waiting guests**. Click **Apply settings** to save them and send them to WoW. No reload is needed for these settings: changes apply on the next file check, normally within six seconds during a question or 30 seconds while idle. Enabling guest questions requires public replies.

Your character is detected automatically. Your questions have their own eight-entry waiting queue and are always selected before waiting guest questions, in arrival order. The active model request is not interrupted. Guests have a separate queue of 20 by default, and each guest may have only one active or queued question. The five-minute cooldown starts when a question is accepted, even if the server later fails. Rejected guests receive a rate-limited whisper explaining the wait. Cooldowns and the latest applied policy are saved by WoW on logout or UI reload.

Public replies are split into messages of at most 255 bytes and sent no faster than once every 1.5 seconds. AI-labelled messages are ignored to prevent response loops. Your client must stay logged in, with the bridge running, to host Qwen for others. The queue display is the last snapshot received from the game, not a guarantee of current state while the game is minimized. Switching to private mode clears queued guest questions and unsent public messages; an active request can still finish locally.

LM Studio only needs to run when you want AI answers. The bridge does not start it automatically. Connection failures appear in the bridge and in your local chat, with a generic error notice sent to the affected guest. Ask again after starting the server.

The hidden launcher prevents a second launcher instance for the same project. Startup errors appear in a dialog; details go to local `bridge/bridge.log`. Close an older console-based bridge before using the new launcher for the first time. When upgrading from 0.1, restart WoW once so it reads the new saved-variable declaration.

## How it works

WoW addons cannot directly call HTTP services or read arbitrary files at runtime. This project uses two supported addon mechanisms as a transport:

1. **Questions leave the game as pixels.** The addon draws an encoded color strip in the upper-left corner. The bridge captures that small area only when a matching game window is in the foreground. A checksum rejects incomplete or corrupted messages. Captured images are not saved.
2. **Replies enter through load-on-demand addons.** The bridge writes an escaped Lua data record into a preinstalled reply file. WoW loads a fresh reply addon and displays the answer in chat. Model output is treated as string data, not executable Lua.

The bridge also writes the latest request as JSON to `bridge/exchange/request.txt`, and the latest answer to `response.txt` and `response.json`. These files contain conversation text and are excluded from the shareable package. Shared mode processes questions from everyone in AI. Disable **Answer other players** to accept only your own questions.

Conversation history is kept in memory and resets when the bridge exits.

## Optional character advice

**Use my character data** includes a fresh, size-limited snapshot with your questions: class, level, race, faction, location, basic stats, equipped item names/IDs, active talents, visible professions and quests. Missing or uncached entries remain unknown, and long snapshots may omit entries. Character data is never attached to another player's question.

- **Include my gold** is off by default. When enabled, it reads your current carried gold, silver and copper.
- **Include my GearScore** is off by default. It requires a compatible addon exposing `GearScore_GetScore`; otherwise the score is unavailable. No score is guessed from equipment.
- **Keep my replies private when character data is used** is on by default. All your replies in character mode stay local, including general questions. Guests still receive shared replies. Turn character data off for ordinary public conversations, or explicitly disable the private option to share character advice.

Click **Apply settings**; changes reach WoW within 30 seconds while idle. Ask a new question afterward. An answer already being generated may use the previous settings. Disabling a field excludes it from subsequent model inputs and separates conversation history by privacy settings; it does not erase old chat or saved answers. Information you explicitly type in your question is still sent. Questions typed in AI are visible to channel members even when the reply stays private.

The snapshot does not supply a loot database or web lookup. Qwen can discuss general WotLK knowledge, but cannot verify custom-realm item sources. It is instructed to state uncertainty and ask for an item link or realm source. The latest snapshot is included in the local `exchange/request.txt`; keep exchange files private.

After upgrading to this version, close and reopen WoW once so the new `Character.lua` file loads, and restart the bridge. Ordinary questions do not require a reload.

## Commands

| Command | Action |
| --- | --- |
| `/wllm status` | Show the channel number, remaining reply slots, and whether a question is pending. |
| `/wllm cancel` | Cancel pending display requests and hide the pixel strip. An API request already in progress may still finish in the background. |

## Limitations and troubleshooting

- **Finite reply slots:** each of the 2,048 reply addons can load only once per UI session. Polling every six seconds allows roughly 3 hours and 25 minutes of accumulated waiting time, not a guaranteed number of conversations. While idle, one slot is checked every 30 seconds to receive live settings, so a fully idle session can use the pool in roughly 17 hours. When exhausted, the addon stops and asks you to log out and back in; it never forces a reload.
- **Window visibility:** minimizing WoW, exclusive fullscreen, overlapping windows, or switching to another app prevents reliable capture. Delivery resumes when WoW is visible and active. Keep the upper-left corner unobstructed. If colors cannot be decoded, try disabling HDR.
- **Latency:** replies normally appear within six seconds after model generation and file delivery. Initial model loading may take longer than the configured timeout.
- **Chat formatting:** replies use the AI channel color, with only the model name highlighted in light blue. Long answers are shortened to 1,800 UTF-8 bytes and split into chat entries of at most 255 bytes, including their prefix. Emoji and common Markdown emphasis are removed for compatibility with the original chat font.
- **Missing reply addons:** close WoW, run Setup again, relaunch the game, and ensure all reply addons are enabled.
- **LM Studio errors:** check the address, model ID, and server state. Errors appear under `Bridge status` in the AI channel. Ask again after resolving the error.
- **A pixel strip that never disappears:** check that the bridge is running and the game's title matches `window_titles`.
- Run only one bridge process per game client.

## Development and validation

The tests use Lua 5.1 with simulated WoW APIs, generated pixel images, reply files, and a local HTTP test server. Install the test-only runtime and run the suite:

```powershell
python -m pip install --target .testdeps lupa
python -m unittest discover -s tests -v
```

Automated tests cover Lua 5.1 transport, owner/guest queue behavior, character snapshots, optional sensitive fields, private reply delivery and model-history isolation. Tests use simulated game APIs and a local HTTP test server without starting LM Studio. The new character features still require an in-game check with your client.

## Sharing

Share the source files or the prepared `WoW-LLM-chat-English.zip`. Do not include your local `bridge/config.json`, exchange files, Python caches, test dependencies, or temporary installations, `bridge/bridge.log`, `bridge/.bridge.lock`, or `bridge/ui_settings.json`. The public configuration uses localhost and a generic example game path.

## References

The pixel-strip and load-on-demand approach was inspired by [wow-ai](https://github.com/chelinho139/wow-ai) and its earlier WoWClaude addon. This implementation uses its own code targeting the original 3.3.5 APIs; the reference project targets a newer client.

The LM Studio connection follows its official [chat completions documentation](https://lmstudio.ai/docs/developer/openai-compat/chat-completions).
