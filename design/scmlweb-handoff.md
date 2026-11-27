# Handoff to the scmlweb maintainers (WP10)

Internal note, not published (it lives outside `docs/`). It lists what scmlweb has to do so that
its HI and HAN pages show hani2's boards for the 2027 competition, and what hani2 now accepts from
it. Everything on the hani2 side is built (WP0 to WP7). The user-facing description of each piece
is in hani2's docs: *Project management → Leaderboards*, *Connecting a website*, *A competition
year, worked through*, and *Authentication → API tokens for the leaderboard API*.

## 1. Seed the `HI2027` and `HAN2027` projects (copy only missing files)

Put the two projects in scmlweb's repository, for example under `resources/hani2/projects/HI2027/`
and `resources/hani2/projects/HAN2027/`, and copy them into hani2's projects folder
(`$HANI2_PROJECTS`, default `$HANI2_HOME/projects`) on start.

**Copy only files that do not exist yet, and never overwrite.** Today scmlweb copies its projects
in on every start; that would erase what admins change in hani2's editor (scores, the leaderboard
block). After the first copy hani2 owns the files. To bring changes back into scmlweb's repository,
run on the hani2 host and commit the result:

```bash
hani2 project export HI2027  --out resources/hani2/projects            # new files only
hani2 project export HAN2027 --out resources/hani2/projects --overwrite # replace what is there
```

`export` never copies results, recordings or caches, and copies `env.json`, `llm_settings.json` and
`models.json` only with `--with-settings` (they may hold keys).

