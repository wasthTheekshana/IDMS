# Runbook: Secret Rotation

Rotate immediately if a secret may have leaked; otherwise quarterly.

## Inventory (all set via .env.docker / CI secrets — never in code)

| Secret                                  | Where issued                       | Consumers                  |
| --------------------------------------- | ---------------------------------- | -------------------------- |
| SECRET_KEY / JWT_SECRET_KEY             | generated (`openssl rand -hex 32`) | api                        |
| DATABASE_URL password                   | Postgres                           | api, worker, beat, migrate |
| R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY | Cloudflare dashboard               | api, worker, backups       |
| MISTRAL_API_KEY                         | Mistral console                    | worker (OCR, embeddings)   |
| GOOGLE_AI_API_KEY                       | Google AI Studio                   | api/worker (Gemini)        |
| GROQ_API_KEY                            | Groq console                       | api                        |
| SENTRY_DSN                              | Sentry project settings            | api, worker                |
| BACKUP_PASSPHRASE                       | generated, stored in secret store  | backup/restore scripts     |

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
