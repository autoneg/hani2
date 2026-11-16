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
    "allow_registration": true
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
| `cookie_secret` | `""` | Secret used to sign the login cookie. When empty, HANI2 generates one and keeps it in `settings/.cookie_secret`, so logins survive restarts. Set it explicitly when several installations must accept the same cookies. |
| `enforce_consent` | `false` | When `true`, a logged-in user who has not consented sees the consent form (the content of `consent.md`) and must agree and sign with their full name before negotiating. The server does not block admins who have not consented, but the login page still sends them to the consent form. |
| `allow_registration` | `true` | Shows the registration form. Registration is always off in `oauth` and `none` modes. |

The login cookie (`hani2_auth`) is valid for 30 days.

## Registration

With registration allowed, the login page offers a **Register** form that asks for a username, password (twice), email (twice), full name and agreement to the consent text. A user who ticks the consent box is stored as consented with the date.

Usernames must be at most 64 characters with no spaces or path characters (`/ \ : * ? " < > |`). The names `ai`, `agent`, `guest` and `admin2`, and anything starting with `prolific_`, are reserved. Passwords need at least 4 characters.

The web app has no form for changing one's own password. Admins reset passwords in the admin console or with `hani2 users passwd`. (The API endpoint `POST /api/auth/password` with `old` and `new` exists for clients that need it.)

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

A provider counts as configured when it has a `key` and a `secret` and `enabled` is not `false`.

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

HANI2 asks for `openid email profile`. A Google user `jane.doe@example.org` becomes `g_jane.doe`.

OAuth users are created on their first login and do not have a usable password. After a successful login they are sent to `/app`. Failures send them back to `/login` with an `error` parameter (`oauth_state`, `oauth_token` or `oauth_failed`).

## Admins

A user is an admin when any of these is true:

- the username is `admin`,
- the account has the role `admin` (set with `hani2 users add --admin`, or in the admin console),
- the account's email is listed in `admin.emails` in `env.json` (case-insensitive). This is the simplest way to make OAuth users admins:

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

`hani2 setup` and every server start create two default accounts when they are missing: `admin` (password from `admin.password`, default `adminpass`) and `user` (password `userpass`). Change both passwords before a public deployment.

### Password storage

Passwords are stored as PBKDF2-SHA256 hashes with a random salt and 200,000 iterations (`pbkdf2_sha256$<iterations>$<salt>$<hash>`). If you edit `users.json` by hand and enter a plain-text password, it still works and is replaced with a hash at the next successful login.

## The playground and guests

`/play` works without an account while `playground.enabled` is `true` in `env.json` (the default). Set it to `false` to close the playground; Prolific links (`/play?PROLIFIC_PID=...`) keep working.

- A guest session is keyed by a `hani2_guest` cookie, so reloading the page keeps the same session. Its results are stored under the user name `guest_<id>`, one folder per browser.
- A Prolific session is keyed by the PID, so a participant can return from another browser.
- An admin who is logged in and opens `/play` is still recognized as an admin.

Some tools are hidden in guest sessions (see [Tools](tools.md)), and admin-only settings stay admin-only.

## The `?admin=1` switch

Adding `?admin=1` (or `true`, `yes`, `on`) to the URL of `/app` or `/play` turns on the *admin view* of that session for anyone, except Prolific participants. It shows the admin badge, the opponent's type and the opponent picker, which is useful for demonstrations and for testing opponents from the playground.

It does not make the user an admin: admin-only tools, admin settings, the message helpers and the admin console still require an admin account.

## Logging

Logins, failed logins and logouts are written to the event log (`login`, `login_failed`, `logout`). See [Studies and results](studies.md).
