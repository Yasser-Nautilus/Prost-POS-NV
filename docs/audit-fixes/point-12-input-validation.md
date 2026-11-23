# Point 12: unit counts, counted cash, PIN entry and explicit payments

Unit quantities are positive integer pieces, as specified by OrderItem and the
existing schema comment. The controller rejects invalid add quantities before
changing a cart and rejects fractional/noninteger quantity deltas. Service checks
cover create/amend even without a product catalogue. SQLite v10 triggers reject
new fractional order-item writes from alternate paths. Existing historical rows
are not rounded or rewritten. A normal integer decrement retains the existing
remove-at-zero behavior and existing saved-amendment authorization.

Physical cash counts must be finite, nonnegative money values. The controller
checks before rounding EGP to piasters, so a small negative cannot round to zero.
The service requires nonnegative integer piasters. Missing bridge counts are no
longer treated as zero; an explicit zero count remains valid. Handover uses the
same validation. No negative adjustment policy is changed: a nonnegative counted
amount can still create a negative variance against expected cash.

PaymentDialog requires an explicit cash input. Empty, malformed, negative or
underpaid cash is rejected; zero is never replaced with the order total. Card and
online payments still collect the full total, and no partial-payment workflow is
introduced. The payment coordinator also rejects nonfinite/negative inputs before
creating a paid state. Quick cash and overpayment/change still work.

PIN creation historically allows a minimum of four characters, without an upper
limit or digits-only rule. Existing hashes cannot reveal how long a credential is.
Therefore accounts are not changed or constrained to four digits: login and the
manager dialog now accept longer keypad input plus editable masked text input.
User management no longer truncates entered credentials to four digits. This
preserves existing long and nonnumeric credentials rather than locking them out.
The backend minimum length and authentication/throttle checks remain intact.

Tests include malformed public bridge values, direct service/repository paths,
no-side-effect count/payment rejection, explicit zero count, long/text login and
manager verification. Rendered production flows reject empty/zero cash before a
valid payment, and real login/manager dialogs accept a 16-digit credential and an
existing text credential. The older transaction rollback test now injects its
invalid persisted-state probe below the newly strict controller, retaining its
original rollback/retry assertions instead of relying on accepting an invalid add.
