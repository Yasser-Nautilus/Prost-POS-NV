# Point 13: authentication audit composition and persistence

Production main now injects the actual AuditRepository into AuthService before
building the UI, matching the already-audited test composition. Failed login and
manager verification events no longer use nonexistent actor 0. Schema v11 makes
audit_log.user_id nullable while retaining its foreign key for known actors.
Migration copies every existing column and ID without changing history; repeated
startup is safe. No synthetic human account is created.

A rejected authentication has no verified human actor, even when a user ID was
supplied or a valid cashier credential was used for an unauthorized manager
request. The actor is NULL and the attempted ID is context in details. The log
contains the stable surface key, generic reason and attempt count, never the
submitted credential, credential hash, salt or session token. Throttle keys and
lockout behavior are unchanged.

User creation now writes a user_created event with the authenticated administrator
as actor and the new user's ID as entity. Internal bootstrap creation without a
session is explicitly System/NULL, never attributed to the new user. Details are
an allowlist of username, role and cashier slot. Account save and audit save share
one transaction in the production composition; audit failure rolls back account
creation instead of silently leaving an unaudited account.

AuditRepository.log now owns an atomic transaction/savepoint. A failed auth-audit
write cannot leave a pending database transaction for unrelated work to commit.
Authentication denial and attempt counting still happen if logging fails; the
failure is reported at error level rather than hidden at debug level. No login
success, credential update or access-control policy was added in this scope.

Regression tests execute the real main composition up to UI creation, persist
unknown/known-attempt login and override failures, preserve throttling under
logging failure, verify creation actor and secret omission, enforce account/audit
rollback, retain cashier restrictions, and migrate populated v10 audit rows with
all fields/IDs intact. There is no UI change in this fix.
