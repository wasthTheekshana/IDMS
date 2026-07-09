# User Management (Admin-Created Accounts) Implementation Plan (Stage B — Task 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Org admins/owners create teammate accounts directly (no email invites): list users, create with role, change role, deactivate. Deactivated users cannot log in.

**Architecture:** Reuses existing `UserRole` enum, `require_role` dependency, `CurrentUser.role`, and `UserRepository.create`. Adds list/update repo methods, three endpoints on the users router, an `is_active` check in login, and a Team panel in the dashboard.

**Role rules:**

- OWNER may create/modify users with roles admin/member/viewer.
- ADMIN may create/modify users with roles member/viewer only (cannot touch admins or owner).
- Nobody modifies the OWNER or their own account through these endpoints.
- MEMBER/VIEWER get 403 on create/update; any authenticated user may list teammates.

## Global Constraints

Same as prior Stage plans (Python 3.12, ruff/mypy, conventional commits, tests only against `idms_test` via env override).

---

### Task 1: Login rejects deactivated users

**Files:** `api/app/services/auth.py` (login), test `api/tests/integration/test_user_management.py`

- [ ] Failing test: register, deactivate via SQL, login → 401 "Account is deactivated".
- [ ] Implement: after the locked check, `if not user.is_active: raise 401`.
- [ ] Suite green; commit `fix(api): reject login for deactivated users`.

### Task 2: List org users — GET /api/v1/users

**Files:** `api/app/repositories/user.py` (`list_by_org`), `api/app/api/v1/users.py`, same test file.

- [ ] Failing test: register → GET /api/v1/users → 200, contains the owner; second org's user not visible; unauthenticated → 401.
- [ ] Implement `list_by_org(org_id) -> list[User]` (order by created_at) + route (before `/{user_id}`) returning `list[UserResponse]`.
- [ ] Suite green; commit `feat(api): list org users endpoint`.

### Task 3: Create user — POST /api/v1/users

**Files:** `api/app/schemas/user.py` (`UserCreateRequest`), `api/app/api/v1/users.py`, `api/app/services/users.py` (new service), same test file.

**Rules:** password min 10 chars (match register), role must be within creator's assignable set, duplicate email → 409, member → 403.

- [ ] Failing tests: owner creates member (201, correct role, can log in); member attempt → 403; duplicate email → 409; admin creating admin → 403.
- [ ] Implement service `create_org_user(body, current_user, session)` enforcing the role matrix; route with `require_role(UserRole.OWNER, UserRole.ADMIN)`.
- [ ] Suite green; commit `feat(api): admin-created user accounts with role rules`.

### Task 4: Update user — PATCH /api/v1/users/{user_id}

**Files:** `api/app/repositories/user.py` (`update_user`), `api/app/schemas/user.py` (`UserUpdateRequest`: optional role, optional is_active), `api/app/api/v1/users.py`, same test file.

**Rules:** target must be in same org (404 otherwise); cannot modify OWNER (403); cannot modify self (403); ADMIN cannot modify ADMIN (403); role changes limited to assignable set.

- [ ] Failing tests: owner deactivates member (200, is_active false, login now 401); owner promotes member→admin; admin demoting admin → 403; modifying owner → 403; self-modify → 403.
- [ ] Implement repo `update_user(user, *, role=None, is_active=None)` + service `update_org_user` + route.
- [ ] Suite green; commit `feat(api): update user role and active status with protection rules`.

### Task 5: Team panel (web)

**Files:** Create `web/components/TeamPanel.tsx`; modify `web/app/dashboard/page.tsx` (nav item "Team" + view).

- [ ] Component: fetch GET /users; table (email, role, status, created); create form (email/password/role select); activate/deactivate button + role dropdown per row; management controls hidden unless current role is owner/admin (decode from /users/me). Errors surfaced inline (409, 403).
- [ ] `npm run lint && npm run type-check` green.
- [ ] Commit `feat(web): team panel — admin-created accounts, roles, deactivation`.

## Definition of Done

Full suite green; owner can create/deactivate users and change roles from the dashboard; deactivated users cannot log in; cross-org isolation intact.
