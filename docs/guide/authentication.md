# Authentication

HANI2 has two kinds of sessions:

- **Logged-in sessions** at `/app`. They belong to a user account and are configured by the authentication mode.
- **Playground sessions** at `/play`. They need no login. Each browser gets a guest session, and a Prolific participant gets a session keyed by their `PROLIFIC_PID`. See [Prolific](prolific.md).

## Authentication modes

Set the mode in `env.json`:

```json
{
  "auth": {
    "mode": "password",
    "cookie_secret": "",
    "enforce_consent": false,
    "allow_registration": true,
    "default_password_login": "auto"
  }
}
```

| `auth.mode` | Behaviour |
| --- | --- |
| `password` | Username and password. This is the default. |
| `oauth` | Only "Sign in with GitHub / Google". Password login and registration are disabled. |
| `dual` | Both: password login and OAuth buttons. |
| `none` | No login at all. Each browser gets its own account named `user_<id>`, remembered by a cookie. |
| `auto` | `dual` when at least one OAuth provider is configured, otherwise `password`. |

`oauth` and `dual` fall back to `password` when no OAuth provider is configured, and any unknown value counts as `password`. `hani2 info` prints the effective mode.

### Other `auth` keys

| Key | Default | Meaning |
| --- | --- | --- |
| `cookie_secret` | `""` | Secret used to sign the login cookie. When empty, HANI2 generates one and keeps it in `settings/.cookie_secret`, so logins survive restarts. Set it explicitly when several installations must accept the same cookies; generate one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `enforce_consent` | `false` | When `true`, a logged-in user who has not consented sees the consent form (the content of `consent.md`) and must agree and sign with their full name before negotiating. The server does not block admins who have not consented, but the login page still sends them to the consent form. |
| `allow_registration` | `true` | Shows the registration form. Registration is always off in `oauth` and `none` modes. |
| `default_password_login` | `"auto"` | Whether an admin may log in with the well-known default password: `auto` refuses it when the server listens on a non-loopback interface, `refuse` always refuses it, `allow` never does. See [Default accounts](#default-accounts). |

The login cookie (`hani2_auth`) is valid for 30 days.

## Registration

With registration allowed, the login page offers a **Register** form that asks for a username, password (twice), email (twice), full name and agreement to the consent text. A user who ticks the consent box is stored as consented with the date.

Usernames must be at most 64 characters with no spaces or path characters (`/ \ : * ? " < > |`). The names `ai`, `agent`, `guest` and `admin2`, and anything starting with `prolific_`, are reserved. Passwords need at least 4 characters.

Users change their own password from the account menu (*Change password*) in the top-right corner of the negotiation page. Admins reset any password in the admin console or with `hani2 users passwd`.

## OAuth with GitHub and Google

HANI2 implements the authorization-code flow for GitHub and Google.

```json
{
  "auth": {"mode": "dual"},
  "oauth": {
    "redirect_uri": "https://negotiate.example.org",
    "providers": {
      "github": {"enabled": true, "key": "<client id>", "secret": "<client secret>"},
      "google": {"enabled": true, "key": "<client id>", "secret": "<client secret>"}
    }
  }
}
```

A provider counts as configured when it has a `key` and a `secret` and `enabled` is `true` (the built-in default is `false`).

`oauth.redirect_uri` is the public base URL of your server. HANI2 appends `/api/oauth/<provider>/callback` to it. When it is empty, the base URL of the incoming request is used, which is fine for local testing but often wrong behind a reverse proxy.

### GitHub

1. Open GitHub → Settings → Developer settings → OAuth Apps → **New OAuth App**.
2. Set **Homepage URL** to your base URL and **Authorization callback URL** to `<base URL>/api/oauth/github/callback`, for example `http://localhost:5006/api/oauth/github/callback`.
3. Copy the client ID into `key` and generate a client secret for `secret`.

HANI2 asks for the `read:user user:email` scopes. A GitHub user `octocat` becomes the HANI2 user `gh_octocat`; the primary email is stored with the account.

### Google

1. In the Google Cloud console, open APIs & Services → Credentials → **Create credentials → OAuth client ID**, application type **Web application**.
2. Add `<base URL>/api/oauth/google/callback` as an authorized redirect URI.
3. Copy the client ID into `key` and the client secret into `secret`.

HANI2 asks for `openid email profile`. A Google user becomes `g_<their Google account id>` (the stable `sub` claim), for example `g_1043…`; the email is stored with the account.

OAuth users are created on their first login and do not have a usable password. After a successful login they are sent to `/app`. Failures send them back to `/login` with an `error` parameter (`oauth_state`, `oauth_token` or `oauth_failed`).

## Sign-in from a trusted website

A website that already has accounts, such as a competition site, can sign its users straight
into HANI2. There are no new passwords and no second registration: the HANI2 account is created
on the first visit. The website signs a short-lived token with a secret it shares with HANI2 and
sends the browser to HANI2 with it.

```json
{
  "auth": {
    "sso": {
      "scmlweb": {
        "secret": "<a random string of 32 or more characters>",
        "login_url": "https://anac.example.org/hani2/sso",
        "label": "ANAC account",
        "prefix": "anac_",
        "issuer": "scmlweb",
        "guest_studies": ["arena/play"],
        "trust_admin_claim": false
      }
    }
  }
}
```

The secret may also come from the environment variable `HANI2_SSO_<NAME>_SECRET`, for example
`HANI2_SSO_SCMLWEB_SECRET`. A provider without a secret (or with one shorter than 16 characters)
is off. With a `login_url`, the login page shows **Continue with your ANAC account**.

The settings of a provider:

| Key | Default | Meaning |
| --- | --- | --- |
| `secret` | — | The shared HS256 secret, 16 characters or more (32+ recommended). Or `HANI2_SSO_<NAME>_SECRET`. |
| `login_url` | — | The website's page that mints a token. Without it, there is no login button (links from the website still work). |
| `label` | the name | The login button's text: **Continue with your &lt;label&gt;**. |
| `prefix` | `anac_` | HANI2 user names are `<prefix><sub>`. Nobody can register a name with this prefix by hand. |
| `issuer` | the name | The `iss` the tokens must carry. |
| `guest_studies` | `[]` | The studies [guest tokens](#guests) may open (`project/study`). |
| `trust_admin_claim` | `false` | `true`: the token's `admin` claim makes the account an admin of this server. See [Admins from the website](#admins-from-the-website). |
| `enabled` | `true` | `false` turns the provider off. |

### The flow

1. The login button opens `/api/sso/<name>/login?next=<page>`. HANI2 sends the browser to
   `login_url?site=<this server's root path>&next=<page>`. `site` is `/` or the root path, for
   example `/hiplay2`. The website chooses this server's address from its own settings by that key. It must
   never send a token to an address taken from the request.
2. The website, with its user logged in, sends the browser to
   `<HANI2 base>/api/sso/<name>?token=<token>&next=<page>`. Links on the website (such as "test my
   agent") can do this directly, without step 1.
3. HANI2 checks the token. It creates or updates the user `<prefix><sub>` (for example `anac_789`),
   logs the browser in and opens `next`. `next` must be a path on this server, for example
   `/app?group=test_hi_789_x`; anything else opens `/app`. Refused tokens open
   `/login?error=sso_<reason>`.

### The token

An HS256 JSON Web Token signed with the shared secret. Its claims:

| Claim | Value |
| --- | --- |
| `iss` | The provider's `issuer` (default: its name). |
| `aud` | `hani2` plus this server's root path, for example `hani2/hiplay2`, or just `hani2` without a root path. A token for one server does not open another. |
| `sub` | The website's user id: 1–48 letters, digits, `_` or `-`. It names the HANI2 account. |
| `iat`, `exp` | Issue and expiry times (Unix seconds), at most 120 seconds apart. 30 seconds of clock skew are allowed. |
| `jti` | A random id of 8–128 characters. Each token works once. |
| `email`, `name` | Optional: stored with the account. |
| `leagues` | Optional: a list such as `["han", "hi"]`, stored with the account. |
| `admin` | Optional: `true` for a person who should be an admin of this server. Counts only with `trust_admin_claim`. |

Any JWT library can make these tokens. Accounts made this way are marked with the provider's
name, and names with their prefix cannot be registered by hand. The website's emails are not
checked by HANI2, so these accounts never become admins through `admin.emails`.

### Admins from the website

With `"trust_admin_claim": true` in a provider's settings, the website can say who is an admin of
this server, for example the organizers of a competition league. The setting is off by default, and
then the claim is ignored.

- A token makes its account an admin only when the token is valid (signature, issuer, audience,
  times and single use are checked as always), it is not a [guest](#guests) token, and its `admin`
  claim is the JSON boolean `true`. Anything else is not a grant: a missing claim, `false`, `null`, or the
  strings `"true"`, `"1"` and numbers such as `1`. The setting itself must also be the boolean `true`.
- The grant is decided again on every hand-off. A valid token without the claim, or with any other
  value, removes it. A refused token (bad signature, expired, replayed, …) changes nothing.
- The grant is stored with the account as `sso_admin`, apart from the `role`. It is kept per server, by
  the token's audience (`hani2`, `hani2/hiplay2`, …). Two servers that share a `HANI2_HOME` keep their own
  admins, so the website can make someone an admin on one server and not on another.
- Removing the claim never removes another kind of admin: a `role` of `admin` given on the *Users*
  page or with `hani2 users add --admin` stays. The built-in `admin` account and `admin.emails`
  admins are separate accounts and are never touched. Hand-off accounts never become admins through
  `admin.emails`.
- With the setting turned off, or the provider removed, its grants stop counting at once. They are
  not deleted, and each next hand-off clears that server's entry.
- Each grant and each removal is written to the event log (`admin_granted`, `admin_revoked`, with the
  provider and the audience) and to the server log as
  `[sso] scmlweb: admin granted for anac_789 on hani2 (the token's admin claim)`.
- A demoted account loses admin rights at once. API calls check the role on every request. Its next
  page load gets a new session without the admin view. An open page's live connection is closed at
  its next message, and the page then reconnects as a non-admin. The same happens when an admin is
  demoted on the *Users* page.
- The *Users* page lists the grant as `sso_admin`. Clearing *admin* there changes only the `role`:
  the next hand-off with the claim makes the account an admin again. To stop that, change the
  website, or turn off `trust_admin_claim`.

A participant who already has a session in the study and comes back through a new hand-off (a new
"play" click on the website) after a finished negotiation gets a new negotiation. A reload of the
page keeps showing the result.

### Guests

A website can also send people who have no account there, for example someone a participant
invited, into one study. It mints the same token with these extra claims:

| Claim | Value |
| --- | --- |
| `guest` | `true` |
| `sub` | An id for the invitation, for example `invite-42`. The account is `<prefix><sub>`, for example `anac_invite-42`. |
| `invited_by` | Optional: who invited them (a number or a string), recorded in the `invited_by` results column. |
| `name` | Optional: the name the guest typed, shown on their page. |

HANI2 accepts a guest token only when `next` names a study (`?study=<project>/<study>` or a
`/s/<project>/<study>/` path) that the provider lists in `guest_studies`. Any other `next` opens
`/login?error=sso_guest`. The guest account:

- has no password and can open only that study, as a participant. Every other study, the default
  study, the playground, the admin console, results and replays answer *403*;
- stays a guest. A guest token for a normal account, or a normal token for a guest account, is
  refused (`sso_conflict`);
- gets one session per browser, because several people may use one invitation. Their results go
  to `<account>~<browser id>` (for example `anac_invite-42~3f2a9c1b0d4e`), and every row records
  `invited_by`.

## Admins

A user is an admin when any of these is true:

- the username is `admin`,
- the account has the role `admin` (set with `hani2 users add --admin`, or in the admin console),
- the account was made by a [trusted website](#sign-in-from-a-trusted-website) whose provider has
  `trust_admin_claim` on, and the last hand-off token to this server carried `"admin": true` (see
  [Admins from the website](#admins-from-the-website)),
- the account's email is listed in `admin.emails` in `env.json` (case-insensitive; not for self-registered or hand-off accounts). This is the simplest way to make OAuth users admins:

    ```json
    {"admin": {"password": "adminpass", "emails": ["me@example.org"]}}
    ```

`admin.password` is the password given to the `admin` account when it is created (by `hani2 setup` or at the first server start). Changing it later has no effect on the existing account; use `hani2 users passwd admin`.

Admins can open `/admin` and have extra controls in the negotiation interface: the session settings, the admin-only tools, the opponent picker and the message helpers. See [Admin console](admin.md).

## Managing users

The user store is two JSON files in the settings folder:

- `users.json` maps each username to its password hash,
- `users_meta.json` holds the metadata: `created`, `email`, `full_name`, `consented`, `consent_date`, `role` and, for OAuth users, `oauth`.

Use the command line:

```bash
hani2 users list
hani2 users add alice --email alice@example.org
hani2 users add bob --admin
hani2 users passwd alice
hani2 users remove bob
```

or the **Users** section of the admin console. The `admin` account cannot be deleted, and admins cannot delete themselves.

### Default accounts

`hani2 setup` and every server start create two default accounts when they are missing: `admin` (password from `admin.password`, default `adminpass`) and `user` (password `userpass`). Change both passwords before a public deployment:

```bash
hani2 users passwd admin
hani2 users passwd user
```

While an account still has its default password, every server start prints a warning such as

```text
[hani2] WARNING: the account 'admin' still has its default password; set one with `hani2 users passwd admin`
```

When the server listens on an interface other machines can reach (for example `hani2 --host 0.0.0.0`), the `admin` account cannot log in with `adminpass`. The login page explains why, and the admin sets a new password on the server with `hani2 users passwd admin` and logs in again. A server that listens only on `127.0.0.1` or `localhost` (the default) still accepts the default password, so a local install works as soon as it is set up. The `user` account is only warned about, never refused.

The server only knows the interface it listens on. Behind a reverse proxy it usually listens on `127.0.0.1`, so set `auth.default_password_login` to `"refuse"` to apply the rule there too. Set it to `"allow"` to switch the rule off.

### Password storage

Passwords are stored as PBKDF2-SHA256 hashes with a random salt and 200,000 iterations (`pbkdf2_sha256$<iterations>$<salt>$<hash>`). If you edit `users.json` by hand and enter a plain-text password, it still works and is replaced with a hash at the next successful login.

## The playground and guests

`/play` works without an account while `playground.enabled` is `true` in `env.json` (the default). Set it to `false` to close the playground; Prolific links (`/play?PROLIFIC_PID=...`) keep working.

- A guest session is keyed by a `hani2_guest` cookie, so reloading the page keeps the same session. Its results are stored under the user name `guest_<id>`, one folder per browser.
- A Prolific session is keyed by the PID, so a participant can return from another browser.
- A browser that is logged in (with a password, OAuth or [a trusted website](#sign-in-from-a-trusted-website))
  plays `/play` under its own account: its playground results are stored with the account and
  appear in its **My Results** tab. It is a separate session from the account's `/app` one and
  never counts towards a study's balance. An admin stays an admin there.

Some tools are hidden in sessions without an account (see [Tools](tools.md)), and admin-only settings stay admin-only.

## The `?admin=1` switch

An admin's session on `/app` or `/play` is always in the *admin view*: the admin badge, the opponent's type and the opponent picker. `?admin=1` and `?opponents=` are admin options. For anyone else they are ignored, so a shared link cannot unlock the opponent picker or pick arbitrary opponent classes. `?group=` works for everyone.

To let a user of a trusted website (for example an organiser on the ANAC site) use these options, make their HANI2 account an admin on the *Users* page of the admin console. Signing in again from the website keeps the role. Or let the website decide: with `trust_admin_claim` on, its `admin` claim makes the account an admin (see [Admins from the website](#admins-from-the-website)).

## Logging

Logins, failed logins and logouts are written to the event log (`login`, `login_failed`, `logout`), and so are admin grants and removals by a trusted website's `admin` claim (`admin_granted`, `admin_revoked`). See [Studies and results](studies.md).

## Production checklist

Before you open a server to other people:

1. **Change the default passwords** with `hani2 users passwd admin` and `hani2 users passwd user`. Every server start warns while either account still has its default password. Only the `admin` login is refused, and only when the server listens on a non-loopback interface (see [Default accounts](#default-accounts)).
2. **Serve over HTTPS behind a reverse proxy** that forwards WebSocket upgrades for `/api/ws/` (see [Troubleshooting](../getting-started/installation.md#troubleshooting) and [Serving under a sub-path](../getting-started/installation.md#serving-under-a-sub-path)). The server then usually listens on `127.0.0.1`, so set `auth.default_password_login` to `"refuse"` to keep refusing the default `admin` password.
3. **Set an explicit `auth.cookie_secret`** when several installations must accept the same login cookies. Generate one with:

    ```bash
    python -c "import secrets; print(secrets.token_urlsafe(32))"
    ```

4. **Keep `admin.emails` short.** Every account whose email is in the list is an admin, so list only the people who need the admin console.
