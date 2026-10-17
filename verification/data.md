# Domain questions — data analysis / ML experiments
- Data leakage: is the split done before any fitting? Are scalers/encoders/imputers/feature selection fit on training data only? For time series and sensor data, is the split chronological? Do the same subjects/devices appear on both sides?
- Is the test set used only once for final evaluation, not for tuning?
- Re-run the analysis if possible. Do the reported numbers reproduce? Are seeds fixed, and do results hold across seeds (mean ± std)?
- Is there a meaningful baseline, and is the improvement larger than run-to-run variance?
- Statistics: were the test's assumptions checked? Are effect sizes and confidence intervals reported, not only p-values? Multiple comparisons?
- Confounders and sampling bias: could something other than the claimed factor explain the result?
- Was data silently dropped, imputed or clipped? Do row counts before/after match what is reported?
- Is the raw data untouched?
