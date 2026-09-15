# Runbook: Secret Rotation

Rotate immediately if a secret may have leaked; otherwise quarterly.

## Inventory (all set via .env.docker / CI secrets — never in code)

| Secret                                  | Where issued                       | Consumers                   |
| --------------------------------------- | ---------------------------------- | --------------------------- |
| SECRET_KEY / JWT_SECRET_KEY             | generated (`openssl rand -hex 32`) | api                         |
| DATABASE_URL password                   | Postgres                           | api, worker, beat, migrate  |
| PLATFORM_ADMIN_DB_PASSWORD              | Postgres (`idms_platform_admin`)   | api (platform-admin routes) |
| PLATFORM_ADMIN_DATABASE_URL             | derived from the above             | api (platform-admin routes) |
| R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | Cloudflare dashboard               | api, worker, backups        |
| MISTRAL_API_KEY                         | Mistral console                    | worker (OCR, embeddings)    |
| GOOGLE_AI_API_KEY                       | Google AI Studio                   | api/worker (Gemini)         |
| GROQ_API_KEY                            | Groq console                       | api                         |
| SENTRY_DSN                              | Sentry project settings            | api, worker                 |
| BACKUP_PASSPHRASE                       | generated, stored in secret store  | backup/restore scripts      |

## Procedure

1. Issue the new credential at the provider (keep the old one active).
2. Update `.env.docker` on the host and the CI secret store.
3. Rolling restart: `docker compose -f infra/docker-compose.yml up -d api worker beat`
4. Smoke test the affected path (login for JWT, upload for R2/OCR,
   AI chat for Gemini/Groq).
5. Revoke the old credential at the provider.
6. **JWT_SECRET_KEY note:** rotation invalidates all sessions — users
   must log in again. Schedule off-peak and announce.
7. **BACKUP_PASSPHRASE note:** old backups stay encrypted with the old
   passphrase — archive the old passphrase in the secret store with a
   dated label; never delete it while backups encrypted with it exist.

---

## Platform admin credentials

The platform super admin is a separate identity from any organization user
(table `platform_admins`), and platform-admin API routes read across every
org through a dedicated Postgres role, `idms_platform_admin`, which carries
the `BYPASSRLS` attribute and is granted `SELECT` only.

### Required environment variables

Both are documented in `.env.example` and must be set for the **api**
service (worker/beat/migrate do not need them):

| Variable                      | Value                                                                    |
| ----------------------------- | ------------------------------------------------------------------------ |
| `PLATFORM_ADMIN_DB_PASSWORD`  | password for the `idms_platform_admin` Postgres role                     |
| `PLATFORM_ADMIN_DATABASE_URL` | `postgresql+asyncpg://idms_platform_admin:<password>@postgres:5432/idms` |

If `PLATFORM_ADMIN_DATABASE_URL` is unset, the API boots but any request to a
platform-admin route fails with a clear `RuntimeError` naming the variable.

### Rotating the role password

```bash
psql -c "ALTER ROLE idms_platform_admin WITH PASSWORD '<new>'"
```

Then update `PLATFORM_ADMIN_DB_PASSWORD` and `PLATFORM_ADMIN_DATABASE_URL`
in `.env.docker` / the CI secret store and restart `api` (step 3 above).

### Bootstrapping the first platform admin account

There is no API route that creates a platform admin — it is a deliberate
out-of-band step, run once per environment:

```bash
# locally
cd api && uv run python -m app.scripts.create_platform_admin --email you@example.com

# against a running deployment
docker compose -f infra/docker-compose.yml exec api \
  python -m app.scripts.create_platform_admin --email you@example.com
```

The script prompts for the password twice (minimum 10 characters), validates
the email's shape, and refuses to run if an admin with that email already
exists. Log in at `/login` with those credentials; the web app redirects
platform-admin accounts to `/admin`.

### Revoking an admin

Set `is_active = false` on the `platform_admins` row. The flag is checked on
every platform-admin request and on token refresh, so an already-issued
access token stops working on its next request — no need to rotate
`JWT_SECRET_KEY`.

```sql
UPDATE platform_admins SET is_active = false WHERE email = 'them@example.com';
```
