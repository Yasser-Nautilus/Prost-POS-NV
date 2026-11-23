# Build dependency security check

On 2026-11-23 the existing lockfile returned four high-rated package findings:
nanoid, postcss, source-map-js and vite. `npm audit fix --ignore-scripts` updated
within the existing package.json ranges, without a forced major upgrade.

Resolved versions verified with npm ls:

| Package | Updated version |
| --- | --- |
| vite | 8.3.8 |
| postcss | 8.5.33 |
| nanoid | 3.3.20 |
| source-map-js | 1.2.4 |

The resulting npm audit returns zero known findings at that check time. These are
primarily build/development-toolchain advisories, not demonstrated exploits of the
packaged POS. A zero audit result is not a guarantee that all code is secure.
The lockfile is committed; CI runs npm ci, npm audit --audit-level=high, lint,
production build and the real Qt/React bridge tests. It also retains the Python
suite and recovery drills.

If a future advisory blocks CI, inspect the advisory, dependency path, affected
range, fixed releases and actual exposure. Prefer compatible updates and rerun
build plus rendered tests. Do not use npm audit fix --force as a default. If a fix
is unavailable, any temporary exception must name the advisory, reason, owner,
expiry and mitigation in a reviewed change; there is no blanket suppression.
