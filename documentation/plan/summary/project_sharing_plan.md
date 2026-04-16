# Plan: Project Sharing Feature

## Context
Users need to share projects with collaborators. Two flows are required:
1. Search for existing app users and add them directly as viewer/contributor
2. Generate a shareable email link with a role assigned; recipient is confirmed on the project after login/register

**Roles:**
- **Viewer** — read-only access
- **Contributor** — read/write access, cannot delete projects or property lists

Owner is the only one who can manage sharing.

---

## Backend

### 1. New `ProjectInvitation` Model
File: `property/models/stage1_models.py`

Fields:
- `uuid`, `project` (FK→Project), `invited_by` (FK→User), `invited_email` (EmailField, indexed)
- `role` choices: `viewer`, `contributor`
- `status` choices: `pending`, `accepted`, `declined`, `expired`, `revoked`
- `token_hash` (sha256 of signed token, unique, indexed) — raw token is never stored
- `accepted_by` (FK→User, nullable), `accepted_at`, `created_at`, `expires_at`

### 2. Token Utility
New file: `property/utils/invitation_tokens.py`
- `generate_invite_token(invitation_uuid)` → `TimestampSigner(salt='project-invite-salt').sign(uuid)`
- `verify_invite_token(token)` → unsign with `max_age=604800` (7 days); raises `BadSignature`/`SignatureExpired`
- `hash_token(token)` → `sha256(token).hexdigest()`

### 3. Migration
Run `makemigrations property` — no existing model is modified.

### 4. New Serializers
File: `property/serializers.py`
- `ProjectInvitationSerializer` — uuid, invited_email, role, status, invited_by_email, invite_url (None; set manually on creation), expires_at, created_at
- `ProjectMembersSerializer` — owner, viewers, contributors (each a `MemberSerializer` with email, first_name, last_name)
- `UserSearchSerializer` — email, first_name, last_name
- `AppNotificationSerializer` — uuid, notification_type, title, message, related_object_uuid, related_object_type, is_read, created_at, actor email/name

### 5. New `AppNotification` Model
File: `property/models/stage1_models.py`

Extensible notification model for all in-app alerts:

Fields:
- `uuid`, `recipient` (FK→User), `actor` (FK→User, nullable — system notifications have no actor)
- `notification_type` choices: `invite_received`, `invite_accepted`, `invite_declined`, `member_removed` (expandable to `project_updated`, `comment_left`, etc.)
- `title` (CharField), `message` (TextField)
- `related_object_uuid` (UUIDField, nullable) — e.g. project UUID
- `related_object_type` (CharField, nullable) — e.g. `'project'`
- `is_read` (BooleanField, default False)
- `created_at`

Index on `(recipient, is_read, created_at)`.

Helper: `create_notification(recipient, actor, notification_type, title, message, related_object_uuid, related_object_type)` utility function in `property/utils/notifications.py`.

### 6. New Endpoints on `ProjectViewSet`
File: `property/views.py` — add `@action` decorators to `ProjectViewSet`

| Method | url_path | Description | Auth |
|--------|----------|-------------|------|
| GET | `members/` | List owner + viewers + contributors | any member |
| GET | `invitations/` | List pending invitations | owner only |
| POST | `invite/` | Create invite, send email | owner only |
| DELETE | `invitations/{invitation_uuid}/` | Revoke invite | owner only |
| DELETE | `members/{member_email}/` | Remove a member | owner only |
| GET | `preview-invite/` (detail=False) | Get invite details without accepting | public (token auth) |
| POST | `accept-invite/` (detail=False) | Accept invite | IsAuthenticated |
| POST | `decline-invite/` (detail=False) | Decline invite | IsAuthenticated |

### New `NotificationViewSet`
File: `property/views.py` — new viewset, registered on router

| Method | url_path | Description |
|--------|----------|-------------|
| GET | `notifications/` | List notifications for request.user |
| POST | `notifications/{uuid}/read/` | Mark one as read |
| POST | `notifications/read-all/` | Mark all as read |
| GET | `notifications/unread-count/` | Return `{ count: N }` |

**`invite/` logic:**
1. Assert request.user == project.owner
2. Return 400 if user already member
3. Return existing pending invite if idempotent match
4. `token = generate_invite_token(uuid)`, `token_hash = hash_token(token)`
5. Create `ProjectInvitation(..., expires_at=now+7d)`
6. `invite_url = f"{FRONTEND_URL}/accept-invite?token={token}"`
7. Send email via `send_mail`
8. If invited user already has an account: `create_notification(recipient=invited_user, type='invite_received', ...)`
9. Return serialized invitation + inject `invite_url`

