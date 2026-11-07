# Integration runbook (issue #2)

Flip one flag at a time, in this order. After each flip: restart `make api`, check `GET /health`, run `make test`, then click the demo path (`qa_checklist.md` rows 1-12).

| Step | Flip | Needs first | Confirm end to end | Status |
|---|---|---|---|---|
| 1 | `MOCK_DATA=0` | P1: SQLite seeded with Sam | Dashboard loads; transactions and pots come from SQLite | [ ] |
| 2 | `MOCK_FORECAST=0` | P2: engine, pots, simulate, alerts | Safe to spend matches the breakdown; dip near 26 Dec; eating-out alert; rent pot counted | [ ] |
| 3 | `MOCK_AGENT=0` | P3: tool loop + keys | Shirt question: affordable, Black Friday 27 Nov, `numbers_used` filled | [ ] |

## Planted demo events (must all appear with real modules)
- [ ] Rent pot ("Dec + Jan rent", £950) protected in safe to spend
- [ ] Balance dip and risk event near 26 Dec
- [ ] Eating-out spike alert with a suggested action
- [ ] Shirt verdict suggests waiting for Black Friday (needs the `clothing` category fix)

## Bug handling
Log each bug as a comment on the owning module's issue using the template in `qa_checklist.md`. Owner fixes within 15 minutes or flips their flag back to 1. Integration never blocks anyone.

## Final demo flags (record here and in the README)
| Flag | Value | Reason |
|---|---|---|
| MOCK_DATA | | |
| MOCK_FORECAST | | |
| MOCK_AGENT | | |

Done when: the demo path works 3 times in a row with these flags.
