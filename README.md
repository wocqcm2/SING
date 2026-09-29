# SING MCP Server Dataset

Launch templates and tool metadata for 779 Model Context Protocol (MCP)
server entries, accompanying [SING: Synthetic Intention Graph for Scalable
Active Tool Discovery in LLM Agents](https://arxiv.org/abs/2606.16591).


Release: **2026.09.28**

## Files

| Path | Purpose |
|---|---|
| `dataset/mcp_config_779.public.json` | The 779 launch templates; `_meta.launch_requirements` records setup, credentials, and known limits. |
| `dataset/servers_779_full.public.json` | Server descriptions, tool names, schemas, and matching launch configurations. |
| `dataset/build_manifest.json` | Dependency inventory. |
| `dataset/benchmark_overrides.json` | Optional benchmark launch configurations. |
| `dataset/.env.example` | Addresses, paths, ports, IDs, usernames, and other non-secret settings. |
| `dataset/api.env.example` | API keys, tokens, passwords, and credential-bearing connection strings. |

## Quick start

From the repository root, use Python 3.10 or newer for the renderer. Install
Node.js/npx or uv for the selected servers. On Linux, make sure the MCP client
can find `uvx`; for a user-local uv install, include `$HOME/.local/bin` in
the client's `PATH`.

```bash
python3 dataset/render_config.py --servers "calculator,find-files" --list-vars
cp -n dataset/.env.example dataset/.env
cp -n dataset/api.env.example dataset/api.env
python3 dataset/render_config.py --servers "calculator,find-files" --strict --client-config --npx-yes
```

Fill the variables reported by `--list-vars`: addresses, paths, ports, IDs,
and usernames go in `dataset/.env`; API keys, tokens, passwords, and connection
strings that may contain passwords go in `dataset/api.env`. The renderer checks
that each variable is in the correct file. Its output is
`dataset/mcp_config_779.local.json`; local files are ignored by Git.
`--client-config` omits the research-only `_meta` field.
`--strict` checks placeholder values, not installation, credential validity, or whether
current upstream tools still match the recorded metadata. Inspect the selected
entry in `_meta.launch_requirements` before starting it.

## Download additional server code

Some servers need code from [MCP-Bench](https://github.com/Accenture/mcp-bench)
or [MCP-Atlas](https://github.com/scaleapi/mcp-atlas). Choose a directory and
set its absolute path in `dataset/.env`:

```dotenv
MCPDATA_ROOT=/absolute/path/to/mcpdata
```

From the repository root, download both projects with:

```bash
python3 dataset/prepare_local_sources.py --clone
```

This places the code where the server configurations expect it. To run a
selected server, also install its dependencies using the setup instructions
in `dataset/mcp_config_779.public.json`.

## Safety and license

Launch commands can download and run third-party software. Review commands,
use isolated environments, and never commit credentials or rendered configs.
The original SING dataset contributions are licensed under
[CC BY 4.0](LICENSE). Third-party server code is not included; follow each
upstream project's license.

## Citation

```bibtex
@article{xiao2026sing,
  title   = {SING: Synthetic Intention Graph for Scalable Active Tool Discovery in LLM Agents},
  author  = {Xiao, Qiao and Shi, Haochen and Gao, Yisen and Hu, Wenbin and Jing, Huihao and Zheng, Tianshi and Xu, Baixuan and Zhang, Ziheng and Wang, Weiqi and Li, Haoran and Bai, Jiaxin and Song, Yangqiu},
  journal = {arXiv preprint arXiv:2606.16591},
  year    = {2026},
  doi     = {10.48550/arXiv.2606.16591}
}
```
