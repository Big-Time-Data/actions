# Big-Time-Data/actions

Shared GitHub Actions for Big-Time-Data repositories.

| Action | What it does |
| --- | --- |
| [`pr-enhance`](pr-enhance/action.yml) | Rewrites a pull request title and body from its commits and diff. A good title and body stay as they are. |
| [`release-notes`](release-notes/action.yml) | Writes GitHub release notes and a short Slack summary for a tag. |
| [`slack-notify`](slack-notify/action.yml) | Posts a title and a message with a colored bar to a Slack incoming webhook. |
| [`mcp-query`](mcp-query/action.yml) | Installs `mcpq`, builds the MCPQ context, posts the diff, then publishes, validates and runs the evals. |

The LLM calls go through [OpenRouter](https://openrouter.ai). The default model is `anthropic/claude-haiku-5.5`.

## Requirements

- A runner with `python3` 3.10 or later and `git`. The `ubuntu-latest` and `macos-latest` runners have both.
- The secret `OPENROUTER_API_KEY` for `pr-enhance`. For `release-notes` the key is optional.
- `actions/checkout` with `fetch-depth: 0` before `pr-enhance` and `release-notes`.

The actions use only the Python standard library. They install nothing.

## pr-enhance

### Use the reusable workflow

This is the shortest setup. The workflow does the checkout and runs the action.

```yaml
name: PR Enhance
on:
  pull_request:
    branches: [main]
    types: [opened, synchronize, reopened]

concurrency:
  group: ${{ github.workflow }}-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  enhance:
    if: github.head_ref == 'dev' && github.event.pull_request.head.repo.full_name == github.repository
    uses: Big-Time-Data/actions/.github/workflows/pr-enhance.yml@v1
    permissions:
      contents: read
      pull-requests: write
    with:
      product: "DTS (Data Tool Suite), a desktop app and CLI/MCP server for dbt"
      environment: Production # only if OPENROUTER_API_KEY is an environment secret
    secrets: inherit
```

### Use the action in your own job

```yaml
    steps:
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
          ref: ${{ github.event.pull_request.head.sha }}
      - uses: Big-Time-Data/actions/pr-enhance@v1
        with:
          openrouter_api_key: ${{ secrets.OPENROUTER_API_KEY }}
          product: "MCPQ, a Go CLI that lets an LLM query a data warehouse"
```

The job needs `pull-requests: write`.

| Input | Default | Description |
| --- | --- | --- |
| `openrouter_api_key` | (required) | OpenRouter API key. |
| `github_token` | `github.token` | Token that can update the PR. |
| `model` | `anthropic/claude-haiku-5.5` | Model id. A comma-separated list sets fallback models in order. |
| `product` | | One line about the product, for the prompt. |
| `instructions` | | Extra rules for the model. |
| `pr_number` | from the event | PR number, for `workflow_dispatch` runs. |
| `exclude` | | More pathspec globs to leave out of the diff. Lockfiles and binaries are always out. |
| `skip_label` | `no-pr-enhance` | The action does nothing when the PR has this label. |
| `max_commits` / `max_diff_chars` / `max_file_chars` | `100` / `60000` / `12000` | Prompt budget. One large file cannot use the full diff budget. |
| `dry_run` | `false` | Generate, but do not change the PR. |
| `fail_on_error` | `false` | If false, a failed model call writes a warning and the PR stays as it is. |

Outputs: `updated`, `title`, `body`.

## release-notes

```yaml
      - uses: actions/checkout@v5
        with:
          fetch-depth: 0
      - id: notes
        uses: Big-Time-Data/actions/release-notes@v1
        with:
          tag: ${{ needs.prepare.outputs.tag }}
          openrouter_api_key: ${{ secrets.OPENROUTER_API_KEY }}
          product: "DTS, a macOS desktop app and CLI/MCP server for dbt"
          header: "## DTS Desktop {tag}"
          footer: |
            ### Downloads
            - **macOS**: download `DTS-{version}-arm64.dmg`
      - run: gh release edit "$TAG" --notes-file "$NOTES_FILE"
        env:
          GH_TOKEN: ${{ github.token }}
          TAG: ${{ needs.prepare.outputs.tag }}
          NOTES_FILE: ${{ steps.notes.outputs.notes_file }}
```

The action finds the previous tag itself. It takes the highest older tag with the same prefix and the same channel: `v2.28.0` compares with `v2.27.10`, and `v2.28.0-beta` compares with `v2.27.5-beta`. Set `previous_tag` to use a different tag.

The notes come from the model when it is available. If not, they come from the GitHub auto notes, then from the git log. The `source` output tells which (`ai`, `github` or `git`).

| Input | Default | Description |
| --- | --- | --- |
| `tag` | (required) | Release tag. It does not have to exist yet. |
| `previous_tag` | auto | Tag to compare with. |
| `prerelease_since` | `channel` | `channel`: a prerelease compares with the last tag of its channel. `any`: with the newest older tag of any channel. A stable tag always compares with the last stable tag. |
| `paths` | | Git pathspecs from the repo root that limit the commits, for one app in a monorepo. With `paths`, the GitHub auto notes are skipped. |
| `target` | the tag, else `HEAD` | Commit for the release. |
| `openrouter_api_key` | | Empty skips the AI step. |
| `github_token` | `github.token` | Used for GitHub auto notes. The auto notes need `contents: write`; without it the action uses the git log. |
| `model`, `product`, `instructions` | | Same as `pr-enhance`. |
| `slack_lines` | `3 to 5` | How many Slack lines to ask for. |
| `header` / `footer` | | Markdown before and after the notes. `{tag}`, `{version}` and `{previous_tag}` are replaced. |
| `out_dir` | `RUNNER_TEMP` | Folder for `release-notes/release-notes.md` and `release-notes/slack-summary.txt`. |
| `fail_on_error` | `false` | Fail when the AI notes are not available. |

Outputs: `notes`, `notes_file`, `slack_summary` (lines that start with `• `), `previous_tag`, `source`.

## slack-notify

```yaml
      - uses: Big-Time-Data/actions/slack-notify@v1
        with:
          webhook: ${{ secrets.SLACK_WEBHOOK_COHESION }}
          title: "New DTS version released"
          color: ${{ job.status }}
          message: |
            *What's new*
            ${{ steps.notes.outputs.slack_summary }}

            Upgrade: `brew update && brew upgrade --cask dts`
```

| Input | Default | Description |
| --- | --- | --- |
| `webhook` | | Incoming webhook URL. If it is empty, the action writes a warning and sends nothing. |
| `title` | | Message title. |
| `message` / `message_file` | | Message text in Slack mrkdwn. `message_file` replaces `message`. |
| `color` | `good` | `good`, `warning`, `danger`, `#rrggbb`, or a job status (`success`, `failure`, `cancelled`, `skipped`). |
| `title_link` | | URL for the title. |
| `dry_run` | `false` | Print the payload and send nothing. |
| `fail_on_error` | `true` | Fail the step when the post fails. |

Output: `sent`.

## mcp-query

This action replaces [Big-Time-Data/mcp-query-action](https://github.com/Big-Time-Data/mcp-query-action). It runs the same steps as `mcpq build --publish` on a laptop:

1. Install the `mcpq` release and check its checksum.
2. Write the `MCPQ_CONN` secret to a file (mode 0600).
3. Install uv when the dbt source runs and `mcpq.yaml` has `dbt_core`.
4. Build the sources.
5. Post the diff to the step summary.
6. Publish, then run `mcpq validate --stage published`.
7. Run the evals when `eval_tags` is set and `MCPQ_EVAL` holds a key.

```yaml
    steps:
      - uses: actions/checkout@v5
      - uses: Big-Time-Data/actions/mcp-query@v1
        with:
          version: v0.0.17
          source: dbt,curated,catalog
          config: mcpq/mcpq.yaml
        env:
          MCPQ_CONN: ${{ secrets.MCPQ_CONN }}
          MCPQ_EVAL: ${{ secrets.MCPQ_EVAL }}
```

Set `publish: false` on pull requests to build and see the diff without a publish.

The `@v1` ref selects the version of this repo, not the `mcpq` release. The `version` input selects the `mcpq` release. Pin it to `vX.Y.Z` for builds that you can repeat.

| Input | Default | Description |
| --- | --- | --- |
| `source` | all enabled | Comma-separated source names. |
| `config` | `./mcpq.yaml`, else `./mcpq/mcpq.yaml` | Path to `mcpq.yaml`, from `working_directory`. |
| `working_directory` | `.` | Folder to run `mcpq` in. |
| `version` | `v0` | `latest`, `vX.Y.Z`, or a major such as `v0` (the newest stable `v0` release). |
| `conn` | env `MCPQ_CONN` | Conn file content or a path to it. The action fails when both are empty. |
| `publish` | `true` | If false, only build and post the diff. |
| `eval_tags` | | Eval tags to run after publish. Empty skips the evals. |
| `eval_api_key` | env `MCPQ_EVAL` | API key of the eval harness. |
| `github_token` | `github.token` | Token for the GitHub API calls that find the release. |
| `bin` | | Path to an `mcpq` binary to use instead of a release (for tests). |

Outputs: `version`, `artifact`, `diff_file`.

The releases come from [Big-Time-Data/homebrew-tools](https://github.com/Big-Time-Data/homebrew-tools/releases).

## Versions

- Each release has an immutable tag `vX.Y.Z`.
- The tag `v1` moves to the latest `v1.Y.Z`.
- Use `@v1` to get fixes. Use `@vX.Y.Z` or a commit SHA to pin.

To release, push a tag: `git tag v1.2.0 && git push origin v1.2.0`. The `release` workflow then creates the GitHub release with `release-notes` and moves `v1`.

## Development

```
src/btd_actions/      shared Python core; one module per action entry point
  runtime.py          inputs, outputs, step summary, annotations
  httpclient.py       JSON over HTTP, retry on 429 and 5xx
  openrouter.py       chat completions with JSON schema output
  github.py, git.py   GitHub API and local git
  diff.py, version.py diff budget, semantic version tags
  installer.py        install a CLI from a GitHub release, check checksums.txt
<action>/action.yml   composite action: maps inputs to INPUT_* and runs python3 -m btd_actions.<module>
tests/                unittest
```

Run the tests:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -t .
```

Run an action on your machine. Set the inputs as `INPUT_<NAME>` variables:

```sh
cd ../some-repo
PYTHONPATH=../actions/src GITHUB_REPOSITORY=Big-Time-Data/some-repo \
  INPUT_GITHUB_TOKEN="$(gh auth token)" INPUT_OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
  INPUT_PR_NUMBER=39 INPUT_DRY_RUN=true python3 -m btd_actions.pr_enhance
```

The `test` workflow runs the unit tests, actionlint, and the actions from the checkout on Linux and macOS. It runs `mcp-query` against a Postgres service. On pull requests, it also runs `pr-enhance` on the PR.

To add an action, add a module in `src/btd_actions/`, a folder with an `action.yml`, tests, and a section in this README.