Suggested seed (each game is a study of its year's project, so one project board pools the game
and the year's Prolific studies; the 2026 `hi-game` and `han-game` projects stay as they are):

```yaml title="HI2027/project.yaml"
full_name: HANI HI 2027
kind: assistant
year: 2027
defaults:
  study_mode: mixed
  opponents: [human+assistant, ":han2027-qualified"]   # this year: from the submitted zips (index.json, §4)
  scheduling: {assistants: balanced}
  pairing: {scope: study, assign: cells, allow_same_assistant: true, fallback: ai}
scores:
  hi_score:
    title: HI-score
    track: hi
    components:
      - {criterion: human_advantage, weight: 0.6}
      - {criterion: hi_team,         weight: 0.4}
scores_enabled: [utility, hi_score, hi_interaction]
leaderboard:
  track: hi
  source: game
  studies: [play]                       # add Prolific studies as they run
  sort_options: [hi_score, utility]
  default_sort: hi_score
  user_options: {games: [all, people, ai]}
  visibility: public
```

```yaml title="HAN2027/project.yaml"
full_name: HANI HAN 2027
kind: opponent
year: 2027
defaults:
  study_mode: solo
scores_enabled: [han_outcome, han_interaction]
leaderboard:
  track: han
  studies: [play]
  include: [{study: HI2027/play, stratum: vs_team}]   # HI games against HAN agents, as their own stratum
  sort_options: [han_outcome, han_interaction]
  user_options: {stratum: [alone, vs_team]}
  defaults: {stratum: alone}
```

Plus `HI2027/studies/play/study.yaml` and `HAN2027/studies/play/study.yaml` (at least
`type: online` and the texts the games use today).

Notes on the seed:

- The `hi_score` above is a placeholder; the real one is decided with the organisers. Its weights
  must sum to 1, every criterion must exist (`hani2 scores criteria HI2027`), and a project whose
  board sorts by a score must enable it in `scores_enabled`. `hani2 scores check HI2027` and
  `hani2 project show HI2027` print every problem.
- `:han2027-qualified` resolves from this year's submissions, so hani2's `env.json` must have
  `{"han": {"current_year": 2027, "submissions": {"2027": {"dir": "~/anac/_agents_han/2027"}}}}`.
  Without them the group expands to nothing and the save is refused.
- `visibility: public` boards need no token. Start with `participants` (hani2's default) if the
  boards should stay closed until the organisers are happy with them.

## 2. Move the games into the year projects

Point the HI game at `HI2027/play` and the HAN game at `HAN2027/play` instead of the 2026
projects: the hand-off link's `next` becomes `/s/HI2027/play/…` (or `?study=HI2027/play`), and
invitation group files go to `<projects>/HI2027/studies/play/results/groups/<key>.json`. If guests
are invited, add the study to the provider's `guest_studies` in hani2's `env.json`
(`auth.sso.<name>.guest_studies: ["HI2027/play"]`).

## 3. Read the project board API for the active project

scmlweb names the active projects in its own configuration, for example
`{"hi": "HI2027", "han": "HAN2027"}` (the competition year is scmlweb's concept; hani2 lists every
board and marks none as active). Its HI page reads `HI2027`'s project board as the default view,
with the existing Tournament table as a second tab; its HAN page reads `HAN2027`'s.

```
GET <hani2>/api/v1/projects/HI2027/leaderboard?sort=&games=&stratum=&window=
GET <hani2>/api/v1/projects/HI2027/studies/play/leaderboard?…      (one study)
GET <hani2>/api/v1/leaderboards                                    (every board: track, year, visibility)
```

- The response (schema `hani2.leaderboard/2`) is documented with a full example in hani2's
  *Project management → The leaderboard API*. Draw the sort menu from `options.sort` and a switch
  only when `options.<switch>` is present, with exactly its values; start from `options.defaults`.
  Any other value gets a **400**, so scmlweb cannot show a view the project does not allow and
  needs no rules of its own.
- Show `entries` (`rank`, `tied_with_leader` as "=2", `label`, the `values` of `columns` with their
  `ci`, `games`, `participants`), then `unranked` as "not ranked yet". `entrant` is the `entrant`
  id scmlweb wrote in the group file (§4), else the Assistant's spec; map it to teams with that.
  On HAN boards, `opponent` replaces `assistant`.
- Show `notes` and `warnings` somewhere (a footnote), and mark scores whose
  `scores.<key>.provisional` is true.
- No names are in the response: no users, no inviters, no participant indices.
- Cache on `data_version`, or send the response's `ETag` back as `If-None-Match` (a 304 when
  nothing changed). Pull; hani2 does not push.
- Status codes: 401 (no or bad token on a non-public board), 403 (token without the scope), 404
  (unknown project or study), 400 (option not allowed).

## 4. Write `entrant` and `own` in group files (and `han_year` when it applies)

The runtime group files scmlweb writes for each game invitation
(`<project>/studies/play/results/groups/<key>.json`) take three new keys:

```json
{"agents": ["human+assistant", ":han2027-qualified"],
 "assistant": "team42.assistant:Helper",
 "entrant": "sub_0412",
 "own": true,
 "ai_fallback": true}
```

| Key | Type | Results column | Meaning |
|---|---|---|---|
| `entrant` | string | `assistant_entrant` | scmlweb's id of the Assistant (submission or team id). It becomes the API's `entrant`. |
| `own` | JSON boolean | `own_assistant` | The participant is on the team that submitted the Assistant. **`false` for a guest's invitation.** Boards count own-team games but require 3 non-owner players before ranking (`min_participants`). |
| `han_year` | int | `opponent_han_year` | Only when the file lists HAN agents **by class path** from scmlweb's zips (not by a `:han<year>-<set>` group): the year of those agents, so their games reach the HAN board's `vs_team` stratum. |

hani2 reads these keys from files it finds (leniently), and keeps them when an admin saves a group
file through its API (strictly: `own` must be a JSON boolean, `han_year` an int). Older hani2
versions ignore them on read and drop them on an admin save.

## 5. Write the HAN submissions `index.json` (§3.4 of the design note)

For the current year, hani2 takes the HAN agents from the submitted zips. scmlweb writes, in the
year's folder that hani2's `env.json` names (`han.submissions.2027.dir`), the zips and an
`index.json` from `agent_placements`. hani2 reads (`hani2.han_submissions.read_index`):

```json
[
  {"entrant": "sub_0981", "team": "t17", "zip": "t17.zip", "class": "t17_agent.agent:MyNegotiator",
   "name": "MyNegotiator", "sha256": "…", "qualified": true, "finalist": false, "winner": false}
]
```

- A list of entries; a mapping with the list under `entries`, `submissions` or `agents`; or a
  mapping of entrant id to entry are all accepted.
- `entrant` (else the zip's name, else `team`) is the id; it must be letters, digits, `_`, `-`
  (anything else is replaced and reported). `zip` is a file name inside the folder; `class` is the
  negotiator class (`module:Class` or `module.Class`). `name` and `sha256` are optional; a
  `sha256` that does not match the zip is reported.
- The sets `:han2027-all`, `-qualified`, `-finalists` and `-winners` follow the flags, so they
  follow scmlweb's placements.
- After writing, run `hani2 han import --year 2027` (unpacks each zip into its own folder, runs
  nothing while unpacking, checks the class imports in a separate process) and
  `hani2 han check --year 2027` (lists entries, their sets, whether each imports, zips the index
  does not list). A new upload (a new hash) gets a new folder; games record which build they played
  (`opponent_han_version`).

## 6. API tokens

Non-public boards need `Authorization: Bearer <JWT>`: HS256, signed with the **same secret**
scmlweb already uses for the sign-in hand-off, but for a different audience:

| Claim | Value |
|---|---|
| `iss` | the provider's issuer (default: the provider's name in hani2's `auth.sso`, e.g. `scmlweb`) |
| `aud` | `hani2-api`, plus the instance's root path when hani2 runs under one (`hani2-api/hiplay2`) |
| `scope` | `leaderboard:read` (a space-separated string or a list); `leaderboard:admin` to also read boards with `visibility: admins` |
| `iat`, `exp` | Unix seconds, at most 120 s apart (30 s clock skew allowed) |

No `sub`, no `jti`: an API token may be reused while it is valid, so mint one per request or once
a minute. A sign-in token (`aud: hani2…`) is refused by the API, and an API token is refused by the
sign-in hand-off; a token naming both audiences is refused by both.

Scopes: `leaderboard:read` reads boards with `visibility: public` or `participants`.
Boards with `visibility: admins` need `leaderboard:admin` (which includes `leaderboard:read`): a
token without it gets **403** for them, and `GET /api/v1/leaderboards` does not list them. Mint
`leaderboard:admin` only for organiser-facing pages, never for the public site.

```python
import base64, hashlib, hmac, json, time

import requests


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def hani2_api_token(secret: str, issuer: str = "scmlweb", root_path: str = "",
                    scope: str = "leaderboard:read") -> str:  # "leaderboard:admin" for admins boards
    now = int(time.time())
    aud = "hani2-api" + (f"/{root_path.strip('/')}" if root_path.strip("/") else "")
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps({"iss": issuer, "aud": aud, "scope": scope,
                           "iat": now, "exp": now + 60}).encode())
    sig = b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def project_board(base: str, project: str, secret: str, root_path: str = "", **query) -> dict:
    r = requests.get(f"{base}/api/v1/projects/{project}/leaderboard", params=query, timeout=30,
                     headers={"Authorization": f"Bearer {hani2_api_token(secret, root_path=root_path)}"})
    r.raise_for_status()
    return r.json()


# board = project_board("https://anac.cs.brown.edu/hiplay2", "HI2027", SECRET, root_path="/hiplay2",
#                       sort="hi_score", games="people")
```

With PyJWT: `jwt.encode({"iss": "scmlweb", "aud": "hani2-api", "scope": "leaderboard:read",
"iat": now, "exp": now + 60}, secret, algorithm="HS256")`. hani2's test suite runs this exact
minting function against its verifier (`tests/test_sso.py`). On the hani2 host,
`hani2 leaderboard token scmlweb` prints a token to try the API with `curl` (`--admin` for one with
`leaderboard:admin`).

## 7. Checklist

- [ ] Seed `HI2027` / `HAN2027` (copy only missing files); remove the copy-on-every-start.
- [ ] hani2 `env.json`: `han.current_year: 2027`, `han.submissions.2027.dir`, `guest_studies`.
- [ ] Hand-off `next` and invitation group files point at `HI2027/play` / `HAN2027/play`.
- [ ] Group files carry `entrant` and `own` (and `han_year` when agents are named by class path).
- [ ] `index.json` written from `agent_placements`; `hani2 han import` / `check` run after uploads.
- [ ] HI and HAN pages read the project board API of the active project (scmlweb config), with the
      Tournament tab kept on HI.
- [ ] API tokens minted per request with the shared secret.