**`preview-invite/` logic (GET, no auth required):**
1. `verify_invite_token(token)` → 400 on failure
2. Lookup `ProjectInvitation` by `hash_token(token)` where `status='pending'`; 400 if not found
3. Return: `{ project_uuid, project_title, invited_by_name, invited_by_email, role, expires_at }` — enough to render the confirmation screen

**`accept-invite/` logic:**
1. `verify_invite_token(token)` → 400 on failure
2. Lookup `ProjectInvitation` by `hash_token(token)` where `status='pending'`; 400 if not found
3. Assert `request.user.email == invitation.invited_email`; 403 on mismatch
4. Add user to `project.viewers` or `project.contributors`
5. Mark invitation accepted
6. `create_notification(recipient=project.owner, actor=request.user, type='invite_accepted', ...)`
7. Return `{ project_uuid, role }`

**`decline-invite/` logic:**
1–3. Same as accept
4. Mark `invitation.status = 'declined'`
5. `create_notification(recipient=project.owner, actor=request.user, type='invite_declined', ...)`
6. Return 200 `{ "detail": "Invitation declined" }`

### 7. WebSocket Notification Consumer
File: `property/consumers.py` (new)

Django Channels is already installed. Add a `NotificationConsumer`:
- Authenticated WebSocket connection at `ws://domain/ws/notifications/`
- On connect: add user to group `notifications_{user_id}`
- `send_ws_notification(user_id, payload)` utility — calls `channel_layer.group_send` — called from `create_notification` if Channels available
- Frontend connects on login, disconnects on logout

### 8. User Search Endpoint
File: `accounts/views.py` — add `search` action to `UserViewSet`

```
GET /api/accounts/users/search/?q=<string>
```
- Filter by `email__icontains` OR `first_name__icontains` OR `last_name__icontains`
- Min 2 chars, limit 10 results
- Exclude request.user from results

---

## Frontend

### 9. New Model Interfaces
File: `src/app/shared/models/project-models.ts`
- `ProjectInvitation`, `ProjectMember`, `ProjectMembers`, `CreateInviteDto`, `AcceptInviteResponse`, `UserSearchResult`, `AppNotification`

### 10. New `SharingService`
New file: `src/app/core/services/sharing-service/sharing.service.ts`
- `getMembers(projectUuid)`, `getInvitations(projectUuid)`, `createInvite(projectUuid, dto)`
- `revokeInvite(projectUuid, invitationUuid)`, `removeMember(projectUuid, memberEmail)`
- `previewInvite(token)` → GET `property/projects/preview-invite/?token=...` (no auth)
- `acceptInvite(token)` → POST `property/projects/accept-invite/`
- `declineInvite(token)` → POST `property/projects/decline-invite/`
- `searchUsers(q)` → GET `accounts/users/search/?q=...`

### 11. New `NotificationService`
New file: `src/app/core/services/notification-service/notification.service.ts`
- REST methods: `getNotifications()`, `markRead(uuid)`, `markAllRead()`, `getUnreadCount()`
- WebSocket: `connect()` / `disconnect()` — connects to `ws://.../ws/notifications/`, emits incoming messages to a `Subject<AppNotification>`
- `notifications$` observable consumed by the store

### 12. New `NotificationStore`
New file: `src/app/core/stores/notification-store/notification.store.ts`
- Signals: `notifications`, `unreadCount`, `isConnected`
- On auth login: call `notificationService.connect()` + load initial list + unread count
- On auth logout: call `notificationService.disconnect()`
- Incoming WS messages appended to `notifications` signal, `unreadCount` incremented

### 13. Notification Bell UI Component
New file: `src/app/shared/components/notification-bell/notification-bell.component.ts`
- Bell icon with red badge showing `unreadCount`
- Clicking opens a dropdown panel listing recent notifications (title, message, time ago, read/unread styling)
- "Mark all read" button
- Individual notification click: mark read + navigate to `related_object_uuid` if applicable
- Add to main navbar/header component

### 14. `AcceptInviteComponent` + Route — Confirmation Screen
New file: `src/app/features/auth/accept-invite/accept-invite.component.ts`

**Logic:**
1. Read token from query params
2. If NOT authenticated: save token to localStorage, redirect to `/login`
3. If authenticated: call `sharingService.previewInvite(token)` (no auth required on backend)
4. Display confirmation card:
   - "**{invited_by_name}** has invited you to join **{project_title}** as a **{role}**"
   - Two buttons: **Accept** and **Decline**
   - Expiry note: "This invite expires on {expires_at}"
5. On **Accept**: call `sharingService.acceptInvite(token)` → navigate to `/projects/{uuid}`
6. On **Decline**: call `sharingService.declineInvite(token)` → navigate to `/projects` with toast "Invitation declined"
7. On token error (expired/invalid): show error state instead of the card

