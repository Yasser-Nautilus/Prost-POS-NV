# Point 14: local business dates and historical report periods

Shift opened_at is stored by SQLite datetime('now','localtime'), a local wall-clock
string without an offset. Its calendar date must not receive a second localtime
conversion. New shifts now set business_date in the same INSERT using local now.
The old v4-to-v5 migration derives the date directly from the stored opening date.
Schema v12 fills only missing business_date values the same way. Shift report
lookup honors an existing business_date, falling back to the local opening date
only for NULL.

Non-NULL historical dates are deliberately not rewritten. The database cannot
say whether an existing differing date was a faulty past backfill or a deliberate
value. Repair requires reviewing those rows and authorizing the specific change.
This update does not claim to repair all previously shifted historical dates.

Printed daily summaries now carry the requested report date and scope through
the controller to the template. Calendar reports show the requested day from
00:00 to 23:59:59; shift reports show their actual opened/closed period, which may
span midnight. The report date/shift ID and the actual print timestamp are separate
labeled fields. Calendar reports still do not mark any shift summary as printed.
A failed shift-period lookup does not silently print a periodless shift report.

Tests run under Africa/Cairo, including winter/summer 23:30 and after-midnight
stored local timestamps, new shifts, legacy backfill and repeated v12 upgrades.
Already-set historical dates are proven unchanged. Real template text calls are
captured for a historical calendar day and a midnight-spanning shift; an image
preview of those exact captured text/style calls was inspected for report date,
period, print timestamp and amounts. This preview is not a hardware print test
or a physical ESC/POS raster emulator. Existing real driver/template regressions
and the full rendered application workflow remain green.
