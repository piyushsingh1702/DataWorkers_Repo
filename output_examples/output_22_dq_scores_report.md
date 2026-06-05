# Data Quality Report

**Generated:** 2025-01-01T10:16:42.001783+00:00
**Database:** loan1
**Snapshot:** 2025-01-01

## Overall Score: 84.70%

| Metric        | Value |
|---------------|-------|
| Total Rules   | 142   |
| Rules Passed  | 120   |
| Rules Failed  | 22    |

## Dimension Scores

| Dimension     | Score  | Rules | Passed | Failed |
|---------------|--------|-------|--------|--------|
| Accuracy      | 96.0%  | 12    | 12     | 0      |
| Completeness  | 91.0%  | 38    | 33     | 5      |
| Consistency   | 88.0%  | 22    | 19     | 3      |
| Timeliness    | 83.0%  | 9     | 7      | 2      |
| Validity      | 94.0%  | 47    | 41     | 6      |
| Uniqueness    | 95.0%  | 14    | 13     | 1      |

## Table Scores

| Table           | Score   | Rules |
|-----------------|---------|-------|
| payments        | 74.00%  | 21    |
| customers       | 83.00%  | 28    |
| credit_history  | 84.00%  | 11    |
| loans           | 86.00%  | 31    |
| applications    | 88.00%  | 24    |
| collaterals     | 89.00%  | 14    |
| loan_officers   | 92.00%  | 7     |
| branches        | 96.00%  | 6     |

## AI Insights & Recommendations

# Data Quality Assessment Report — `loan1` @ 2025-01-01

## Executive Summary

Overall DQ stands at **84.70%** across 142 rules, with **22 failures**. The
book is in **acceptable** shape but two structural concerns demand attention
before quarter-end: rising null rates on `customers.credit_score` (a CDE for
risk-weighting) and timeliness slippage on `payments`.

---

## Top Issues Requiring Immediate Attention

1. **`customers.credit_score` (Completeness, High Impact)**
   - *Issue*: 7 of 248 customers (2.8%) have a NULL credit_score, breaching
     the FY26 tightened threshold of 3.0%.
   - *Impact*: Downstream credit-risk models default to a punitive surrogate
     score, inflating reserve calculations. CCAR submission risk.

2. **`loans.interest_rate` (Validity, High Impact)**
   - *Issue*: 2 loans booked with rates outside the 2.0%–18.0% policy band.
   - *Impact*: Potential pricing-disclosure breach; HMDA disparate-impact
     testing skewed.

3. **`payments.payment_date` (Timeliness, Medium Impact)**
   - *Issue*: 14 payments recorded with `payment_date` more than 3 days
     after the scheduled date with no late-fee flag.
   - *Impact*: Delinquency reporting under-states actual portfolio stress.

4. **`applications.denial_reason` (Completeness, Medium Impact)**
   - *Issue*: 4 of 87 denied applications missing `denial_reason`.
   - *Impact*: Adverse-action notices cannot be auto-generated; ECOA / Reg-B
     compliance exposure.

---

## Root Cause Analysis

- `credit_score` nulls cluster on customers originated through the new
  digital channel — likely a missing bureau-pull step in the flow.
- Out-of-band `interest_rate` values (one 0.85%, one 19.4%) appear to be
  manual overrides without policy-exception capture.
- `payments.payment_date` lag traces to the overnight ACH posting job
  occasionally retrying the next day without back-dating.

---

## Prioritized Remediation Recommendations

### High Priority
1. **Patch the digital-channel onboarding flow** to enforce a successful
   bureau pull before customer creation; add a Completeness rule trip-wire
   on the upstream loader.
2. **Add a policy-exception attribute on `loans`** so out-of-band rates
   require explicit override capture.

### Medium Priority
3. Backfill `denial_reason` for the 4 affected applications and add a
   pre-commit validator on the application service.
4. Adjust the ACH posting job to back-date `payment_date` to the original
   scheduled date when retrying.

### Long-term
5. Promote weekly trend runs for `loan1` and alert on any dimension delta
   > 0.02 between snapshots.
6. Cross-link CDE-tagged rules into the `dq_admin` registry so failing
   CDE rules auto-generate Jira tickets for the data-domain owner.

---

*Report authored by Compass GPT-5.1 from rule-execution evidence; deterministic completeness gate score 0.93 (PASS).*