Register in `app.routes.ts` at path `accept-invite` **without** authGuard.

### 15. Modify `AuthStore` Post-Login/Register
File: `src/app/core/stores/auth-store/auth.store.ts`

In both `login` and `register` success callbacks, after setting state:
1. Start `notificationService.connect()` (always)
2. Check `localStorage.getItem('pending_invite_token')`
3. If present: remove from storage, navigate to `/accept-invite?token={token}` (show confirmation screen)
4. If absent: existing `router.navigate(['/'])`

### 16. Upgrade Project Settings — Sharing UI
File: `src/app/features/projects/components/project-settings/project-settings.component.ts` (and template)

New signals: `members`, `pendingInvitations`, `userSearchResults`, `lastGeneratedInviteUrl`, `inviteMode` (`'direct' | 'link'`)

**Direct-add tab (Option 1):**
- Text input → debounce 300ms, min 2 chars → call `searchUsers(q)` → dropdown with `First Last (email)` options
- Selecting a user + role → PATCH project (existing `viewers`/`contributors` SlugRelatedField path)
- Member list rows each have a "Remove" button → `removeMember()`

**Invite-link tab (Option 2):**
- Email input + role dropdown + "Send Invite" button → `createInvite()` → show read-only invite URL with Copy button
- Pending invitations table: Email | Role | Sent | Expires | Revoke button

### 17. Upgrade Project Creation Wizard Step 3
File: `src/app/features/projects/components/project-create/steps/step3-collaboration.component.ts`
- Replace plain email input with user-search autocomplete (same as Step 16 direct-add)
- No invite-link flow here (project doesn't exist yet)

---

## Invite-Through-Auth Flow

**Unauthenticated user:**
```
Click /accept-invite?token=xxx
  → AcceptInviteComponent: not authenticated
  → Save token to localStorage('pending_invite_token')
  → Redirect to /login (or /register)
  → After login/register: AuthStore redirects to /accept-invite?token=xxx
  → AcceptInviteComponent: now authenticated
  → Call previewInvite(token) → show confirmation screen
  → User clicks Accept → acceptInvite(token) → navigate to /projects/{uuid}
  → User clicks Decline → declineInvite(token) → navigate to /projects
```

**Authenticated user:**
```
Click /accept-invite?token=xxx
  → AcceptInviteComponent: authenticated
  → Call previewInvite(token) → show confirmation screen
  → User clicks Accept → acceptInvite(token) → navigate to /projects/{uuid}
  → User clicks Decline → declineInvite(token) → navigate to /projects
```

**Notifications triggered:**
- Owner sends invite → `invite_received` notification to invited user (if account exists)
- User accepts → `invite_accepted` notification to project owner
- User declines → `invite_declined` notification to project owner
- Owner removes member → `member_removed` notification to removed user

Error cases:
- Token expired: 400 `invalid_or_expired_token` → show error card "This invite has expired"
- Email mismatch: 403 `email_mismatch` → show error card "This invite was sent to a different email"
- Already used/revoked: 400 `invitation_already_used` → show error card

---

## Implementation Order

**Backend first:**
1. `ProjectInvitation` + `AppNotification` models + migration
2. `invitation_tokens.py` + `notifications.py` utilities
3. Serializers
4. `ProjectViewSet` sharing actions (incl. `preview-invite`, `decline-invite`)
5. `NotificationViewSet`
6. `NotificationConsumer` (WebSocket)
7. `UserViewSet` search action
8. Tests

**Frontend second:**
9. Model interfaces
10. `SharingService` + `NotificationService`
11. `NotificationStore`
12. Notification bell UI component + wire into navbar
13. `AcceptInviteComponent` (confirmation screen) + route
14. `AuthStore` pending-invite + notification connect logic
15. Project settings sharing UI
16. Wizard step 3 autocomplete

---

## Verification
- Direct add: owner adds a user by email/name → user appears in project members list → user can access project
- Invite link (logged in): click link → confirmation screen → accept → on project as viewer/contributor
- Invite link (logged in): click link → confirmation screen → decline → back to /projects, owner notified
- Invite link (not logged in): click link → login → confirmation screen → accept → on project as member
- Invite link (no account): click link → register → confirmation screen → accept → on project as member
- Token expiry: >7 days mock → preview returns 400 → error card shown
- Email mismatch: invite sent to A, accepted by B → 403 → error card shown
- Revoke invite: owner revokes → preview/accept both return 400
- Remove member: owner removes viewer → user loses access → removed user gets in-app notification
- Notifications: invite sent → bell badge increments for recipient; accept/decline → bell badge for owner
- WebSocket: notification arrives in real time without page refresh
- Run existing project/account tests
